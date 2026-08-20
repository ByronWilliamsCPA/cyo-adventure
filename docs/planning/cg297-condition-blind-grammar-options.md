# CG-1 and CG-2 count choices the reader may never see

Written 2026-08-18 for owner ruling on `UW-C297`. Every number below was executed, not recalled;
the reproducing commands are named beside each.

## What the defect is

`UW-C292` made PL-20, PL-25 and PL-26 measure the *configuration* graph, so a story with conditioned
choices is graded on paths a reader can actually walk. The choice-grammar rules were not changed.
`choice_grammar.py::_is_decision` and `_is_single_choice` still read `len(node.choices)` and never
look at `choice.condition`, so they grade the graph as declared rather than as rendered.

A node declaring three choices, two of them conditioned, is a three-way decision to CG-2 and a
decision node to CG-1, no matter how many options the reader in front of it can see.

L2-14 does not cover the gap. It fires only where two or more choices are visible, so the
one-visible case is exempt by construction. Nothing else measures it either: L2-9's dead-end check
catches *zero* visible choices, and the catalog has none of those.

## What it costs, measured

`uv run python /tmp/cg297.py` over the 68 committed non-sidecar skeletons:

| | count |
| --- | ---: |
| skeletons declaring at least one choice condition | 14 of 68 |
| their bands | 10-13: 3, 13-16: 6, 16+: 5 |
| nodes whose visible-choice count varies by configuration | 61 |
| nodes declared with 2+ choices that show exactly ONE option in some reachable configuration | **40** |
| nodes that show zero options anywhere | 0 |

**Forty one-button nodes is not forty defects.** A gate that is closed until you hold the key is
ordinary design: the reader sees "go back" alone, which is correct and intended. Counting those as
grammar violations would be a rule that fires on the feature.

The harm is not the node, it is the *run*. `uv run python /tmp/cg297b.py` compares the longest
choiceless run CG-1 can see against the longest one a reader actually walks:

| skeleton | band | CG-1 cap | declared run | reader's run | |
| --- | --- | ---: | ---: | ---: | --- |
| the-cinder-bazaar | 16+ | 6 | 3 | **10** | breaches, invisibly |
| the-quiet-harbor-protocol | 16+ | 6 | 6 | **8** | breaches, invisibly |
| the-winter-of-the-wolf-queen | 10-13 | 6 | 5 | 6 | at the cap |
| the-iron-spire-trial | 13-16 | 6 | 3 | 4 | inside |
| the other 10 conditioned books | | | | equal to declared | |

**Two committed books railroad a reader past CG-1's own cap while CG-1 reports them compliant.**
The worst is `the-cinder-bazaar`, verified by walking a real configuration path rather than by a
memoized estimate (`uv run python /tmp/cg297c.py`):

```
a3_ap1_exit -> a3_gate -> a3_full -> f_enter -> f_road -> f_marked
            -> cg_goods -> cg3_scene -> cg3_water -> cg3_dry
```

Ten consecutive one-option stops. Three of those nodes declare 4, 4 and 2 choices, so CG-1 reads the
chain as three short corridors separated by decisions and scores the longest at 3. The reader presses
one button ten times.

## Correcting a cost figure I gave earlier

I told the owner this fix "puts a configuration walk in the grammar layer, which `UW-C292` already
priced at 4.2s per walk at the cap." Both halves are misleading and the measurements say so.

1. **The grammar rules do not run in the request path at all.** CG-1, CG-2 and CG-3 sit behind
   `enforce_grammar`, which defaults `False` in `run_gate` and is passed `True` by exactly one
   caller: `scripts/check_skeleton.py --strict`. No production path enables them. Latency here is
   offline authoring cost, not gate cost.
2. **4.2s was the wrong book.** That figure came from the 99,423-configuration gamebook draft. The
   largest *conditioned committed* skeleton is `the-tenfold-siege` at 9,832 configurations, and one
   walk over it takes **0.169s**; `the-cinder-bazaar` takes 0.048s. End to end, `--strict` on either
   runs ~3.6s, dominated by interpreter startup. A third walk is a 1 to 5 percent change to an
   offline command.

This is the third cost figure in two days that did not survive being executed. The standing rule from
`AL-471` applies to me here: a document may not quote a bound it did not run.

## The options

| # | Option | Findings on today's catalog | Cost | What it leaves |
| --- | --- | ---: | --- | --- |
| A | Do nothing, document the gap | 0 | none | Two books railroad readers; grows as the teen cells are authored, since all 14 conditioned books are 10-13 and up |
| B | Make CG-1 and CG-2 state-aware | up to **40** on CG-2 alone | one walk, offline | Fires on legitimate conditional gating; CG-1's *share* has no clean definition over a graph whose composition varies by configuration |
| C | **New rule over the visible run, CG-1 and CG-2 unchanged** | **2** | one walk, offline | CG-2 keeps declared-fan semantics; the reader's-eye reading is a separate, named measurement |
| D | Static approximation: flag a node whose choices are all conditioned | untested, over-reports by construction | none | Cheap, but proves nothing and re-creates the "gate measures a different quantity" defect |
| E | Report it in `--headroom` only, no rule | 0 blocking | one walk, offline | Informs the author, gates nothing |

### Why B is the wrong shape despite being the obvious one

Two reasons, and the second is the harder one.

**It fires on the feature.** Forty nodes show one option somewhere. Most are a closed gate, which is
the whole point of conditions. A rule producing forty findings of which two matter trains authors to
ignore it, which is how CG-4 got restricted rather than loosened earlier this week.

**CG-1's share has no well-defined state-aware reading.** The run cap does: the longest chain of
consecutive one-visible-choice configurations is a single number over the configuration graph. But
"the share of non-ending nodes that are choiceless" is a ratio over the *declared* node set, and in
configuration space one node appears once per reachable state of it. Do you weight by node,
by configuration, or by the worst path? Each answers a different question, and picking one silently
is exactly the unit error this workstream has now found five times. B forces that choice; C does not.

### Why not D

It reports a shape, not the harm. A node with all choices conditioned may still always show two, and
a ten-stop corridor can be assembled from nodes that individually look fine, which is precisely what
`the-cinder-bazaar` does. Approximating here re-creates the defect class the last four fixes removed.

## Recommendation: C, shipped advisory, with E's report alongside it

**A new rule, CG-5, measuring the longest run of consecutive one-option stops over the configuration
graph, against the band's existing `_DISCRETE_RUN_CAP`.** CG-1 and CG-2 keep their declared-graph
reading unchanged, and the new rule is named for what it measures so the two cannot be confused.

Grounds:

1. **It targets measured harm.** Two real cases, one of them a ten-stop corridor, against forty
   mostly-legitimate findings from B.
2. **It reuses a bound that already exists.** No new constant to calibrate; `_DISCRETE_RUN_CAP` is
   the number CG-1 already applies, now also applied to the run the reader walks.
3. **The definition is unambiguous** in configuration space, which CG-1's share is not.
4. **It costs a walk in an offline command that already performs two** (policy and Layer 2), at
   0.05 to 0.17s on the affected books.
5. **It breaks nothing that passes.** Both books it fires on already fail `--strict` today, so the
   census stays at 4 pass / 66 fail.

**Advisory rather than blocking, on the charter's own procedure.** That procedure asks whether the
newest deliberately compliant artifact passes the new bound. All four strict-bar skeletons authored
in this workstream declare **zero** variables and **no** conditions, so they pass trivially and
therefore tell us nothing. There is no conditioned artifact authored to the bar to test against, and
shipping blocking on an untested bound is what put CG-3's young-band ceilings in the state they were
in this morning. State the flip condition instead: **CG-5 becomes blocking once one conditioned book
is authored to the strict bar and passes it deliberately.**

Ship E's line with it either way: `--headroom` should print the declared and visible run lengths side
by side, because the gap between them is the thing an author cannot otherwise see.

**If C is rejected**, E alone is the honest minimum: it surfaces the ten-stop corridor to whoever
looks, without asserting a bound nobody has authored against. A is not defensible now that the harm
is measured rather than hypothesised.
