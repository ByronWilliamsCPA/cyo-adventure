"""Build the W16 pilot: three drafting-guide variants and their fill prompts.

The measurement workplan (W8, W9, W10, W14) varies decoding, model, premise,
and context. Nothing in the programme has ever varied the PROMPT CONTENT: the
drafting guide is spliced into every generation stage as one fixed text, and
the diversity recommendation (skeleton-free alternatives proposal, section
11.3, Layer 1 item 2) already suspects that "the shared prompt is a fixed
armature" without a fill-stage measurement behind it. This pilot supplies the
missing measurement shape: same bound skeleton, same theme brief, same fill
contract, three guide variants, two isolated authors per variant, deterministic
scoring only.

Arms:

- FULL: the production guide text as a fill author sees it (frontmatter and
  the Related Documents link list stripped; both are meaningless in a prompt).
- NOCRAFT: FULL minus the whole "Craft for Delight" section, the guide's only
  positive-craft (unenforced) section.
- MIN: a compact constraints-only block: voice rules, the 5-8 reading window,
  the 5-8 words-per-node envelope, and the endings note. About one tenth the
  FULL text.

Pre-registered questions, fixed before any author runs:

1. Armature: does within-arm cross-author convergence (shared four-grams per
   1000, bodies only, per-node gramming) rise with guide bulk? Prediction,
   from the convergent-elaboration mechanism (brief section 21): FULL is at or
   above MIN. Falsifier: FULL within 1.0 per 1000 of MIN, which would say the
   guide is not a fill-time armature and the Layer-1 "parameterize the guide"
   item loses its fill-stage premise.
2. Craft cost: do the deterministic craft signals (FK grade and in-band rate,
   words per node, dialogue share, second-person density, told-emotion rate)
   move when the craft section is removed? No direction is pre-registered
   except one: FK in-band should NOT differ materially across arms, because
   every arm carries the reading-level table.

Status: a PILOT for effect sizes, per the workplan's admission rule 3
(deterministic measures enter as reported statistics first). No production
adoption decision is taken from an n-of-one-pair-per-arm run.

Protocol constants, all arms: the bound skeleton built by bind_theme.py from
`skeletons/5-8/the-school-garden-mystery.json` with `binding.json` (a fresh
rooftop-kitchen-garden theme; the contract's own default_binding is rejected
by its own legacy lexicon, a tooling lesson logged separately); one fixed
theme brief; labels frozen byte-identical (a documented deviation from
fill.md's label-rewrite rule, so the measured surface is bodies only); single
pass; no revision round; authors never told there are arms or siblings.
"""

from __future__ import annotations

from pathlib import Path

HERE = Path(__file__).parent
REPO = HERE.parents[3]
TPL = REPO / "src" / "cyo_adventure" / "generation" / "templates"

THEME_BRIEF = (
    "A curious kid helper solves a gentle mystery in a rooftop kitchen garden "
    "behind a bakery: something small has been nibbling the basil at night. "
    "Tone: gentle mystery. Themes: kindness, curiosity, patience, nature. "
    "The reader is 5 to 8 years old."
)

DIFF_DIRECTIVE = (
    "This is the first story generated from this skeleton for this family. "
    "No differentiation constraints apply."
)

SCHEMA_RULES = """\
- Every `<<FILL ...>>` body must be replaced by final prose; leaving any
  directive text in a body fails validation (PL-27).
- Do not change: any `id`, any `target`, any `condition`, any `effects` or
  `on_enter`, `is_ending`, `variables`, `start_node`, or any `metadata` field.
- Ending nodes keep their `ending` block exactly as given, including `title`.
- The story must remain valid JSON with the same shape as the input.
- Never use the em-dash character anywhere in the output.
"""

MIN_GUIDE = """\
## Constraints

Voice: second person ("you"), present tense, for the whole book. Choice labels
are imperative action phrases. Endings state what happens; they never ask a
question.

Reading level (age 5-8): Flesch-Kincaid grade target 2.0, acceptable window
1.0 to 3.0. Short, simple sentences. Familiar vocabulary. One idea per
sentence.

Node length (age 5-8 prose): aim for a story-wide mean of 70 words per node,
advisory band 50 to 95, hard per-node maximum 155. A tense beat may run short;
no node may exceed the maximum.

Endings: at least two distinct endings exist in the structure; do not add or
remove any.
"""

LABEL_FREEZE = """\
## Choice labels (pilot override)

For this fill, keep every choice `label` byte-identical to the input. Do not
rewrite, rephrase, or re-theme any label. The labels are already written for
this theme.
"""


def guide_variants() -> dict[str, str]:
    """Build the three guide texts from the production template."""
    raw = (TPL / "drafting_guide.md").read_text(encoding="utf-8")
    lines = raw.splitlines()
    # Strip YAML frontmatter (first two '---' fence lines) and everything from
    # the Related Documents rule onward.
    assert lines[0] == "---"
    close = lines.index("---", 1)
    body = lines[close + 1 :]
    rel = next(i for i, l in enumerate(body) if l.startswith("## Related Documents"))
    # The '---' separator sits immediately above the header; cut there.
    full = "\n".join(body[: rel - 1]).strip() + "\n"

    craft = full.index("## Craft for Delight")
    after = full.index("## Concept Brief Field List")
    # Remove the craft section; the separator above it survives in full[:craft].
    # Two textual cross-references to the section remain in the reading-level
    # section; they are retained text and are deliberately not edited.
    nocraft = full[:craft] + full[after:]
    return {"FULL": full, "NOCRAFT": nocraft, "MIN": MIN_GUIDE}


def render_prompt(guide: str, skeleton_json: str) -> str:
    """Render fill.md with this pilot's constants and the given guide text."""
    tpl = (TPL / "fill.md").read_text(encoding="utf-8")
    out = (
        tpl.replace("{drafting_guide}", guide)
        .replace("{schema_rules}", SCHEMA_RULES)
        .replace("{skeleton_with_fill_directives}", skeleton_json)
        .replace("{theme_brief}", THEME_BRIEF)
        .replace("{differentiation_directive}", DIFF_DIRECTIVE)
    )
    # Two pilot overrides, appended where fill.md states the task: freeze
    # labels, and write to a file instead of replying with JSON.
    out = out.replace(
        "## Your Task",
        LABEL_FREEZE + "\n## Your Task",
        1,
    )
    out += (
        "\n\n## Output override (pilot)\n\n"
        "Instead of replying with the JSON, WRITE the complete Storybook JSON "
        "to the file `filled.json` in your working directory, then reply with "
        "one line: the total word count of your filled bodies.\n"
    )
    return out


def main() -> int:
    """Write guide variants and prompts next to this script."""
    skeleton_json = (HERE / "bound_skeleton.json").read_text(encoding="utf-8")
    for arm, guide in guide_variants().items():
        (HERE / f"guide_{arm}.md").write_text(guide, encoding="utf-8")
        (HERE / f"PROMPT_{arm}.md").write_text(
            render_prompt(guide, skeleton_json), encoding="utf-8"
        )
        print(f"{arm:8s} guide words={len(guide.split()):5d}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
