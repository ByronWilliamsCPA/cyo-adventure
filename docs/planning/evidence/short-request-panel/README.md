# Short-request panel: baseline design (WP-0.2)

> **Status.** Design only, fixed before any generation. Nothing here has been run, no provider has been called,
> and no money has been spent. Source: WP-0.2 of the
> [Story Plan implementation plan](../../story-plan-implementation-plan.md) and section A.4.5 of the
> [architecture review addendum](../../architecture-review-2026-11-20.md). Decision record:
> [ADR-033](../../adr/adr-033-story-plan-meaning-layer.md). Register row: `UW-G36`.

## Purpose

Make the pre-change behaviour of the short-request path reproducible, so the baseline arms can be run at any later
time (WP-4.1) and compared against plan-first (WP-4.2) under the pre-registered kill criterion.

## The panel

[`panel.json`](./panel.json) holds 20 requests. Each has a hand-written list of three to five elements, written from
the request text alone before any generation. **The lists are frozen: do not edit them after the first job runs.**

| Source | Count | Where it comes from |
| --- | ---: | --- |
| `premise_panel` | 16 | `PREMISE_PANEL` in `scripts/measure_theme_coverage.py:53-70`, verbatim and in order (checked by script when this file was written) |
| `dragon_line` | 1 | "a story about a dragon who is afraid of the dark", the worked example of the addendum |
| `guardian_brief` | 3 | Two-sentence guardian briefs written for this panel (G01 to G03), each within the 500-character request limit |

Bands: 8-11 and 10-13, each request at both, so **40 jobs per arm**. Length is fixed at short for every job so
commissioned words are comparable.

## Arms

| Arm | Path | Run in |
| --- | --- | --- |
| (a) | Current skeleton fill (`skeleton_fill`) | WP-4.1, from the baseline tag |
| (b) | Current fresh generation (`fresh_generation`) | WP-4.1, from the baseline tag |
| (c) | Plan-first (`plan_fill`) | WP-4.2, after the plan layer exists |

## Measures

Taken from the review (A.4.5) and WP-3.3; nothing is added.

- **Delivery.** A book came out (yes or no); words delivered as a share of words commissioned.
- **Request fidelity.** For each request a blind adult reader, on one sampled path, marks each frozen element
  present or absent, then answers "is this the story that was asked for" from 1 to 5. The rating sheet is assembled
  by `scripts/measure_request_fidelity.py` (WP-3.3); a person rates.
- **Agency and continuity.** Hand counts, and the continuity reader of WP-3.2 (arm c).
- **Cost and wall-clock** per book, and the model serving each call (record the served model, not the configured one).
- **Approver minutes.**

## Kill criterion (pre-registered, unchanged from WP-4.2)

Plan-first replaces skeleton fill for on-demand requests only if **all** hold:

1. delivery rate is not lower than arm (a);
2. request fidelity is higher on at least two thirds of requests;
3. blind paired preference for plan-first is at least two thirds of pairs;
4. cost is no more than three times arm (a).

If fidelity rises and delivery falls, use plan-first for catalog books only. If neither fidelity nor preference
moves, the plan layer does not help thin prompts; stop and report (the next lever is the pitch step or the model).

## Reproducing the baseline

1. **Code.** Run arms (a) and (b) from the commit recorded in [Baseline commit](#baseline-commit), using a worktree
   at that commit so `cyo_adventure` and the prompt templates resolve to that code.
2. **Harness.** Reuse
   [`run_fill.py`](../structural-verification-2026-11-20/run_fill.py) as the model: it builds the production
   OpenRouter cascade with `build_provider`, calls the production `fill_skeleton`, and records every call (rendered
   prompts, raw reply, serving provider and model, tokens, wall clock) plus `estimate_run_cost`. Its three declared
   deviations (Stage 1 gate skipped, default binding held fixed, optional forced chunking) suit a prompt A/B but
   **not** this panel: for the baseline the binding should come from the production binder and Stage 1 should run as
   in `generation/worker.py::_run_skeleton_fill`, so the arm reflects what a family would get. Arm (b) needs a thin
   driver around the fresh-generation path (`generation/worker.py`, `generation/prompts.py`); it does not exist yet
   and is part of WP-4.1.
3. **Brief.** Build each job's brief the way `story_requests/brief.py::brief_from_request` does (raw request text as
   the premise, `"Explorer"` protagonist, `tier=1`, fixed pattern), because that defaulting is what is being
   measured.
4. **Fixed inputs.** Production cascade, production defaults, one run per job, no retries beyond the production
   ones. Pin the model pins that are in force on the day and record them.
5. **Order.** Run all jobs in a fixed order (panel order, band 8-11 then 10-13) and store runs under
   `runs/<arm>/<request-id>-<band>/`.

## Estimated cost of running it later

| Item | Estimate | Basis |
| --- | --- | --- |
| Arm (a), 40 jobs | 12 to 30 USD | 0.30 to 0.76 USD per fill measured on 2026-11-20 ([evidence](../structural-verification-2026-11-20/README.md)) |
| Arm (b), 40 jobs | 12 to 30 USD, less certain | No measured fresh-generation rate at these bands; assumed comparable per book |
| Arms (a) and (b) together (WP-4.1) | 30 to 60 USD | Implementation plan WP-4.1; the review gives roughly 15 to 30 USD per arm |
| Arm (c) (WP-4.2) | 20 to 60 USD | Implementation plan WP-4.2, to be narrowed by WP-2.6 |
| Blind rating labour | not priced | WP-3.3; person time, not provider spend |

The Phase 4 cap proposed for D7 is 150 USD, hard stop. This package spends nothing.

## Baseline commit

The WP calls for a git tag `baseline/pre-story-plan` on the `main` merge of the branch that adds this file. Tagging is
not done in this change. The pre-change code is the repository code at the parent of the first Story Plan code
change; this change touches only documents, so the merge commit of this change carries exactly the pre-change code
paths. The exact commit to tag is recorded in the pull request that merges this change, and must be recorded here
(replace this paragraph) when the tag is created.

- Pre-change code, as reviewed: `87dc0885e63aeeb8e1639422d68afaa3f40f6134` (the base of this change; no source file
  differs between it and the merge of this change).
- Tag to create after merge: `baseline/pre-story-plan` at the merge commit of this change on `main`.

## Review status

Reviewed by a second agent on 2026-11-21 (WP-0.2 acceptance item: lists reviewed by the owner or a second agent).
The review checked each list for faithfulness to the request, coverage of what is central, markability by a blind
adult on one path, independence between elements, and fit with a safe 8-11 or 10-13 story. No request text was
changed; the 16 `premise_panel` texts match `PREMISE_PANEL` verbatim. The per-request changes are recorded in
`review.changes` in [`panel.json`](./panel.json). In summary:

- **Every list was rewritten into observable form.** Bare nouns ("a dog", "afraid", "a case") now say what a reader
  would see on the page; judgment endings ("some change by the end", "the wish is honoured") now name a stated or
  shown outcome on the path read.
- **Duplicates removed.** P07 ("a cake" and "baking") merged; P09 ("a journey" and "arrival or return") split into
  the flight shown and the end state; P14 ("bravery" and "some change") separated into an action and a feeling.
- **Coverage added.** P02 and D01 now require the fear to be shown and to change, with the fire or the dark on the
  page; P07 now requires the cake to be for her; G01 and G02 state whose nervousness and what "together" means.
- **Safety.** No element needs anything unsafe in either band.

The owner has not reviewed the lists. Items for the owner to decide, none of which blocks freezing the lists:

1. **G01 and the school.** The brief mentions the daughter's worry about a new school, but the requested story is the
   cat's. The list does not require a school scene; add one if the guardian's context should be mirrored.
2. **G02 and the baby.** A baby cannot literally work; "together" is defined as the same task, the baby carried or
   nearby counting. Tighten this if a stricter reading is wanted.
3. **P01 to P16 are the children's own words**, so "main character" is read as the child or a stand-in. The panel
   does not require the child to be named in the book.
4. Creating the `baseline/pre-story-plan` tag remains open.
