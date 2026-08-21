# Known-answer validation result: FAILED, and the failure is informative

Run 2026-08-21, register row `S-0` (section F of the
[diversity test register](../../diversity-test-register.md)). Written after the verdicts, per this
directory's README; not edited thereafter.

> **Provenance.** All six raters are model raters: independent, blind subagent sessions of the
> serving frontier model (session model id `claude-fable-5`), one prompt each, no repo access, no
> knowledge of arms or of the experiment. Verdicts were checked with `protocol.py validate` against
> the pre-registered contract before being recorded; all six satisfy it.

## Deviation carried in from registration

The pre-registered pairs (three D-7c same-armature pairs, one D-7c-vs-W16 control) were never
committed: PR #715 merged this directory's rig and the D-7c/W16 rigs, and the fills stayed on the
deleted working branch. Register row `S-0` re-based the validation before any rater ran:
same-armature pairs `d7-stratified-plan` C vs D and `d7b-bare-names` C vs D; control
`d7-stratified-plan/filled_C` vs `mutation-per-request-pilot/book-s-the-midnight-museum`
(different graph, 26 vs 95 nodes; different world, clocktower vs museum; **same band**, where the
original control also crossed band). Pass rule tightened from 2-of-3 same-armature to 2-of-2. Two
counterbalanced raters per pair.

## Verdicts

| Pair | Order | same_adventure | first_yes | distinctness |
| --- | --- | --- | --- | --- |
| d7-glossed C/D (same armature) | C then D | yes | 2 | 1 |
| d7-glossed C/D (same armature) | D then C | yes | 2 | 1 |
| d7b-bare C/D (same armature) | C then D | yes | 2 | 1 |
| d7b-bare C/D (same armature) | D then C | yes | 2 | 1 |
| control: clocktower vs museum | clocktower first | yes | 41 | 2 |
| control: clocktower vs museum | museum first | yes | 12 | 2 |

Both same-armature pairs fired, all four raters, at scene 2 (the manual protocol's history lands at
2 to 4). **The control also fired, both raters.** Per the pre-registered rule ("a rater that fires
on the control is recorded as a failed instrument, not softened into a caveat"), and per `S-0`'s
margin ("any miss = instrument fails"):

**The automated recognition protocol is NOT validated. E2 (`S-2`) and E4 (`S-4`) perceptual
confirmations are blocked on a validated instrument; their deterministic endpoints stand. Every
perceptual claim inherited from the mutation pilot (the position-3 recognition, the 2.0/5 score) is
marked unconfirmed, as the sourcing plan's E0 falsifier branch pre-registered.**

## What the failure looks like from inside

Two observations, recorded for the repair and not as softening:

1. **The control raters cite real shared structure, not noise.** Both name the same chain: rooms
   off a hub each teaching a piece of a cipher, a central mechanism that jams when forced, a
   founder's letter in a locked room, and tell-the-town / keep-it-secret / take-the-treasure
   endings. The clocktower book and the museum book do substantially contain that chain. This is
   the programme's own catalog-convergence finding (D-6 idiom floor, Q-3c premise mode) appearing
   inside a "different graph, different world" pair. The re-based control may therefore not be a
   valid negative control at all: within one band, two catalog-lineage mysteries can genuinely be
   the same adventure at the decision level. The original pre-registered control crossed band and
   world into a school-garden book precisely to avoid this, and it was the artifact we did not
   have.
2. **The two pre-registered criteria were asymmetric, and the asymmetry is where the failure
   lives.** Same-armature pairs fire on first-yes at or before scene 5; the control was required
   simply never to be called same-adventure, at any position. The control's first-yes positions are
   12 and 41, against 2/2/2/2 for the same-armature pairs, and its distinctness scores are 2
   against 1. Under a position-bounded firing rule (yes at or before scene 5) the instrument would
   have separated all six verdicts correctly. That re-specification cannot be adopted on this data,
   because these known answers are now seen; it is the hypothesis the next validation tests.

## What unblocks the instrument

1. Author or recover a true cross-band control (a 5-8 or W16-style book against a 10-13 clocktower
   book), since a same-band catalog-lineage pair is now suspected of being convergence-bearing.
2. Re-specify the firing rule symmetrically (same-adventure = yes with first-yes at or before
   scene 5, both criteria) in `protocol.py`'s docstring, as a new pre-registration.
3. Re-run with fresh known-answer pairs that no rater prompt in this run touched, two
   counterbalanced raters per pair, and record here.

Until all three happen, the manual protocol remains the only recognition instrument with any
validation history, and it is expensive; the sourcing programme proceeds on deterministic
endpoints, which is the branch its plan pre-registered.
