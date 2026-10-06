"""Combining readers' scores into a result for each essay."""

from dataclasses import dataclass, field
from decimal import ROUND_HALF_UP, Decimal
from itertools import combinations

from ..models import Assignment, ContestSettings, Essay

TWO_PLACES = Decimal("0.01")


def quantize(value):
    return value.quantize(TWO_PLACES, rounding=ROUND_HALF_UP) if value is not None else None


@dataclass
class EssaySummary:
    essay: Essay
    active: list = field(default_factory=list)
    submitted: list = field(default_factory=list)
    pending: list = field(default_factory=list)
    averages: list = field(default_factory=list)
    final: Decimal | None = None
    spread: Decimal | None = None
    initial_spread: Decimal | None = None
    divergent: bool = False
    has_rescore: bool = False
    needs_rescore: bool = False
    complete: bool = False
    missing_readers: int = 0
    rank: int | None = None


def combine(averages, method):
    """Final score from the readers' average scores (each out of 10)."""
    if not averages:
        return None
    if method == ContestSettings.RESCORE_CLOSEST_TWO and len(averages) > 2:
        pairs = list(combinations(averages, 2))
        smallest = min(abs(a - b) for a, b in pairs)
        # When the re-score lands exactly between the two initial readers both
        # pairs are equally close; average them rather than let the order in
        # which judges happened to be assigned decide the result.
        closest = [(a + b) / 2 for a, b in pairs if abs(a - b) == smallest]
        return sum(closest, Decimal("0")) / len(closest)
    return sum(averages, Decimal("0")) / len(averages)


def summarize(essay, config, assignments=None):
    """Roll one essay's assignments up into scores and status flags.

    Pass `assignments` (with sheets loaded) when summarising many essays to
    avoid a query per essay.
    """
    if assignments is None:
        assignments = list(essay.assignments.select_related("judge", "sheet"))
    summary = EssaySummary(essay=essay)
    summary.active = [a for a in assignments if a.is_active]
    summary.submitted = [
        a for a in summary.active if a.status == Assignment.STATUS_SUBMITTED and hasattr(a, "sheet")
    ]
    summary.pending = [a for a in summary.active if a.is_pending]
    summary.averages = [a.sheet.average for a in summary.submitted]
    summary.has_rescore = any(a.round == Assignment.ROUND_RESCORE for a in summary.active)

    initial = [a for a in summary.active if a.round == Assignment.ROUND_INITIAL]
    initial_done = [a for a in initial if a.status == Assignment.STATUS_SUBMITTED]
    initial_averages = [a.sheet.average for a in initial_done if hasattr(a, "sheet")]
    summary.missing_readers = max(0, config.readers_per_essay - len(initial))

    if len(summary.averages) >= 2:
        summary.spread = max(summary.averages) - min(summary.averages)
    if len(initial_averages) >= 2:
        summary.initial_spread = max(initial_averages) - min(initial_averages)
        summary.divergent = summary.initial_spread >= config.divergence_threshold

    initial_finished = len(initial_done) == len(initial) and not summary.missing_readers
    summary.needs_rescore = summary.divergent and initial_finished and not summary.has_rescore
    summary.complete = (
        bool(summary.submitted)
        and not summary.pending
        and not summary.missing_readers
        and not summary.needs_rescore
    )
    # The "two closest" rule is for re-scored essays only; otherwise every
    # reader counts equally.
    method = config.rescore_method if summary.has_rescore else ContestSettings.RESCORE_MEAN_ALL
    summary.final = quantize(combine(summary.averages, method))
    return summary


def summarize_all(config=None, essays=None):
    config = config or ContestSettings.load()
    if essays is None:
        essays = Essay.objects.filter(status=Essay.STATUS_APPROVED)
    essays = list(essays.select_related("prompt"))
    by_essay = {}
    rows = Assignment.objects.filter(essay__in=essays).select_related("judge", "sheet")
    for assignment in rows:
        by_essay.setdefault(assignment.essay_id, []).append(assignment)
    return [summarize(essay, config, by_essay.get(essay.id, [])) for essay in essays]


def rank(summaries):
    """Rank fully scored essays within each division (ties share a rank)."""
    ranked = {}
    for division in {s.essay.division for s in summaries}:
        rows = [s for s in summaries if s.essay.division == division and s.complete]
        rows.sort(key=lambda s: (-s.final, s.essay.code))
        previous, position = None, 0
        for index, row in enumerate(rows, 1):
            if row.final != previous:
                position = index
                previous = row.final
            row.rank = position
        ranked[division] = rows
    return ranked
