---
title: "Structural verification of the 2026-11-20 prompt and state-promotion changes"
schema_type: planning
status: complete
owner: core-maintainer
purpose: "Paid fill-and-gate measurement of two same-day changes: the reader-agency fill prompts with
  per-merge notes (old versus new prompts on the same skeletons) and skeleton state promotion (fills of
  two promoted skeletons). Records what the deterministic instruments and a hand reading show, at a
  sample size stated on every claim, and what to change next."
tags:
  - planning
  - generation
  - evaluation
audience: product-owner, engineering
---

# Structural verification, 2026-11-20

> **Status**: complete | **Run**: 2026-11-20, 21:49 to 22:27 UTC | **Spend**: 5.05 USD provider-reported
> (5.89 USD estimated) against a 15 USD cap | **Evidence**:
> [evidence/structural-verification-2026-11-20/](./evidence/structural-verification-2026-11-20/README.md)
>
> **Sample size, stated once and meant everywhere below**: Run A is three OLD and three NEW fills on each of
> two skeletons (plus one chunked fill); Run B is two fills on each of two skeletons. One model, one brief
> per skeleton, native themes. Differences of a few counts between arms are inside the fill-to-fill
> variance this round measured, and nothing here is significance-tested.

## 1. Summary

- **Gate and contract: no regression.** 17 of 17 fills delivered, none blocked by the gate, and every
  delivered book's choices, conditions and effects match its skeleton exactly; on the two promoted skeletons
  the model's raw reply already did, before any normalization. Three Run A first replies (1 OLD, 2 NEW)
  miscopied the graph (a renamed or duplicated node) and were repaired by the loop. No `content_filter` stop
  on any call. The NEW arm produced no `needs_review` book; the OLD arm produced three,
  all from the 0.6 fill-rate floor.
- **Merge seams: real improvement on one skeleton, none on the other, and the detector hides the
  difference.** On `the-clockwork-menagerie` the NEW prompt cut seams from 8, 8, 8 to 3, 0, 1 (detector and
  hand count agree). On `the-last-train-north` the detector reports 12, 0, 5 against 2, 1, 2, but a hand read
  of all 147 merge openings counts **17, 3, 12 against 1, 9, 15**: the NEW prompt taught the model new ways to
  say the route did not matter ("the same truth from two angles", "The letter, read or unread, ...") that
  `merge_seams` cannot see. Its recall on the NEW arm is about 16 percent.
- **Every residual defect sits on skeleton text that asks for it.** All residual NEW-arm seams are on merges
  whose beat itself says "both readings converge", "all three ways bring Nia out" or "every path ends here";
  about 93 percent of option recaps (both arms) are on decisions whose beat enumerates the options; the
  second-person labels are the skeleton's own labels, kept verbatim. A prompt rule loses to a beat that
  contradicts it, and the converse held too: the two promoted skeletons, whose merge beats carry the
  "never say which way the hero came" instruction, got no seam in 470 merge passages.
- **Recaps, labels, give-up endings, dialogue: no demonstrated effect.** Recaps are unchanged; the drop in
  second-person labels on `the-last-train-north` (20 against 30 to 49) is the NEW arm rewriting zero labels,
  so the skeleton's 20 defective labels survive; give-up endings and dialogue move within noise.
- **State promotion works mechanically and mostly works for a reader.** Of 22 plant-to-payoff pairs played
  with `StoryEngine`, 18 show a connection a child would see (12 of 12 on `the-lantern-keepers-list`),
  3 are thin, 1 is unearned. Two fills leak a plant into a route that never planted it, and one payoff
  depends on another payoff the reader may not have seen. About 3 to 4 percent of random readers reach any
  payoff.

## 2. Method

The OLD arm ran the unmodified baseline worktree (`1c42b3b`), the NEW arm this branch; the generation code
differs only in `prompts.py`, the new `merge_notes.py` and the fill templates (diffed before running,
`prompts/generation-code-diff-stat.txt`; the orchestrator, chunking, reading-level loop and binding are
identical). Both arms filled byte-identical bound skeletons (the contract's `default_binding`) from the same
production-shaped native brief, through the production `build_provider` cascade and `fill_skeleton` with
production defaults. Declared deviations from the worker: Stage 1 skipped; the binding fixed rather than
LLM-chosen; one fill forced onto the chunked path. Every fill was scored from the NEW worktree with
`run_fill_gate`, `check_fill_integrity.py`, `check_prose_craft.py --json`, `measure_consequence.py`,
`validator.dialogue`, and an exact condition/effects comparison against the skeleton. Full harness and run
log: the evidence [README](./evidence/structural-verification-2026-11-20/README.md).

**Model actually serving.** `deepseek/deepseek-v4-pro` on `azure/us` for 16 of 17 fills entirely. In
`A-cm-old-3` one Stage D reading-level call received a leg-fatal HTTP 400 and was answered by
`anthropic/claude-sonnet-4.6` (106 output tokens); the fill itself is v4-pro.

**Hand seam count.** I read the first three sentences of every merge node in every Run A fill and counted a
seam when the opening states or hedges that the reader's route did not matter ("whether X or Y", "X, or Y,",
"both approaches ... the same", "the same truth from two angles"). Bare beat echoes ("The small wrongness
converged") and structure jargon ("The second bottleneck had opened") were not counted as seams.

## 3. Run A: old versus new prompts

### 3.1 `16+/the-last-train-north` (21 merges, 43 decisions, 24,445 commissioned words)

| Metric | OLD 1 | OLD 2 | OLD 3 | NEW 1 | NEW 2 | NEW 3 | NEW chunked |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Outcome | needs_review | passed | passed | passed (1 repair) | passed | passed (1 repair) | passed |
| Gate blocked | no | no | no | no | no | no | no |
| State contract exact | yes | yes | yes | yes | yes | yes | yes |
| Merge seams, detector | 12 | 0 | 5 | 2 | 1 | 2 | 12 |
| **Merge seams, hand** | **17** | **3** | **12** | **1** | **9** | **15** | **14** |
| Option recaps | 24 | 33 | 28 | 24 | 32 | 33 | 25 |
| Second-person labels | 30 | 31 | 49 | 20 | 20 | 20 | 29 |
| Labels rewritten (of 174) | 163 | 138 | 174 | 0 | 0 | 0 | 31 |
| Give-up endings | 0 | 0 | 1 | 1 | 1 | 0 | 0 |
| Early setbacks | 4 | 4 | 4 | 4 | 4 | 4 | 4 |
| Passages with dialogue | 0.160 | 0.181 | 0.167 | 0.174 | 0.285 | 0.208 | 0.292 |
| Words delivered | 12,774 | 17,032 | 15,458 | 17,673 | 19,290 | 17,382 | 22,412 |
| Story fill rate | 0.511 | 0.680 | 0.615 | 0.711 | 0.769 | 0.694 | 0.885 |
| Est. cost USD | 0.358 | 0.393 | 0.310 | 0.655 | 0.436 | 0.533 | 0.763 |

For reference, the committed `out/the-last-train-north.filled.json` (a different authoring path) scores 21
seams, 26 recaps, 20 second-person labels and fill rate 0.929 on the same instruments.

### 3.2 `8-11/the-clockwork-menagerie` (12 merges, 29 decisions, 15,831 commissioned words)

| Metric | OLD 1 | OLD 2 | OLD 3 | NEW 1 | NEW 2 | NEW 3 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Outcome | passed (2 repairs) | needs_review | needs_review | passed | passed | passed |
| Gate blocked | no | no | no | no | no | no |
| State contract exact | yes | yes | yes | yes | yes | yes |
| **Merge seams (detector = hand)** | **8** | **8** | **8** | **3** | **0** | **1** |
| Option recaps | 12 | 15 | 19 | 12 | 13 | 15 |
| Second-person labels | 6 | 6 | 6 | 6 | 6 | 6 |
| Labels rewritten (of 183) | 2 | 13 | 13 | 11 | 9 | 4 |
| Give-up endings | 0 | 0 | 0 | 0 | 0 | 0 |
| Passages with dialogue | 0.150 | 0.012 | 0.006 | 0.132 | 0.012 | 0.048 |
| Words delivered | 16,718 | 9,474 | 7,728 | 12,355 | 13,905 | 13,639 |
| Story fill rate | 0.969 | 0.583 | 0.479 | 0.740 | 0.848 | 0.828 |
| Est. cost USD | 0.772 | 0.262 | 0.237 | 0.319 | 0.306 | 0.278 |

The committed fill scores 8 seams, 21 recaps, 6 second-person labels.

### 3.3 Verdict per hypothesis (Run A)

| Claim | Verdict at this n | Basis |
| --- | --- | --- |
| Fewer merge seams | **Supported on clockwork, not on last-train-north** | Clockwork 24 to 4 across three fills each, no overlap. Last-train-north hand count 32 to 25, with ranges 3 to 17 and 1 to 15 overlapping almost completely. |
| Fewer option recaps | **Not supported** | 85 to 89 and 46 to 40 summed over three fills. |
| Fewer label defects | **Not supported as a fix** | The NEW arm stopped rewriting labels (0 of 174) instead of correcting them; every defective label is the skeleton's own. |
| Fewer give-up endings | **Not supported** | 1 to 2 on last-train-north, 0 to 0 on clockwork; both NEW give-up endings follow beats that end on loss. |
| More dialogue | **Inconclusive** | Up on last-train-north (mean 0.169 to 0.222), flat on clockwork (0.056 to 0.064), and the clockwork spread between two fills of one arm (0.012 to 0.150) dwarfs either difference. |
| No worse gate results | **Supported** | 0 blocked either arm. First replies broke structure in 1 of 6 OLD and 2 of 6 NEW (a duplicated or renamed node id: copying errors, not prompt content), all repaired. `needs_review`: 3 of 6 OLD, 0 of 6 NEW. |
| Per-batch merge notes on the chunked path | **Delivered, not effective here (n=1)** | Each of the 21 merges was listed in exactly one batch's notes, and the fill still opened 14 of them with a seam. |

One secondary pattern is worth a larger run rather than a conclusion: the NEW arm delivered more of its
commissioned words (mean fill rate 0.72 against 0.60 on last-train-north, 0.81 against 0.68 on clockwork),
which is what kept it clear of the fill-rate floor.

### 3.4 Read by hand: three merges per fill

The full set (the same three merges in all 13 fills) is in
[merge-readings.md](./evidence/structural-verification-2026-11-20/merge-readings.md). Em-dashes in model
prose are rendered as " - " below and there.

The NEW prompt doing what it says, on the beat "all three ways bring Nia out above the great spring-room"
(`A-cm-new-2`, `n_spring`):

> Nia stood above the great spring-room and saw why the whole menagerie had fallen asleep. The great
> mainspring lay below her like a cracked rib.

The same node in every OLD fill: "All three ways brought Nia out above the great spring-room." Two of the
three NEW fills wrote that sentence too ("All three paths brought Nia out ...", "All three ways led Nia to
..."): the beat's own wording wins two times in three.

The OLD failure on last-train-north's "both readings converge" beats (`A-ltn-old-1`, `g2a0_4`):

> Whether demanded or observed, the conductor's frozen clock offered Vera the same small wrongness.

The NEW failure on the same beats, which the detector does not see (`A-ltn-new-3`, `g3a1_4`; ten more nodes
in that fill open the same way; `A-ltn-new-2`, `g0a2_4`):

> The child had given Vera the same truth from two angles, different only in how the hand was offered.
>
> The letter - read or unread - had opened a door in Vera's chest that she had kept locked for a long time.

The NEW fill that got it right on those beats (`A-ltn-new-1`, `g1a1_4`; all 16 of its route-pair merges open
this way, and none mentions a route):

> The wrongness was gentle and absolute: the child was not a child.

Structure vocabulary leaking into prose, OLD only, from beats that say "BOTTLENECK" (`A-ltn-old-2`,
`p2_who_passengers`): "Vera stood in the centre of the dining car and looked at the faces around her. The
second bottleneck had opened." (6 occurrences across the three OLD fills, 1 across the four NEW fills.)

### 3.5 Why the residual defects survive the new prompt

The skeletons tell the model to commit them, and the beat is nearer the passage than the rule.

- **Seams.** All 16 route-pair merges on last-train-north carry the beat "both readings of X converge on the
  same small wrongness", which demands a claim true of both inbound readings; that is what the hedges are.
  On clockwork every residual NEW seam (4 of 4) is on a merge whose beat says "both routes meet", "all three
  ways bring" or "every path ends here".
- **Recaps.** 33 of last-train-north's 43 decision beats and 23 of clockwork's 29 enumerate the options
  ("offers Vera two ways to read it; one is direct ..., the other is patient"). 93 percent of all recap hits
  in both arms sit on those nodes (crude regex attribution; see `merge-readings.md` for the prose).
- **The converse, inside this round.** The two promoted skeletons carry an explicit instruction in every
  merge beat ("MERGE: readers reach this scene by more than one route; open in the moment, assert only what
  is true on every route, and never say which way the hero came"), and their four fills opened **none** of
  470 merge passages with a seam (detector 0; a hand scan of every candidate opening found only dilemma
  framing such as "either the most sensible thing anyone did today, or ..."). Different skeletons and bands,
  so this is a confounded comparison, but it points the same way: the instruction works when it sits in the
  beat.
- **Labels.** Last-train-north's skeleton ships 20 second-person labels ("Let the hour take you.") and
  clockwork 6; `the-orchard-signal` ships 31 meta labels ("Decide what to do about the paper.") and 19
  second-person. Every fill that left labels alone inherited all of them.

## 4. Run B: state-promoted skeletons

### 4.1 Instruments

| Metric | lantern 1 | lantern 2 | orchard 1 | orchard 2 |
| --- | ---: | ---: | ---: | ---: |
| Outcome | passed | passed | passed | passed |
| State-bearing choices | 15 | 15 | 13 | 13 |
| Conditions and effects exact (raw reply / delivered) | yes / yes | yes / yes | yes / yes | yes / yes |
| Variable names, types, initials intact | yes | yes | yes | yes |
| Variable descriptions rewritten by the model | 3 of 3 | 3 of 3 | 3 of 3 | 3 of 3 |
| Merge nodes / detector seams | 106 / 0 | 106 / 0 | 129 / 0 | 129 / 0 |
| Option recaps | 0 | 0 | 9 | 7 |
| Second-person / meta labels (all the skeleton's) | 2 / 0 | 2 / 0 | 19 / 31 | 19 / 31 |
| Passages with dialogue | 0.091 | 0.076 | 0.223 | 0.145 |
| Story fill rate | 0.639 | 0.750 | 0.881 | 0.887 |
| Fork consequence: false choices / forks | 119 / 300 | 119 / 300 | 10 / 288 | 10 / 288 |
| Est. cost USD | 0.322 | 0.342 | 0.509 | 0.450 |

The model rewrote each variable's `description` into its own plan for the plant ("If true, she learned how
wind actually moves across the ridge by testing one lantern in the worst spot, which later helps ..."). The
normalizer keeps descriptions as leaf text, so this is harmless, and it shows the model planning the link.

### 4.2 Plant to payoff, played in both states

All 22 pairs, with the shortest route to each payoff site with and without the plant, are in
[playthroughs/](./evidence/structural-verification-2026-11-20/playthroughs/B-lkl-new-1.md).

| Variable | Pairs | Would a child see the connection? |
| --- | ---: | --- |
| lantern `did_start_beacon_steps` | 2 x 2 | Yes, 4 of 4. Fill 1: Wren tests a lantern in the worst wind spot, later "Wren had tested the wind on the steps earlier". Fill 2: a glove marked A.T. with a phone number becomes Arthur Tremlett arriving with storm shades. |
| lantern `did_start_sheepfold_turn` | 2 x 2 | Yes, 4 of 4 (Mr Ovens' fuel caches; Dot Mallow's oat biscuits for Mr Ovens). |
| lantern `did_knock_doors_that` | 2 x 2 | Yes, 4 of 4 (Mrs Kitto; Mrs Chen and Mr Riley). |
| orchard `did_ask_whether_notebooks` | 2 x 2 | Yes, 4 of 4 (Ada's mother's loose sheet from 1952; Ada's "October bloom" margin note). |
| orchard `did_go_down_read` | 1 x 2 | Yes, 2 of 2, one with a prop mismatch (copied onto "the back of his hand", recalled from "the exercise book"). |
| orchard `did_find_who_wrote` | 2 x 2 | Thin in 3, unearned in 1. The plant yields the name "D. Faulks", but `n04d0` shows the signature to every reader and two labels name Faulks, so knowing the name is not something only this reader has. |

Best pair (`B-lkl-new-1`). The plant, after "Knock on the doors that used to say yes":

> Wren knocked, and old Mrs Kitto opened it before the echo had died. She had hung lanterns on this ridge for
> thirty years before her knees gave out, ... "I've been waiting," she said, and she was already putting on
> her coat.

And the payoff only that reader gets, when the hero asks Mr Ovens for the quad bike:

> Old Mrs Kitto had known Mr Ovens for forty years. She picked up the phone in the hall and spoke five words
> into it. Two minutes later, the quad's engine started in his yard.

Worst pair (`B-os-new-1`, `cq_payoff_did_find_who_wrote`). The plant gave only a name written in an exercise
book; the payoff claims knowledge nobody wrote: "Jonah recalled what he had learned about Faulks: the
surveyor's other work, the pattern of reports that always matched what the client wanted."

**Defects the instruments did not see** (a keyword leak scan over every node reachable with the variable
false, then read):

- `B-lkl-new-2`, `fn_ovens`, on a route without the sheepfold plant: "It was not the careful,
  biscuit-offering politeness of earlier."
- `B-os-new-1`, ending `e05_0`, reachable without the gate plant: "What Jonah was left with was a photo of a
  notice on a gate".
- `B-lkl-new-2`, `cq_payoff_did_start_beacon_steps` opens "Arthur Tremlett was still at the sheepfold gate",
  an event written only into the OTHER payoff site; a reader who reaches this site first has never met him.

Two structural facts temper all of this: these payoffs are rare (a uniform random reader reaches any payoff
in 4.3 percent of `the-lantern-keepers-list` plays and 3.0 percent of `the-orchard-signal` plays, from 20,000
simulated plays each, although about two thirds of plays set at least one plant), and the payoff directive is
structural ("show the earlier choice returning"), so every link above was invented by the model. It invented
well when the plant scene had to name something concrete (the `cq_plant` directive asks for exactly that) and
when the hub after a planting choice gave it room; it invented badly when the plant's content was already
public.

### 4.3 Verdict per hypothesis (Run B)

| Claim | Verdict at n = 2 fills per skeleton |
| --- | --- |
| Conditions and effects preserved exactly | **Supported**: 4 of 4, in the raw reply as well as after normalization. |
| Merges written state-neutral | **Mostly**: no seam in any of the four fills (106 and 129 merges each; detector and a hand scan agree), but 2 of 4 fills leak a plant into an unplanted route. |
| Payoffs visibly connect to their plants | **Mostly**: 18 of 22 clear, 3 thin, 1 unearned; the weak ones share one cause (a plant whose content every reader already has). |

## 5. What this does and does not show

It shows, on these four skeletons and this model: the new prompts do not hurt the gate or the state contract;
they cut seams where the skeleton's merge beats are physical ("both routes meet at the savanna arch") and do
not where the beats demand an epistemic convergence; the agency rules lose to contradicting beats; the seam
detector is not fit to measure a prompt change aimed at it; and state promotion's contract mechanics hold.

It does not show a catalog-wide effect, an effect on any other model, an effect under reskinned briefs, or
anything about how a child actually reads these books. Three fills per arm cannot separate an effect smaller
than the fill-to-fill spread, which on last-train-north is 3 to 17 seams within one arm.

## 6. Recommended next steps

> **Status: frozen 2026-11-21 (owner decision D2), pending the decision report.** Under
> [ADR-033](./adr/adr-033-story-plan-meaning-layer.md) and WP-0.1 of the
> [implementation plan](./story-plan-implementation-plan.md), the steps below that reach for new skeletons, strict remediation of the failing shells, mutation, flywheel or diversity rounds are not to be started; step selection follows the plan's phases instead. Nothing here is deleted or revoked; it stays merged
> and unused until the plan's decision report (WP-4.4, owner decision D10) resumes, restricts or retires it.

1. **Fix the skeleton text, not the prompt.** Add a beat lint to `check_skeleton.py` (route-merge language in
   merge beats, option enumeration in decision beats, second-person and meta labels on third-person shells),
   then rewrite the beats and labels of the four skeletons measured here. This is the cheapest lever the
   round found and it does not depend on the model obeying a rule.
2. **Repair `merge_seams` recall before using it again as evidence or as an approver advisory**: add the
   appositive hedge ("X, or Y,") and "the same truth from two angles" shapes, with this round's sentences as
   fixtures, and re-score against the hand counts in the evidence bundle.
3. **Keep the prompt change.** It is harmless to the gate, clearly better on clockwork, and its higher fill
   rate deserves the larger run below. Do not count it as having fixed recaps, labels or setbacks.
4. **Roll out state promotion with two guards**: reject plant candidates whose content is visible on routes
   that did not plant it (`orchard`'s `did_find_who_wrote`), and add a plant-leak check that flags plant
   vocabulary on nodes reachable with the variable false. Iterate the payoff directive to name the planted
   object and to forbid referring to another payoff site.
5. **Fix the cascade's model attribution.** The worker stamps a job with `FallbackProvider.model`, which is
   the LAST leg that answered; `A-cm-old-3` would have been recorded as a `claude-sonnet-4.6` book because one
   106-token Stage D call fell over, although v4-pro wrote the fill.
6. **Then a larger run**, after items 1 and 2: 10 skeletons x 3 fills x 2 arms is 60 fills, about 20 to 24 USD
   at this round's measured 0.30 to 0.40 USD per fill, scored by the repaired detector plus a hand audit of
   a sample.

## 7. Lessons recorded

`AL-796` through `AL-801` in the [authoring lessons log](./authoring-lessons-log.md), each cited by a
`UW-C495` through `UW-C500` row in the [unscheduled work register](./unscheduled-work-register.md).
