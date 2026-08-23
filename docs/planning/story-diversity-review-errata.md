---
schema_type: planning
title: "Story Diversity Review Errata"
description: "Authoritative record of a seven-reviewer adversarial pass and a 98-document corpus survey against
  story-diversity-analysis.md and its two downstream plans. Records what was refuted, by what evidence, and what
  each finding changes. The two plans are superseded pending a rebuild; this document is the correction of record."
tags:
  - planning
  - generation
  - diversity
  - review
status: active
owner: core-maintainer
authors:
  - name: "Byron Williams"
purpose: "Keep the corrections in one auditable place rather than patching them across three documents that were
  already revised ten times. Records the outcome honestly, including one fabricated quotation and a claim that
  would have been escalated as a compliance finding, so the defects are not rediscovered."
component: Strategy
source: "Seven parallel adversarial reviewers (funnel proxy, path-mass model, two absence claims, the SR-8
  retraction, catalog re-derivation, internal consistency, privacy/authorization), each instructed to refute
  rather than confirm and to re-derive from source; a survey of all 98 documents under docs/planning,
  docs/planning/adr, docs/architecture, docs/compliance; and PR #413
  (docs/planning/cyoa-book-benchmark-comparison.md). 2026-07-25."
---

> **Status of the three reviewed documents.**
> [story-diversity-analysis.md](story-diversity-analysis.md) remains useful: its measurements were re-derived
> independently by three reviewers and held, with four numeric corrections applied in place.
> [story-diversity-remediation-plan.md](story-diversity-remediation-plan.md) and
> [story-diversity-execution-plan.md](story-diversity-execution-plan.md) are **superseded**: do not start work
> from them. They are retained for provenance. Section 6 below states what a rebuild must carry forward.

---

## 1. Headline

The measurements were sound; the inferences drawn from them largely were not.

Every quantitative claim across the three documents was independently re-derived, and essentially all of it
reproduced as at 2026-07-26 (catalog counts have moved since; see
[catalog-census.md](./catalog-census.md) and `UW-G24`): 61 skeletons / 58 production-eligible, 132 curated themes with zero overlap against the tag map's
12 values, the 0.333 Jaccard and the vocabulary asymmetry behind it, 1,778 gamebook endings splitting
104 / 73 / 1, the shallow-tail tables at 25 / 33 / 50 percent, no `min_endings` breach once scoped to
foreclosing terminals, and the count-versus-mass decoupling (confirmed strongly, under four independent reader
models). The clone pair was confirmed on **stronger** grounds than originally offered: a start-preserving,
ending-kind-preserving graph isomorphism across all 550 nodes and 796 edges, not merely a low feature distance.

What failed was reasoning: a proxy invented mid-analysis and then treated as a measurement, a metric defined two
ways in one table, an example that a later section of the same document erased, two validator rules cited
without being read, two absence claims from partial greps, and a worked example that was misquoted.

Four defects found **by** this process are real and independent of the plan's fate: an unvalidated client-writable
`save_slots` field, a stale accepted spec, a series continuation state the gate rejects, and two authorization
gaps. Section 5 lists them.

## 2. Retractions

Ordered by seriousness.

### 2.1 A fabricated quotation (analysis section 3.4; repeated in the remediation plan)

The analysis quoted `the-cave-of-echoes`'s `la_fork` beat as ending
`'{A2_SIGN} deepens into a warning...'` and built on it the claim that every fill of that tree contains
"a two-way split where one branch looks inviting and the other looks like a warning."

The actual beat, `skeletons/8-11/the-cave-of-echoes.json` (not `10-13`, which the reviewer's own report
miscited):

```text
<<FILL role=choice words=100 beats='the way splits into two tracks: on one side {A1_SIGN} catches
the light, on the other {A2_SIGN} deepens into a warm, pulling sound'>>
```

Both branches are inviting. There is no warning, and the beat ends at "sound" -- the trailing ellipsis in the
original quotation concealed that the text had been altered. This was the only concrete evidence offered for
D23, an L-sized deliverable requiring its own ADR. **Corrected in place.** The structural claim behind it
(beats are byte-frozen; `fill.md` plus the Stage 1 fidelity gate pin the scene) was independently verified and
stands, but it now rests on the accurate beat, which is a weaker illustration.

### 2.2 A compliance claim that was false (remediation plan section 1.6, D35)

The plan asserted that `story_requests/interpretation.py` cites
`coppa-gdpr-remediation-plan.md Section 5 Decision 4` as governing Route A self-naming policy and that "a
security-relevant decision is currently governed by a document that cannot be read."

The document exists, at **`docs/compliance/coppa-gdpr-remediation-plan.md`**, and `covers/storage.py:28`
already cites it with that path. Section 5 contains the Route A discussion at line 729, resolved at 757. The
original search was scoped to `docs/planning/` only. **Retracted.** D35 reduces to adding a path prefix to one
comment; it is not an M0 milestone item, and the "cannot be read" framing should never have been written,
because that is the kind of claim that gets escalated.

### 2.3 The 33% fail-depth fraction, as justified (section 1.7)

The recommendation rested on a proxy for "where the shared opening funnel ends": the BFS depth at which 10% of
a tree's nodes become reachable. Three independent defects:

- **It contradicts the phenomenon.** The shared spine computed properly, as the nodes lying on every
  root-to-terminal path via dominator intersection, is **1 to 6 nodes, median 3**. Five of the 14 gamebook
  skeletons branch four or five ways at the start node; there is no funnel. The proxy assigned those books
  funnels of 6 to 10 nodes.
- **It is not invariant to changes that leave the opening untouched.** Because 10%-of-nodes scales with tree
  size while `min_complete` is a per-cell constant, appending nodes at maximum depth moves the median proxy
  from 9 to 13 and collapses 33% from 13/14 to 4/14. `corr(proxy, N) = +0.49`.
- **It is circular.** `proxy / min_complete` has median **0.304**. The 10% threshold was in effect "about a
  third of `min_complete`", and a third was then reported as the finding. Sweeping the knob: 5% yields 25%,
  10% yields 30%, 11% collapses to 9/14, 20% yields 57%.

Against eleven alternative operationalizations, 25% clears 14/14 on five of them including the dominator spine,
and the median "smallest fraction clearing 13/14" is **21%**. Separately, the headline count is wrong: 33%
clears **12** of 14, not 13, because `the-iron-spire-trial` (floor 7.92, funnel 8) also fails and was never
named.

**And the rationale fails across skeletons, which is where it had to hold.** Within-cell opening-content Jaccard
is median 0.089, max 0.177; start-node-only median 0.043; opening out-degree sequences are distinct on 18 of 19
same-cell pairs. Two books in a cell were never confusable at the opening. The sole exception is the clone pair,
already tracked as D9, where a depth floor is the wrong instrument.

What survives: the ending-count headroom analysis (25% and 33% cost the same single exception, and none once
scoped to foreclosing terminals), and a fail-depth floor as a *difficulty* rule, which section 1.7 itself
admitted has no basis in ADR-011 or the corpus. A corpus-wide search confirms it: "difficulty", "win rate" and
"frustration" appear in exactly one document, as a moderation flag string. It is a product decision, not a
derivable one.

### 2.4 The rule ID (37 references)

`PL-22` is a shipped, registered rule: `validator-rules.md:122`, the band-profile fail-closed guard, which
`validator-rules.md:131` confirms suppresses PL-15 through PL-21 when it fires. Two rules under one ID are
semantically incompatible, not merely confusing. The next free policy ID is **`PL-23`**. Rule-ID maxima across
the registry and source: `PL-22`, `SR-7`, `L1-7`, `L2-13`, `RL-13` -- so the proposed `SR-8`/`SR-9` did not
collide.

> **Amendment (2026-07-26), and a defect in the check above.** Those maxima were correct against `main` and are
> still correct against `main` after PR #418 merged. They were never sufficient, because they were measured only
> against merged state: **open PR #416 claims `SR-8`, `PL-23` and `PL-24`.** So `PL-23` is not free and
> `SR-8` is taken. The live plan now specifies `SR-9` for its continuation-state rule and `PL-25` for the
> deferred fail-depth floor, and `L2-14` remains free because #416's "adds L2-13" is a catalog entry for a rule
> already shipped in `layer2.py`. The method rule this failure produced is recorded as rule 5's amendment in
> `story-diversity-plan-v2.md` section 7: state whether a rule-ID claim rests on `main` or on `main` plus the
> open PR set. The historical `SR-8`/`SR-9` names elsewhere in this document refer to the *retracted* proposals
> from the superseded plans and are left as written, since renaming them would falsify the record of what was
> refuted.

### 2.5 The restart design (sections 1.11, 1.12; D46, D47, D48, D51)

Four independent sources say the mechanism should be path replay, and snapshots were chosen against all four.

- **`runtime-semantics.md` (status: accepted) section 6, "No Backtracking in v1"**, normative: "the reader moves
  forward only. There is no 'back' button in v1... a back button requires undoing effects, which demands an
  **event-log model rather than a snapshot model**... any Phase-1 back-button implementation requires a revision
  to this document and an ADR." The rationale names precisely the defect the consistency reviewer found.
  **Superseded 2026-07-26**: section 6 was revised into "Backtracking by Forward Replay" by ADR-024. The
  quotation above is retained as the text this review was conducted against.
- **The same document, section 5**, specifies `save_slots` normatively as part of the save format, and states
  "There is no mechanism to reconstruct intermediate states from a save" -- the direct contradiction of the
  plan's "snapshots avoid the problem entirely by storing the state rather than re-deriving it."
- **`pathfinder-structure-exploration.md` section 4.3**: "Undo replays the path prefix; the recomputed state is
  identical every time."
- **Shipped code**: `frontend/src/reader/Reader.tsx:210` -- "Kids mis-tap constantly; Go back undoes just the
  last choice by replaying" -- with `back` and `canGoBack` in `player/engine.ts`.

Two further defects in the design as written:

- **The safe-point predicate is not computable.** The plan defined a safe point as the most recent visited node
  with an untaken choice, and claimed it was derivable from persisted state. It is not: the same
  non-recoverability that prevents re-deriving `var_state` prevents knowing which choices were exercised, and a
  snapshot stores state, not a ledger. Worse, `player/state.py` `Snapshot` **contains** `path` and `visit_set`,
  so restoring one truncates the history the predicate reads, and `once: true` gates re-open.
- **`save_slots` already has a producer.** `api/schemas.py:80` accepts it in `ReadingStateBody`;
  `api/reading.py:412` writes it verbatim to JSONB; `schemas.py:116` returns it; a test accepts a 64,000-byte
  payload; `offline/sync.ts:111` whitelists it into every PUT. The plan's "nothing can ever write to it" and
  "no API exposes slots" are both false, so D51 would have documented a falsehood.

**Consequences.** M3 requires a revision to an accepted normative document plus its own ADR, which the plan did
not scope. D46 must extend the existing replay affordance rather than introduce snapshots. D48 is
unimplementable as written: section 1.12 abolished authored placement, so a checkpoint derived from where the
reader has already been cannot be placed past a depth floor, and a reader terminating at depth 2 has no safe
point past depth 8 to 12. D51 is deleted and replaced by the security item in section 5.1.

### 2.6 The path-mass evidence (section 1.9)

The premise -- ending count and path mass are decoupled, so a `min_positive_endings` floor measures the wrong
thing -- is **confirmed strongly**. The evidence offered for it was not.

- **The table defines its own metric two ways.** The `Positive` column counts `valence == positive`; SPM counts
  `kind in {success, completion}`. They disagree in **8 of 14** rows. `the-tenfold-siege` is listed with 2
  positive endings while SPM scores 6; `the-drowned-court` with 5 while SPM scores 7. So "five positive
  endings, and effectively no path mass reaches any of them" attributes to a five-ending set a figure computed
  over a seven-ending set.
- **"Only 30 to 136 of each book's declared endings are ever hit" is false.** `the-cinder-bazaar` reaches 141 of
  141 and `the-sunspire-ascent` 74 of 74. The table showed the worst half of the population and a
  population-level inference was drawn from it.
- **The flagship example is erased by the same document.** `the-drowned-court` has zero `death` and zero
  `capture` endings; **93.3% of its 105 endings are `setback`**. Under section 1.12's own rule that a setback
  auto-loops to a safe point, and with a purely choice-uniform reader, its session SPM is **100%**. It is one of
  exactly four skeletons whose 0.00% the plan's own later remedy fully dissolves. `the-pale-road` (147 `death`
  endings, zero setbacks, 0.00% both per-walk and per-session) was the durable example.
- **The 0.00% is two to three orders of magnitude low for a competent reader.** Two or three plies of lookahead
  move 13 of 14 skeletons from ~0% to 41-100%, and the cues are legible: a bag-of-words scorer picks the
  surviving option at 72-100% held-out accuracy, because labels telegraph. At measured p=0.90 across win paths
  of 7 to 42 consecutive branches, SPM lands at **1.3% to 34.9%, median ~9%**.

Two attacks failed, and the original stands on both: ignoring `condition`-gated choices was harmless (8 of 14
gamebooks declare zero variables; for the rest, honouring conditions moves SPM by at most 0.06pp, and no
satisfying ending is gated out of reach), and the walker was validated in lockstep against `StoryEngine` with
zero divergences in 1,800 walks.

### 2.7 The per-topology SPM key (D18)

Not calibratable. Four of six topology classes have **zero** gamebook instances (`sorting_hat`, `open_map`,
`time_cave`, `loop_and_grow` all 0; `branch_and_bottleneck` 8, `gauntlet` 6). The plan's only illustration, "a
gauntlet earns a lower floor than a sorting_hat", sets n=6 against n=0. The two populated classes do not
separate (eta-squared 0.367, within-group variance exceeding between-group; `the-harrowstone-keep` and
`the-drowned-court` sit at 100% and 0% in the same class), effective n is lower still because two of the eight
are the clone twins, and **the one available comparison runs backwards**: gauntlets score higher (86.1% mean)
than `branch_and_bottleneck` (34.2%).

What does key on topology is the fail-kind mix (eta-squared 0.636), and it keys on it for a reason: it
determines whether the setback auto-loop applies at all. That is the defensible key.

### 2.8 The series rules (sections 1.10, 1.12; D41, D42, D43, D44)

- **The retraction of SR-8 rested on a misreading.** The plan stated "SR-5 already requires a **reachable**
  satisfying ending." `series.py:210-213` is a pure existence quantifier over `book.nodes` -- no graph, no
  `start_node`, no conditions. Orphaning all four of book 1's win endings still returns `ok=True` with zero
  findings; the per-book L1-3 gate catches it, which is a different rule doing the work.
- **SR-8 was never a gap against ratified policy.** ADR-011 section 8's invariant is scoped to *satisfying*
  endings. Measuring all 152 endings against it measured a rule the ADR never made. The conditional revival
  ("if M3 is deferred, SR-8 comes back") is therefore also unfounded.
- **SR-9 contradicts a recorded decision.** SR-4's docstring states the top-index book *may* be non-final, that
  open chains are first-class per ADR-011 section 8, and that "v1 generation always writes `is_final=False`".
  SR-9 would fail every v1-generated chain, and its disjunct is vacuous, since for the highest-index book a
  successor by definition does not exist. It reduces to "the last book must be final", forbidding exactly what
  ADR-011 blesses. Retract or reframe as an ADR amendment; the S sizing is wrong either way.
- **What is real, and already registered.** `series-stress-test-findings.md` F3 documents the `has_lantern`
  inversion as Medium *authoring guidance*, and its section 3 verified only the `has_lantern=true` path. The
  escalation is that the gate **blocks** book 2 at `has_lantern=false` with two `L2-11` dead-branch errors,
  while all four of book 1's win endings are reachable with it false, and `vigor` is monotone (68 `dec`, zero
  `inc`) so restart cannot restore state never earned. That is a promotion of F3 from guidance to
  gate-detectable defect, not a new finding. What is genuinely missing is a rule that continuation entry state
  be admissible -- L2 only ever walks from `start_node` with declared initials.

### 2.9 The privacy split (sections 1.1, 1.3; D1, D2)

- **"Echo-safe by construction" is false.** Running the actual echo floor against all 132 catalog themes,
  **129 of 132 pass at band `3-5`** -- `institutional abuse`, `grief`, `moral cost`, `isolation`, `sacrifice`
  among them. Only three are withheld, and only for containing the stems `lethal` or `drowning`.
  `band_mandatory_bundles` is a hand-listed frozenset of concrete violent nouns with no conceptual coverage of
  abstract mature themes, and the floor for `13-16`/`16+` is the empty set.
- **D1 and D2 are the same mutation.** The echo signature *is* `_THEME_TAG_MAP`. D2 grows it. So D2 changes what
  a child sees, violating constraint 5 ("the WS-7 echo path is byte-identical after D1") and failing the echo
  golden tests P1 requires to pass unchanged. The two deliverables were described as independent and are not.
- **The vocabulary is already open.** `normalize.py:544` passes unmapped `metadata_themes` through verbatim, so
  "closed by construction" is a property of one call site, not of the function.
- **The DPIA conclusion checks the wrong axis.** "No new personal data at rest" does not address the change D2
  actually makes, which is to a child-facing surface's content appropriateness.
- **The masking defence is unavailable.** `extract_entities` requires a `Storybook` and detects medial-caps
  tokens in node bodies; it cannot run at request time, and `_tag_matches` never calls `mask_tokens`.
- **D4 reverses a ratified decision without citing it.** `normalize.py:470-482` documents the empty-signature
  behaviour as deliberate: "never 'identical theme', so it must never register as similar to anything."
- **D3 and D4 contradict each other** on the same branch: D3 says leave `jaccard_similarity` untouched, D4
  changes its empty-set return.
- **And the fix could reproduce the diagnosed no-op.** D3 and D4 both push toward "similar". With 3-tree cells,
  `cell_theme_saturation` pins at 1.0 after three reads, the ladder sits permanently at `LEAF`/`CATALOG`, and
  `_blended_weight` becomes rank-equivalent to recency-only -- the mirror image of the headline finding. The
  "escalation trigger rate" metric has no ceiling and cannot detect it.
- **The 95% coverage target is unsupported.** No measurement establishes that a 60-120 tag curated keyword map
  recognises 95% of free-text child premises; the panel that would test it is built in the same milestone. The
  whole privacy simplification rests on that untested expectation.

### 2.10 The visibility lattice (sections 1.4, 1.5, 1.6)

- **The dual-role mechanism is wrong, and the project had already chosen a better one.**
  `admin-guardian-dual-roles-plan.md` identifies this risk ("silent escalations for a guardian-who-is-admin
  acting on guardian surfaces") and recommends passing acting role **explicitly at admin-gated call sites
  instead of deriving it**. The plan cited `acting_role` as "the primitive already exists"; deriving from it is
  the problem. `acting_role(own_family)` returns `GUARDIAN`, so evaluating the lattice against it would let a
  dual-role adult raise their own ceiling through the admin approve path -- the exact loophole the section
  claimed to close.
- **One reported "exploit" is a documented capability.** `authorization-matrix.md:96` lists admin-authored
  requests as permitted for "any family, or catalog-targeted with no family". The defect is that a ceiling
  default keyed on `initiator_role` mishandles an intended capability, not that the system has a hole. Reported
  as a security exploit in an earlier summary; that was wrong.
- **The lattice is not implementable at the stated enforcement point.** There is no `Storybook` to
  `StoryRequest` join: `GenerationJob.storybook_id` is deliberately not a foreign key and multiple jobs exist
  per storybook. Imported and `fresh_generation` books have no chain at all and would fail **open** to
  `CATALOG`.
- **D32 conflicts with a `#CRITICAL` invariant.** `publishing/service.py:309-317`: visibility "is stamped ONLY
  here, inside the sole publish path... it must never be settable outside an admin-gated approve", with three
  named enforcement points. A guardian-surface ceiling change is exactly what that forbids, so D32 is an
  amendment to a security invariant, not an audited path. Relatedly, `LEGAL_TRANSITIONS` has no transition out
  of `PUBLISHED` except `ARCHIVE`, so both post-publish decisions require a second writer the plan does not
  constrain.
- **A supporting fact was false.** The plan stated `LEGAL_TRANSITIONS` "has no machine-reachable transition out
  of `published`"; `state_machine.py:76` has `(PUBLISHED, ARCHIVE) -> ARCHIVED`. The conclusion survives, the
  fact does not.
- **D28 cannot record what it needs to.** `events/writer.py:37` whitelists `"visibility"` only in
  `EventType.RELEASED`; a post-publish change needs a new event type or `record_event` strips it.
- **D27's fix never fires.** There are two defaults, and it addresses one. `ReviewDetailPage.tsx:171` holds
  `useState<Visibility>('family')` and always sends an explicit value, so in production the body is never
  omitted.
- **Multi-guardian "most restrictive" is not representable** over D25's single scalar field, and has no
  deliverable.
- **The ceiling is not the guardian's control over cross-family disclosure.** Ring 2 discloses another family's
  child `display_name` plus their rating (`recommendations.py:334-337`), governed by connection consent on a
  different surface; and admins hold global cross-family read regardless of visibility. The family-only
  guarantee is narrower than stated: it restricts other families' browse, assign and read of the *book*.
- **One requirement is satisfied already.** Section 1.6's load-bearing read-time requirement holds by
  construction: `interpretation` is a column on `story_request` only, never copied into `StorybookVersion.blob`
  or any storybook read surface.

### 2.11 Telemetry (D16)

The premise is false. `ReadingState` is a single mutable current-state row with `path` overwritten and no
history; `Completion`'s primary key includes `ending_id` with one `found_at`, so **re-reads are not counted and
depth-at-terminal is not recorded at all**. Only "which endings were collected" exists. `r1-deferred-debt-register.md`
U5 already registers this as Phase 4b Medium, noting it needs a new read endpoint "and likely a schema/index
decision". So D16 is new durable persistence plus a migration plus a child-behaviour privacy review, not
reporting over existing rows -- and D47's snapshot restore would truncate `path`, destroying the one signal it
needs. The corpus contains no other mention of reading telemetry or session depth, so the gap itself is real.

### 2.12 Numeric corrections (applied in place)

| Claim | Was | Is |
| --- | --- | --- |
| Cells holding exactly three trees | 14 of 18 | **15 of 18** (the analysis's own table already showed 15; 15x3 + 2x4 + 1x5 = 58) |
| P(second story reuses the first tree), 3-cell | 20.1% | **exactly 20.0%** = 1/5; general form 1/(2n-1) |
| Same, 4-cell | 13.9% | **14.286%** = 1/7 |
| Clone pair effects | "49 effects: identical" | **47 vs 49** -- and that 2-effect delta is the entire source of the nonzero distance |
| Negative endings, clone pair | 145 | **148** |
| 33% clears the funnel proxy on | 13 of 14 | **12 of 14** (`the-iron-spire-trial` unnamed) |
| Cell space | 18 cells | **24**, six empty -- and no `short` skeleton exists for either teen band in either style, so a `13-16/short` request has zero candidates and 422s |

## 3. Findings the corpus already held

The root cause of five defects above is that the planning corpus was never surveyed. It holds 98 documents; four
were read.

| Already answered in | What it settles |
| --- | --- |
| `runtime-semantics.md` (accepted) sections 5, 6 | Backtracking is deferred by normative rule, with the snapshot-versus-event-log rationale; `save_slots` is a specified save-format field |
| `pathfinder-structure-exploration.md` sections 4.1-4.4, 5.2 | Deterministic "your build is the roll" ladder with L2-11 proving band reachability; randomness rejected; player-authored initial state worked through |
| `admin-guardian-dual-roles-plan.md` | The dual-role escalation risk and the explicit-acting-role-at-call-sites fix |
| `authorization-matrix.md` | Admin-authored requests into any family are an intended, documented capability |
| `series-stress-test-findings.md` F1-F3 | The `has_lantern` inversion, absent series linkage on import, and auto-repair replacing imported content |
| `r1-deferred-debt-register.md` U5 | The reading-history gap D16 depends on, with a phase and an owner |
| `validator-rules.md` | The rule registry; `PL-22` taken, `PL-23` free **on `main`** (but claimed by open PR #416, see the 2026-07-26 amendment in section 2.4) |
| `docs/compliance/coppa-gdpr-remediation-plan.md` | Route A self-naming policy, the document claimed to be missing |

**Any future rule ID, ADR reference, or "this is unaddressed" claim must be checked against the registry and the
corpus first.** That single step would have prevented sections 2.2, 2.4, 2.5, 2.8, 2.10 and 2.11.

## 4. What survives

- Every re-derived measurement in section 1.
- The count-versus-mass decoupling, and therefore the rejection of a `min_positive_endings` floor.
- The clone pair, on proven isomorphism.
- The vocabulary asymmetry: the stored side unions raw curated themes the request side cannot emit, so symmetric
  Jaccard scores a byte-identical premise at 0.333 and it does not register as similar.
- The beat-freezing constraint behind D23, on the accurate beat.
- That difficulty, win-arc count and reading telemetry are genuinely unspecified corpus-wide.
- The fail-kind mix as a defensible key where topology is not.

## 5. Defects found by this review, independent of the plan

Each is real, present-tense, and worth its own issue regardless of what happens to the diversity work.

### 5.1 `save_slots` is exempt from the anti-forgery gate

`reading.py:168-175` passes `current_node`, `var_state`, `path`, `visit_set` and `choice_path` to
`validate_reading_state` and **omits `save_slots`**, defeating the `#CRITICAL` intent two lines above
("so a forged current_node/var_state/path cannot be persisted"). Inert today because nothing restores from a
slot; the moment anything does, a client-forged slot becomes a state-restoration input and its `current_node`
could be any node in the graph. Only bound today is 64 KB. Either validate it or remove it from the PUT body.

### 5.2 An accepted normative spec is stale against shipped code

`runtime-semantics.md` section 6 states there is no back button in v1 and that any implementation "requires a
revision to this document and an ADR". `Reader.tsx:210` ships one. The revision and ADR never happened.

### 5.3 A series continuation state the gate rejects

`the-sunken-temple` declares `has_lantern` initial `true` ("won at Harrowstone"), which book 1 does not
guarantee; the full gate on book 2 with `has_lantern=false` returns `blocked=True` with two `L2-11` errors. No
rule inspects continuation entry state. Escalates `series-stress-test-findings.md` F3.

### 5.4 Shipped `RESTART` discards carried series state

`frontend/src/player/machine.ts:108` resets to the start node with declared initials, which in a continuation
read fabricates `has_lantern=true` and `vigor=5` the reader never earned. `engine.ts:288-297` separately
disables replay for continuation reads, so the one rewind affordance is off precisely in state-carrying books.

### 5.5 Two authorization gaps

A ceiling default keyed on `initiator_role` would treat an admin-authored request into a real family as
unconstrained (documented capability, undocumented consequence); and `acting_role` returns `GUARDIAN` for a
same-family admin approve, so any rule evaluated against it inverts for dual-role adults.

### 5.6 Minor

`api/recommendations.py:340` emits a real child `display_name` cross-family under dual consent with no
ring-keyed redaction. `TAU_CELL` is loaded from `ws5_floor_baseline.json` at import rather than being the
constant 0.05 the plan assumes. K19 is marked delivered in `capability-register.md:133` while the
pre-submission half is unbuilt.

## 6. What a rebuild must carry forward

> **The rebuild is [story-diversity-plan-v2.md](story-diversity-plan-v2.md)** (2026-07-25). It carries the seven
> rules below as its own section 7, states what it does *not* claim as its section 2, and is materially smaller:
> twelve near-term deliverables, six independent defects, eight deferred items each behind a named prerequisite,
> and four decisions.

1. **Survey the corpus before proposing.** Five defects trace to skipping it.
2. **Separate measurement from inference explicitly.** The measurements held; the inferences did not. Any
   invented proxy must be stated as invented, with its free parameters and a sensitivity sweep, or not used to
   decide anything.
3. **One metric, one definition per table.** The `Positive`-versus-SPM mismatch and the fail-depth column's two
   conventions were both self-inflicted.
4. **Do not let a later section quietly erase an earlier section's evidence.** The `the-drowned-court` flagship
   and section 1.7's Constraint 1 were both dissolved by section 1.12 of the same document, in place, unnoticed.
5. **Check rule IDs, ADR numbers and "unaddressed" claims against the registry.**
6. **Quote source text verbatim or not at all.**
7. Keep the four independent defects in section 5 as their own work items; they do not depend on the diversity
   plan being rebuilt.
