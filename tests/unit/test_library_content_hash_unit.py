"""Unit tests for ``storybook_content_hash`` (no DB, no ASGI stack).

The integration suite (``tests/integration/test_library_content_hash.py``)
pins the property that actually matters in production: the listed digest
equals sha256 of the bytes the read route serves. It cannot reach one input
class, though, because a ``jsonb`` column rejects NaN/Infinity on write, so a
non-finite float can only arrive by calling the helper directly.

That input class is load-bearing anyway. ``_library_item`` is explicitly built
to tolerate a malformed metadata float (it defaults the field and logs
``library_item_malformed_metadata``) rather than fail the listing, and the
digest runs once per book inside that listing. A digest that raised on such a
blob would 500 the whole shelf, for every book on it, which is strictly worse
than the staleness the digest exists to detect. These tests hold that line.
"""

from __future__ import annotations

import hashlib
import json
import math

import pytest

from cyo_adventure.api.library import _library_item, storybook_content_hash


def _blob(target: float) -> dict[str, object]:
    """Return a minimal listing blob whose reading-level target is ``target``."""
    return {
        "title": "The Lantern",
        "metadata": {"tier": 2, "reading_level": {"target": target}},
    }


@pytest.mark.unit
def test_storybook_content_hash_with_nonfinite_float_returns_stable_digest() -> None:
    """A NaN in the blob yields a real digest instead of raising ValueError.

    ``json.dumps`` raises on a non-finite float only when ``allow_nan=False``.
    Mirroring Starlette's setting here would turn one bad float into a 500 on
    the entire library listing, so the default is used deliberately. The digest
    must still be non-empty and repeatable, not a swallowed null that would
    leave the book permanently unverifiable on the client.
    """
    blob = _blob(math.nan)

    first = storybook_content_hash(blob)
    second = storybook_content_hash(blob)

    assert first.startswith("sha256:")
    assert len(first) == len("sha256:") + 64
    assert first == second


@pytest.mark.unit
def test_storybook_content_hash_distinguishes_nonfinite_from_finite_blob() -> None:
    """A NaN target and a finite target are not collapsed to one identity.

    A degraded-but-stable digest is only useful if it still discriminates; a
    constant fallback would make every malformed book compare equal to every
    other one.
    """
    assert storybook_content_hash(_blob(math.nan)) != storybook_content_hash(_blob(3.5))


@pytest.mark.unit
def test_storybook_content_hash_matches_strict_rendering_for_finite_blob() -> None:
    """Relaxing ``allow_nan`` changes no byte for a blob Starlette can serve.

    This is the guarantee the client depends on: for every blob the read route
    is able to render, the digest is taken over exactly those bytes. The two
    settings differ only on inputs that route would 500 on, which no client can
    ever cache.
    """
    blob = _blob(3.5)
    strict = json.dumps(
        blob,
        ensure_ascii=False,
        allow_nan=False,
        indent=None,
        separators=(",", ":"),
    ).encode("utf-8")

    expected = f"sha256:{hashlib.sha256(strict).hexdigest()}"

    assert storybook_content_hash(blob) == expected


@pytest.mark.unit
def test_library_item_with_nan_target_keeps_hash_and_warns(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """The tolerated-malformed path still produces a usable content identity.

    Ties the two contracts together at the call site: the field degrades to
    zero and one structured warning is emitted (the pre-existing tolerance
    contract), and the item still carries a real ``content_hash`` (the new
    one), so the listing neither fails nor silently drops staleness detection
    for that book.
    """
    with caplog.at_level("WARNING"):
        item = _library_item("nan-story", _blob(math.nan), 3)

    assert item.reading_level_target == pytest.approx(0.0)
    assert "library_item_malformed_metadata" in caplog.text
    assert "reading_level.target" in caplog.text
    assert item.content_hash.startswith("sha256:")
