"""`RS-B2`: the moderation_threshold seed grid must mirror the code constants.

The seed migration hand-copies the graded-category list and the age-band list,
because a migration must not import live application code: an import would let
a later refactor change what an already-applied migration meant. Nothing at
runtime ties the two together, so these tests are the tie. They parse the
migration's own SQL text and compare it against the constants it claims to
mirror.

None of this needs a database. The companion integration test
(tests/integration/test_threshold_seed_grid_applied.py) proves the SQL actually
inserts what it says against a freshly migrated schema; this module proves the
SQL says the right thing in the first place.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from cyo_adventure.moderation.classifiers import _OPENAI_BRIGHTLINE
from cyo_adventure.moderation.report import Verdict
from cyo_adventure.moderation.thresholds import (
    DEFAULT_THRESHOLD,
    GRADED_SCORE_CATEGORIES,
    KNOWN_CATEGORIES,
)
from cyo_adventure.storybook.models import AgeBand

pytestmark = pytest.mark.unit

_MIGRATION = (
    Path(__file__).resolve().parents[2]
    / "supabase"
    / "migrations"
    / "20260831120000_seed_moderation_threshold_grid.sql"
)

_EXPECTED_ROWS = 36

# The 13 categories the live Stage-0 classifier grades, as captured in
# docs/planning/safety/stage0-baseline-2026-08-01.json's own payload keys.
_LIVE_OPENAI_CATEGORIES = frozenset(
    {
        "harassment",
        "harassment/threatening",
        "hate",
        "hate/threatening",
        "illicit",
        "illicit/violent",
        "self-harm",
        "self-harm/instructions",
        "self-harm/intent",
        "sexual",
        "sexual/minors",
        "violence",
        "violence/graphic",
    }
)


def _sql() -> str:
    """Return the migration's EXECUTABLE text, with comment lines removed.

    Every assertion below reads the statement, not the rationale around it.
    That file's comments deliberately quote the shapes they warn against
    ("DO UPDATE", a concrete score), so a substring search over the whole file
    would find the warning and report the very defect it warns about.
    """
    return "\n".join(
        line
        for line in _MIGRATION.read_text(encoding="utf-8").splitlines()
        if not line.lstrip().startswith("--")
    )


def _values_blocks(text: str) -> list[list[str]]:
    """Return the quoted literals of every ``(VALUES ...)`` list, in order.

    Parsing the migration rather than re-listing its contents is the point: a
    test that restated the 36 pairs would agree with itself while the migration
    drifted out from under it.
    """
    blocks: list[list[str]] = []
    for match in re.finditer(r"\(VALUES", text):
        depth = 0
        for offset in range(match.start(), len(text)):
            if text[offset] == "(":
                depth += 1
            elif text[offset] == ")":
                depth -= 1
                if depth == 0:
                    blocks.append(
                        re.findall(r"'([^']*)'", text[match.start() : offset + 1])
                    )
                    break
        else:  # pragma: no cover - unbalanced parens would be a syntax error
            pytest.fail("unbalanced VALUES list in the seed migration")
    return blocks


def _bands_and_categories(text: str) -> tuple[list[str], list[str]]:
    """Return the (bands, categories) literal lists from the seed's two VALUES.

    Identified by CONTENT, not by position: keying off "the first list is bands"
    would silently swap meaning if the two FROM operands were ever reordered,
    and both callers would then be asserting against the wrong list while
    still passing.
    """
    blocks = _values_blocks(text)
    assert len(blocks) == 2, f"expected two VALUES lists, found {len(blocks)}"
    band_values = {band.value for band in AgeBand}
    bands = [b for b in blocks if set(b) & band_values]
    categories = [b for b in blocks if not set(b) & band_values]
    assert len(bands) == 1, "could not identify the band VALUES list"
    assert len(categories) == 1, "could not identify the category VALUES list"
    return bands[0], categories[0]


def test_the_seed_migration_exists() -> None:
    """A missing file would make every other test here vacuously pass."""
    assert _MIGRATION.is_file(), f"{_MIGRATION} is missing"


def test_the_seed_migration_mirrors_the_graded_categories_exactly() -> None:
    """The category VALUES list must equal GRADED_SCORE_CATEGORIES.

    Cited by the ``#ASSUME`` marker on GRADED_SCORE_CATEGORIES. Set equality in
    both directions: an extra category in the migration seeds a dial the code
    does not consider graded, and a missing one leaves a cell invisible in the
    console that the code says is tunable.
    """
    _, categories = _bands_and_categories(_sql())
    assert set(categories) == set(GRADED_SCORE_CATEGORIES)
    assert len(categories) == len(GRADED_SCORE_CATEGORIES)


def test_the_seed_migration_covers_every_age_band() -> None:
    """The band VALUES list must equal the AgeBand enum.

    The DB's ck_moderation_threshold_age_band CHECK enforces the same domain,
    so a band this seed MISSPELLS fails the migration loudly; a band it simply
    OMITS fails nothing at all, which is the case worth pinning.
    """
    bands, _ = _bands_and_categories(_sql())
    assert set(bands) == {band.value for band in AgeBand}
    assert len(bands) == len(AgeBand)


def test_the_seed_row_count_is_the_full_band_by_category_product() -> None:
    """36 rows: six bands times six graded categories.

    The plan's own verification instruction for `RS-B2`. Derived as a product of
    the two parsed lists so it cannot drift out of step with either.
    """
    bands, categories = _bands_and_categories(_sql())
    assert len(bands) * len(categories) == _EXPECTED_ROWS


def test_no_graded_category_is_a_bright_line_category() -> None:
    """A score floor cannot change what surfaces for a bright-line category.

    A flagged bright-line category yields a BLOCK, and ``admin_surfaces`` never
    hides a BLOCK, so seeding one of those cells would create a dial that does
    nothing while looking exactly like the dials that do something.
    """
    assert not (set(GRADED_SCORE_CATEGORIES) & set(_OPENAI_BRIGHTLINE))


def test_graded_plus_bright_line_accounts_for_every_live_category() -> None:
    """Graded plus bright line must be exactly the 13 live categories.

    The test above proves no overlap; this one proves nothing was dropped.
    Together they pin GRADED_SCORE_CATEGORIES as a derivation rather than a
    hand-picked list that merely looks reasonable.
    """
    assert (
        set(GRADED_SCORE_CATEGORIES) | set(_OPENAI_BRIGHTLINE)
        == _LIVE_OPENAI_CATEGORIES
    )


def test_every_graded_category_is_suggested_by_the_admin_editor() -> None:
    """The admin editor must suggest every category whose floor actually bites.

    Cited by the ``#VERIFY`` on KNOWN_CATEGORIES. Before `RS-B2` this failed for
    all six: the suggestion list named seven live OpenAI categories and every
    one of them was bright line, so the editor advertised only the dials that
    do nothing.
    """
    missing = [c for c in GRADED_SCORE_CATEGORIES if c not in KNOWN_CATEGORIES]
    assert missing == []


def test_known_categories_is_sorted_and_free_of_duplicates() -> None:
    """Folding the graded set in must not reorder or repeat.

    ``KNOWN_CATEGORIES`` feeds a datalist the admin reads top to bottom; a
    duplicate would render twice, and an unsorted list would scramble on every
    edit to the literal set behind it.
    """
    assert list(KNOWN_CATEGORIES) == sorted(KNOWN_CATEGORIES)
    assert len(set(KNOWN_CATEGORIES)) == len(KNOWN_CATEGORIES)


def test_the_seed_is_behaviour_preserving_on_both_lanes() -> None:
    """Every seeded row must equal DEFAULT_THRESHOLD in effect.

    ``min_verdict = 'flag'`` is DEFAULT_THRESHOLD's verdict, so the guardian
    lane is byte-identical; ``min_score`` is NULL, which
    ``admin_noise_floor_for`` resolves to the flat floor, so the admin lane is
    too. A seed that changed either would ship an unratified cutoff under cover
    of a plumbing migration.
    """
    assert DEFAULT_THRESHOLD.min_verdict is Verdict.FLAG
    assert DEFAULT_THRESHOLD.min_score is None
    text = _sql()
    select_body = text[text.index("SELECT") : text.index("FROM")]
    assert "'flag'" in select_body
    assert "NULL" in select_body
    # A numeric literal anywhere in the projected row would be a concrete
    # score, which wins over the global flat floor and deadens it.
    assert not re.search(r"\d*\.\d+", select_body), (
        "a concrete min_score would deaden the global flat floor for that pair"
    )


def test_the_seed_never_overwrites_an_admin_edit() -> None:
    """ON CONFLICT must be DO NOTHING, never DO UPDATE.

    A DO UPDATE would revert every cutoff an operator had set, the next time
    the migration chain replays against a database that already holds rows,
    which is exactly what a fresh staging restore does.
    """
    text = _sql()
    assert 'ON CONFLICT ("age_band", "category") DO NOTHING' in text
    assert "DO UPDATE" not in text
