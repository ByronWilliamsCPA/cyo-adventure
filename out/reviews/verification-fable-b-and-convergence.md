# Blind-spot reviews: what two independent readers agreed on, and what survived checking

Two Fable readers took five books each, with the full current coverage in hand and
instructions to report only what falls outside it. `the-big-red-balloon` and
`the-night-market` were given to both, so agreement could be measured rather than
assumed.

## The convergence

Five classes were named independently by both readers:

| Class | Reader A | Reader B |
| --- | --- | --- |
| A node asserts state the taken path never established | F1, on 3 books | flagship, on tide-pool endings |
| Revisitable nodes replay text contradicting accumulated state | F6 | hub reset on tide-pool and night-market |
| A named character disappears for most of a book | F3, Ada | Ada, same book |
| Imitable unsafe practice presented as triumph | F8 | solo flame, snow tunnels, hand-feeding wild rabbits |
| Protagonist name collisions across books | F10, two Milos and two Pips | two of five books star a Milo |

Two readers, different book sets, no contact, same five classes. That is the
strongest evidence available here that these are properties of the corpus rather
than of a reader's taste.

## What I verified myself

**Reader B's flagship: VERIFIED, and structurally provable.**

`the-tide-pool-rescue` declares `variables: []` under a `loop_and_grow` topology.
It therefore tracks no state at all, while its endings assert accumulated history:

| Ending | Distinct animals named in its text | Fewest a reader can have met on a path reaching it |
| --- | --- | --- |
| `e_story` | 3 | 1 |
| `e_names` | 4 | 1 |
| `e_toast` | 4 | 1 |
| `e_song` | 4 | 1 |

`e_tide_snail` says "Three rescues by you, and one by the tide" and is reachable
by `n_start -> n_walk -> n_meet -> t_fi_cr -> cr_scene -> cr_meet -> cr_plan ->
cr_win -> cr_thanks -> e_tide_snail`, which contains exactly one rescue.

This is the cleanest instance of the shared class because the contradiction needs
no interpretation: a book with no variables cannot know how many rescues occurred,
so any ending that states a count is asserting something the engine cannot
support.

**Reader A's flagship: REFUTED.** All 15 paths to `the-night-market`'s `f_string`,
`e_up_chorus`, `f_lantern` and `f_friends` pass through a node that writes and
folds the wish. Its other two instances hold (`baking-day` `n_seeds_ok` pockets an
acorn nobody pocketed; `the-sleepy-little-star` `n_almost` offers "her moonbeam" on
two of three paths that never mention one).

So: pattern real, one flagship wrong, one flagship right and provable. Node ids
from these reports need re-checking before they reach a ticket.

## The check this earns, and why W15 is not a precedent against it

W15 was dropped because catching a paraphrased leak is entailment (`AL-366`).
This is a different question with a cheaper answer, in two tiers:

1. **Declared-state tier, deterministic and exact.** For any ending or merge node
   asserting a count or a set ("three rescues", four names), the book must declare
   variables that can carry it. `the-tide-pool-rescue` fails on inspection of its
   own metadata. No prose understanding required.
2. **Named-entity tier, deterministic and approximate.** For each definite
   reference to a named entity in node N, check that every path to N passes
   through a node introducing it. W1's `validator/paths.py` already enumerates the
   paths; first mention is a string search.

The honest limit is the converse case, which both tiers miss: state established as
"she tucked it away" and asserted as "safe in her pocket" shares no noun. That is
the same wall W15 hit, so this must be scoped and sold as named-entity continuity
rather than as information-state coverage.
