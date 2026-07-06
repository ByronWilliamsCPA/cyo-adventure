"""Unit tests for skeleton band auto-match."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

from cyo_adventure.generation import skeleton_match
from cyo_adventure.generation.skeleton_match import select_skeleton_for_band

if TYPE_CHECKING:
    from pathlib import Path

    import pytest


def test_select_skeleton_for_band_returns_first_eligible_slug_alphabetically() -> None:
    """8-11 has three production-eligible skeletons; the first alphabetically wins."""
    assert select_skeleton_for_band("8-11") == "the-cave-of-echoes"


def test_select_skeleton_for_band_skips_non_eligible_skeleton() -> None:
    """10-13's alphabetically-first skeleton (the-clocktower-cipher) is
    non-eligible and must be skipped in favor of the next eligible one."""
    assert select_skeleton_for_band("10-13") == "the-hollow-lighthouse"


def test_select_skeleton_for_band_returns_none_for_unknown_band() -> None:
    """A band with no skeleton directory returns None, not an error."""
    assert select_skeleton_for_band("99-100") is None


def test_select_skeleton_skips_malformed_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A corrupt JSON file must be skipped, not crash the scan.

    select_skeleton_for_band runs synchronously inside POST /authoring-plan. A
    raw JSONDecodeError/OSError is not a ProjectBaseError, so it would bypass
    app.py's structured handler and surface as an unstructured 500 instead of
    the contracted "returns None / a valid slug, never crashes" behavior. The
    alphabetically-first file here is unparseable; scanning must continue to the
    valid, production-eligible one.
    """
    band_dir = tmp_path / "8-11"
    band_dir.mkdir()
    (band_dir / "aaa-broken.json").write_text("{ not valid json", encoding="utf-8")
    (band_dir / "zzz-good.json").write_text(json.dumps({}), encoding="utf-8")
    monkeypatch.setattr(skeleton_match, "_SKELETON_ROOT", tmp_path)

    assert select_skeleton_for_band("8-11") == "zzz-good"
