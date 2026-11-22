# Validation set and split for the continuity reader and the plan reviewer (WP-3.1)

`validation-set.json` is the one labelled set, and the one split by book, that both model stages are measured on: the
continuity reader (WP-3.2, thresholds D6) and the plan reviewer (WP-3.7, thresholds D12). A prompt may be tuned on the
`tuning` half only; each stage reports its thresholds on the `held_out` half. Because the split is shared, neither stage
is tuned on the other's held-out books. See `docs/planning/story-plan-implementation-plan.md`, WP-3.1, WP-3.2, WP-3.7
and the D6 and D12 rows.

The file is generated, not hand-edited:

```bash
uv run python scripts/build_validation_set.py            # regenerate the JSON from the sources
uv run python scripts/build_validation_set.py --check    # fail if the JSON is not what the sources build
uv run python scripts/build_validation_set.py --summary  # print the per-half counts and the split
uv run pytest tests/unit/test_validation_set.py          # invariants, plus a byte-for-byte rebuild
```

The builder reads only committed files, calls no model and uses no network. Every reader item names an exact book
revision whose sha256 is pinned in the builder (`BOOKS`), and every node id an item names is checked to exist in that
revision. Findings that the sources record as prose are transcribed in the builder as `FINDINGS` rows (and the
2026-11-22 minor residuals as `RESIDUAL_MINORS` rows); each row must name an id that appears as an entry in its source
file, and node ids that appear in that file. A changed source, a moved book or a mistyped node makes the build fail
rather than drift. The split is frozen the same way: a build whose split search would move a book fails (see
[The split](#the-split)). In a shallow clone the pinned pre-fix revisions
are absent, so the unit test skips the rebuild and still checks the structural invariants and the working-tree hashes.

The synthetic seeded-defect plans that D12 permits are **not** in this file and must never be added to it: WP-3.7 puts
them in a sibling file (proposed name `validation-set.synthetic.json`) and reports them separately. See
[Shortfall and the seeding proposal](#shortfall-against-d12-and-d6-and-the-seeding-proposal).

## Thresholds, fixed before any prompt is written

Decided by the owner on 2026-11-21, in session, before WP-3.2 or WP-3.7 wrote a prompt. Quoted from the plan; the same
values are in the JSON under `thresholds`.

**D6, continuity reader, on the held-out half:** "recall at least 0.8 on known defects, no more than one false flag per
50 nodes on clean books, two-run agreement at least 0.9, on the held-out half".

**D12, plan reviewer, on the held-out half** (every value adopted as proposed):

| Item | Decided value |
| --- | --- |
| Defect recall | reject or `unsure` on at least 90 percent of labelled defective plans, and on every blocker-severity entry |
| Flag rate on clean plans | reject or `unsure` on at most 20 percent |
| Run agreement | identical verdicts on at least 90 percent of plans across two runs |
| Minimum validation size | at least 15 defective and 15 clean held-out plans, supplemented with seeded-defect plans reported as synthetic; if the minimum cannot be met the reviewer is not validated. **Amended 2026-11-21** (`AL-853`): the clean held-out minimum is met by a fresh blind extraction plus a second independent blind extraction of each of the five held-out post-fix books, results reported per book (the effective clean sample is five books); synthetic defective plans seed checker-visible and checker-invisible defects, each reported separately |
| Sample rate | 1 in 10 in steady state; 100 percent through the pilot (WP-4.2, WP-4.3) |
| Suspension | the owner overturns any blocker-class pass, or more than 1 in 5 of the last 10 sampled passes (at least 5 sampled) |
| Scope of authority | per defect class: only classes with measured recall; others advisory |

## Format

Top level: `schema` (`validation-set/v1`), `work_package`, `generator`, `readme`, `thresholds`, `split` (seed, method,
forced units with reasons, and every unit's half, band and coin flip), `summary` (the per-half counts below) and
`items`.

### Item fields

| Field | Meaning |
| --- | --- |
| `id` | Stable id. Answer-key entries keep their `KD-*` id; findings are `<prefix>-<source id>` (`SS` Sky-Ship, `LH` Hollow Lighthouse, `MM` Midnight Museum, `SG` Signal in the Static, `CE` Cave of Echoes, `VO` Vanishing Orchard, `MI` Mapmaker's Island, `TT` Thornwood Trial, `CM` Clockwork Menagerie, `CC` Clocktower Cipher); the 2026-11-21 residuals are `R1121-<report id>` (for example `R1121-SG-2`), since the report's ids reuse the book prefixes; `PJ-*` payoff judgments, `MC-*` merge counts, `CB-*` clean books, `PL-*` plans |
| `kind` | `node_assertion`, `payoff_judgment`, `merge_count`, `clean_book` (reader items) or `plan` (reviewer items); see the next table |
| `half` | `tuning` or `held_out`, always equal to `split.units[book.unit].half` |
| `book` | `unit` (the split key: the book's slug, or the skeleton slug for model fills of that skeleton), `key` (the pinned revision, `<slug>@<commit>` or a run label), `file`, `revision` (`git:<commit>` or `working-tree`) and `sha256`. Smoke plans have no book, only `unit` and `shape_hash` |
| `node`, `other_nodes` | The node the finding is anchored on, and the other nodes the source names. Either may be a choice id; those are also listed in `choice_ids` |
| `expected_verdict` | Reader items: `defect` or `clean`; `count` for merge counts. Plans: `reject` (the reviewer must answer reject or `unsure`), `pass`, or `unknown` (not scored) |
| `defect_class` | A string on reader items (vocabulary below), `merge_seam` on merge counts, `null` on clean items. On plans, the sorted list of classes the plan's book carries |
| `class_source` | `source` when the findings file states the class; `builder` when this builder assigned it from the finding's text (the WP-0.4 files mostly give no class) |
| `severity` | `blocker`, `should-fix`, `minor`, `unrated`, or the answer key's `leak`, `thin`, `unearned`. On plans, the highest severity the book carries |
| `severity_source` | How the source states severity, and any mapping applied |
| `source` | `doc` (the file) and `anchor` (the id or section in it) |
| `scored_for` | `D6` (continuity recall and false flags), `D6-payoff` and `D6-merge` (reported beside D6, not in its recall figure), `D12`, or `observe-only` |
| `label_strength` | `strong`; `weak` (no known defect but never given a full continuity read); `count-agreement` (Clockwork merge counts, where hand and detector counts agree); `unlabelled` |
| Kind-specific extras | `merge_count`: `merge_nodes`, `hand_seams`, `detector_seams`. `clean_book`: `node_count`, `fixed_nodes` (nodes that carried a defect before the fix, the strongest negatives: for Lighthouse and Orchard the anchor node of each pre-fix finding, for the five books fixed on 2026-11-22 every node a 2026-11-21 residual names), `known_residuals` (see [Known residuals](#known-residuals-the-minor-residual-rule)). `plan`: `plan` (`file`, `sha256`, `pointer` into the file, and `revision` for pinned `out/` plans), `producer`, `defects` (id, class, severity of every defect the book revision carries), `blocker_entries`, `known_residuals` (the book revision's, on blind and hand-written plans), `note` |

### Kinds

| Kind | One item is | Scored how |
| --- | --- | --- |
| `node_assertion` | One known defect at a node in an exact revision: a pre-fix revision, or for the 2026-11-21 residuals a WP-0.4 post-fix revision | D6 recall: did the reader flag the node (or a listed other node) |
| `payoff_judgment` | One payoff site of a planted variable; `clean` when a child would see the link to the plant, `defect` for the four public-plant entries | Reported beside D6 |
| `merge_count` | One Run A fill: its merge nodes and the hand count of openings that say the route did not matter | By count: nodes flagged against `hand_seams` (per-node hand labels were never recorded) |
| `clean_book` | One book revision with no open blocker or should-fix finding (Lighthouse and Orchard post-fix; the five held-out books as fixed on 2026-11-22) | D6 false flags per 50 nodes, a flag on a known residual excepted; `weak` books reported apart |
| `plan` | One Story Plan, labelled by the defects its book carries | D12 |

Defect classes: the answer key's seven (`unestablished_fact_on_route`, `state_contradiction`, `repeated_reveal`,
`two_backstories`, `plant_leak_unplanted_route`, `cross_payoff_reference`, `public_plant`) plus the WP-1.6 second reads'
`label_outcome_mismatch`, `timeline`, `location_or_physical_state` and `other`, and `merge_seam` for merge counts.

## Sources and what each contributes

| Source | Items | Notes |
| --- | --- | --- |
| WP-1.3 answer key, `../story-plan-retro/known-defects.json` | 13 `node_assertion`, 4 `payoff_judgment` | Read directly, not transcribed. The four `public_plant` entries are payoff judgments |
| 2026-11-20 plant-payoff judgments (`../structural-verification-2026-11-20/playthroughs/`) | 18 `payoff_judgment` (`clean`) | The plan's 22 judgments are these 18 plus the 4 public-plant entries above (the builder checks the 22 sites partition exactly). One clean pair carries a prop mismatch, noted on the item |
| 2026-11-20 hand-read merge openings | 7 `merge_count` items covering **147** openings (21 merges times 7 fills of `the-last-train-north`) | The count matches the plan's 147. The hand read recorded seams per fill, not per node, so these score by count. Added: 6 Clockwork fills (72 openings) whose hand and detector counts agree. The 470 Run B openings with no seam are not included (a hand scan of candidate openings only) |
| WP-0.4 findings, seven family-test books (`../story-plan-retro/findings-*.md`) | 165 `node_assertion` on the pre-fix revisions | Lighthouse B1 to S4 are the `KD-LH-*` entries and are not repeated; its M- and N-ids are added |
| WP-1.6 second reads (`../fresh-corpus-2026-11-21/second-read-*.md`) | 101 `node_assertion` | Classes and severities are the readers' own |
| Residual check of the five held-out post-fix books, [`residuals-2026-11-21.md`](./residuals-2026-11-21.md) | 20 `node_assertion` on the WP-0.4 post-fix revisions (1 blocker, 8 should-fix, 11 minor) | Every "real" verdict, with the report's own class and severity. Its nine "not a defect" verdicts are left out (below) |
| Lighthouse and Orchard post-fix books (pinned by commit) | 2 `clean_book`, plus `B-lkl-new-1` as `weak` | Still clean under WP-0.4; unchanged by the residual checks |
| The five held-out books fixed on 2026-11-22 (`out/<slug>.filled.json` at the fix commits; records [`fixes-2026-11-22-<slug>.md`](./fixes-2026-11-22-the-signal-in-the-static.md)) | 5 `clean_book` | `fixed_nodes` are the 2026-11-21 residuals' nodes |
| Residual check of the fixed books, [`residuals-2026-11-22.md`](./residuals-2026-11-22.md) | no items: 9 minor `known_residuals` on the fixed books and their plans | All five clean (no blocker, no should-fix). SG-7, SG-8, MM-5, MI-12 to MI-17, verified like `FINDINGS` rows |
| Blind plans x1 to x9 and x5b (WP-1.4), y1 to y5 (G1 re-run), z1 to z3 (WP-1.6) | 18 `plan` | Each manifest's `book_sha256` is checked against the plan's provenance and maps it to a pinned book; labelled with every defect item of that book. `x3` (`B-lkl-new-1`) is a weak `pass` |
| Blind clean-plan passes c1 to c5 and d1 to d5 ([`clean-plans/`](./clean-plans/manifest.json), prompt v2) | 10 `plan` (`reject`) | Two independent passes of each WP-0.4 post-fix revision; `reject` because those revisions now carry the 2026-11-21 residuals |
| Blind clean-plan passes e1 to e5 and f1 to f5 ([`clean-plans-fixed/`](./clean-plans-fixed/manifest.json), prompt v2) | 10 `plan` (`pass`, strong) | Two independent passes of each fixed revision; `known_residuals` carry that book's minors |
| Hand-written post-fix plans `out/<slug>.plan.json` | 7 `plan`: 2 `pass` (Lighthouse, Orchard), 5 `reject` (the held-out five) | Pinned by commit; provenance must name the post-fix book's sha256, so the five held-out ones bind the defective post-fix revisions |
| WP-2.3 smoke runs, `../plan-generation-smoke-2026-11-21/runs/*.json` | 6 `plan` (`unknown`) | Generated plans (`pointer` `/plan`). **Unlabelled and not scored**: use them for flag-rate observation only. Split by their shape slug |

Left out on purpose, by the sources' own judgement: every "checked, not defects", "left alone" and "read but not fixed"
entry; agency problems in the control books; Lighthouse M6 (two sentences opening "Mira", style), M8 and N6 (verified
not defects), its typo fixes and its three child-safety flags C1 to C3 (not continuity). From the residual checks: the
nine 2026-11-21 "not a defect" verdicts (SS-4, SG-3, MI-3, MI-4, MI-6, CE-3, MM-1, MM-2, MM-3), the gated-label SP-A
findings both reports list, and every 2026-11-22 group marked artifact, not a defect or already adjudicated. The set has
no item kind for a verified clean judgement at a node (`node_assertion` is defect-only), so these are not recorded as
items; the reports themselves call them false-flag bait, and a reviewer that flags one on a clean book is producing a
genuine false flag.

## Known residuals: the minor-residual rule

A clean book revision can carry verified defects that were recorded rather than fixed. They sit in the `known_residuals`
of that revision's `clean_book` item and of every plan bound to it, never as reader defect items, so they neither enter
D6 recall nor turn a plan into `reject`. Each entry has `nodes`, `choice` (a choice id or `null`), `defect_class`,
`source` and `note`; the 2026-11-22 entries also carry the report's `id` and `severity` (`minor`).

- **Scoring.** A reader flag, or a plan-review reject or `unsure`, that cites a known residual's node or choice is a
  true positive, not a false flag. A flag elsewhere on the book is still a false flag.
- **Orchard** (tuning): the pilot's label and outcome contradiction (`c_b1a_dec_2` into `e_b1a`), on the post-fix book
  and its hand-written plan.
- **The five fixed held-out books**: the 2026-11-22 check found 9 minors, all on text unchanged since 2026-11-21:
  Signal SG-7, SG-8; Museum MM-5; Mapmaker's MI-12 to MI-17; none for Cave of Echoes or Sky-Ship. They sit on the
  `CB-*` items of the fixed revisions and on the e/f plans.
- **Precedence.** A blocker or should-fix is never a known residual: a revision carrying one is defective, its plans
  are `reject`, and its findings are reader items. That is what moved the five WP-0.4 post-fix revisions out of the
  clean side on 2026-11-21, even for Museum, whose only residual (MM-4) is minor: the residual report recommended
  keeping Sky-Ship, Cave and Museum clean with known residuals, but their plans were re-extracted against the fixed
  revisions instead, so every real 2026-11-21 residual is labelled as a defect of the revision it was found in.

## The split

One split, by book: every item of a book (its pre-fix and post-fix revisions, every reader item and every plan of it)
shares one `book.unit` and therefore one half. Model fills of one skeleton share a unit, because they share the graph,
the beats and in Run B the defect sites.

**Forced into tuning** (seen in reviewer-prompt design, `../plan-review-pilot-2026-11-21/README.md`):
`the-hollow-lighthouse` (pre-fix blind plan x1 and the post-fix plan), `the-lantern-keepers-list` (Run B `B-lkl-new-1`
and `B-lkl-new-2`), `the-orchard-signal` (Run B `B-os-new-1`, The October Blossom; `B-os-new-2` is a fill of the same
skeleton with the same public-plant defect at the same node ids, so it goes with it), and `the-vanishing-orchard`
(post-fix plan). The G1 revision of the SP checks was designed with the G1 answer key in view; that weakens the
deterministic checker's G1 pass, not these model stages, which have never seen the key, so it does not move any book.

**Free books** are assigned by exhaustive search over all assignments, maximising in order: (1) the smaller of the
held-out real defective-plan count and clean-plan count; (2) the number of (band, defective or clean) plan cells the
held-out half covers; (3) agreement with a coin flip per book, `sha256("<seed>:<slug>") mod 2`. Seed:
`990054da2cc73d8b2b4c6b5744dc197288c40213`, the full hash of the commit that recorded D6 and D12, fixed before the split
was first computed. Criteria (1) and (2) placed every book with plans except `the-thornwood-trial`, which they leave
indifferent (with it held out the held-out half has 6 defective and 5 clean plans, without it 5 and 5); its coin sends
it to tuning, which also gives tuning a never-fixed fresh-corpus book. `the-last-train-north` (merge counts only) and
`the-locked-carousel` (smoke plans only) went by their coins.

**The split is frozen.** Tuning prompts are written against it, so a book that moved halves would carry what a prompt
was tuned on into the held-out half. The builder records the assignment in `RECORDED_SPLIT`, re-runs the search on every
build, and fails if the search would move any unit; a new split can only come from an owner decision, never as a side
effect of new items. When the 2026-11-21 residuals, the fixed revisions and the 20 c/d/e/f plans were added the search
still reproduced the recorded split: all ten clean held-out plans come from the five held-out fixed books, so moving any
of them lowers criterion (1), and Thornwood, Clockwork and Clocktower stay indifferent and follow their coins as before.

| Unit | Band | Half | What it holds |
| --- | --- | --- | --- |
| `the-hollow-lighthouse` | 10-13 | tuning (forced) | 10 KD + 11 findings; clean book; plans x1, x2, y2, y4, post-fix |
| `the-lantern-keepers-list` | 8-11 | tuning (forced) | 2 KD; 12 clean payoffs; weak clean book; plans x3 (weak pass), x4, y5; smoke 6 |
| `the-orchard-signal` | 10-13 | tuning (forced) | 1 KD leak + 4 public-plant; 6 clean payoffs; plans x5, x5b, x6, y1, y3 |
| `the-vanishing-orchard` | 13-16 | tuning (forced) | 42 findings; clean book; post-fix plan |
| `the-thornwood-trial` | 13-16 | tuning | 25 findings; plan z1 |
| `the-locked-carousel` | 8-11 | tuning | smoke plans 1, 3, 4 |
| `the-sky-ship-stowaway` | 8-11 | held out | 8 findings + 3 residuals; fixed clean book; plans x7, post-fix, c5, d1 (reject), e5, f2 (pass) |
| `the-midnight-museum` | 10-13 | held out | 19 findings + 1 residual; fixed clean book; plans x9, post-fix, c1, d3 (reject), e2, f5 (pass) |
| `the-signal-in-the-static` | 13-16 | held out | 19 findings + 5 residuals; fixed clean book; plans x8, post-fix, c3, d4 (reject), e1, f3 (pass) |
| `the-cave-of-echoes` | 8-11 | held out | 10 findings + 3 residuals; fixed clean book; plans post-fix, c2, d5 (reject), e4, f1 (pass); smoke 2, 5 |
| `the-mapmakers-island` | 10-13 | held out | 56 findings + 8 residuals; fixed clean book; plans post-fix, c4, d2 (reject), e3, f4 (pass) |
| `the-clockwork-menagerie` | 8-11 | held out | 48 findings; 6 merge counts; plan z2 |
| `the-clocktower-cipher` | 10-13 | held out | 28 findings; plan z3 |
| `the-last-train-north` | 16+ | held out | 7 merge counts (147 openings) |

## Counts per half

Reader items:

| | Tuning | Held out |
| --- | ---: | ---: |
| Known defects (`node_assertion` plus defect `payoff_judgment`) | 95 | 208 |
| of which blocker / should-fix / minor | 22 / 35 / 26 | 39 / 83 / 86 |
| of which unrated / leak / thin / unearned | 5 / 3 / 3 / 1 | 0 / 0 / 0 / 0 |
| Clean payoff judgments | 18 | 0 |
| Merge openings in `merge_count` items | 0 | 219 (147 hand-labelled plus 72) |
| Clean books, strong (nodes) | 2 (342) | 5 (660), the fixed revisions |
| Clean books, weak (nodes) | 1 (132) | 0 |

Known defects by class:

| Class | Tuning | Held out |
| --- | ---: | ---: |
| `unestablished_fact_on_route` | 39 | 114 |
| `location_or_physical_state` | 11 | 36 |
| `two_backstories` | 11 | 14 |
| `other` | 4 | 14 |
| `timeline` | 10 | 9 |
| `label_outcome_mismatch` | 11 | 10 |
| `state_contradiction` | 1 | 8 |
| `repeated_reveal` | 1 | 2 |
| `cross_payoff_reference` | 1 | 1 |
| `plant_leak_unplanted_route` | 2 | 0 |
| `public_plant` | 4 | 0 |

Classes: 144 of the 299 `node_assertion` items carry the source's class; 155 were assigned by the builder (`class_source`).

Plan items:

| | Tuning | Held out |
| --- | ---: | ---: |
| Defective (`reject`), real | 12 plans of 6 book revisions in 4 units | 20 plans of 10 book revisions in 7 units: x7, x8, x9, z2, z3 (pre-fix or catalog); c1 to c5, d1 to d5 and the five hand-written post-fix plans (post-fix revisions) |
| of which carry a blocker entry | 5 | 8 (x7, x8, x9, z2, z3; c3, d4 and the Signal post-fix plan, SG-2) |
| Clean (`pass`), strong | 2 (Lighthouse, Orchard post-fix) | 10: e1 to e5 and f1 to f5, two blind passes of each fixed revision |
| Clean (`pass`), weak | 1 (x3) | 0 |
| Unlabelled (`unknown`, smoke) | 4 | 2 |

Every family band (8-11, 10-13, 13-16) has at least one defective and one clean held-out plan.

Held-out D12 plans per book (`summary.held_out.d12_plans_by_unit`; strong labels only, smoke plans excluded):

| Book | `reject` | `pass` | Clean plans are | Known residuals on the clean plans |
| --- | ---: | ---: | --- | --- |
| `the-sky-ship-stowaway` | 4 (x7, post-fix, c5, d1) | 2 | e5, f2 | none |
| `the-midnight-museum` | 4 (x9, post-fix, c1, d3) | 2 | e2, f5 | MM-5 |
| `the-signal-in-the-static` | 4 (x8, post-fix, c3, d4) | 2 | e1, f3 | SG-7, SG-8 |
| `the-cave-of-echoes` | 3 (post-fix, c2, d5) | 2 | e4, f1 | none |
| `the-mapmakers-island` | 3 (post-fix, c4, d2) | 2 | e3, f4 | MI-12 to MI-17 |
| `the-clockwork-menagerie` | 1 (z2) | 0 | | |
| `the-clocktower-cipher` | 1 (z3) | 0 | | |
| **Total** | **20** | **10** | | |

## Shortfall against D12 and D6, and the seeding proposal

**D12, current state.** The held-out half holds **20 real defective plans and 10 clean plans**. The defective side
meets the minimum of 15 with real plans. The clean side meets the minimum as amended on 2026-11-21 (`AL-853`): two
independent blind extractions (e and f) of each of the five held-out books, so the effective clean sample is five books
and WP-3.7 reports clean results per book (table above), never as ten independent plans. The amendment named the
"post-fix" books; the 2026-11-21 residual check then found defects in those revisions (a blocker in Signal), so the
books were fixed on 2026-11-22 and re-extracted, and the fixed revisions, checked clean on 2026-11-22, are the ones the
amendment's two passes now bind. The c/d passes of the post-fix revisions count on the defective side.

**D12, history.** When the set was first built the held-out half held 5 real defective plans and 5 clean plans, and
the text below was written to that state. It is kept because the seeding proposal still applies: the amendment keeps
synthetic defective plans, reported separately.

The defective shortfall was **10 plans**, which D12 allows to be met with seeded-defect plans reported separately as
synthetic. The clean shortfall was also **10 plans**, and seeding cannot fill it: a seeded plan is defective by
construction. Ways to raise the clean count, each an owner decision before WP-3.7 runs (option 1, with a second pass,
is the one taken):

1. Blind re-extraction (the WP-1.4 method and prompt v2, fresh agents) of the five held-out post-fix books: +5 clean
   plans from a different writer than the hand-written ones, 10 in all.
2. A WP-0.4-style fix of the two held-out fresh-corpus books (`the-clockwork-menagerie`, `the-clocktower-cipher`) with
   hand-written plans for the fixed editions: +2, or +4 with blind re-extractions of them as well. This needs the edit
   pause (`UW-M20`) lifted for those books.
3. Accept a smaller clean count by amending D12, with the report showing the interval on the flag rate.

Options 1 and 2 together reach 12 to 14 clean held-out plans. A second independent blind extraction of each held-out
clean book (as x5 and x5b were for one book) adds 5 more, at the cost of several plans per book, which the report must
then show as clustered by book. A meaning-preserving edit of a clean plan ("seeded null")
is a useful control for whether the reviewer reacts to edits at all, but it is not an independent clean plan and should
not count toward the 15.

**Proposed seeding for WP-3.7** (not generated here: transplanting a witness onto a real plan needs per-plan choices of
node, fact and thread, which is not a trivial deterministic step):

- Start from each WP-1.2 rule witness in `src/cyo_adventure/storyplan/checks.py` (`WITNESSES`, checked by
  `uv run python scripts/check_story_plan.py --verify-witnesses`). Each witness is one property change to a clean plan:
  SP-1 drops a choice entry, SP-2 adds a plant fact to a shared node's `requires`, SP-3 establishes a second backstory on
  a sibling route, SP-4 establishes a plant fact on a shared path (two witnesses), SP-5 puts a payoff behind its own
  gate, SP-6 makes one payoff lean on another, SP-7 drops a negative ending's gift, SP-8 makes an opening decision
  costless, SP-9 forges a slot token or the injury sense of "wound". SP-0 (a stale hash) is a binding error, not a plan
  defect, and should not be seeded.
- Apply one defect per seeded plan, to a clean plan of the same half only: held-out clean plans seed only held-out
  synthetic items, tuning clean plans only tuning ones. A seed's `book.unit` is its clean plan's unit.
- Check every seed with `check_plan` the way `verify_witnesses` does: it must trip exactly its intended rule. Record
  the rule, the clean plan's id and the edited path on each synthetic item.
- With 10 held-out clean plans (5 books) and 9 seedable rule patterns, seed at least one plan per book on different
  rules; spread the rules so no rule supplies more than two seeds. The real defective side no longer needs seeds to
  reach 15, so synthetic recall is reported only as the amendment requires, beside real recall.
- Report three figures, never merged: real defective recall, synthetic recall, and clean flag rate. Because every rule
  witness is a defect the deterministic checker already catches, and D11 lets the reviewer pass only plans the checks
  passed, synthetic recall measures the reviewer on checker-visible defects only. The pilot's one clear win (KD-LH-B2,
  a state contradiction) was checker-invisible; a second seed family for checker-invisible defects (a label that
  contradicts its outcome, a fact that contradicts `truth`) would measure that, but D12 names the witnesses, so that
  family needs the owner's agreement.

**D6.** D6 sets rates, not a minimum size. The held-out half has 208 known defects across 7 books (39 blockers) for
recall and 5 strong clean books (the fixed revisions) with 660 nodes for the false-flag rate, where the bar of one flag
per 50 nodes allows at most 13 false flags, flags on the 9 known residuals excepted. That is enough to measure each
rate; the per-class figures are thin for `state_contradiction` (8), `repeated_reveal` (2) and `cross_payoff_reference`
(1), and the held-out half has no
`plant_leak_unplanted_route` or `public_plant` item at all (all Run B defects are in forced-tuning books), so recall
on those classes is unmeasured on the held-out half.

## Limits recorded, not hidden

- **Builder-assigned classes and severities.** The WP-0.4 files mostly give no class, and the Cave file grades
  high/med/low; 155 classes and the Cave severity mapping are the builder's, marked on each item. The Lighthouse N-ids
  have no severity in the source and are `unrated`.
- **Plan labels come from the book.** A blind plan is labelled with every defect its book carries. Some defects
  (minor wording, a title) may not be visible in any plan, so a plan's `defects` list is an upper bound on what the
  reviewer can see; WP-3.7 should score `reject` per plan, and report blocker coverage per entry.
- **One reader per book.** Every label is one agent's reading, verified with `StoryEngine`; no second human read them.
- **Known residuals in clean controls.** The plan-review pilot found a label and outcome contradiction
  (`c_b1a_dec_2` into `e_b1a`) in the post-fix `the-vanishing-orchard` that the WP-0.4 read missed, and the 2026-11-22
  check left 9 minors in the fixed held-out books. They are recorded in `known_residuals`; a flag there is a true
  positive. See [Known residuals](#known-residuals-the-minor-residual-rule).
- **"Clean" means no blocker or should-fix, after blind extraction.** The 2026-11-21 check found real residuals that a
  full WP-0.4 read had missed in all five held-out books, and the 2026-11-22 check found 9 more minors on text unchanged
  since then. A clean label is the latest verified state, not a proof of no defect.
- **Severity spread of rejected plans.** Plans are labelled by every defect their book revision carries, so a plan can
  be `reject` on minor residuals alone (c1, d3 and the Museum post-fix plan carry only MM-4, minor). WP-3.7 should report
  defective recall split by the worst severity a plan carries, as well as overall.
- **Merge seams are not continuity.** Merge counts measure route-hedging openings, a different defect from an
  unestablished fact, and are reported beside D6, never in its recall.
- **What the set does not cover.** As WP-3.7 notes, there is nothing here on dull, generic or off-request plans, so
  those classes have no measured recall and stay advisory under D12's scope-of-authority row.
