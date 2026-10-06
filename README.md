# Essay contest judging portal

A web portal for blind judging of the Duke–UNC China Leadership Summit Essay
Contest. Administrators upload the submitted PDFs, the portal blacks out
identifying details on the pages, and invited judges read those pages and
score them against the contest rubric. Django, PostgreSQL, Docker; English and
简体中文.

## What it does

**Administrators**

- Bulk-upload essay PDFs, plus a spreadsheet of authors.
- Review each essay page by page: the portal has already placed black boxes
  over what it found; switch boxes on or off, draw new ones, leave out a title
  page, and release the essay to judges only when satisfied.
- Invite judges and other administrators by one-time link. No email server
  is needed: the portal writes each message and opens it in your own mail app.
- Auto-assign two readers per essay (balanced workloads, conflicts respected),
  with manual overrides.
- See progress per judge, overdue sheets, divergent scores and referrals.
- Launch re-scores, confirm finalists, export everything to XLSX or CSV.

**Judges**

- Set up their own sign-in from the invitation: a passkey (fingerprint, face
  or device PIN) or a password.
- Sign a statement that they have read the rubric and declare any essay
  question they hold strong personal views on.
- Read each assigned essay as its own pages, exactly as the contestant laid
  them out (footnotes, superscripts, italics, bibliography, figures), with the
  judging sheet beside it: four criteria scored 0–10 in steps of 0.5, a
  justification for each, the rubric's level descriptors one click away, live
  totals and word count, automatic draft saving.
- Flag suspected plagiarism or AI markers, or hand an essay back if they
  cannot judge it fairly.

Judges never get the PDF itself. They get flat images of its pages with the
redactions burned in, under a random essay ID; they never see an author's
name, school, email or file name, who else is reading the same essay, or what
anyone else scored.

## Deploying

You need a Linux server with Docker and a DNS name pointing at it.

```bash
cp .env.example .env
```

Edit `.env`: set `SECRET_KEY`, `POSTGRES_PASSWORD`, the three address settings,
`ADMIN_EMAIL` and `ADMIN_NAME`, and the `EMAIL_*` block if you have SMTP
credentials. Then:

```bash
docker compose up -d --build
```

Caddy obtains an HTTPS certificate for `SITE_ADDRESS` automatically (ports 80
and 443 must be reachable). On first start the portal creates the first
administrator and prints a one-time link for setting up your sign-in:

```bash
docker compose logs web | grep -A1 "one-time link"
```

Open that link, create a passkey or choose a password, and you are in.

If the server already runs a reverse proxy, delete the `caddy` service from
`docker-compose.yml`, publish the `web` service's port 8000 to it, and make
sure the proxy sets `X-Forwarded-Proto` and `X-Forwarded-For`.

### Backups

Everything lives in two Docker volumes: `pgdata` (database) and `media`
(the submitted PDFs and the page images made from them; allow roughly 5–10 MB
of disk per essay).

```bash
docker compose exec db pg_dump -U portal portal | gzip > portal-$(date +%F).sql.gz
```

```bash
docker run --rm -v judging-portal_media:/m -v "$PWD":/out alpine tar czf /out/media-$(date +%F).tgz -C /m .
```

Both contain author identities. Store them accordingly.

### Updating

```bash
docker compose up -d --build
```

Database migrations run automatically when the `web` container starts.

## Running a contest

1. **Settings** — set the judging deadline (after the last date essays can
   arrive), and check the divergence threshold and number of readers per essay.
2. **Essay prompts** — the 2026 prompts (I–VI) are loaded automatically on
   first start. Check them; judges declare conflicts against this list.
3. **Judges and admins** — invite judges. Each gets a one-time link.
4. **Upload** — import the author spreadsheet first, then the essay PDFs.
5. **Anonymization review** — look over each essay's pages, adjust the black
   boxes, and release it.
6. **Assignments** — auto-assign, and email judges.
7. **Dashboard** — watch progress; reminders go out automatically.
8. **Divergence and re-scores** / **Referrals** — deal with what comes up.
9. **Results** — confirm finalists and export.

### The author spreadsheet

CSV or XLSX with a header row. `filename` is required and must match the
uploaded file names; `name`, `email`, `school`, `division` (whether the author
is a `high school` or `undergraduate` student) and `prompt` (`I`–`VI`, a
number, or the theme) are optional. It can be imported before or after the
files, and re-imported at any time.

**An essay is judged in the category of its prompt.** Prompts I–III are the
high school category and IV–VI the undergraduate category. A high school
student who answers Prompt V is ranked with the undergraduates; the portal
records the author's own level separately and applies this for you. An
undergraduate who answers a high school prompt, which the rules do not allow,
is flagged on the review checklist, as is an essay well over the word limit.

Importing it is strongly recommended: the portal can only redact a name it
knows.

**File names must be unique.** Rows are matched to files by name alone. If two
contestants both submit `essay.pdf`, or the spreadsheet lists one file name
for two authors, the portal attaches no author record to either, flags both,
and will not release them until an administrator has opened each essay and
saved the correct author details. Renaming files before upload (for example
to a submission number) avoids this entirely.

## How anonymization works

Submissions are PDFs only. For every uploaded file the portal:

1. Renders each page to an image, in a separate short-lived process with its
   own time and memory limits, and records where every word sits on the page.
2. Leaves out a title page (a short first page followed by the essay proper).
3. Places black boxes over the author's full name in any order (`Wei Zhang`,
   `Zhang Wei`, `Zhang, Wei`), their school, every email address and phone
   number, any name found in the file's properties, labelled lines such as
   `Name: …` on the first page, and running headers that carry the name
   (`Zhang 3`).
4. Outlines, without blacking out, things a person should judge: part of the
   name appearing alone, part of the school name, phrases like "at my school".
5. Gives the essay a random ID such as `E-7KQ3M` and puts it in the review
   queue.

Step 4 is deliberate. In essays about China, an author's surname (Li, Wang,
Xi) is often also a politician's, so single names are outlined for the
reviewer rather than removed.

An administrator then goes through the pages. They see what a judge will see:
the real pages, with black boxes. A click switches a box on or off; dragging
draws a new one (over a logo, a signature, a letterhead); "redact a word
everywhere" finds a word on every page; any page can be left out. Release is
blocked while the author's full name, school or an email address is still
readable on a page, unless the reviewer explicitly overrides it. The same
check applies to any later change to a released essay, and starting the
automatic pass again on a released essay pulls it back from judges. Importing
author details after release re-checks the essay and pulls it back if the
name is on a page.

On release the portal writes new images with the boxes painted into the
pixels. Those images are all a judge's browser ever receives: there is no text
layer, no file properties and nothing underneath a box to uncover.

### Citations

Because judges read the essay's own pages, every form of citation arrives
exactly as written: footnotes at the foot of the page, superscript note
numbers, author–date and bracketed references, a bibliography with its
indentation, italic titles, tables and figures.

Each essay also has a **Text** tab: a plain-text copy of the same pages (minus
anything under a black box) for copying a web address or searching. It follows
the PDF's own line breaks and reading order, so use it for copying, not for
reading. Digits inside web addresses and DOIs are never mistaken for phone
numbers.

A box over the author's own name or school will also cover it inside a
citation (an author at Duke citing "Duke University Press"). The reviewer can
switch such a box off where it gives nothing away.

The portal does not check that a cited source exists: spotting fabricated
citations remains the judges' job.

### Limits

- Automatic redaction is a first pass, not a guarantee; the page-by-page
  review is the control.
- **Scanned PDFs** (images of paper) can be judged, but nothing can be found
  in them automatically. The reviewer draws every box, and has to confirm so
  before release.
- A PDF can contain text that is not visible on the page. It cannot appear in
  the page images, but it would appear in the Text tab; the review screen
  shows that text too, and the release check covers it.
- Comments, stamps and form fields added on top of a PDF are not shown.
- Password-protected PDFs, and files over the page or size limit, are stored
  and flagged; ask the contestant for a corrected file.

## Scoring rules

- Each criterion is scored 0–10 in steps of 0.5. A reader's score for an essay
  is the mean of the four criteria.
- A sheet can be submitted only when all four criteria are scored, each has a
  justification, comments total at least 100 words (a Chinese character counts
  as one word), any flag is explained, and the confirmation is signed.
  Submitted sheets are locked; an administrator can reopen one.
- An essay's final score is the mean of its human readers' scores. Essays are
  ranked within their division once every assigned reader has submitted.
- When any two initial readers differ by the divergence threshold or more
  (default 2.0 points), the essay is flagged and an administrator assigns one
  further reader. Settings control whether the final score then averages all
  three readers or the two closest (if the third lands exactly midway, both
  pairs are averaged, which gives the middle score).
- A judge is never assigned an essay they have held before, or one answering a
  prompt they declared a conflict with, and is not assigned anything until
  they have signed the statement. An essay with no prompt on record cannot be
  screened, so it is only given to judges who declared no conflicts at all.

**AI readers are not part of this version.** The rubric's 75% human / 25% AI
weighting is therefore not applied: results here are the human component only.

## Accounts and signing in

Nobody can register themselves. An administrator adds a person under **Judges
and admins**, and the portal creates a one-time link (valid 14 days by
default). The person opens it and sets up how they will sign in:

- **A passkey (recommended).** The browser asks for a fingerprint, face or
  device PIN, and from then on signing in is one tap, with no email address
  or password typed. The secret never leaves the person's device; the portal
  stores only a public key, so there is nothing here for an attacker to steal
  or guess, and a passkey will not work on a look-alike site.
- **A password**, for anyone whose device or browser cannot do passkeys (some
  phones sold in mainland China, and links opened inside apps such as WeChat).

People can add more passkeys (one per device) or a password later from their
account page. If someone loses their device or forgets their password, an
administrator opens their page, creates **a new sign-in link**, and sends it;
**Remove their passkeys** is there for a lost or stolen device.

Two things to know about passkeys:

- They require HTTPS, which the deployment above provides.
- They are tied to the portal's address. If you move the portal to a different
  domain name, existing passkeys stop working and people need a new sign-in
  link.

## Email

**Without an email server (the default).** The portal never sends anything
itself. Instead it writes each message and you send it from your own email:

- *Invitations and new sign-in links*: after you create one, **Open in my
  email app** opens the message addressed to that person, in their language,
  with the one-time link in it. The link is shown once.
- *New essays* and *reminders*: on the **Assignments** page, a button opens a
  message addressed to you with the relevant judges in Bcc (so they do not see
  one another), one message per language. After announcing new essays, press
  **mark as announced**.

Every message can also be copied as text, for a chat app or a mail program
that does not open from links. What you give up is automation: nothing goes
out unless you press a button, including deadline reminders.

**With an email server.** Set the `EMAIL_*` variables and the portal sends
invitations, sign-in links, new-assignment notices, referral alerts to
administrators and deadline reminders itself (by default 3 days and 1 day
before, plus one overdue notice), each in the recipient's language and logged
under **Logs → Email**.

## This year's contest

The prompts, the 1,500-word limit, the contact address and a short brief for
judges (length, format, citation and AI rules as published to contestants)
come from https://www.dukechinaessay.com and live in `portal/contest.py`. On
first start they are loaded into the database; after that, prompts are edited
under **Setup → Essay prompts** and the word limit and contact address under
**Settings**. To reload them from the file (overwriting edits to prompts I–VI):

```bash
docker compose exec web python manage.py load_contest
```

For next year, edit `portal/contest.py`. The Chinese text of the prompts and
the brief is a working translation and should be reviewed.

## Changing the rubric or the translations

- The rubric text, in both languages, is in `portal/rubric.py`. **The Chinese
  rubric is a working translation and should be reviewed by the committee
  before judging opens.**
- Interface strings are in `portal/locale/zh_Hans/LC_MESSAGES/django.po`.
  After editing, run `python manage.py compilemessages` inside `portal/` (the
  Docker build does this for you).

Rebuild and restart after either change.

## Development

```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
```

```bash
echo "DEBUG=1" > .env && .venv/bin/python manage.py migrate
```

```bash
.venv/bin/python manage.py seed_demo
```

```bash
.venv/bin/python manage.py runserver
```

`seed_demo` fills a development database with made-up judges, essays and
scores and prints the demo sign-in details (it refuses to run unless
`DEBUG=1`). Run the tests with:

```bash
.venv/bin/python manage.py test portal
```

## Security notes

- Accounts are invitation-only. People sign in with a passkey (nothing secret
  is stored on the server) or a password (stored hashed). Invitation and
  sign-in links are single-use, expire, and only their hashes are stored. The
  web server keeps no access log, so the links are not copied into log files.
- Sign-in attempts are capped per email and address, per address, and per
  email, over a 15-minute window.
- Original submissions are stored under random names outside the web root and
  are served only to administrators; each download is logged.
- Uploaded files come from contestants and are treated as hostile. Each PDF is
  parsed and rendered in a separate process that caps its own CPU time and
  memory and is killed after 90 seconds, so a malformed or malicious file can
  fail but cannot stall or crash the portal. There are limits on file size,
  page count and total text, and the redaction patterns cannot be made to run
  for minutes by crafted text.
- What judges receive is generated by the portal (plain images and text), not
  passed through from the submitted file.
- Every page carries a content security policy that allows scripts only from
  the portal itself, `Cache-Control: no-store` (essays and scores do not linger
  in a shared computer's browser), and anti-framing headers.
- Spreadsheet exports neutralise cells that begin with `=`, `+`, `-` or `@`,
  so a judge's comment cannot run as a formula.
- **Logs → Activity** records uploads, releases, changes to redactions,
  assignments, submissions, reopened sheets, exports and account changes.
- Once HTTPS is confirmed working, set `HSTS_SECONDS=31536000` in `.env`.

What the portal does not protect against, by design:

- **Administrators are fully trusted.** Any administrator can see every
  identity and score, and can issue a password-reset link for any account
  (and so sign in as that person). Keep the number of administrators small;
  every such action is in the activity log.
- **Whoever controls the server controls the data.** Original files and the
  database are not encrypted at rest, and backups contain author identities.
- **Redaction is a first pass.** The human review before release is the
  control that keeps identities from judges. A reviewer who releases a page
  with a name still on it has released that name.
