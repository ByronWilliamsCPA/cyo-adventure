---
title: "ADR-030: Children's-privacy review of the engagement-correlation analysis job"
schema_type: planning
status: proposed
owner: core-maintainer
purpose: "Discharge the ADR-018 children's-privacy review that task C3 names as a hard
  precondition before any code: set the minimum-cohort threshold the analysis job must
  enforce, allowlist the fields it may read and emit, decide where its artifact may be
  written and whether it may ever be committed to this public repository, and record the
  no-route constraint as a decision rather than an implementation note."
tags:
  - planning
  - architecture
  - decisions
  - privacy
  - compliance
---

# ADR-030: Children's-privacy review of the engagement-correlation analysis job

> **Status**: Proposed (2026-08-28). **Awaiting owner ratification.** This document was
> drafted by an agent under the owner's standing "proceed under assumed approval" ruling for
> this blocked item, with the mitigation that the job it authorises ships flag-OFF behind a
> kill switch. **It is not a completed human privacy review and must not be cited as one.**
> It becomes Accepted only when the owner ratifies it; until then the flag stays off and no
> artifact is produced against real reader data.
> **Revised 2026-08-29**, before ratification, following a senior review of the first draft. The
> revision is additive: it binds the threshold to each emitted signal rather than only to the reader
> cohort, adds the emit allowlist the first draft left open, and states the egress rule generally
> instead of naming two of its paths. Nothing already decided was reversed, and the status is
> unchanged. The document the owner ratifies is this one.
> **Date**: 2026-08-28
> **Relates to**: [ADR-018](./adr-018-childrens-privacy-compliance.md) (the governing
> children's-privacy architecture; D6's data inventory obligation is discharged in Decision 8
> below), [ADR-016](./adr-016-recommendation-sharing-social-boundary.md) (the no-free-text
> principle that makes `kid_flag` a closed vocabulary), and
> [ADR-005](./adr-005-mandatory-human-approval.md) (the human gate this job never touches,
> because it is read-only and downstream of publication).

## TL;DR

The C3 analysis job may be built, under a set of constraints that are decisions here rather
than implementation preferences.

**The minimum-cohort threshold is 5 distinct families.** A storybook whose reading outcomes
come from fewer than 5 distinct `family_id` values is excluded from the output entirely, with
no row, no partial row, and no null-filled placeholder. The count is over families and not
over child profiles, because siblings in one household are not independent observers and the
adult who could re-identify them sees the whole household's contribution at once. The number
is derived from first principles for a children's product, not measured: the production
distribution of readers per storybook is not observable from here, and Decision 10 states
what measurement would justify revising it and in which direction.

**The same threshold binds every emitted signal, not only the row.** Ratings, completions and flags
are contributed by subsets of a book's readers, so a book that clears the gate on 5 reading families
can still carry a cell built from one. Each published figure must reach 5 distinct families in its
own contributing population, and a signal that does not is suppressed while the rest of the row is
published.

**The artifact is never committed to this repository.** A public git history is not
retractable, and an aggregate over five families of real children, once pushed, stays public
even if this threshold is later found insufficient. There is no in-repository default output
path, and a construction-time settings validator refuses to boot the job when its configured
output path resolves inside a git working tree.

**The job acquires no route**, because a route is a data-egress path and this is precisely the
data set that should not gain one.

## Context

### Problem

Task C3 of the testing-improvement plan proposes a read-only analysis job joining Stage-4
engagement advisories and validator statistics against aggregated real reading outcomes per
storybook, so that over time the project can tell which synthetic quality scores actually
predict that a band's readers finish a book and come back to it. The plan's own text makes an
ADR-018 children's-privacy review a hard precondition before any code, and carries this
assumption marker:

> `#CRITICAL: security: a per-storybook aggregate can re-identify a child when a storybook has
> very few readers, which is the normal case for a homelab-scale catalog. #VERIFY: the privacy
> review must set and the job must enforce a minimum-cohort threshold below which a storybook
> is excluded from the output entirely, and the threshold must be asserted by a test, not
> merely documented.`

That marker is correct, and it understates the problem in one respect: the re-identification
risk here is not only about small counts. Three structural properties of this schema make
per-storybook aggregation sharper than the general case.

1. **`storybook.visibility` is bimodal and defaults to the narrow state.**
   `_STORYBOOK_VISIBILITY_VALUES` is `'family', 'catalog'` (`db/models.py:101`) and the column
   defaults to `family` (`db/models.py:1432`). A `family`-visibility book has a ceiling of one
   household's children by construction, so every aggregate over one is an aggregate over one
   family, whatever its reader count.
2. **A storybook can be *about* a named child.** `Storybook.personalization_subject_profile_id`
   (`db/models.py:1458`, ADR-023) is a nullable FK to `child_profile`. For a book with that
   column set, a published row is attributable to a specific child by the book's own identity,
   with no counting argument needed. This is not addressed by any cohort threshold.
3. **`kid_flag` is finer-grained than the aggregate the plan authorises.** `kid_flag.node_id`
   is a passage identifier (`db/models.py:2899`), so a per-node flag breakdown is a statement
   about which passage of a book upset a reader. ADR-016's no-free-text principle already
   removed the child's words from this table; it did not make the passage pointer safe to
   publish.

The plan also names inputs that partly do not exist in the shape it assumes, which bears on
what the job can be scoped to read. Stage-4 engagement advisories are real and are persisted
as a `stage: 4` entry inside `storybook_version.moderation_report` (`db/models.py:1484-1486`,
written by `moderation/pipeline.py::_persist_report`), per storybook version and never per
child. The validator statistics are not persisted per storybook at all: consequence distance
(`validator/consequence.py:267`) has no caller in `src/` and is exercised only by an offline
CLI, reconvergence exists only as an unenforced `BandProfile.reconvergence_ceiling`
(`validator/band_profile.py:35`), and structural distance (`diversity/structure.py:299,397`)
is computed on demand from skeleton and story JSON. No `diversity_score` column exists. This
review does not resolve that gap; it records it, because a reviewer who assumes those columns
exist will mis-scope the allowlist below.

### Constraints

- **No measurement is available.** No existing code counts distinct readers per storybook;
  this job would be the first. The local development database is seed data (5 storybooks,
  3 child profiles, 0 `reading_state` rows) and is not evidence about production, and
  connecting to production to characterise the distribution is out of scope for writing a
  review that exists to constrain what may be looked at. The threshold below is therefore
  derived, and is labelled as derived.
- **Homelab scale is the operating assumption.** ADR-004 puts this project on a homelab-first
  deployment with a small real user base; the production roster is four adult accounts. A
  threshold calibrated for a consumer-scale catalog would be the wrong instrument, and one
  calibrated to publish something under current conditions would be no instrument at all. The
  threshold below resolves that tension by accepting that the job may legitimately publish
  nothing for a long time.
- **This repository is public.** Anything committed here is world-readable at push time and
  stays readable in history after deletion. That is a hard constraint on the artifact and is
  decided in Decision 6 rather than left to the implementer.
- **Day grain is an established posture, not a new idea.** `ReadingActivityDay`'s docstring
  (`db/models.py:1745-1747`) records that no session rows and no timestamp finer than a day
  ever reach the server. Any timestamp this job touches inherits that posture.

### Significance

The cost of getting this wrong is asymmetric and one-directional. A threshold set too high
delays a calibration signal that the flywheel currently does without entirely, since its
candidate strategy triggers on request-side saturation only. A threshold set too low, in an
artifact that reached a public history, discloses reading behaviour of identifiable children
and cannot be undone by any subsequent fix. When one side of an error is a delay and the other
is irreversible, the review picks the delay.

## Decision

### 1. The minimum-cohort threshold is 5 distinct families

A storybook is included in the output only if its reading outcomes come from **at least 5
distinct `family_id` values**. Below that it is excluded entirely: no row, no partially
populated row, no null placeholder, and no appearance in any list of storybook identifiers the
artifact contains.

**The cohort is counted over families, not over child profiles.** The two differ, and the
difference is not conservative in the direction one might guess. A single family with five
children satisfies any profile-based threshold of 5 while the aggregate remains one
household's data, and that household's own adult can subtract every contribution and read the
remainder as zero. Siblings also share a home, a shelf, and usually a reading session, so
their outcomes are correlated rather than independent observations. `family_id` is reachable
from every outcome table through `child_profile.family_id`.

**The threshold binds every emitted signal, not only the row.** Clearing the gate at the storybook
level does not clear every cell in that storybook's row. Each emitted aggregate is computed over its
own contributing population, that population is counted in distinct `family_id` values, and it must
itself reach 5:

- completion rate and return-read rate: families with an observed read of the book;
- the rating aggregate: families that rated it;
- flag counts by reason: families that flagged it (Decision 5, which restates this floor for the
  population it governs).

A signal whose own contributing population is below 5 is **suppressed for that storybook**, as the
marker Decision 3 defines, while the rest of the row is published normally. The book itself passing
is not a licence for the cell.

This is the "why 5 and not 3" arithmetic below, applied where it actually bites. A book read by 5
families and rated by 1 satisfies every other rule in this document, and its published rating mean
is exactly one child's `rating.value`, an integer from 1 to 5 with a `BETWEEN 1 AND 5` check
constraint on it. A single test of the reader-cohort threshold does not catch that, which is why
Decision 7 requires the per-signal case as its own fixture.

**Why 5 and not 3.** With a cohort of 3, an adult in one of the three families knows their own
household's contribution exactly and is left inferring across two unknowns. Every outcome
signal in scope has a small integer domain: `rating.value` is 1 to 5 with a `BETWEEN 1 AND 5`
check constraint, completion is a boolean per ending, and flag counts are small. A mean over
three values from a five-value domain, with one value known, frequently determines the
remaining two uniquely and almost always narrows them to two or three possibilities. That is a
disclosure, not a hypothetical one.

**Why 5 and not 10 or 11.** Health-sector conventions in the 10 to 11 range exist because
those data sets combine sensitivity with large denominators. Here the denominator is a homelab
catalog. A threshold of 11 would suppress every storybook indefinitely, which sounds safe and
is in fact the least safe outcome available, because a control that never permits any output
is a control that gets argued down by whoever needs the output later, and it gets argued down
under deadline rather than in a review. Five is defensible on the arithmetic above, is the
common minimum cell size in general-purpose statistical disclosure control, and leaves the job
capable of producing something once a book has genuine cross-family reach.

**Why not 2.** One against one. Not worth the sentence, recorded so the reasoning is closed at
the bottom end as well as the top.

**Derived, not measured.** This is a first-principles threshold for a children's product. It
is not the output of any measurement of this system, and nothing in this document should be
read as evidence about the production distribution. Decision 10 states what would justify
changing it.

**Not operator-configurable.** The threshold is a module-level constant in the job's own code
with no environment variable and no settings field. An operator must not be able to lower it,
and there is no legitimate reason to want to at runtime. Lowering it is a code change, a
review, and an amendment to this ADR, in that order.

### 2. Two categorical exclusions that do not depend on a count

Both are evaluated before any aggregation, and both are stronger than a threshold because the
predicate is a column value rather than a computed cardinality.

- **`storybook.visibility = 'family'` books are excluded categorically.** Their reader ceiling
  is one household. They could never reach 5 families and the threshold would exclude them
  anyway, which is exactly why the exclusion is worth stating separately: the threshold's
  correctness depends on the cohort count being computed correctly, and this one does not.
- **Any storybook with a non-null `personalization_subject_profile_id` is excluded
  categorically**, regardless of visibility, cohort size, or anything else. That column names
  the child the book is about. No aggregate over a book that is about one identified child is
  publishable at any cohort size, and no counting argument reaches this case.

### 3. The output grain is the storybook, its contents are allowlisted, and the cohort is not subdivided

One row per storybook. Where a signal is version-scoped (the Stage-4 engagement advisory,
completions), the job reads the currently published version only, via
`storybook.current_published_version`.

Splitting a row by version, by age band within a book, by ending, by month, or by any other
dimension subdivides the cohort, and a subdivided cell is the classic failure of a
threshold applied only at the top level: five families pass the gate, then a per-version split
produces a cell of one. **Any breakdown dimension the job later grows must re-apply the
5-family threshold at the leaf cell, not at the storybook.** Adding a dimension without doing
so is a change to this decision and needs an amendment here.

Age band, which the emit allowlist below admits, is a property of the **book** (the band the story
targets, taken from the request that produced it or from the Storybook blob's declared band),
never `child_profile.age_band`. The job reads no attribute of any child.

**No total spans more than one storybook.** The artifact contains no grand total, no corpus-wide
count, no summary row, no "all books" line, and no count of how many storybooks were considered,
included, or excluded. This is what makes suppression sufficient on its own: a suppressed book's
cell is recoverable by subtraction only if some published figure includes it, and no published
figure spans books. Complementary suppression is therefore not needed, but that conclusion is a
consequence of this rule and not independent of it, so the rule is stated rather than assumed. The
same reasoning applies within a row: a per-signal cell suppressed under Decision 1 must not be
recoverable from any other cell in that row, which is why no exact denominator is published.

**Emit allowlist.** A row may contain these fields and no others. Anything not listed is denied,
including fields a later change would find natural to add. The read allowlist in Decision 4 closes
what the job may look at; this closes what it may say, and the two are separate holes.

| Field | Form | Notes |
|-------|------|-------|
| `storybook_id` | the `storybook.id` UUID | The book's own identifier, not any person's |
| `age_band` | the book's declared band | Never `child_profile.age_band` (paragraph above) |
| `engagement_verdict` | the Stage-4 `Verdict` value, `advisory` or `pass` | A closed enum (`moderation/report.py:32-43`). The free-text `message` is not emitted, see below |
| `completion_rate` | families that reached any ending over reader families, rounded to the nearest `0.05` | Suppressed under Decision 1 if reader families are below 5 |
| `return_read_rate` | families with a completion on a later calendar date than their first, over reader families, rounded to the nearest `0.05` | Derived only from the date-truncated `completion.found_at` that Decision 4 admits. Same suppression |
| `rating_mean` | mean `rating.value` over rater families, rounded to the nearest `0.1` | Suppressed if rater families are below 5 |
| `flag_counts` | counts keyed by the three `kid_flag.reason` values, or the suppression marker | Governed by Decision 5 |
| `*_family_band` | the contributing-family count for each signal, as a bucket: `5-9` or `10+` | Never the exact count, never a raw denominator |

**The form of a suppressed cell.** A cell suppressed under Decision 1's per-signal floor or under
Decision 5 is emitted as one explicit suppression marker: never as a null, never as a zero, never as
an omitted key, and never as a rate computed over whatever families happened to contribute. Its
`*_family_band` is suppressed with it, because a band on a suppressed signal restates the population
the suppression withheld. The consumer treats a marker as **unknown**, and Decision 7 requires a test
that it is indistinguishable across the whole range it covers.

Denied explicitly, each with the reason, because a denial without a reason gets reversed:

- **The Stage-4 `message`.** It is LLM-authored free text (`moderation/stages.py:1275-1281`), and an
  allowlist whose entire purpose is that a row's contents can be enumerated is defeated by one
  unbounded field. It is also the field an agent would most naturally quote into a summary, which
  Decision 6 forbids. The two arguments that it cannot carry child data are both sound (personalized
  books are excluded categorically by Decision 2, and ADR-023 stores sentinel slots rather than
  names), but they are reasons emitting it would be safe, not reasons to emit it. What the job
  correlates is the verdict.
- **Exact contributing-family counts, exact cohort size, and any raw numerator or denominator.**
  A count of 1 beside a mean recovers the value. Bucketing is why the rates carry a stated rounding:
  a full-precision rate reconstructs the exact denominator that the bucket deliberately withholds.
  At the floor of 5 the rounding buys little on its own, and there the protection is the per-signal
  floor plus the absence of any identifier, not the rounding.
- **Any identifier of a family, child profile, device, guardian, or moderator**, in any form,
  including hashed, truncated, or positional. This is load-bearing beyond the obvious: because the
  artifact names no family, a reader cannot tell which households are in a cohort, so even a rate of
  `0.0` or `1.0` attributes to nobody.
- **`kid_flag.node_id` in any form.** Decision 5.
- **Any total spanning more than one storybook.** The paragraph above.
- **Anything else.** The list is closed. A new field is an amendment to this ADR, and Decision 7
  requires the test to assert against the allowlist rather than against a list of forbidden names, so
  that a field added later fails by default rather than passing by omission.

This allowlist is also the concrete referent of "the artifact's schema" in Decision 6.3, which named
it as a committable thing without saying what it was.

### 4. Read allowlist

The job may read these columns and no others. Anything not listed is denied, including columns
added to these tables in future.

| Table | Columns the job may read | Used for |
|-------|--------------------------|----------|
| `storybook` | `id`, `visibility`, `status`, `current_published_version`, `personalization_subject_profile_id` | Eligibility and the categorical exclusions in Decision 2 |
| `storybook_version` | `storybook_id`, `version`, `moderation_report` (the `stage: 4` entry only) | The synthetic engagement advisory being correlated |
| `child_profile` | `id`, `family_id` | Mapping outcomes to families for the cohort count. Nothing else on this table is readable |
| `reading_state` | `child_profile_id`, `storybook_id`, `version` | Distinct-reader identification only |
| `completion` | `child_profile_id`, `storybook_id`, `version`, `ending_id`, `found_at` truncated to calendar date | Completion and the return-read derivation |
| `rating` | `child_profile_id`, `storybook_id`, `value` | The rating aggregate |
| `kid_flag` | `storybook_id`, `version`, `profile_id`, `reason` | Flag aggregation, subject to Decision 5 |

Explicitly denied, with the reason, because a denial without a reason gets reversed by the
next person who wants the column:

- **`reading_state.path`, `visit_set`, `current_node`, `var_state`, `seed_var_state`,
  `save_slots`, `character_id`, `state_revision`, `last_event_id`, `last_synced_at`.** These
  are one child's traversal of a story graph. `path` and `current_node` are passage-level, and
  a traversal is close to a behavioural fingerprint. Completion is available from the
  `completion` table without touching any of them.
- **`reading_state.updated_by_device_id`** and **the whole `device_download` table**. Device
  identifiers, and a download is not a reading outcome.
- **`kid_flag.node_id`.** See Decision 5.
- **`rating.rated_at` and `rating.updated_at`, `kid_flag.created_at`, `resolved_at`,
  `resolved_by`, `resolution`.** Fine-grained timestamps and moderator identities, neither
  needed for correlation.
- **`child_profile` everything except `id` and `family_id`**, in particular `display_name`,
  `age_band`, `avatar`, `pin_hash`, and the whole personalization and accessibility settings
  block.
- **`storybook_assignment`.** It is the read gate, and it would give the job a denominator of
  "assigned but never opened". That is guardian behaviour, not child reading outcome, and it
  would let the job distinguish which families were assigned a book and ignored it. The cohort
  is defined by observed reads instead.
- **`reading_activity_day`.** **This table has no storybook column at all** (`db/models.py:1743-1801`);
  it is child-and-day grain only. It therefore cannot be joined per storybook by any query, and
  **reading time is out of scope for this job**. This is a schema fact, not a policy choice, and
  it is recorded here so nobody re-litigates it by proposing a join that cannot be written.
- **Any free text from a child.** There is none to deny (ADR-016), recorded so the absence
  stays a designed property rather than an accident.

### 5. `kid_flag.node_id` may not appear in the output, in any form

Not raw, not hashed, not as a position index, not as a count keyed by node. The plan
authorises a per-storybook aggregate; a passage pointer is a level finer than that, and it is
a pointer to the specific passage at which a child recorded that something scared or confused
them. Flags are also rare, so a per-node count in a cohort of five is very likely to be a
count of one, which is a statement about one child's reaction that the child's own guardian,
and every other guardian in the cohort by elimination, can partly attribute.

Flag data appears in the output only as counts by `reason` at storybook grain, and only when at
least **5 distinct flagging families** have flagged the storybook. The population is families, not
flags: five flags from one household are one household's data, and Decision 1 spends two paragraphs
on why per-family counting is the correct grain precisely because a household's own adult can
subtract its entire contribution. Counting flags rather than families would have re-admitted at the
flag cell the exact case the threshold exists to exclude. This is the per-signal floor of Decision 1
applied to the population this decision governs; it is restated here rather than only referenced,
because the flag cell is where the wrong population is easiest to reach for.

**Below that floor the whole cell is one suppression marker spanning 0 to 4 flagging families.** A
zero is not published. A marker used only for 1 to 4, with zero published as zero, publishes exactly
the predicate the marker exists to hide: that at least one child flagged this book. In a cohort of
five that is a real disclosure, coarse but real, about children's negative reactions, and it is
available to every guardian in the cohort who knows their own child did not flag it. Publishing
`<5` across the whole range is the standard disclosure-control form and it is what this decision
takes.

Two things about that choice, stated because both are costs:

- **It makes the flag signal uninformative at homelab scale**, probably for the whole life of the
  current catalog, since nearly every book will sit in the 0-to-4 range and read `<5` whether it was
  never flagged or flagged four times. That is accepted on the asymmetry in Significance and on
  Decision 10's pre-commitment: an uninformative cell is a delay, and a published "some child
  flagged this" is not retractable. Legibility was the thing given up, and it was given up
  deliberately rather than overlooked.
- **It is not the tri-state collapse this repository has paid for elsewhere.** That failure was two
  falsy arms collapsing into one benign branch at a decision point. `<5` is a third named value,
  distinct from both a count and an absence, and the consumer must treat it as **unknown** and never
  as zero. A zero and a suppression remain different facts; what changed is that zero is no longer
  among the published values, so the consumer is never in a position to mistake one for the other.

### 6. The artifact does not leave the deployment host, and is never committed to this repository

**Decision: the artifact may not be committed to this repository, ever.** Not to `docs/`, not
to `out/`, not to a report directory, not behind a `.gitignore` entry that a later `git add -f`
or a reorganisation could defeat. This repository is public. A push is not retractable: the
blob stays reachable in history after any subsequent deletion, and the disclosure would have to
be reasoned about as permanent from that moment. The asymmetry in Significance decides this
outright.

**The general rule, of which committing is one case.** Committing is the egress path this repository
makes easiest, so it is stated first and hardest, but it is not the rule. The rule is that **the
artifact, and any excerpt or derivative of it including a single row, does not leave the deployment
host.** Quoting rows into a GitHub issue or a pull request body, pasting a run into a report
document, a commit message, or a chat message, attaching it to a ticket, uploading it to a bucket,
and including it in an LLM prompt are all the same disclosure as committing it, and all are covered
by this prohibition. Given this project's agent-driven workflow, an agent summarising a run into a
pull request description is the most likely real leak here, more likely than a stray `git add`, and
it is named so that it is a violation rather than an omission. Decision 6.3's observation that a
fixture copied from a real run is a commit by another name is the same argument; it was scoped to
fixtures and it generalises.

**Who may read it on the host.** The artifact is written by the account the job runs as, mode `0600`,
into a directory owned by that account with mode `0700`, outside any git working tree and outside any
directory that is backed up, synced, or served. Its only reader is the flywheel candidate strategy
running as that same account. No other account on the host has read access and no copy is made
anywhere. This is stated because the first draft was silent on it, and a file whose readership is
unstated is a file whose readership grows.

Three consequences the implementer must build to:

1. **There is no in-repository default output path.** The output directory comes from
   configuration with no default. A job with no configured destination does not run.
   Deliberately, **no `.gitignore` entry is added for this artifact**, because an ignore entry
   is a statement that the artifact belongs in the tree and merely should not be staged. It
   does not belong in the tree.
2. **The settings validator in Decision 7 refuses to boot when the configured path resolves
   inside a git working tree.** Stated honestly: this defends the developer-workstation case,
   which is where the mistake actually happens, since a deployed container has no working tree
   to write into and would pass the check trivially. That is the right place to spend the
   check.
3. **What may be committed** is the artifact's schema, the job's code, and synthetic fixtures.
   A fixture that is a copy of a real run is a commit of the artifact by another name and is
   covered by the same prohibition.

**Retention.** The job keeps at most the current and the immediately preceding run, each under
a run-scoped filename, and deletes anything older on each successful run. Turning the kill
switch off deletes the artifacts rather than orphaning them. Two runs is enough to diff a run
against its predecessor, which is the only reason to keep more than one, and a retention rule
of "however many accumulate" is how D4's three windowless data classes happened.

**The residual that retention creates, and the condition on which it is accepted.** Keeping two runs
is what makes run-over-run differencing possible, and differencing is a disclosure that the
single-run thresholds above do not cover: the delta between consecutive runs of a book already well
above threshold is household-sized, and a delta of one family is a cell of one however large the
cohort behind it. The residual is accepted **because of the reader model stated above**, and only
because of it: the sole reader is a process on the deployment host running as an account that
already holds database credentials, and can therefore compute anything a delta could disclose
directly from the source tables, more precisely and without the artifact. The marginal disclosure is
nil against that reader. The acceptance is worded this way so that it visibly expires. If the
artifact ever gains a reader without database access, or if the egress rule above is relaxed for any
path, this residual is no longer covered by anything and needs its own answer, which is either
suppressing deltas or retaining a single run.

### 7. The kill switch and the construction-time validator

Following the exemplar at `core/config.py:1211-1212` and
`_reject_start_override_against_production_kws` at `core/config.py:2125`, the safety property
is enforced by code that runs at settings construction, not by operator discipline.

- **The flag**: `analysis_engagement_correlation_enabled: bool = Field(default=False,
  validation_alias="ANALYSIS_ENGAGEMENT_CORRELATION_ENABLED")`. Default False, so the job
  ships inert and turning it on is a deliberate per-tier act taken after the owner ratifies
  this ADR.
- **What it disables**: everything. Off, the job does not read the database, does not compute,
  and does not write. It is not a mode that produces a redacted artifact, because a redaction
  path that only runs when the flag is off is a path nobody exercises.
- **The construction-time validator**:
  `_reject_engagement_analysis_output_inside_repository`, a `model_validator(mode="after")`
  that raises `ConfigurationError` when the job is enabled and either (a) the output directory
  is unset, or (b) the resolved output directory has a `.git` entry at or above it. **Refusal
  to boot is the control**, in the same posture as the KWS validators: a tier that acquires a
  bad output path by copying another tier's environment file stops, rather than quietly
  writing children's reading aggregates into a checkout that something later stages.

Three details of that validator are pinned here rather than left to the implementer, because each
has a plausible reading that would make it pass where it should refuse:

- **the `.git` check is file-or-directory existence, not directory existence.** This repository's
  worktrees at `.worktrees/<slug>` mark themselves with a `.git` **file** holding a `gitdir:`
  pointer, not a directory. A check written as `is_dir()` accepts every worktree, and worktrees are
  where concurrent sessions in this project actually do their work.
- **an empty-string output path counts as unset**, taking branch (a) and refusing, rather than
  counting as a configured path that resolves to the current directory. `${VAR:-}` in a compose file
  yields an empty string rather than an absent variable, a shape this project has already been bitten
  by on constrained settings fields; the check is on a non-empty value.
- **the path is `Path.resolve()`d before its parents are walked.** Walking an unresolved path finds
  no `.git` above a symlink whose target sits inside a checkout, so a symlinked output directory
  would pass a check that the real destination fails.

**These properties are asserted by tests, not merely documented**, per the plan's `#VERIFY`:

- a test that a storybook with a 4-family cohort is absent from the output and a 5-family
  cohort is present, which pins the integer and its comparison direction (a threshold test
  that only checks the exclusion passes against an inverted comparison);
- a test on a fixture of 5 reading families of which only 1 rated the book: the row is present and
  the rating cell is absent. This pins the per-signal floor separately from the row-level one, and it
  is a distinct test because an implementation that applies the gate exactly once passes every
  reader-cohort test there is;
- a test that each categorical exclusion in Decision 2 fires independently of cohort size;
- a test that a serialised artifact contains no field outside Decision 3's emit allowlist, asserted
  against the allowlist itself rather than against a list of forbidden names, so that a field added
  later fails by default rather than passing by omission;
- a test that the flag cell holds the same suppression marker at 0 flagging families as at 4, which
  pins Decision 5's fold and would fail against the more legible zero-plus-marker form;
- a test that no serialised artifact contains a total, count, or summary spanning more than one
  storybook;
- a test that `node_id` appears nowhere in a serialised artifact;
- a test that settings construction raises when the job is enabled with an output path inside
  a git working tree, **paired with** a test that it constructs cleanly with a path outside
  one. Cite the pair: the refusal alone passes for a validator that refuses unconditionally.

### 8. No route, and it is a decision rather than an implementation note

The job is a scheduled analysis job writing a report artifact. **It acquires no API route,
now or later.** The reasoning is the plan's own and is recorded here as the decision so it
survives the plan document: a route is a data-egress path, reachable by anything that can
reach the service, subject to whatever authorisation bug the service acquires next, and this
data set is exactly the kind that should not gain one. The 37 routers in `app.py` are the
service's egress surface; this job stays off it.

A consumer that needs this output reads the artifact from the filesystem in the same
deployment. If a future requirement genuinely needs it over HTTP, that is a new decision that
amends this ADR, and its threshold analysis starts over, because a threshold derived for a
file on one host is not a threshold for an endpoint.

### 9. The ADR-018 D6 obligation

D6 requires "a single authoritative map of every data element the system holds, recording for
each one: what it is, **from whom it is collected** (the child directly, the guardian about the
child, staff, or the generation pipeline), **why it is collected** (the specific product
function that needs it), who it is disclosed to, how long it is kept, and how it is deleted",
and it decides that "the inventory is **generated from the ORM models**, and a hand-maintained
inventory is not an acceptable form of this deliverable"
(`adr-018-childrens-privacy-compliance.md:885-931`).

What this job owes it:

- **No new data element.** The job collects nothing. It adds no column, no table, and no ORM
  model, and it reads only elements the reading APIs already store. The generated inventory's
  element rows are therefore unchanged, and the generation mechanism D6 decided on is
  unaffected.
- **A new processing activity, which is a different thing.** D6's "why it is collected" and
  "who it is disclosed to" columns change meaning for the elements in Decision 4's allowlist:
  they acquire a secondary purpose (catalog quality calibration) and a new internal recipient
  (the flywheel candidate strategy). That belongs in
  `records-of-processing-activities.md`, which is already per-activity and already lists
  recipients, and it must be written **before the flag is first turned on**, not after.
- **A derived holding with its own retention answer.** The artifact is not an element in the
  inventory, but it is a holding derived from children's data, and Decision 6 gives it a
  stated window (current run plus one) and a stated deletion trigger (each successful run, and
  flag-off). This is deliberate: D4 already carries three classes with no window, and this
  review is not adding a fourth.
- **A necessity note.** The Rule's necessity limit bars conditioning a child's participation on
  collecting more than is reasonably necessary. This job conditions nothing: it is read-only,
  downstream of publication, and no child's experience changes whether it runs or not. That is
  the whole of the necessity analysis, and it is short because the job's read-only,
  no-new-collection shape is what makes it short.

### 10. What would change this decision

The threshold may be **raised** on judgment at any time. **Lowering it requires an owner ruling
recorded as an amendment here**, and the pressure to lower it is the predictable one: the job
will publish nothing for a long time, and "5 is too strict, we cannot see anything" will be
the argument. That argument is not evidence.

The measurement that would justify revisiting the number, in either direction, is the
**empirical distribution of distinct `family_id` per catalog-visibility storybook**, reported
as a histogram of storybooks per cohort-size bucket. Note what that measurement is: a count of
**books** per bucket, containing no per-child values and no per-storybook rows, so it can be
taken without publishing anything this ADR restricts. It is the one number that turns this
derived threshold into a calibrated one. Concretely:

- If that histogram shows a substantial mass of catalog books at cohort sizes well above 5
  (say a median above 25), the threshold is costing nothing and should be **raised**, because
  a threshold below the achievable cohort size is a threshold doing no work.
- If it shows nearly all catalog books below 5, that is evidence the **job is premature**, not
  evidence the threshold is wrong. The correct response is to leave the flag off, not to lower
  the number until output appears.

Three other conditions void the analysis above and require a fresh review rather than an
adjustment:

- the output gains any consumer other than the flywheel candidate strategy;
- the job gains a route, a breakdown dimension (Decision 3), a field outside Decision 3's emit
  allowlist, or a new source table;
- the schema gains a child-linked column that the allowlist would silently admit, which is why
  the allowlist is closed by default rather than a deny-list.

## Consequences

### Positive

- The C3 job's hard precondition is discharged with a number an implementer can encode as a
  single integer, plus two categorical exclusions that hold without depending on that integer
  being computed correctly.
- Two re-identification vectors that the plan's own `#CRITICAL` marker did not name are closed:
  `personalization_subject_profile_id` (a book about one identified child, which no cohort
  threshold reaches) and cohort subdivision by version or any other breakdown dimension.
- A third is closed by binding the threshold to each emitted signal rather than only to the reader
  cohort, so the book read by five families and rated by one publishes no rating. The plan's
  `#VERIFY` as written would have been satisfied by an implementation with that hole in it, because
  a threshold test at the row level passes against a gate applied exactly once.
- Both sides of the job are now closed by default. Decision 4 closes what may be read and Decision 3
  closes what may be said; a closure argument on one side of a pipeline does not reach the other, and
  the first draft had it on only one.
- The public-repository question is answered as a decision with a mechanism behind it, rather
  than left to whoever writes the output path.
- The reading-time question is closed on a schema fact rather than a preference, so it does not
  return as a proposal each time someone reads the plan.

### Trade-offs

- **The job will very likely publish nothing for a long time**, possibly for the whole of R1
  and R2. That is accepted, and Decision 10 pre-commits to reading an empty output as evidence
  about catalog reach rather than as evidence about the threshold.
- Family-grain counting is more conservative than profile-grain and will suppress some books
  that a profile count would pass. That is the intended direction.
- Excluding `storybook_assignment` costs the job a real signal (assigned but never opened),
  which is arguably the most interesting engagement outcome there is. It is excluded anyway,
  because it is guardian behaviour rather than child reading outcome and it is not needed for
  the correlation the plan actually asked for.
- The validator in Decision 7 is honest about defending the developer-workstation case and
  passing trivially in a container. A stronger deployment-side control is possible and is not
  specified here.
- **The flag signal carries no information until a book reaches 5 flagging families**, because
  Decision 5 folds zero into the suppression marker. At the current catalog's scale that is every
  book, so the field will read `<5` corpus-wide for a long time. Legibility was traded for the last
  increment of suppression, knowingly, on the grounds in Decision 5.
- The emit allowlist is closed by default, so every field a future consumer wants is an amendment to
  this ADR rather than a code change. That friction is the point, and it will be felt as friction.

### Technical debt

- **The plan's named validator inputs do not exist in persisted form.** Consequence distance,
  reconvergence, and diversity scores are not columns; two of the three have no production
  caller at all. The correlation the plan describes is therefore not buildable end to end from
  the allowlist above until those statistics are persisted per storybook version. This review
  does not authorise persisting them, and doing so is a separate change with its own review,
  since a new column on `storybook_version` is a new data element in D6's sense (although not a
  child-linked one).
- This ADR is `proposed` and the job it authorises is gated on ratification. If the flag is
  turned on before ratification, the mitigation the owner's assumed-approval ruling depends on
  has not been honoured.

## Follow-on work

- **`UW-A57`** (Cluster A, `decision`): owner ratification of this ADR. Until it is ratified,
  the kill switch stays off and no artifact is produced against real reader data. The owner is
  also the only person who may lower the threshold in Decision 1.
- **`UW-A50`** (Cluster A, existing, ADR-018 D6): unchanged in scope by this ADR, which adds no
  data element to the inventory. It gains one dependent obligation: the new processing-activity
  entry in `records-of-processing-activities.md` described in Decision 9, which must land before
  the flag is first turned on.
- **`UW-C426`** (Cluster C, new): the authoring-lessons row `AL-695` behind this ADR's Technical
  debt bullet, on plan documents naming persisted inputs that are not persisted.
- **`UW-C427`** (Cluster C, new): the authoring-lessons row `AL-696`, on a minimum-cell threshold
  that binds the top-level cohort while the signals aggregated inside it go ungated. Raised by the
  senior review of this ADR's first draft and fixed in Decision 1; the row carries the general sweep
  of this repository's other suppression and gating surfaces for the same shape.
- **`UW-C428`** (Cluster C, new): the authoring-lessons row `AL-697`, on a closure argument made on
  one side of a data path and assumed to cover the other. Fixed here by Decision 3's emit allowlist;
  the row carries the general check.

## Note on the documentation nav

This ADR is deliberately **not** added to `mkdocs.yml`'s nav. That nav's ADR list stops at ADR-011
and does not include ADR-029 or any other ADR after ADR-011, so the directory is navigated through
[`adr/README.md`](./README.md), which does list this one. Adding a single entry for ADR-030 would
invent a convention that holds for exactly one document. Recorded here because the reasoning existed
nowhere in the tree and the omission otherwise reads like an oversight.
