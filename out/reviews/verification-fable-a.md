# Verification of blind-spot report A (2026-08-14)

The report claims 12 findings. This file records what I checked directly, before
any of it is acted on, because a review is a claim and not evidence.

## F1, "merge nodes assert state never established on the taken path"

Cited on three books. **Verified on two, refuted on the flagship.**

| Instance | Claim | Result |
| --- | --- | --- |
| `the-night-market` `f_string` / `e_up_chorus` launch "the folded wish" that the `f_lantern` and `f_friends` lanes never write | REFUTED | all 15 paths to each of `f_string`, `e_up_chorus`, `f_lantern` and `f_friends` pass through a node depicting the writing or folding act |
| `baking-day-with-grandma-vole` `n_seeds_ok` | VERIFIED | the acorn is introduced at `n_seeds` ("On top sat the shiny acorn"), then `n_seeds_ok` states "The shiny acorn was safe in Grandma Vole's pocket". The word "pocket" appears nowhere earlier on the only path to that node. Nobody pockets it |
| `the-sleepy-little-star` `n_almost` | VERIFIED | "Or hold her moonbeam and shine all at once?" `moonbeam` occurs in exactly two nodes, `n_slide` and `n_almost`. `n_almost` has three incoming paths and only one passes through `n_slide`, so on two of three readings the phrase is a definite reference to an object the reader has never met |

So the pattern is real and the headline example is wrong. Both halves matter: the
class earns work, and the specific node ids in the report cannot be pasted into a
ticket without being re-checked.

## Why this is worth pursuing, and why W15 is not a precedent against it

W15 proposed an author-declared secrets list plus a checker, and was DROPPED
because catching a paraphrase is an entailment problem and no lexical resource in
the dependency set answers one (`AL-355`).

This is a different problem with a different solution. It does not ask whether a
secret leaked in other words. It asks whether a **definite reference** ("the
folded wish", "her moonbeam", "the shiny acorn was safe in her pocket") is
reachable by a path that never introduced its referent. That is graph dominance
plus lexical first-mention, both of which this repository already has: W1's
`validator/paths.py` enumerates the paths, and first-mention is a string search.
No entailment is required.

The honest limit is the converse: it can only see referents that are *named*
consistently. A state established as "she tucked it away" and asserted as "safe
in her pocket" shares no noun, and this catches nothing there. That is the same
wall W15 hit, so the check should be scoped to named entities and stated as
such rather than sold as information-state coverage.

## Not yet verified

F2 to F12 are recorded as claims only. F5 (physics of the balloon flipping
between branches) and F6 (revisitable nodes replaying text that contradicts
accumulated state) look checkable by the same machinery and are the next two
worth testing. F8 and F9 are safety and guardian-signal judgements that no
deterministic check settles, and belong to a human.
