"""The shared slotted-surface enumerator (storybook/slotted_surfaces.py).

A21 found four private copies of "walk the three surfaces a ``{SLOT}`` token
may live in": in ``generation/binding.py``, ``mutation/contract_gate.py``,
``scripts/parameterize_skeleton.py``, and the leak scan itself. Four copies is
how a surface gets checked by one pass and missed by another, which is exactly
the defect A21 reported. These tests pin the single definition, including the
malformed-input tolerance the two callers that walk mid-migration documents
depend on.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from cyo_adventure.storybook.slotted_surfaces import (
    iter_slotted_surfaces,
    slot_tokens_in_surfaces,
)

if TYPE_CHECKING:
    from collections.abc import Mapping


def test_the_three_legal_surfaces_are_all_enumerated() -> None:
    """Beats guidance, ending title, and choice label, in document order."""
    skeleton: Mapping[str, object] = {
        "nodes": [
            {
                "id": "n1",
                "body": "<<FILL role=setup words=80 beats='{HERO} waits'>>",
                "choices": [{"id": "c1", "label": "Enter {PLACE}.", "target": "n2"}],
            },
            {"id": "n2", "ending": {"id": "e1", "title": "The {PRIZE}"}},
        ]
    }
    assert [
        (surface.kind, surface.location, surface.text)
        for surface in iter_slotted_surfaces(skeleton)
    ] == [
        ("beats", "n1", "{HERO} waits"),
        ("label", "n1/c1", "Enter {PLACE}."),
        ("title", "n2", "The {PRIZE}"),
    ]


def test_the_beats_surface_excludes_the_fill_wrapper() -> None:
    """Only the inner group is authored text; ``role``/``words`` are syntax."""
    skeleton: Mapping[str, object] = {
        "nodes": [{"id": "n1", "body": "<<FILL role=setup words=80 beats='a room'>>"}]
    }
    surfaces = list(iter_slotted_surfaces(skeleton))
    assert [surface.text for surface in surfaces] == ["a room"]
    assert "role=" not in surfaces[0].text


def test_a_beats_segment_spanning_a_newline_still_matches() -> None:
    """DOTALL is load-bearing: a multi-line beats block is one group."""
    skeleton: Mapping[str, object] = {
        "nodes": [{"id": "n1", "body": "<<FILL role=setup words=80 beats='one\ntwo'>>"}]
    }
    assert [s.text for s in iter_slotted_surfaces(skeleton)] == ["one\ntwo"]


def test_a_non_fill_body_yields_no_beats_surface() -> None:
    """A filled node's prose is not a slotted surface and must not be scanned."""
    skeleton: Mapping[str, object] = {
        "nodes": [{"id": "n1", "body": "Real prose, already filled."}]
    }
    assert list(iter_slotted_surfaces(skeleton)) == []


def test_malformed_documents_yield_nothing_rather_than_raising() -> None:
    """Mid-migration callers walk documents the gate has not accepted yet."""
    assert list(iter_slotted_surfaces({})) == []
    assert list(iter_slotted_surfaces({"nodes": "not-a-list"})) == []
    assert list(iter_slotted_surfaces({"nodes": ["not-a-node", 7, None]})) == []


def test_non_string_surface_values_are_skipped() -> None:
    """A caller can only report on text that exists."""
    skeleton: Mapping[str, object] = {
        "nodes": [
            {
                "id": "n1",
                "body": 123,
                "ending": {"id": "e1", "title": 456},
                "choices": [
                    "not-a-choice",
                    {"label": 789},
                    {"id": "c2", "label": "Go."},
                ],
            }
        ]
    }
    assert [(s.kind, s.location, s.text) for s in iter_slotted_surfaces(skeleton)] == [
        ("label", "n1/c2", "Go.")
    ]


def test_a_choice_without_an_id_still_reports_a_usable_location() -> None:
    """A missing choice id must not produce a location ending in "/None"."""
    skeleton: Mapping[str, object] = {
        "nodes": [{"id": "n1", "choices": [{"label": "Go."}]}]
    }
    surface = next(iter(iter_slotted_surfaces(skeleton)))
    assert surface.choice_id is None
    assert surface.location == "n1"


def test_slot_tokens_are_collected_across_every_surface() -> None:
    """The token set is the union over all three surfaces, deduplicated."""
    skeleton: Mapping[str, object] = {
        "nodes": [
            {
                "id": "n1",
                "body": "<<FILL role=setup words=80 beats='{HERO} and {HERO}'>>",
                "choices": [{"id": "c1", "label": "Enter {PLACE}."}],
            },
            {"id": "n2", "ending": {"id": "e1", "title": "The {PRIZE}"}},
        ]
    }
    assert slot_tokens_in_surfaces(skeleton) == frozenset({"HERO", "PLACE", "PRIZE"})


def test_a_lowercase_or_digit_leading_brace_group_is_not_a_token() -> None:
    """The token grammar is all-caps and letter-initial; near-misses are text."""
    skeleton: Mapping[str, object] = {
        "nodes": [{"id": "n1", "ending": {"id": "e1", "title": "{lower} {1BAD} {OK}"}}]
    }
    assert slot_tokens_in_surfaces(skeleton) == frozenset({"OK"})
