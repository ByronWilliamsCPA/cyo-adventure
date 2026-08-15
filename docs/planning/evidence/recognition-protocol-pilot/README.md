# Recognition protocol, automated: pilot and known-answer validation

> **Provenance.** Rater verdicts here are model judgments (the weak evidence class); the point
> of this directory is to validate the automated instrument against known answers before
> anything downstream trusts it, exactly as brief section 20 requires of any new instrument.

Run 2026-08-15 on branch `claude/story-quality-techniques-40jyg6`.

The blind same-adventure read (book one in full, book two scene by scene, first-commitment
position) is the single most decision-bearing instrument in the diversity programme: it
produced the topology finding (framework doc section 4, S5 through S9), and every run of it so
far was a hand-built prompt in a session, with no frozen protocol, no fixed blinding rule, and
no reading-order definition. `protocol.py` freezes all three (child-visible surfaces only, node
ids withheld, breadth-first reading order, sequential commitment) so the protocol stops
drifting between experiments, and so it can someday run as a catalog gate rather than an
experiment.

## Pre-registered known answers

Fixed before any rater ran; full statements in `protocol.py`'s docstring.

1. The three D-7c same-armature pairs (C vs D within each arm) must be called same-adventure
   with first-yes position at or before scene 5 on at least two of three.
2. A cross-skeleton control (a D-7c clocktower book vs a W16 school-garden book) must not be
   called same-adventure.
3. Keep iff both hold. A rater that misses same-armature pairs, or fires on the control, is
   recorded as a failed instrument, not softened into a caveat.

## Deviations and limits, declared

- Single-prompt sequential-commitment approximation of a true multi-turn reveal (declared in
  the docstring; the manual runs used the same approximation).
- Rater tier is recorded per verdict file; verdicts across tiers are not pooled.
- One rater per pair in this pilot; the manual protocol's counterbalanced two-rater design is
  the production form.

## Files

- `protocol.py`: prompt builder, blinding, reading order, verdict schema, and the
  verdict validator.
- `verdict_<pair>.json`: one rater verdict per pair. Not yet present: no rater has run.
- `results.md`: the validation outcome, written after the verdicts and never edited.
  Not yet present.

## Running it

```bash
# build the rater prompt for one ordered pair
python protocol.py build <book_one.json> <book_two.json> --out prompt.md

# check a returned verdict against the pre-registered contract, before recording it
python protocol.py validate verdict_<pair>.json --book-two <book_two.json>
```

`validate` enforces the verdict rules that were pre-registered but previously
unchecked: one `per_scene` entry per Book Two scene, entries exactly `yes` or `no`,
no `yes` reverting to `no`, `first_yes_position` agreeing with the array, and
`same_adventure` agreeing with both. A verdict that fails is a failed run of the
instrument, per known answer 3 above; it is not edited to pass.
