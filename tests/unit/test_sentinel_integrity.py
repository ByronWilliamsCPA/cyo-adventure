"""Unit tests for the sentinel-integrity check core (ADR-023, plan section 3).

Covers both check variants:

- ``check_sentinel_integrity`` (full, Variant A, plan 3.2): compares the
  EXPECTED per-node sentinel set (derived from a pre-fill skeleton) against
  the ACTUAL per-node sentinel set (derived from a filled blob).
- ``check_sentinel_integrity_at_rest`` (at-rest, Variant B, plan 3.3): a
  blob-only corruption check with no pre-fill reference, used by rescreen.

Fixtures here are deliberately minimal raw dict mappings (only the ``nodes``
/ ``body`` / ``ending`` / ``choices`` keys these pure functions actually
read), not full ``Storybook``-schema-valid documents; the module under test
never calls ``Storybook.model_validate``, so a full schema is unnecessary
scaffolding for these tests.
"""

from __future__ import annotations

from cyo_adventure.storybook.sentinels import wrap
from cyo_adventure.validator.sentinel_integrity import (
    IntegrityResult,
    check_sentinel_integrity,
    check_sentinel_integrity_at_rest,
)

_HERO = wrap("HERO", "Explorer")
_GATE = wrap("GATE", "Big Door")
_PRIZE = wrap("PRIZE", "Golden Cup")


def _node(
    node_id: str,
    body: str,
    *,
    ending_title: str | None = None,
    choices: list[dict[str, object]] | None = None,
) -> dict[str, object]:
    node: dict[str, object] = {"id": node_id, "body": body}
    if ending_title is not None:
        node["ending"] = {"id": f"e_{node_id}", "title": ending_title}
        node["choices"] = []
    else:
        node["choices"] = choices if choices is not None else []
    return node


def _blob(nodes: list[dict[str, object]]) -> dict[str, object]:
    return {"nodes": nodes}


# ---------------------------------------------------------------------------
# Variant A: check_sentinel_integrity
# ---------------------------------------------------------------------------


class TestCheckSentinelIntegrityHappyPath:
    """A filled blob that copies every declared sentinel verbatim passes."""

    def test_happy_path_ok_no_violations(self) -> None:
        """2-3 sentinels across nodes plus an ending title, all copied verbatim."""
        start_beats = f"The hero, {_HERO}, arrives at {_GATE} and meets {_HERO} again."
        pre_fill = _blob(
            [
                _node(
                    "n_start",
                    f"<<FILL role=setup words=40 beats='{start_beats}'>>",
                    choices=[{"id": "c_a", "label": "Go forward.", "target": "n_end"}],
                ),
                _node(
                    "n_end",
                    "<<FILL role=ending words=20 beats='The hero celebrates.'>>",
                    ending_title=f"The {_PRIZE}",
                ),
            ]
        )
        filled = _blob(
            [
                _node(
                    "n_start",
                    f"{_HERO} stood before {_GATE}. {_HERO} smiled bravely.",
                    choices=[{"id": "c_a", "label": "Go forward.", "target": "n_end"}],
                ),
                _node(
                    "n_end",
                    "The hero celebrated at last.",
                    ending_title=f"The {_PRIZE}",
                ),
            ]
        )
        result = check_sentinel_integrity(pre_fill, filled)
        assert result == IntegrityResult(ok=True, violations=[])

    def test_no_personalizable_slots_no_sentinels_passes(self) -> None:
        """A blob with no sentinels at all passes cleanly (the overwhelming case)."""
        pre_fill = _blob(
            [
                _node(
                    "n_start",
                    "<<FILL role=setup words=40 beats='The hero arrives.'>>",
                    choices=[{"id": "c_a", "label": "Go.", "target": "n_end"}],
                ),
                _node("n_end", "ending body", ending_title="The End"),
            ]
        )
        filled = _blob(
            [
                _node(
                    "n_start",
                    "The hero arrived at the gate.",
                    choices=[{"id": "c_a", "label": "Go.", "target": "n_end"}],
                ),
                _node("n_end", "The hero rested.", ending_title="The End"),
            ]
        )
        result = check_sentinel_integrity(pre_fill, filled)
        assert result.ok is True
        assert result.violations == []


class TestCheckSentinelIntegrityDropped:
    """A filled node that omits an expected sentinel is a 'dropped' violation."""

    def test_dropped_sentinel_reported(self) -> None:
        pre_fill = _blob(
            [_node("n_a", f"<<FILL beats='{_HERO} walks.'>>", ending_title="Fixed")]
        )
        filled = _blob(
            [_node("n_a", "The hero walked generically.", ending_title="Fixed")]
        )
        result = check_sentinel_integrity(pre_fill, filled)
        assert result.ok is False
        assert len(result.violations) == 1
        violation = result.violations[0]
        assert violation.node_id == "n_a"
        assert violation.kind == "dropped"
        assert violation.token == _HERO


class TestCheckSentinelIntegrityForged:
    """A filled node that adds an undeclared sentinel is a 'forged' violation."""

    def test_forged_sentinel_reported(self) -> None:
        pre_fill = _blob(
            [_node("n_a", "<<FILL beats='The hero walks.'>>", ending_title="Fixed")]
        )
        filled = _blob(
            [_node("n_a", f"{_HERO} walked generically.", ending_title="Fixed")]
        )
        result = check_sentinel_integrity(pre_fill, filled)
        assert result.ok is False
        assert len(result.violations) == 1
        violation = result.violations[0]
        assert violation.node_id == "n_a"
        assert violation.kind == "forged"
        assert violation.token == _HERO


class TestCheckSentinelIntegrityMigrated:
    """A sentinel expected in node A that appears in node B, per-node on both."""

    def test_migrated_sentinel_reported_on_both_nodes(self) -> None:
        pre_fill = _blob(
            [
                _node("n_a", f"<<FILL beats='{_HERO} walks.'>>", ending_title="A"),
                _node(
                    "n_b", "<<FILL beats='Something else happens.'>>", ending_title="B"
                ),
            ]
        )
        filled = _blob(
            [
                _node("n_a", "The hero walked generically.", ending_title="A"),
                _node("n_b", f"{_HERO} appeared here instead.", ending_title="B"),
            ]
        )
        result = check_sentinel_integrity(pre_fill, filled)
        assert result.ok is False
        by_node = {v.node_id: v for v in result.violations}
        assert set(by_node) == {"n_a", "n_b"}
        assert by_node["n_a"].kind == "migrated"
        assert by_node["n_a"].token == _HERO
        assert by_node["n_b"].kind == "migrated"
        assert by_node["n_b"].token == _HERO


class TestCheckSentinelIntegrityMutation:
    """A mutated sentinel (inner value or wrapper) is caught."""

    def test_mutated_inner_value_caught_as_dropped_and_forged(self) -> None:
        """A well-formed but differently-valued token is a dropped+forged pair.

        The mutated token (``{~HERO:Champion~}``) is itself well-formed, so
        it is not a near-miss; it is caught purely via set-mismatch: the
        original expected token is missing (dropped) and a new, undeclared
        token is present (forged). It is not "migrated" because the mutated
        token does not appear as a drop anywhere else.
        """
        pre_fill = _blob(
            [_node("n_a", f"<<FILL beats='{_HERO} walks.'>>", ending_title="Fixed")]
        )
        mutated = wrap("HERO", "Champion")
        filled = _blob(
            [_node("n_a", f"{mutated} walked generically.", ending_title="Fixed")]
        )
        result = check_sentinel_integrity(pre_fill, filled)
        assert result.ok is False
        kinds = {(v.kind, v.token) for v in result.violations}
        assert kinds == {("dropped", _HERO), ("forged", mutated)}
        assert all(v.node_id == "n_a" for v in result.violations)

    def test_mutated_wrapper_whitespace_caught_as_malformed_and_dropped(self) -> None:
        """A whitespace-mangled wrapper is a near-miss (malformed) plus a drop.

        The mangled text is not a well-formed sentinel, so ``find_sentinels``
        never sees it: the expected token is simply absent from the actual
        set (dropped), and the near-miss scan separately reports the mangled
        text as malformed.
        """
        pre_fill = _blob(
            [_node("n_a", f"<<FILL beats='{_HERO} walks.'>>", ending_title="Fixed")]
        )
        mangled = "{~ HERO:Explorer~}"
        filled = _blob(
            [_node("n_a", f"{mangled} walked generically.", ending_title="Fixed")]
        )
        result = check_sentinel_integrity(pre_fill, filled)
        assert result.ok is False
        kinds = {(v.kind, v.token) for v in result.violations}
        assert kinds == {("dropped", _HERO), ("malformed", mangled)}


class TestCheckSentinelIntegrityChoiceLabel:
    """A sentinel emitted into a choice label is always a violation."""

    def test_sentinel_in_choice_label_reported(self) -> None:
        pre_fill = _blob(
            [
                _node(
                    "n_a",
                    "<<FILL beats='The hero walks.'>>",
                    choices=[{"id": "c_a", "label": "Go forward.", "target": "n_b"}],
                ),
                _node("n_b", "ending", ending_title="End"),
            ]
        )
        filled = _blob(
            [
                _node(
                    "n_a",
                    "The hero walked generically.",
                    choices=[
                        {
                            "id": "c_a",
                            "label": f"Go toward {_HERO}.",
                            "target": "n_b",
                        }
                    ],
                ),
                _node("n_b", "The end.", ending_title="End"),
            ]
        )
        result = check_sentinel_integrity(pre_fill, filled)
        assert result.ok is False
        violation = next(v for v in result.violations if v.kind == "in_choice_label")
        assert violation.token == _HERO
        assert violation.node_id == "<choice-label>"

    def test_malformed_in_choice_label_reported(self) -> None:
        pre_fill = _blob(
            [
                _node(
                    "n_a",
                    "<<FILL beats='The hero walks.'>>",
                    choices=[{"id": "c_a", "label": "Go forward.", "target": "n_b"}],
                ),
                _node("n_b", "ending", ending_title="End"),
            ]
        )
        mangled = "{~hero:Explorer~}"
        filled = _blob(
            [
                _node(
                    "n_a",
                    "The hero walked generically.",
                    choices=[
                        {
                            "id": "c_a",
                            "label": f"Go toward {mangled}.",
                            "target": "n_b",
                        }
                    ],
                ),
                _node("n_b", "The end.", ending_title="End"),
            ]
        )
        result = check_sentinel_integrity(pre_fill, filled)
        malformed = [v for v in result.violations if v.kind == "malformed"]
        assert len(malformed) == 1
        assert malformed[0].token == mangled
        assert malformed[0].node_id == "<choice-label>"


# ---------------------------------------------------------------------------
# Variant B: check_sentinel_integrity_at_rest
# ---------------------------------------------------------------------------


class TestCheckSentinelIntegrityAtRest:
    """The at-rest (blob-only) corruption check used by rescreen."""

    def test_clean_published_blob_passes(self) -> None:
        blob = _blob(
            [
                _node(
                    "n_a",
                    f"{_HERO} stood before {_GATE}.",
                    choices=[{"id": "c_a", "label": "Go.", "target": "n_b"}],
                ),
                _node("n_b", f"{_HERO} celebrated.", ending_title=f"The {_PRIZE}"),
            ]
        )
        result = check_sentinel_integrity_at_rest(
            blob, frozenset({"HERO", "GATE", "PRIZE"})
        )
        assert result == IntegrityResult(ok=True, violations=[])

    def test_no_personalizable_slots_no_sentinels_passes(self) -> None:
        blob = _blob(
            [
                _node(
                    "n_a",
                    "The hero stood before the gate.",
                    choices=[{"id": "c_a", "label": "Go.", "target": "n_b"}],
                ),
                _node("n_b", "The hero celebrated.", ending_title="The End"),
            ]
        )
        result = check_sentinel_integrity_at_rest(blob, frozenset())
        assert result.ok is True
        assert result.violations == []

    def test_unknown_slot_id_reported(self) -> None:
        blob = _blob([_node("n_a", f"{_HERO} stood alone.", ending_title="Fixed")])
        result = check_sentinel_integrity_at_rest(blob, frozenset({"GATE"}))
        assert result.ok is False
        assert len(result.violations) == 1
        violation = result.violations[0]
        assert violation.kind == "unknown_slot"
        assert violation.token == _HERO
        assert violation.node_id == "<global>"

    def test_malformed_near_miss_reported(self) -> None:
        mangled = "{~HERO:~}"
        blob = _blob([_node("n_a", f"{mangled} stood alone.", ending_title="Fixed")])
        result = check_sentinel_integrity_at_rest(blob, frozenset({"HERO"}))
        assert result.ok is False
        assert len(result.violations) == 1
        violation = result.violations[0]
        assert violation.kind == "malformed"
        assert violation.token == mangled
        assert violation.node_id == "<global>"

    def test_sentinel_in_choice_label_reported(self) -> None:
        blob = _blob(
            [
                _node(
                    "n_a",
                    "The hero stood alone.",
                    choices=[
                        {
                            "id": "c_a",
                            "label": f"Go toward {_HERO}.",
                            "target": "n_b",
                        }
                    ],
                ),
                _node("n_b", "The end.", ending_title="Fixed"),
            ]
        )
        result = check_sentinel_integrity_at_rest(blob, frozenset({"HERO"}))
        assert result.ok is False
        violation = next(v for v in result.violations if v.kind == "in_choice_label")
        assert violation.token == _HERO
        assert violation.node_id == "<choice-label>"
