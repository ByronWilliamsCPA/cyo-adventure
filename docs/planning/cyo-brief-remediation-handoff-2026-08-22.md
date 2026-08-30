# Handoff: build a project plan for the generation-framework remediation

Handoff of 2026-08-22, for a team that has not seen the analysis that produced it.

> ## Supersession notice, 2026-08-30
>
> **This handoff addresses a planning team as of 2026-08-22 and its instructions are historical
> record, not live direction.** Read
> [the gap analysis's supersession notice](./cyo-brief-gap-analysis-2026-08-22.md#supersession-notice-2026-08-30)
> before acting on anything here. Specifically: section 7's "two high-impact PRs are still open" is
> wrong, both #729 (`167c29da`) and #737 (`41d30909`) merged; #737 carried **eight** owner rulings,
> not nine; `GA-D1` is largely answered by the ADR-005 amendments of 2026-08-25 and 2026-08-28 (#764,
> #769, #776, #778) and only three residuals survive; the economics inputs are superseded by #784's
> [unit-cost-model.md](./unit-cost-model.md), whose revenue anchor is a $1.99 or $4.99 subscription
> rather than the catalog subscription plus credit packs assumed here; and the parallel review this
> handoff mentions is now scheduled on `main` by
> [generation-review-workstream-plan-2026-08-22.md](./generation-review-workstream-plan-2026-08-22.md),
> which any plan built from section 6 must sequence against.

**Your task**: turn the item inventory in section 6 into a sequenced project plan with owners,
estimates, and milestones. Everything you need is on branch `claude/cyo-brief-analysis-jys942`.

**What you are not being asked to do**: re-run the analysis. It has been done twice and adversarially
validated once. Section 3 tells you which parts to trust and which to distrust.

---

## 1. The product in one paragraph

CYO Adventure generates choose-your-own-adventure books for children with LLMs. A family requests a
book by premise; the system selects a pre-authored **skeleton** (a story graph whose node bodies hold
`<<FILL ...>>` directives), fills it with prose, runs it through deterministic validation and
moderation, and a human approves it before any child reads it. The catalog spans 18 offered cells
(age band x length x style). Age bands run 3-5 through 16+. The programme's stated goal is **high
quality CYO books at a cost the product can carry**.

The subject of the analysis is
[cyo-generation-research-brief-2026-08-22.md](./cyo-generation-research-brief-2026-08-22.md), the
brief that describes the framework (principles F1-F8), the pipeline, and the evidence behind both.

---

## 2. Read these, in this order

| # | Document | What it gives you |
| --- | --- | --- |
| 1 | [cyo-brief-gap-analysis-2026-08-22.md](./cyo-brief-gap-analysis-2026-08-22.md) | The findings that survived validation, plus a **correction log** of what was retracted |
| 2 | [cyo-brief-gap-remediation-plan-2026-08-22.md](./cyo-brief-gap-remediation-plan-2026-08-22.md) | One plan per item: problem, change, files, tests, blast radius, rollback, acceptance, falsifier, and the **local-vs-OpenRouter cost classification** |
| 3 | [cyo-brief-review-reconciliation-2026-08-22.md](./cyo-brief-review-reconciliation-2026-08-22.md) | Reconciles this analysis against a **parallel 13-agent review** and against a **live experimental round** that supersedes parts of both. Also carries the PR 715-737 sweep and the eight owner rulings |
| 4 | [evidence/brief-gap-analysis-2026-08-22/](./evidence/brief-gap-analysis-2026-08-22/README.md) | 24 raw reports (16,688 lines) plus the PR sweep. Reference material, not required reading |

Two other reviews exist on other branches and are summarized in document 3, so you do not need to
read them: the parallel review on `claude/stoic-maxwell-60szsf`, and the live structural round in
PR #737 on `claude/cyo-live-story-generation-kxm0ya`.

---

## 3. How much to trust what you are reading

**This matters more than any individual finding.**

The first analysis round was run under an instruction to find gaps. A red-team pass measured the
result: **63% criticality inflation** (10 of 16 sampled critical/high findings survived only at
lower severity) and **40% of findings framed as absences**, of which at least 24 restated an existing
register row, owner ruling, or in-code self-label.

A second round of twelve adversarial validators then tried to refute every load-bearing finding.
**It overturned more than it confirmed.** Seven headline claims were retracted outright, including
all three of the original top recommendations.

Practical rules for you:

- **Trust documents 1, 2 and 3.** They are post-validation and carry the corrections.
- **Do not trust `round1-findings/` on its own.** Always read a round-1 finding against its round-2
  validator. The evidence README repeats this warning.
- **Where documents disagree, the live round (document 3, section 1) wins.** It is empirical and
  postdates everything else.

---

## 4. Non-negotiable repo conventions

From `CLAUDE.md`. A plan that ignores these will not merge.

- **Never work on `main`.** Branch as `{type}/{slug}`, conventional-commit types.
- **Sign every commit** (`git commit -S`). Conventional Commits for messages and PR titles.
- **No em-dash characters** anywhere, including docs and commit messages.
- **Tag assumptions** with `#CRITICAL` / `#ASSUME` / `#EDGE` paired with `#VERIFY`, mandatory for
  timing, external resources, data integrity, concurrency, security, and payment.
- **Quality gates**: Ruff, BasedPyright strict, Bandit, 80% coverage. `pre-commit run --all-files`.
- **Authoring lessons are mandatory.** Any authoring or validator run appends to
  `authoring-lessons-log.md`, validated by `scripts/check_lessons_log.py`. An open lesson must also
  be cited by a `UW-C*` row, enforced by `scripts/check_work_linkage.py`.

### The ID trap you will hit

`check_lessons_log.py` requires **consecutive ids from AL-001 with no gaps**. Multiple branches are
in flight, each appending. This has already caused real damage:

- PR #719's merge **renumbered 322 published lesson and register ids across 35 files**, and that PR
  states no existing check would catch a bad resolution.
- Commit `6fc2b34` renumbered colliding register rows when main merged into the sourcing branch.
- Commit `bf7cad1` cites `AL-296`/`AL-297` for content that now lives at `AL-309`.

**Consequence for your plan**: do not append lesson or register rows on a long-lived branch. Draft
them, and allocate them at merge time from the merged head. That allocation has now happened: the
rows are listed in document 2 under "Ledger rows, as allocated" and land on
`docs/consolidate-landing-ledger`, which is the single allocation point for the parallel landings.
`W9` exists to fix the underlying hazard.

---

## 5. State of play

### Already decided by the owner (PR #737, eight rulings). Do not re-litigate.

*Count note, 2026-08-30: nine entries follow but the ruling count is eight, and both are right.*
*Entry 5 is not a separate ruling: it is the ADR-011 amendment that ruling 9.1 (entry 4)*
*commissioned. Entries 1-4 are rulings 8.1-8.3 and 9.1; entries 6-9 are rulings 9.2-9.5. The*
*merged commit `41d30909` is titled "eight owner rulings", and section 8.3 of the*
*[reconciliation](./cyo-brief-review-reconciliation-2026-08-22.md) carries the same split. The*
*entries are left numbered 1-9 so the cross-references into them stay valid.*

1. The diversity bar is **any-reader, not social distance**. Interim serving rule: same-skeleton
   books must not reach the same reader.
2. Machine-critical fields are **normalized post-fill** rather than trusted to model obedience.
3. `ending.title` and story titles are **writable leaf content**, not frozen.
4. The ADR-011 decisions-per-path window ruling was **deferred** pending an audit.
5. **ADR-011 amended**: per-cell derived decision windows, a **gamebook exemption**, recalibrated
   endings ceilings.
6. Bulk vendor direction: **reject sonnet-for-everything on cost**; invest in cheap models reaching
   quality by engineering; widen the bake-off to grok and gemini.
7. The fill-rate floor is a **non-blocking `needs_review` forcer**, never a hard block, until
   per-vendor and per-band calibration exists.
8. Add a `metadata.narrative_person` field rather than inferring narrative person.
9. Cap identical zero-content `content_filter` retries at **two**; the production direction is
   re-pairing, not blind retry.

### Already fixed by merged work. Do not plan these.

- **Fill feasibility** (#727): `is_fill_feasible` is wired as a selection filter
  (`skeleton_match.py:193`), the cap is 131,072 tokens, `UW-C07` is `done`, all 59 production
  skeletons are feasible, and the previously-dead 13-16 and 16+ bands generate again.
- **Strict catalog cover** (#730): 20 strict-passing shells now span all 18 offered cells.
- **Syllable counting** (#719): rebuilt against CMUdict ground truth, closing a real Goodharting
  root cause (`AL-389`).

### Settled empirically. Treat as fact.

- **Shared-structure convergence is intrinsic.** The differentiation directive, the only shipped
  defence, moved shared 4-grams from **96.3 to 110.7 per 1000** against a budget of 4.0. It makes
  convergence worse. Hand-authored same-skeleton twins score 202.0.
- **The fill-rate hole is substantially vendor-shaped.** sonnet-5 clears the 0.6 floor and the band
  target on exactly the pairs v4-pro fails, at roughly **7x unit cost**.
- **Catalog census: 74 auto-pickable shells** across 18 cells, all populated (pools 3-5, median 4).
  149 files = 84 graphs + 65 sidecars.
- **The largest book commissions 42,233 words** (677 nodes); catalog maximum is 49,953. The brief's
  "~118,000-word" figure is wrong.

---

## 6. The work inventory

Full per-item plans in document 2. `$` is OpenRouter spend; nine of the fourteen items need none.
*Corrected 2026-08-30: read "nine of twelve". The table has fourteen rows, nine of them at $0*
*(`GA-D1`, `W1`, `W3`, `W5`, `W6`, `W7`, `W8`, `W9`, `X2`). The nine is right, the twelve was a*
*miscount of the denominator.*

| ID | Item | Type | Spend | Depends on |
| --- | --- | --- | --- | --- |
| **GA-D1** | ~~Rule on the hard-block publish override. A book carrying a moderation hard block publishes in two clicks; `publishing/service.py:412` guards only `moderation_report is None`. Deliberate design, but untraced, unversioned, and self-approvable by a dual-role adult~~ *Materially corrected 2026-08-30: only the separation-of-duties half survives. See the GA-D1 note below this table.* | **Owner decision** + code | $0 | Production query (see 7) |
| **GA-D2** | Decide what F5 claims, and find a cross-family reuse lever. The shared "structural" stratum is byte-identical across the flagship pair and enumerates a closed decision menu. **Rulings 1 and 6 excluded both previously proposed levers, so no candidate survives** | **Owner decision** + research | $10-25 | W3 |
| **W1** | Job lifecycle: `queued->running` uncommitted, `rq_job_id` omitted, causing double enqueue and double spend. The only live money leak | Code | $0 | none; **blocks W2** |
| **W2** | Cap the reading-level loop. Measured at **38%, 51%, 59%** of a book's bill for an `in_band` result of 0.155 | Code + validation | $3-5 | W1 |
| **W3** | Land `UW-C225`: `check_sibling_fills.py` grams a joined string, so the gate scope and the published calibration disagree | Code | $0 | none; **blocks D2, W10** |
| **W4** | Classify content-filter failures as terminal. `AL-492` records a live incident retried **7 of 7**. Ruling 9 sets the interim cap; the classification work remains | Code | <$0.10 | none |
| **W5** | Give `run_guard_battery.py` a runner. It is the gate registry and is invoked by nothing but its own test. Fix the two false-failure causes first (`--allow-title-rewrite`, a `{PLACEHOLDER}` blind spot) that would fail 28 of 31 books for non-reasons | Code | $0 | none; **blocks W6, W7** |
| **W6** | Split the walk floor by form and enforce it for prose CYO. **Five shells give a random-walking reader exactly zero probability of a satisfying ending**; 11 breach. Ruling 5 supplies the gamebook exemption | Code | $0 | W5 |
| **W7** | Wire the two genuinely unwired detectors: `validator/imitable.py` (imitable-action harm, zero callers) and `validator/blind_spots.py` (built to make gate silence legible, itself silent). Advisory first, then set thresholds from measurement | Code | $0 | W5 |
| **W8** | Recalibrate CG-1/2/3 against a non-circular anchor. **97% of strict findings are CG-1/2/3**, calibrated to an internal table while everything else is calibrated to the JHM corpus. Run `check_skeleton.py` over the 40 JHM digraphs and set a two-sided policy | Code | $0 | **blocks all `--strict` work** |
| **W9** | Harden the register and lessons machinery: six demonstrated integrity holes, plus a new one (a row whose body contradicts its own status, `UW-C07`) | Code | $0 | none |
| **W10** | Settle model selection. Only "checker in the author's loop" and "not v4-pro for structure" survive scrutiny. 3 legs x 12 replicates x 2 counterbalanced cells, uncensorable primary endpoint, instrumented loop | Research | $5-15 | W3 |
| **X1** | Confirm cross-vendor structural convergence: 7 of 342 shell-shell pairs breach TAU_CELL, **all cross-vendor**, while 0 of 190 shell-catalog pairs do. Three labs independently emitted 45 nodes, 91 choices, branching exactly 3.000 | Research | $3-6 | W3 |
| **X2** | Compose ADR-023 personalization and ADR-028 persistent characters with the framework. Persistent per-child casts push toward sameness exactly where S-4 measures distinctness | Design | $0 | D2 |

> **GA-D1, corrected 2026-08-30.** The struck text was already stale when this handoff was
> written, and the correction is recorded rather than swapped in silently, because the point of this
> file is what the 2026-08-22 analysis concluded.
>
> What is now false: the guard is not one condition. `publishing/service.py::
> _assert_report_permits_approval` runs four gates in order, refusing an approval when the report is
> absent (`approve_without_moderation`), unusable (`approve_with_unusable_moderation`), or admits
> nodes the reviewer never saw (`approve_with_incomplete_coverage`), and finally, under ADR-005's
> **2026-08-25 amendment (gate D2)**, refusing to publish over a block or high-severity finding
> without a non-whitespace `override_reason` (`approve_requires_override_reason`). The override is
> also audited: the RELEASED pipeline event carries `overridden_block_count` and
> `overridden_high_count`, and the free-text reason is logged (it is kept off the durable event row
> by the PII-free payload allowlist, spec D3). So "two clicks", "untraced", and "unversioned" are all
> retired: the override is versioned in ADR-005, gated on a reason, and structurally audited. The
> `service.py:412` line reference has drifted with the file and should not be re-cited.
>
> What still stands: **there is no separation of duties on approval.** An adult holding both the
> guardian base role and `is_admin` can approve their own family's book, including over a hard block,
> because `api/approval.py::_load_admin_story` deliberately does not call `authorize_family` (admin
> authority is cross-family by design). ADR-005 names this the owner-as-admin exception, and the
> audit stamp does distinguish the two cases: `Principal.acting_role()` returns the guardian base
> role for an own-family review and `admin` only for a genuine cross-family one. But nothing requires
> a second reviewer. Four-eyes approval is not an existing invariant, and whether to make it one
> remains the owner decision this row is asking for. State the item that way; do not restate the
> retracted framing.

**Totals**: immediate remediation $0; all open experiments **$21 to $51.10**. For scale, the live
round that produced the decision-grade directive result cost **$3.28 metered**. Spend is not the
constraint.

*Corrected 2026-08-30: read "$27-55". This was wrong when written, not overtaken, so it is fixed in
place. The five nonzero rows are `GA-D2` $10-25, `W2` $3-5, `W4` <$0.10, `W10` $5-15, and `X1` $3-6,
which sum to $21 at the low end and $51.10 at the high end. Neither the conclusion (spend is not the
constraint) nor any per-item figure changes.*

### Explicitly do not do

Each was proposed and refuted. Document 2 carries the reasoning.

- Enforce `--strict` as-is: it collapses selection from **74 shells to 20** and deletes the
  `open_map` and `time_cave` topologies. Do `W8` first.
- Gate `validator/consequence.py`: **`UW-C181` is an owner ruling rejecting it**, and it returns
  `None` for 48 of 84 books.
- Add a novelty term to the pass criterion.
- Build path-level evaluation before the instrument question is settled.
- Reconstruct D-7b selections for solution transfer: the reconstructor sets the answer.
- Guardian-primary approval as the economics fix: ADR-005's 2026-06-30 amendment moved the approver
  **to** admin, re-ratified 2026-07-16.

---

## 7. Blockers and prerequisites

- **`GA-D1` needs a production query first.** Query for published versions with
  `summary.hard_block: true`. **Nonzero means this is a live incident, not a latent design gap**,
  and the plan changes to incident response. This could not be run during the analysis: the
  `supabase` MCP server was unauthenticated. Authorise it via claude.ai connector settings, or
  `claude mcp` / `/mcp` in an interactive session.
  *Corrected 2026-08-30: read the result against ADR-005's 2026-08-25 amendment (gate D2). Any hit
  approved on or after that date carried a recorded `override_reason` and audited
  `overridden_block_count` on its RELEASED event, so it is a deliberate, attributable override
  rather than a silent one. Only a hit predating the amendment, or one with no override counts on
  its event, is the silent-publish case this bullet was written to detect. The question the query
  actually settles now is how often the override is exercised, and by whom relative to the book's
  own family.*
- **~~Two high-impact PRs are still open~~: #729 (retire Ollama, Modal becomes cascade leg 3) and
  #737 (the eight rulings).** *Corrected 2026-08-30: both merged. #729 landed as `167c29da` and #737
  as `41d30909`, and #737 carried eight rulings, not nine. This blocker is discharged; the code and
  the rulings are both on `main`.* Note that a later commit, `3ad864a3` (#747, 2026-08-24), went
  further than #729 and set the production fill model to `deepseek/deepseek-v4-pro`, so any plan
  built on the model assumptions in this handoff needs re-deriving.
- **`W8` gates all `--strict` work.** Any plan that enforces the strict bar before recalibration will
  take the catalog down.

---

## 8. Open questions to resolve before you plan

1. **`GA-D2` has no candidate lever.** Both proposed ones are excluded by ruling. Is the answer a
   per-family reuse cap (serving-side, cheap), a new structural mechanism (research, $10-25), or
   accepting intrinsic convergence and competing on something else? This is the largest open
   question in the programme.
2. **What is the cost target?** No cost-per-book number exists anywhere, and no runtime spend cap
   exists (the only `_MAX_COST_USD` is a $999,999.99 overflow clamp). Reconstructed all-in is
   **$1.51 / $5.70 / $24.52** low/central/high, and the entire spread is one unmeasured quantity:
   actual human review minutes.
3. **How much review time does a book actually take?** Nothing measures it. Estimates span 1.9 to
   8.2 hours depending on whether you assume delivered or commissioned words. Until this is
   instrumented the unit economics cannot close, and it is the single highest-leverage measurement
   available.
4. **Does the reading-level cap in `W2` cost band conformance?** Ship the measurement with the cap.

---

## 9. What nobody has examined

Both reviews concentrated on generation. **Never opened**: the frontend (436 files), the player and
offline path, series continuity, personalization, the cover-art pipeline, onboarding and request
intake, and what a family experiences when generation fails. One review declared "the reader is
absent" from the framework while `reader-path-engagement-design.md` and
`check_prose_craft.py --max-moral-tags` both exist.

Treat this as scope for a later pass, and as a caution: the analysis you are working from is
generation-shaped.

## Related

- [Gap analysis](./cyo-brief-gap-analysis-2026-08-22.md)
- [Remediation plan](./cyo-brief-gap-remediation-plan-2026-08-22.md)
- [Reconciliation](./cyo-brief-review-reconciliation-2026-08-22.md)
- [Evidence](./evidence/brief-gap-analysis-2026-08-22/README.md)
- [Research brief under analysis](./cyo-generation-research-brief-2026-08-22.md)
- [Unscheduled work register](./unscheduled-work-register.md),
  [authoring lessons log](./authoring-lessons-log.md)
