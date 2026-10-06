"""Deciding which judge reads which essay."""

import random
from collections import defaultdict

from django.db import transaction

from ..models import Assignment, ContestSettings, Essay, JudgeAttestation, User


class NoEligibleJudge(Exception):
    pass


def available_judges():
    """Active judges who have signed the pre-judging statement.

    Until a judge signs, their conflicts of interest are unknown, so they are
    not given essays.
    """
    return User.objects.filter(role=User.ROLE_JUDGE, is_active=True, attestation__isnull=False)


def _serialise():
    """Let only one assignment run at a time (call inside a transaction).

    Two admins pressing "Auto-assign" together would otherwise each see the
    same open slots and both fill them.
    """
    ContestSettings.load()
    ContestSettings.objects.select_for_update().get(pk=1)


def _state():
    judges = list(available_judges())
    load = defaultdict(int)
    prior = defaultdict(set)  # essay id -> every judge who has ever held it
    for essay_id, judge_id, status in Assignment.objects.values_list(
        "essay_id", "judge_id", "status"
    ):
        prior[essay_id].add(judge_id)
        if status in Assignment.ACTIVE_STATUSES:
            load[judge_id] += 1
    conflicts = defaultdict(set)
    through = JudgeAttestation.conflict_prompts.through
    for user_id, prompt_id in through.objects.values_list("judgeattestation__user_id", "prompt_id"):
        conflicts[user_id].add(prompt_id)
    return judges, load, prior, conflicts


def eligible_judges(essay, judges, load, prior, conflicts):
    return [
        judge
        for judge in judges
        if judge.id not in prior[essay.id]
        # With no prompt on record we cannot screen for conflicts, so a judge
        # who declared any conflict is kept away from the essay altogether.
        and (
            not conflicts[judge.id]
            if essay.prompt_id is None
            else essay.prompt_id not in conflicts[judge.id]
        )
        and (judge.max_load is None or load[judge.id] < judge.max_load)
    ]


def open_slots(config=None):
    """Approved essays that still need initial-round readers: [(essay, n)]."""
    config = config or ContestSettings.load()
    counts = defaultdict(int)
    for essay_id in Assignment.objects.filter(
        round=Assignment.ROUND_INITIAL, status__in=Assignment.ACTIVE_STATUSES
    ).values_list("essay_id", flat=True):
        counts[essay_id] += 1
    slots = []
    for essay in Essay.objects.filter(status=Essay.STATUS_APPROVED):
        need = config.readers_per_essay - counts[essay.id]
        if need > 0:
            slots.append((essay, need))
    return slots


@transaction.atomic
def auto_assign(actor=None, rng=None):
    """Fill every open reader slot, keeping judges' workloads level.

    Judges are skipped for essays on a prompt they declared a conflict with,
    essays they have held before, and once they reach their personal cap.
    Returns (created_assignments, unfilled) where unfilled is [(essay, n)].
    """
    rng = rng or random.Random()
    _serialise()
    judges, load, prior, conflicts = _state()
    slots = open_slots()
    rng.shuffle(slots)
    created, unfilled = [], []
    for essay, need in slots:
        for _ in range(need):
            candidates = eligible_judges(essay, judges, load, prior, conflicts)
            if not candidates:
                unfilled.append((essay, need))
                break
            lightest = min(load[j.id] for j in candidates)
            judge = rng.choice([j for j in candidates if load[j.id] == lightest])
            created.append(
                Assignment.objects.create(
                    essay=essay, judge=judge, round=Assignment.ROUND_INITIAL, assigned_by=actor
                )
            )
            load[judge.id] += 1
            prior[essay.id].add(judge.id)
            need -= 1
    return created, unfilled


def candidates_for(essay):
    """Judges who may be given this essay, lightest workload first."""
    judges, load, prior, conflicts = _state()
    candidates = eligible_judges(essay, judges, load, prior, conflicts)
    candidates.sort(key=lambda j: (load[j.id], j.full_name.lower()))
    for judge in candidates:
        judge.current_load = load[judge.id]
    return candidates


@transaction.atomic
def assign(essay, judge=None, *, round_=Assignment.ROUND_INITIAL, actor=None, rng=None):
    """Assign one reader; pick the least-loaded eligible judge if none is given."""
    _serialise()
    if judge is None:
        candidates = candidates_for(essay)
        if not candidates:
            raise NoEligibleJudge()
        lightest = candidates[0].current_load
        judge = (rng or random).choice([j for j in candidates if j.current_load == lightest])
    elif judge.pk not in {candidate.pk for candidate in candidates_for(essay)}:
        raise NoEligibleJudge()
    return Assignment.objects.create(essay=essay, judge=judge, round=round_, assigned_by=actor)
