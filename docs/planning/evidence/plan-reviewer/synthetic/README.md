# Synthetic seeded-defect plans for the plan reviewer (WP-3.7, D12)

Owner decision D12 (as amended 2026-11-21) lets the plan reviewer's validation set be supplemented with plans seeded
with one defect each, **reported separately as synthetic**. This directory is that supplement:

- `validation-set.synthetic.json`, schema `validation-set-synthetic/v1`, the items;
- `SY-<family>-<rule or class>-<n>.plan.json`, one seeded plan per item (indent 2, ASCII only, trailing newline).

**These items are never merged into `docs/planning/evidence/continuity-reader/validation-set.json`** or into any
recall or flag-rate figure computed from it. They share no id with it (every id starts `SY-`), they carry
`label_strength: "synthetic"` and `scored_for: "D12-synthetic"`, and the two families below are reported apart from
each other as well. The real set stays the headline; see `docs/planning/evidence/continuity-reader/README.md`.

## What is in it

| | Held out | Tuning | Total |
| --- | ---: | ---: | ---: |
| Family A, checker-visible | 11 | 9 | 20 |
| Family B, checker-invisible | 8 | 4 | 12 |
| Total | 19 | 13 | 32 |

Every item has `expected_verdict: "reject"` (the reviewer must answer reject or `unsure`). A seed takes its source
plan's `half` and `book` (`book.unit` is the source plan's unit), so the split of `validation-set.json` is respected:
held-out sources seed only held-out items and tuning sources only tuning items. A prompt may be tuned on the tuning
items only.

Held-out items per book (five books, at least two family A seeds on different rules and one family B seed each):

| Book | Family A rules | Family B classes |
| --- | --- | --- |
| `the-cave-of-echoes` | SP-1, SP-9 | B1, B3 |
| `the-mapmakers-island` | SP-2, SP-7, SP-8 | B2 |
| `the-signal-in-the-static` | SP-4, SP-6 | B3, B4 |
| `the-midnight-museum` | SP-4 (second witness), SP-5 | B1, B4 |
| `the-sky-ship-stowaway` | SP-3, SP-9 (second witness) | B2 |

## Family A: checker-visible

One property change per WP-1.2 witness (`WITNESSES` in `src/cyo_adventure/storyplan/checks.py`), moved onto a real
clean plan. SP-0 (a stale hash) is a binding error, not a plan defect, and is not seeded; SP-D is advisory and is not
seeded. SP-4 and SP-9 each have two witnesses since the G1 revision, and both are used. A seed must trip **exactly its
intended rule** through `check_plan`, the function `verify_witnesses` uses: the set of ERROR rule ids of the seeded
plan must equal `{intended_rule}`. The builder searches a fixed ordering of candidate edits (breadth first from the
start node, ledger order for facts) and keeps the first candidate that does, so no random number generator is
involved. No rule supplies more than two seeds in a half.

| Rule | Witness (WP-1.2) | What the seed changes on a real plan |
| --- | --- | --- |
| SP-1 | drop a choice's plan entry | deletes `choices.<id>` of a decision choice |
| SP-2 | a shared node presupposes a plant | adds a fact only some routes establish to a node's `requires` |
| SP-3 | a second backstory | adds a rival fact contradicting a truth fact, at a node one reading also crosses |
| SP-4 | the plant shown on the shared path | a node on the unplanted path establishes the thread's plant |
| SP-4 (second) | the plant's named half shown to all | an unplanted-path node shows what only planted readers saw |
| SP-5 | a payoff behind its own gate | moves a payoff site where readers are only planted or only unplanted |
| SP-6 | a payoff leans on another's | moves a payoff out of another payoff passage and requires what only it showed |
| SP-7 | a negative ending's gift dropped | deletes `endings.<id>` of a negative ending |
| SP-8 | an opening decision made costless | sets every cost at a decision node to `None.` |
| SP-9 | a forged slot token | appends `{HERO}` to a fact sentence |
| SP-9 (second) | the injury sense of "wound" | appends the injury noun "wound" beside a clock word to a fact |

SP-6 is the one witness that did not transplant as a single change. The witness gates a payoff on two plants by
editing the book, which a seed must not do (the book, and so the shape the reviewer sees, stays the real one). Every
real plan gates a payoff on its own variable and records each plant at the node after its planting choice, so the
plant-blind analysis SP-6 uses still sees every plant, and a payoff leaning on another thread's plant raises SP-2 as
well. The shape that trips SP-6 alone is a payoff passage requiring a fact established only by another thread's payoff
passage and reached only through it, so the seed moves one thread's payoff there (two edited paths).

### Family A seeds

| Id | Half | Book | Source | Rule | Edited path |
| --- | --- | --- | --- | --- | --- |
| SY-A-SP-1-1 | held out | cave-of-echoes | e4 | SP-1 | `/choices/c_left` |
| SY-A-SP-9-1 | held out | cave-of-echoes | f1 | SP-9 | `/facts/maya_explorer/text` |
| SY-A-SP-2-1 | held out | mapmakers-island | e3 | SP-2 | `/nodes/mg_creek/requires` |
| SY-A-SP-7-1 | held out | mapmakers-island | e3 | SP-7 | `/endings/e_tw_stair_fail` |
| SY-A-SP-8-1 | held out | mapmakers-island | e3 | SP-8 | `/choices/c_n_start_1/cost` (+4) |
| SY-A-SP-4-1 | held out | signal-in-the-static | e1 | SP-4 | `/nodes/n_shelf/establishes` |
| SY-A-SP-6-1 | held out | signal-in-the-static | e1 | SP-6 | `/threads/has_battery/payoff_sites` (+1) |
| SY-A-SP-4-2 | held out | midnight-museum | f5 | SP-4 (second) | `/nodes/n_desk_chalk/establishes` |
| SY-A-SP-5-1 | held out | midnight-museum | f5 | SP-5 | `/threads/read_back/payoff_sites` |
| SY-A-SP-3-1 | held out | sky-ship-stowaway | e5 | SP-3 | `/facts/hold_holds_salt_fish` (+1) |
| SY-A-SP-9-2 | held out | sky-ship-stowaway | e5 | SP-9 (second) | `/facts/bree_dreams_sky/text` |
| SY-A-SP-4-3 | tuning | lighthouse | lighthouse post-fix | SP-4 | `/nodes/n_start/establishes` |
| SY-A-SP-5-2 | tuning | lighthouse | lighthouse post-fix | SP-5 | `/threads/t_key/payoff_sites` |
| SY-A-SP-9-3 | tuning | lighthouse | lighthouse post-fix | SP-9 (second) | `/facts/mira_stranded/text` |
| SY-A-SP-1-2 | tuning | orchard | orchard post-fix | SP-1 | `/choices/c_n_start_1` |
| SY-A-SP-2-2 | tuning | orchard | orchard post-fix | SP-2 | `/nodes/rec_conv/requires` |
| SY-A-SP-3-2 | tuning | orchard | orchard post-fix | SP-3 | `/facts/quiet_is_river_fog` (+1) |
| SY-A-SP-7-2 | tuning | orchard | orchard post-fix | SP-7 | `/endings/e_rec_a` |
| SY-A-SP-8-2 | tuning | orchard | orchard post-fix | SP-8 | `/choices/c_n_start_1/cost` (+3) |
| SY-A-SP-9-4 | tuning | orchard | orchard post-fix | SP-9 | `/facts/rowan_arrives_by_bus/text` |

Source `e4` and the like are the `PL-e4` plans of `validation-set.json`. Each item's `edited_paths` lists every path,
and `description` says what the edit does.

Rules that could not be seeded in a half: the tuning half has no SP-6 and no second SP-4 seed (no Lighthouse payoff is
reached only through another thread's payoff passage, and no thread there has a planted-only fact a payoff relies on).
Cave of Echoes and Mapmaker's Island declare no variables, so they carry no SP-4 to SP-6 seed; Cave has no negative
ending, so it carries no SP-7 seed. The Orchard plan declares no variables either, so its seeds are SP-1, SP-2, SP-3,
SP-7, SP-8 and SP-9. The SP-9 second witness (the injury "wound") did not trip for the 13-16 sources (Signal,
Orchard), so it is seeded only on 8-11 and 10-13 plans.

## Family B: checker-invisible

Defects the deterministic checks cannot see, which the plan reviewer exists to catch. They are hand-designed, one edit
set per seed, in `SEEDS_B` of the builder. Four classes (the id carries the code, `defect_class` the name):

| Code | Class | The seed |
| --- | --- | --- |
| B1 | `label_outcome_mismatch` | a choice's `intent` and `cost` say the opposite of what its target establishes |
| B2 | `truth_contradiction` | a node establishes a fact the truth rules out, `contradicts` left empty |
| B3 | `ending_gift_mismatch` | an ending's `gift` contradicts its valence, its own passage or the truth |
| B4 | `payoff_shows_mismatch` | a payoff's `shows` credits something other than what the planting choice set up |

**Checker-invisible verification.** The builder runs `check_plan` on every B seed (after re-reading the plan from the
exact text it will write) and **fails the build** unless the seed raises no ERROR and no warning, keyed by rule, node
and fact, that its source baseline did not already raise. Each item records `checker_errors: []`, an `intended_class`,
its `edited_paths`, a `description` and a one-sentence `reviewer_should_say`. Severity is the designer's own
reasoning: `blocker` for a contradiction with the truth, `should-fix` for a label, gift or payoff line that misleads.

Examples, one per class (the full edits are in each item's `edited_paths` and `description`):

- **B1, SY-B-B1-1** (source e4, `/choices/c_lakeback/intent` and `cost`): "retreat from the slippery shelf" becomes
  "wait on the shelf until the tide turns".
- **B2, SY-B-B2-1** (source e3, new fact `alder_sailed_home` established at `tw_enter`): "A faded note in the survey
  tower says Alder finished the chart and sailed home safely."
- **B3, SY-B-B3-2** (source e1, `/endings/e_count_wait/gift`): "the sea was the clock, and it does not wait for
  daylight" becomes "the loop is saved, and Kell and Marin are on the phone together by morning".
- **B4, SY-B-B4-1** (source e1, `/threads/has_battery/payoff_sites/0/shows`): "she splices grandpa's JUST IN CASE
  battery across the empty terminals and the station holds" becomes "she splices grandpa's headset across the empty
  terminals and the station holds".

In SY-B-B1-1 the target `ra_lake_back` still establishes that Maya retreats along the passage to daylight, so the new
label contradicts the outcome. In SY-B-B2-1 the truth is that a storm took Alder's boat and Alder never returned. In
SY-B-B3-2 the ending is negative and its passage says the loop is gone. In SY-B-B4-1 the thread planted the spare
battery.

### Family B seeds

| Id | Half | Book | Source | Class | Edited paths | Severity |
| --- | --- | --- | --- | --- | --- | --- |
| SY-B-B1-1 | held out | cave-of-echoes | e4 | B1 | `/choices/c_lakeback/intent` (+1) | should-fix |
| SY-B-B3-1 | held out | cave-of-echoes | e4 | B3 | `/endings/da_bat_back/gift` | should-fix |
| SY-B-B2-1 | held out | mapmakers-island | e3 | B2 | `/facts/alder_sailed_home` (+1) | blocker |
| SY-B-B3-2 | held out | signal-in-the-static | e1 | B3 | `/endings/e_count_wait/gift` | should-fix |
| SY-B-B4-1 | held out | signal-in-the-static | e1 | B4 | `/threads/has_battery/payoff_sites/0/shows` | should-fix |
| SY-B-B1-2 | held out | midnight-museum | f5 | B1 | `/choices/c_alarm_hide/intent` (+1) | should-fix |
| SY-B-B4-2 | held out | midnight-museum | f5 | B4 | `/threads/has_chalk/payoff_sites/0/shows` | should-fix |
| SY-B-B2-2 | held out | sky-ship-stowaway | e5 | B2 | `/facts/quill_sells_calf` (+1) | blocker |
| SY-B-B1-3 | tuning | lighthouse | lighthouse post-fix | B1 | `/choices/c_a_hearth_1/intent` (+1) | should-fix |
| SY-B-B4-3 | tuning | lighthouse | lighthouse post-fix | B4 | `/threads/t_key/payoff_sites/0/shows` | should-fix |
| SY-B-B2-3 | tuning | orchard | orchard post-fix | B2 | `/facts/grandmother_writes_postcards` (+1) | blocker |
| SY-B-B3-3 | tuning | orchard | orchard post-fix | B3 | `/endings/e_pho_a/gift` | should-fix |

## Sources, and the baseline repair

Sources are the validation set's clean plans: `expected_verdict: "pass"`, `label_strength: "strong"`. Held out, these
are the e and f plans of the five fixed books (this set uses `e1`, `e3`, `e4`, `e5`, `f1`, `f5`); tuning, the post-fix
plans of `the-hollow-lighthouse` and `the-vanishing-orchard`. Museum's minor-only plans (post-fix, `c1`, `d3`) are
never sources: they are `pass` only by ruling (`AL-882`) and carry a known residual, and the builder refuses them. The
builder verifies each source plan and its book against the sha256 the validation set records (reading the pinned git
revision when the working tree has moved on).

**The clean plans are clean as books, not as checked plans.** The e and f plans are labelled `pass` because their
*book* carries no blocker or should-fix. Run through `check_plan` today, `e1`, `e3`, `e5` and `f5` still raise ERRORs
(`e1`: one SP-3; `e3`: seventeen SP-2 and one SP-3; `e5`: one SP-2; `f5`: two SP-9), and so do `e2`, `f2`, `f3` and
`f4`, which are not used here; `e4`, `f1` and both tuning plans are clean. These are blind-extraction artefacts (a
blind extractor records a presupposition the book does not guarantee), and the plans' own `provenance.notes` mention
several. A seed that must differ from a checker-clean plan by exactly one defect cannot start from a plan that already
trips rules, so each source is first brought to zero ERRORs by a mechanical, recorded **baseline repair**
(`repair_baseline` in the builder):

| Finding | Repair |
| --- | --- |
| SP-2 or SP-6 on a node or choice | drop the unguaranteed fact from that `requires` |
| SP-3 ERROR | drop the contradiction mark between the two facts the finding names |
| SP-9 | reword the string from a table (only `f5`: "the wound wren" becomes "the wren, wound up,") |

Every seed lists its source's repairs in `baseline_repairs`, and the document lists them per source under `sources`.
`e3` carries 16, `f5` two, `e1` and `e5` one each, the rest none. A repaired baseline is not a plan in
`validation-set.json`: the seeds are "a real clean plan, repaired, plus one defect", not "a real clean plan plus one
defect". That separate fact, that most clean e/f plans fail the checker, also matters to the real flag rate (D11 lets
the reviewer pass only a plan the checks passed), and is recorded in the authoring lessons log, not decided here.

The Orchard post-fix source carries a known residual of its own (`c_b1a_dec_2` into `e_b1a`, a label and outcome
mismatch that the plan-review pilot found). Every Orchard seed inherits it; a reviewer flag citing that choice or
`e_b1a` is not credit for the seed, which is scored on its `edited_paths`.

## Limits

- **Synthetic defects are cleaner than real ones.** Each seed has exactly one defect, in an otherwise clean plan, at a
  known place. Real defects come in company, are subtler and hide in prose-level judgement. **Recall on synthetic
  items overstates real recall.**
- **Family A is checker-visible by construction.** D11 lets the reviewer pass only plans the checks passed, so a
  reviewer that reads the checker's findings gets family A for free. Report it as a floor, and never as evidence of
  reviewing skill.
- **Family B is hand-designed.** The edits were written by a person who knew what the reviewer would look for, so a B
  seed may be easier (a gift that says the opposite outright) or harder (a one-word object swap in a `shows` line)
  than a real defect. The four classes are the ones D12 names; there are no seeds for dull or generic plans or plans
  that miss the request, and those classes stay advisory.
- **Repaired baselines.** See above: four of the six held-out sources differ from the plans in `validation-set.json`
  at the paths in `baseline_repairs`.
- **Small and clustered.** 32 seeds from eight source plans of seven books; a figure over them is a count, not a rate
  with a tight interval. Report counts per rule and class, never one pooled number.
- **Seeds are one defect each, but not one fact.** SP-3, SP-6 and the B2 seeds add a fact or move a payoff, so they
  touch two paths.

## Rebuild and check

```bash
uv run python scripts/build_synthetic_plans.py            # write the plans and validation-set.synthetic.json
uv run python scripts/build_synthetic_plans.py --check    # rebuild in memory, exit 1 on any drift or stray plan file
uv run python scripts/build_synthetic_plans.py --summary  # print the counts per family, rule or class and half
uv run pytest tests/unit/test_synthetic_plans.py          # family rules, halves, minimums, rebuild, no em-dash
```

The builder reads only committed files (the validation set, the source plans and books, through their recorded
sha256), calls no model, uses no network and no random number generator; the split seed it records is a label, not an
input. A shallow clone lacks the pinned git revisions, so the builder exits 2 and the tests that need them skip.
