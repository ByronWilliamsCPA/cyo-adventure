# W16 pilot: fill-prompt guide ablation

> **Provenance.** Every fill and every number in this directory is model-generated and
> model-measured. No human and no child has read any of it. Deterministic measures are the
> evidence class throughout; there is no judge panel anywhere in this pilot.

Run 2026-08-15 on branch `claude/story-quality-techniques-40jyg6`. The programme has ablated
decoding parameters (W8), models (W9), premises (W10), and context composition (W14), and has
never ablated PROMPT CONTENT. The skeleton-free alternatives proposal (section 9, step 0d, and
section 11.3 Layer 1 item 2) proposed exactly this and it was never run: the drafting guide is
one fixed text spliced into every generation call, suspected of acting as a shared armature,
with no fill-stage measurement behind the suspicion.

## Design

Same bound skeleton (`bound_skeleton.json`: `the-school-garden-mystery` bound to a fresh
rooftop-kitchen-garden theme via `binding.json`), same theme brief, same fill contract, same
single-pass no-revision protocol. One variable: the `{drafting_guide}` text inside the
production `fill.md` template.

| arm | guide | words |
| --- | --- | --- |
| FULL | production guide as a fill author sees it | 3,517 |
| NOCRAFT | FULL minus the whole "Craft for Delight" section | 2,558 |
| MIN | constraints-only block (voice, 5-8 FK window, 5-8 words/node, endings) | 101 |

Two isolated authors per arm (seats S1, S2), six fills. Authors receive one prompt file each,
byte-identical within an arm; they are not told there are arms, seats, or an experiment.

## Pre-registered questions

Fixed before any author ran; the full statements are in `build_variants.py`'s docstring.

1. **Armature.** Within-arm cross-author convergence (shared four-grams per 1000, bodies
   only, per-node gramming): prediction FULL at or above MIN, from the convergent-elaboration
   mechanism (brief section 21). Falsifier: FULL within 1.0 per 1000 of MIN.
2. **Craft cost.** Deterministic craft deltas (FK and in-band, words per node, dialogue
   share, second-person density per 1000 words, told-emotion rate) reported per arm. One
   pre-registered non-effect: FK in-band should not differ materially across arms, since
   every arm carries the reading-level table.

**Status: pilot.** One author pair per arm sizes effects for a real W16 run; per the
measurement workplan's admission rule 3, nothing here is promoted to a gate or a production
prompt change on this run alone.

## Protocol notes and deviations, declared up front

- The contract's own `default_binding` is rejected by its own `legacy_lexicon` rule, so the
  documented no-bindings reference render of `bind_theme.py` is unusable on this skeleton; a
  fresh binding was authored instead (a tooling lesson, logged in the authoring lessons log).
- Choice labels are frozen byte-identical (a documented deviation from `fill.md`'s
  label-rewrite rule) so the measured surface is bodies only.
- The FULL guide strips YAML frontmatter and the Related Documents link list, which are
  meaningless inside a prompt; NOCRAFT retains two textual cross-references to the removed
  section (retained-section text is not edited).
- The second-person-density measure computed here doubles as a prototype of the deferred
  `W2.3` fill-gate check (drafting guide, Voice section), which is not built anywhere yet.

## Files

- `build_variants.py`, `binding.json`, `bound_skeleton.json`, `guide_*.md`, `PROMPT_*.md`:
  the deterministic rig.
- `<ARM>/S<n>/filled.json`: the six fills.
- `results.md`: measurements, written after the fills and never edited thereafter.
