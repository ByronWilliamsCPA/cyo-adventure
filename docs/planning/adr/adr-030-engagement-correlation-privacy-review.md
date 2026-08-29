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

### 3. The output grain is the storybook, and the job may not subdivide the cohort

One row per storybook. Where a signal is version-scoped (the Stage-4 engagement advisory,
completions), the job reads the currently published version only, via
`storybook.current_published_version`.

Splitting a row by version, by age band within a book, by ending, by month, or by any other
dimension subdivides the cohort, and a subdivided cell is the classic failure of a
threshold applied only at the top level: five families pass the gate, then a per-version split
produces a cell of one. **Any breakdown dimension the job later grows must re-apply the
5-family threshold at the leaf cell, not at the storybook.** Adding a dimension without doing
so is a change to this decision and needs an amendment here.

Age band, where the artifact reports it, is a property of the **book** (the band the story
targets, taken from the request that produced it or from the Storybook blob's declared band),
never `child_profile.age_band`. The job reads no attribute of any child.

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

Flag data appears in the output only as counts by `reason` at storybook grain, and only when
the storybook's **flag count is itself at least 5**. The same integer is applied to this second
population because it is the same disclosure problem. Below that, the field is emitted as an
explicit suppression marker rather than as a zero, since a zero and a suppression are different
facts and collapsing them is the tri-state failure this repository has already paid for
elsewhere.

### 6. The artifact is never committed to this repository, and has no in-repository default path

**Decision: the artifact may not be committed to this repository, ever.** Not to `docs/`, not
to `out/`, not to a report directory, not behind a `.gitignore` entry that a later `git add -f`
or a reorganisation could defeat. This repository is public. A push is not retractable: the
blob stays reachable in history after any subsequent deletion, and the disclosure would have to
be reasoned about as permanent from that moment. The asymmetry in Significance decides this
outright.

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

**Both properties are asserted by tests, not merely documented**, per the plan's `#VERIFY`:

- a test that a storybook with a 4-family cohort is absent from the output and a 5-family
  cohort is present, which pins the integer and its comparison direction (a threshold test
  that only checks the exclusion passes against an inverted comparison);
- a test that each categorical exclusion in Decision 2 fires independently of cohort size;
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
- the job gains a route, a breakdown dimension (Decision 3), or a new source table;
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
