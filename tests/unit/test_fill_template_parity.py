"""Parity checks across the four fill prompt templates.

A ruling that changes what the model is told about a fill must reach every
template that drives a fill, not just the one the ruling was written against.
There are four of them, and they form two independent axes:

* one-shot (``fill.md``) against chunked (``fill_subset.md``);
* unbound against bound (``fill_bound.md``, ``fill_subset_bound.md``), the
  variants that additionally fence validated theme values.

``AL-531`` recorded the freeze-split ruling reaching only some sites of record.
The narrative-person ruling then repeated it: the clause landed in ``fill.md``
while ``check_prose_craft.py`` began failing books on
``metadata.narrative_person``, so a chunked or bound fill was gated on an
instruction it was never given. Chunking is selected for the largest books and
binding for themed ones, so the gap fell on the hardest cases rather than the
rare ones.

These tests compare clause bodies byte for byte rather than checking that a
keyword appears, because a paraphrase that drifts is the same defect wearing a
passing test.
"""

from __future__ import annotations

import re
from importlib.resources import files

import pytest

_TEMPLATES = files("cyo_adventure.generation.templates")

FILL_TEMPLATES = (
    "fill.md",
    "fill_bound.md",
    "fill_subset.md",
    "fill_subset_bound.md",
)

# Each entry is a clause every fill template must carry, keyed by its heading
# text. Add a row here when a ruling adds a section to fill.md; the parity test
# then fails until the other three templates carry it too.
SHARED_CLAUSE_HEADINGS = ("Narrative person",)

# Clauses the one-shot pair shares but the chunked pair cannot: the one-shot
# model returns a whole document and ``normalize_fill`` restores only the frozen
# fields, so both writable leaves apply. ``merge_fill_batch`` never reads
# variables from a batch reply, so the chunked pair states the ending-title half
# alone.
ONE_SHOT_CLAUSE_HEADINGS = ("What you may rewrite",)

ONE_SHOT_TEMPLATES = ("fill.md", "fill_bound.md")
CHUNKED_TEMPLATES = ("fill_subset.md", "fill_subset_bound.md")

# Wordings that re-freeze a leaf the 2026-08-21 ruling made writable (sections
# 8.2 and 8.3). The new clause being present is not enough: a template that also
# keeps one of these tells the model both things at once and it picks
# unpredictably, which is the defect this file exists to catch.
REFROZEN_LEAF_PATTERNS = (
    (
        r"[Ee]nding `?titles?`?[^.\n]*\bare final\b",
        (
            "ending titles are writable theme content (ruling 8.3); "
            "normalize_fill and chunking._merged_ending both accept a "
            "rewritten one"
        ),
    ),
    (
        r"`variables` declarations",
        (
            "a variable's `description` is writable theme documentation "
            "(ruling 8.2); only its machine fields are frozen"
        ),
    ),
    (
        r"\bending blocks\b",
        (
            "freezing the ending block wholesale re-freezes its `title`; "
            "name the frozen keys (`id`/`kind`/`valence`) instead"
        ),
    ),
)


def _read(name: str) -> str:
    """Return the text of a bundled template.

    Args:
        name: Template file name, for example ``"fill.md"``.

    Returns:
        The template's decoded contents.
    """
    return _TEMPLATES.joinpath(name).read_text(encoding="utf-8")


def _clause_body(text: str, heading: str) -> str | None:
    """Extract one clause body from a template, ignoring its heading level.

    The one-shot template nests its clauses one level deeper than the chunked
    one, so the heading level is deliberately not part of the comparison.

    Args:
        text: Full template text.
        heading: Heading text to locate, without leading hashes.

    Returns:
        The clause body with surrounding blank lines stripped, or None when
        the template does not carry the clause at all.
    """
    match = re.search(
        rf"^#{{2,4}} {re.escape(heading)}\n\n(.*?)(?=\n^#{{2,4}} |\Z)",
        text,
        re.MULTILINE | re.DOTALL,
    )
    return match.group(1).strip() if match else None


@pytest.mark.parametrize("heading", SHARED_CLAUSE_HEADINGS)
@pytest.mark.parametrize("name", FILL_TEMPLATES)
def test_every_fill_template_carries_each_shared_clause(
    name: str, heading: str
) -> None:
    """A shared clause is present in all four fill templates."""
    assert _clause_body(_read(name), heading) is not None, (
        f"{name} is missing the {heading!r} clause. A fill driven by this "
        f"template is gated on an instruction it never receives."
    )


@pytest.mark.parametrize("heading", SHARED_CLAUSE_HEADINGS)
def test_every_shared_clause_body_is_identical_across_templates(
    heading: str,
) -> None:
    """The four templates state a shared clause in exactly the same words."""
    bodies = {name: _clause_body(_read(name), heading) for name in FILL_TEMPLATES}
    distinct = set(bodies.values())
    assert len(distinct) == 1, (
        f"The {heading!r} clause has drifted apart across templates: "
        f"{ {name: (body or '')[:60] for name, body in bodies.items()} }"
    )


def test_the_bound_variants_are_supersets_of_their_unbound_originals() -> None:
    """Each bound template carries every heading its unbound original has.

    ``prompts.py`` documents the bound variants as their unbound original plus
    the bound-fill blocks. A heading present upstream and absent downstream is
    a ruling that reached one path only, which is the shape this module exists
    to catch.
    """
    pairs = (("fill.md", "fill_bound.md"), ("fill_subset.md", "fill_subset_bound.md"))
    for unbound, bound in pairs:
        unbound_headings = set(
            re.findall(r"^#{2,4} (.+)$", _read(unbound), re.MULTILINE)
        )
        bound_headings = set(re.findall(r"^#{2,4} (.+)$", _read(bound), re.MULTILINE))
        missing = unbound_headings - bound_headings
        assert not missing, f"{bound} is missing headings from {unbound}: {missing}"


@pytest.mark.parametrize("heading", ONE_SHOT_CLAUSE_HEADINGS)
def test_the_one_shot_templates_state_their_shared_clause_identically(
    heading: str,
) -> None:
    """``fill_bound.md`` lifts the one-shot-only clause from ``fill.md`` verbatim.

    The chunked pair is excluded on purpose: its merge whitelist is narrower, so
    it must not repeat the variable-description half of this clause.
    """
    bodies = {name: _clause_body(_read(name), heading) for name in ONE_SHOT_TEMPLATES}
    assert all(bodies.values()), (
        f"The {heading!r} clause is missing from "
        f"{[name for name, body in bodies.items() if not body]}."
    )
    assert len(set(bodies.values())) == 1, (
        f"The {heading!r} clause has drifted between the one-shot templates: "
        f"{ {name: (body or '')[:60] for name, body in bodies.items()} }"
    )


def _ending_title_rule(text: str) -> str | None:
    """Return the chunked output-contract rule that governs ``ending_title``.

    The rule's number is stripped so a renumbering of the surrounding list is
    not read as a drift in what the rule says.

    Args:
        text: Full template text.

    Returns:
        The rule text without its ordinal, or None when no numbered rule in the
        template mentions ``ending_title``.
    """
    for line in text.splitlines():
        stripped = line.strip()
        if re.match(r"^\d+\. ", stripped) and "`ending_title`" in stripped:
            return re.sub(r"^\d+\. ", "", stripped)
    return None


def test_the_chunked_templates_state_the_ending_title_rule_identically() -> None:
    """Both chunked templates carry the same ``ending_title`` rule.

    ``merge_fill_batch`` accepts ``ending_title`` on either chunked path, so a
    template that omits the rule asks for less than the merge would take and the
    skeleton's title survives the reskin.
    """
    rules = {name: _ending_title_rule(_read(name)) for name in CHUNKED_TEMPLATES}
    assert all(rules.values()), (
        f"No numbered output rule mentions `ending_title` in "
        f"{[name for name, rule in rules.items() if not rule]}. The merge "
        f"accepts the field, so the prompt has to ask for it."
    )
    assert len(set(rules.values())) == 1, (
        f"The `ending_title` rule has drifted between the chunked templates: "
        f"{ {name: (rule or '')[:60] for name, rule in rules.items()} }"
    )


@pytest.mark.parametrize("name", CHUNKED_TEMPLATES)
def test_the_chunked_output_example_shows_ending_title(name: str) -> None:
    """The chunked reply example carries the key the merge whitelist accepts."""
    assert '"ending_title"' in _read(name), (
        f"{name}'s output example never shows `ending_title`, so a model "
        f"following the example alone never returns one."
    )


@pytest.mark.parametrize(("pattern", "why"), REFROZEN_LEAF_PATTERNS)
@pytest.mark.parametrize("name", FILL_TEMPLATES)
def test_no_fill_template_refreezes_a_writable_leaf(
    name: str, pattern: str, why: str
) -> None:
    """No template still freezes a leaf the 2026-08-21 ruling opened up."""
    match = re.search(pattern, _read(name))
    assert match is None, (
        f"{name} still says {match.group(0)!r}, which contradicts the clause "
        f"granting the rewrite: {why}."
    )


@pytest.mark.parametrize("name", FILL_TEMPLATES)
def test_no_template_states_a_shared_clause_twice(name: str) -> None:
    """A heading must appear once per template, so parity compares the real body.

    ``_clause_body`` uses ``re.search``, which returns the FIRST match, so a
    template carrying a heading twice is compared on its first copy and its
    second is invisible to every other check in this module. That is not
    hypothetical: two independent series both added ``## Narrative person`` to
    ``fill_subset.md`` at different insertion points, git merged both without a
    conflict, and the identical-body test above kept passing on the first copy
    while the model received the clause twice in one prompt, in two different
    wordings (PR #737 review-fix pass). Duplicate headings are checked for
    every heading, not just the shared ones, since the failure is structural.
    """
    headings = re.findall(r"^#{2,4} (.+)$", _read(name), re.MULTILINE)
    repeated = sorted({h for h in headings if headings.count(h) > 1})
    assert not repeated, (
        f"{name} states these headings more than once: {repeated}. The clause "
        f"reaches the model twice and every parity check here silently "
        f"compares only the first copy."
    )
