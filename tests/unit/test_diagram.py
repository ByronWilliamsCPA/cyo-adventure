"""Unit tests for the skeleton-to-PlantUML diagram transform."""

from __future__ import annotations

import pytest

from cyo_adventure.generation.diagram import _parse_fill


@pytest.mark.unit
def test_parse_fill_extracts_role_and_words() -> None:
    body = "<<FILL role=setup words=85 beats='Pip looks for a mitten'>>"
    assert _parse_fill(body) == ("setup", 85)


@pytest.mark.unit
def test_parse_fill_handles_completion_role() -> None:
    body = "<<FILL role=completion words=80 beats='a cozy resolution'>>"
    assert _parse_fill(body) == ("completion", 80)


@pytest.mark.unit
def test_parse_fill_returns_none_for_non_fill_body() -> None:
    assert _parse_fill("Once upon a time the fox was warm.") == (None, None)
