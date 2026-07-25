---
schema_type: planning
title: "Story Diversity Execution Plan"
description: "Executable schedule for the 53 actionable deliverables in story-diversity-remediation-plan.md,
  re-sequenced from discovery order into dependency and value order: seven milestones, one branch per shippable
  unit, with decision gates, the critical path, and per-milestone exit criteria."
tags:
  - planning
  - generation
  - diversity
status: active
owner: core-maintainer
authors:
  - name: "Byron Williams"
purpose: "Turn the remediation plan's design record into work that can be started. The remediation plan's phases
  P1-P10 were numbered in the order the analysis discovered them, not the order the work should happen; this
  document re-groups them by dependency and value, names the branch each group ships on, and states what must be
  decided before code."
component: Strategy
source: "story-diversity-remediation-plan.md (deliverable inventory D1-D56 and sections 1.1-1.13);
  story-diversity-analysis.md (findings 2.1-3.9); CLAUDE.md branch and quality-gate conventions."
---

> **Read this with, not instead of, [story-diversity-remediation-plan.md](story-diversity-remediation-plan.md).**
> That document holds the evidence, the measurements, and the reasoning for every deliverable. This one holds
> only the ordering. Deliverable IDs are identical across both.

---

## 1. Why a second document

The remediation plan's ten phases were numbered as the analysis found them. That order is close to the reverse
of the order the work should be done in:

- **P10 turned out to be the root cause.** `restart-on-fail` being specified, unrepresentable, and half-built is
  what makes the P4 symptoms exist at all (section 1.11). It is numbered last and is close to first in value.
- **P4 shrank twice under review.** PL-22 went from "rebalance the gamebook cells" to 73 ending relocations, and
  D18 was replaced outright when path mass superseded ending count (sections 1.7, 1.9, 1.12).
- **P9 mostly retracted.** D41, D42, and D44 are resolved-or-retracted and carry no work (section 1.12); only
  SR-9 (D43) and an ADR note (D45) survive.
- **Three deliverables are ADR text, not code**, and they gate the code that follows (D15, D45, D49).

So: **56 numbered deliverables, 53 actionable** (D41, D42, and D44 carry no work), 32 S / 19 M / 2 L. Of the
53, **52 are scheduled below**; D7 is held as an unscheduled fallback per section 7. Re-sequenced below.

---

## 2. Milestones

One branch per row unless noted. Branch names follow the `{type}/{descriptive-slug}` convention in `CLAUDE.md`.

### M0: Decisions and ADR text (unblocks M2 and M3)

| Deliverable | What | Effort |
| --- | --- | --- |
| D15, D45, D49 | **One ADR-011 amendment PR** covering three things at once: PL-22's 33% fraction, the series-plus-gamebook tension (a series book's fails must be `setback`-shaped), and that `restart-on-fail` is a player-level loop over hard terminals rather than the graph edge the ADR currently implies. | S |
| D35 | Restore or repoint `coppa-gdpr-remediation-plan.md`, cited by `interpretation.py` as governing Route A self-naming but absent from `docs/planning/`. | S |
| D51 | Document `save_slots` as reserved for D47 so a contributor does not assume checkpoints work. | S |
| D56 | **Decision needed:** may a guardian withdraw challenge-mode availability for a profile? | S |

Branch: `docs/adr-011-amendment-depth-and-restart` (D15/D45/D49), `docs/restore-coppa-remediation-plan` (D35),
`chore/document-save-slots-reserved` (D51).

**Why first.** Three code milestones cite ADR numbers that do not exist yet. Writing the amendment first costs a
day and removes the "is this ratified?" question from every later PR.

### M1: Turn the diversity signal on, and gate the catalog

The highest immediate value in the plan, and entirely independent of everything else. Nothing downstream of
similarity does anything until this lands.

| Deliverable | What | Effort |
| --- | --- | --- |
| D1 | Split `theme_signature` into `echo_signature` and `similarity_signature`; pure refactor, no output change. | S |
| D6 | Committed evaluation panel of realistic premises (pets, sports, family, school, music, invention). | S |
| D2 | Expand and unify the controlled vocabulary against the 132 themes the catalog already declares. | M |
| D3 | Replace symmetric Jaccard with a containment measure for request-versus-story. | S |
| D4 | Make "unknown" distinct from "dissimilar"; treat unknown conservatively. | S |
| D5 | Re-derive `tau_theme` on the D6 panel and record the new value with its basis. | S |
| D8 | CI audit: pairwise `structural_distance` per cell, failing below `TAU_CELL`. | S |
| D10 | Clarify or fix `structure_fingerprint` as an identity check, not a clone check. | S |
| D9 | Resolve the live clone pair (`the-sunken-temple` / `the-harrowstone-keep`). | M |
| D43 | SR-9: the highest-index series book must be `is_final`, or a successor must exist. | S |

Branches: `fix/similarity-signature-coverage` (D1, D6, D2, D3, D4, D5),
`feat/in-cell-clone-audit` (D8, D10, D43), `fix/resolve-clone-pair-13-16-gamebook` (D9).

**Order within the branch matters:** D1 before D2, so the echo path is a named, protected function before its
vocabulary changes. D6 before D5, so the threshold is re-fit against a committed panel rather than a guess.

**Explicitly not built:** D7, the open-vocabulary similarity signature. Build only if D2 plus D6 show coverage
short of the 95% target, and only then take on section 1.1's privacy review and DPIA question.

### M2: Start telemetry, and land PL-22

Telemetry is a long-lead item: it produces nothing on day one and gates D18, D19, and D50. Start it as early as
possible so data accumulates while other milestones run.

| Deliverable | What | Effort |
| --- | --- | --- |
| D16 | Instrument real reading depth, early-exit rate, and satisfying-ending rate from `ReadingState` and `Completion`. | M |
| D14 | PL-22 fail-depth floor at 33% of `min_complete`, scoped to `death`/`capture` terminals. | S |
| D17 | Relocate the 73 foreclosing endings PL-22 rejects, via M2 ending re-map. | M |

Branches: `feat/reading-depth-telemetry` (D16), `feat/pl-22-fail-depth-floor` (D14),
`fix/relocate-shallow-foreclosing-endings` (D17).

**Gate:** D14 needs M0's ADR amendment ratified. D16 needs nothing and should start on day one of M1.

### M3: Restart-on-fail, then challenge mode (the root cause)

The highest-leverage work for the gamebook cells, because it addresses the cause rather than the symptoms.

| Deliverable | What | Effort |
| --- | --- | --- |
| D46 | Engine-written checkpoints at derived safe points, snapshotting into `save_slots`. | M |
| D47 | Two-tier restart: `setback` auto-loops to the last safe point; a foreclosing terminal offers last-safe-point or node 1. | M |
| D48 | Checkpoint placement at or past the funnel-clearing depth (the same 33% quantity as PL-22). | S |
| D50 | Re-shape D18's floor as a session-level cumulative satisfying rate. | S |
| D52 | Per-(profile, series) row carrying challenge mode; band-gated to 13-16 and 16+. | M |
| D53 | Atomic, server-authoritative series reset preserving `Completion` rows. | M |
| D54 | Opt-in surface stating the consequence before enabling. | S |
| D55 | Mode-change policy: downgrade allowed, no retroactive undo of a death. | S |

Branches: `feat/restart-on-fail-checkpoints` (D46, D47, D48),
`feat/challenge-mode-series-reset` (D52, D53, D54, D55), `refactor/session-level-spm-measure` (D50).

**Strict order:** D46 → D47 → D48. D52 → D53 → D54/D55. D50 after D47, since it re-shapes a measure whose
meaning D47 changes.

**Highest-risk deliverable in the plan: D53.** A multi-row destructive reset that must be atomic,
server-authoritative, correct against `state_revision` on every affected row, and must never be applied
optimistically through `offline/sync.ts`. Give it the review attention its blast radius deserves.

### M4: Make escalation act, and scope to the reader

Depends on M1: escalation cannot act on a signal that does not fire.

| Deliverable | What | Effort |
| --- | --- | --- |
| D11 | Thread `DifferentiationLevel` and neighbours into `fill_skeleton` and `fill.md`. | M |
| D12 | Variation-axis library, one axis drawn per request. | S |
| D13 | Feature-vector-aware selection weighting. | M |
| D20 | `profile_id` scoping for history, weighting, and the ATG partner. | M |
| D21 | ATG against the k nearest same-tree fills; calibrate per-band thresholds. | M |
| D22 | Recency window: distinct storybooks rather than versions, or raise the cap. | S |

Branches: `feat/escalated-fill-differentiation` (D11, D12), `feat/feature-vector-selection-weighting` (D13),
`feat/per-profile-diversity-scoping` (D20, D22), `feat/atg-k-nearest-and-calibration` (D21).

### M5: Visibility and expectation setting (parallel track)

Independent of the diversity work end to end. If there is capacity for two tracks, this is the second one.

| Deliverable | What | Effort |
| --- | --- | --- |
| D25 | Guardian visibility ceiling at intake, derived from the acting role. | S |
| D26 | `resolve_visibility` as a pure lattice meet over a frozen table. | S |
| D27 | Fix the `ApproveBody` default, which becomes a silent downgrade. | S |
| D28 | Audit every visibility resolution. | S |
| D34 | Evaluate `resolve_visibility` against the acting role, with a dual-role test. | S |
| D29 | Catalog path: exclude family-facing artifacts structurally. | M |
| D33 | Assert D29's exclusion is read-time, not publish-time. | S |
| D32 | Guardian ceiling-change path. | M |
| D30 | Document the family-only relaxation's actual scope. | S |
| D31 | Gate the catalog prong on Phase 7 COPPA compliance. | S |
| D36 | Serve the restriction set from the API, keyed on band. | M |
| D37 | Surface it on the kid request surface. | M |
| D38 | Surface the fuller set on guardian intake. | S |
| D39 | Enforce the `GUARDIAN_CONTROL` disclosure level. | S |
| D40 | Regression-test stated restrictions against enforced ones. | S |

Branches: `feat/guardian-visibility-ceiling` (D25, D26, D27, D28, D34),
`feat/catalog-surface-decoupling` (D29, D33, D30, D31), `feat/guardian-ceiling-change-path` (D32),
`feat/request-page-restrictions` (D36, D37, D38, D39, D40).

**Strict order:** D25 → D26/D27/D28 → D29 → D32/D33. D33 gates D32: if the exclusion is not read-time, ceiling
changes are not safe. D36 → D37/D38/D39.

**Note:** D27 changes a wire contract, so regenerate the frontend client and commit the diff in the same PR
(`CLAUDE.md` architecture note 1; the `contract` CI job fails on drift).

### M6: Outcome mix, once telemetry has data

Gated on D16 having accumulated enough real reading data to calibrate against. Do not set these floors from the
structural model alone.

| Deliverable | What | Effort |
| --- | --- | --- |
| D18 | Satisfying-path-mass floor keyed on topology, calibrated against D16. | M |
| D19 | In-cell outcome spread, enforced by D8's audit. | M |

Branch: `feat/satisfying-path-mass-floor` (D18, D19).

### M7: Raise the ceiling

Longest lead time, ships last, and the design work should start during M1 so it is not the bottleneck later.

| Deliverable | What | Effort |
| --- | --- | --- |
| D23 | Alternate beat phrasings sharing an outcome contract. Needs a design doc and its own ADR. | L |
| D24 | Grow the small cells past three trees each. | L |

Branches: `docs/adr-alternate-beat-phrasings` then `feat/alternate-beat-phrasings` (D23),
WS-8's existing flywheel path for D24.

---

## 3. Critical path

```text
M0 (ADR text, ~1 day)
 |
 +--> M1 (signal + catalog)  ------------------> M4 (escalation acts)  --+
 |     D1->D2/D3->D5 ; D8,D10,D43 ; D9                                  |
 |                                                                      +--> done
 +--> M2 (D16 telemetry, start day one) --------> M6 (outcome mix) ------+
 |     D14 -> D17                                                        |
 |                                                                      |
 +--> M3 (D46->D47->D48/D50 ; D52->D53->D54/D55)  root cause ----------+

M5 (visibility + expectation setting)   fully parallel, no dependency on the above
M7 (D23 design during M1, code last)
```

**The long pole is M6, and its dependency is calendar time, not effort.** D18 and D19 need real reading data
from D16, and D16 needs readers. Start D16 first, before anything else in M2, or M6 slips by however long the
telemetry lags.

**The second-longest pole is M7's D23**, which needs a design doc and an ADR before any code. Start the design
during M1.

**M3 is the highest value per unit effort** and depends only on M0's ADR sentence. If only one milestone can run
after M1, run M3.

---

## 4. Suggested first two sprints

**Sprint 1.** M0 in full (four small items, one of which is a decision). M1's
`fix/similarity-signature-coverage` branch (D1, D6, D2, D3, D4, D5) and `feat/in-cell-clone-audit` (D8, D10,
D43). Start D16's instrumentation so data begins accumulating. That is 11 deliverables, 9 of them S.

Exit criteria: over 95% of the D6 panel yields a non-empty signature; a byte-identical premise against a stored
story with curated themes scores as similar (it scores 0.333 and fails today); the clone audit fails on current
`main` and passes after D9; every WS-7 echo golden test unchanged.

**Sprint 2.** M1's D9. M2's D14 and D17. M3's `feat/restart-on-fail-checkpoints` (D46, D47, D48). Begin M7's
D23 design doc.

Exit criteria: PL-22 fails on the 73 foreclosing shallow terminals before D17 and passes after; no skeleton
regresses on PL-20; a `setback` terminal auto-returns the reader to a safe point with `var_state` and
`visit_set` restored.

---

## 5. Per-milestone exit criteria

Every branch clears the project quality gate before merge (`CLAUDE.md`): `uv run pytest
--cov=src --cov-fail-under=80`, `uv run ruff check .`, `uv run basedpyright src/`, `uv run bandit -c
pyproject.toml -r src`, `pre-commit run --all-files`. Frontend branches additionally run `npm run lint`,
`npm run typecheck`, `npm run test:run`. Any branch touching a backend route or Pydantic model regenerates the
API client and commits the diff.

Beyond that, each milestone has the acceptance criteria already stated in its remediation-plan phase; they are
not restated here so the two documents cannot drift.

---

## 6. Decisions still needed, and when

| Decision | Blocks | Needed by |
| --- | --- | --- |
| May a guardian withdraw challenge-mode availability? (D56) | D54's surface | M3 |
| Should PL-22 become `max(0.33 * min_complete, funnel_clearing_depth)`? | Nothing; a refinement | After M6's data |
| Should the ATG become blocking, and at what threshold? | D21's final form | M4 |
| Does the similarity signature need a DPIA addendum? | D7 only, which is not planned | Only if D7 is revived |
| ADR for alternate beat phrasings (D23) | All of M7 | M1, so M7 is not blocked |

One product decision is outstanding (D56); the rest are either refinements or gated on data.

---

## 7. What this plan deliberately does not do

- **D7** (open-vocabulary similarity signature) is not scheduled. M1's curated expansion is expected to make it
  unnecessary, and it is the only path that reopens the privacy review in section 1.1.
- **D41, D42, D44** carry no work: SR-8 is retracted and `brass-lantern` needs no continuity remediation, both
  conditional on M3 shipping. **If M3 is deferred indefinitely, SR-8 comes back** and D41 must be rescheduled.
- **No safety exception is requested anywhere.** Every deliverable holds the ADR-011 constraint grammar, the
  full validator and moderation gate, and the selection novelty floor.
