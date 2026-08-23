"""The seeded demo series must not be two copies of one book (`AL-574`).

`scripts/` is not an importable package (no `__init__.py`, by design; see the
per-file-ignores `INP` for `scripts/**/*.py` in `pyproject.toml`), so both
modules are loaded directly from their file paths via importlib.

Two scripts build the same fixture chain, `seed_dev_data.py` (the canonical
copy) and `seed_series_catalog.py`, and both write `status="published"`
directly rather than going through `publishing/service.py::approve`. That is
what puts them outside every gate `approve` enforces, SR-10 included, so the
gating has to be re-established inside each script and pinned here.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path
from typing import TYPE_CHECKING, Any

import pytest

from cyo_adventure.core.exceptions import ValidationError
from cyo_adventure.diversity.grams import shared_run_profile
from cyo_adventure.diversity.normalize import storybook_text
from cyo_adventure.storybook.models import Storybook as StorybookDoc
from cyo_adventure.validator.series import SERIES_MAX_SHARED_RUN_WORDS

if TYPE_CHECKING:
    from types import ModuleType

pytestmark = pytest.mark.unit

_SCRIPTS = Path(__file__).resolve().parents[2] / "scripts"
_SERIES_ID = "00000000-0000-0000-0000-000000000001"


def _load(name: str) -> ModuleType:
    """Load a seed script by file path, since scripts/ is not a package."""
    spec = importlib.util.spec_from_file_location(name, _SCRIPTS / f"{name}.py")
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_SEEDERS = ("seed_series_catalog", "seed_dev_data")


def _blobs(module: ModuleType) -> list[dict[str, object]]:
    """Build every blob of the module's series chain, in book order."""
    return [
        module._series_blob(story_id, title, book_index, _SERIES_ID)
        for story_id, title, book_index in module._SERIES_BOOKS
    ]


@pytest.mark.parametrize("name", _SEEDERS)
def test_series_fixture_books_do_not_reuse_prose(name: str) -> None:
    """The seeded chain passes SR-10, and by a real margin rather than barely.

    Before 2026-08-23 every body was ``f"{title}: <one shared sentence>"``, so
    the two books differed only by the digit in ``title``, which the diversity
    tokenizer (``[a-z']+`` over lowercased text) discards outright. Measured on
    that fixture the pair gave a longest shared run of 87 words at 100.00%
    coverage: as prose, book 2 WAS book 1.

    Asserting only that no SR-10 finding fired would pass on a fixture sitting
    one word under the bound, so the measurement itself is pinned.
    """
    module = _load(name)
    blobs = _blobs(module)
    module._assert_chain_clean(blobs)

    books = [StorybookDoc.model_validate(blob) for blob in blobs]
    profile = shared_run_profile(
        storybook_text(books[0], include_choice_labels=False),
        storybook_text(books[1], include_choice_labels=False),
    )
    assert profile.coverage == 0.0
    assert profile.longest * 4 <= SERIES_MAX_SHARED_RUN_WORDS


@pytest.mark.parametrize("name", _SEEDERS)
def test_the_chain_gate_catches_the_shared_template_it_was_written_for(
    name: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Give book 2 book 1's prose again and the gate must refuse to seed.

    Without this, `_assert_chain_clean` could be silently broken (an empty
    findings filter, the wrong severity, a report that never reaches SR-10)
    and the test above would still pass, because a clean fixture is clean
    either way. This restores the exact defect and demands the raise.
    """
    module = _load(name)
    prose: tuple[dict[str, str], ...] = module._BOOK_PROSE
    monkeypatch.setattr(module, "_BOOK_PROSE", (prose[0], dict(prose[0])))

    reused = _blobs(module)
    with pytest.raises(ValidationError) as excinfo:
        module._assert_chain_clean(reused)

    message = str(excinfo.value)
    assert "SR-10" in message
    assert name in message


@pytest.mark.parametrize("name", _SEEDERS)
def test_a_book_index_without_prose_is_refused_not_indexed_past(name: str) -> None:
    """Adding a third book to `_SERIES_BOOKS` must fail loudly, not IndexError."""
    module = _load(name)
    with pytest.raises(ValidationError, match="no body prose"):
        module._series_blob("s_x", "X", 3, _SERIES_ID)


def test_both_seed_scripts_carry_the_same_fixture_prose() -> None:
    """The duplicated copies must not drift.

    `seed_series_catalog._series_blob` is a verbatim copy of the one in
    `seed_dev_data`, duplicated because scripts/ is not importable. Nothing
    else pins the two prose tables together, so a fix applied to one copy and
    not the other would leave a chain that still reuses prose in whichever
    environment the other script seeds.
    """
    catalog: Any = _load("seed_series_catalog")._BOOK_PROSE
    dev: Any = _load("seed_dev_data")._BOOK_PROSE
    assert catalog == dev
