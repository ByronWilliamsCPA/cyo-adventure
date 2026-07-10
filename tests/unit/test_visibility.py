"""Unit tests for the Visibility app-boundary enum (WS-E, decision E1)."""

from __future__ import annotations

import pytest

from cyo_adventure.publishing.state_machine import Visibility


def test_visibility_values_are_closed() -> None:
    """The enum holds exactly the two ratified visibility states."""
    assert {v.value for v in Visibility} == {"family", "catalog"}


def test_visibility_rejects_unknown_value() -> None:
    """Coercing an unmodeled string raises rather than silently authorizing."""
    with pytest.raises(ValueError, match="public"):
        Visibility("public")
