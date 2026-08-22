"""Unit tests for ``chunking._merged_ending``'s eligibility guard.

The chunked fill path merges a model reply into a document that has already
passed the structural gate, and the merge is a whitelist: prose in, nothing
else. ``ending_title`` is the newest entry on that whitelist (ruled
2026-08-21, ``docs/planning/live-structural-round-2026-08-21.md`` section
8.3), and its guard has to hold against a reply that names the key on a node
that owns no ending block.

These tests live apart from ``test_chunked_fill.py`` deliberately: they pin
the ordering between the eligibility rejection and the nothing-proposed
short-circuit, which is the thing that regressed.
"""

from __future__ import annotations

from typing import Any

import pytest

from cyo_adventure.core.exceptions import ValidationError
from cyo_adventure.generation.chunking import merge_fill_batch

pytestmark = pytest.mark.unit


def _document(*, with_ending: bool) -> dict[str, Any]:
    """Return a one-node document, optionally carrying an ending block.

    Args:
        with_ending: Whether the single node owns an ``ending`` block.

    Returns:
        A document shaped like the skeleton the chunked merge folds into.
    """
    node: dict[str, Any] = {
        "id": "n1",
        "body": "<<FILL role=scene words=40>>",
        "is_ending": with_ending,
    }
    if with_ending:
        node["ending"] = {
            "id": "e1",
            "kind": "completion",
            "valence": "positive",
            "title": "Home Safe",
        }
    return {"schema_version": "2.0", "start_node": "n1", "nodes": [node]}


def test_an_explicit_null_ending_title_on_a_non_ending_node_is_rejected() -> None:
    """``"ending_title": null`` must not inject an ending onto a plain node.

    JSON ``null`` and an absent key both arrive as ``None`` from ``dict.get``,
    so an ``if proposed is None: return ending`` short-circuit placed BEFORE
    the ``isinstance(ending, dict)`` rejection let this reply through the
    guard entirely. The caller writes the return value to ``merged["ending"]``
    whenever the reply names the key, so the node came out of a prose-only
    merge carrying a brand new ``"ending": None`` that the skeleton never had.
    The eligibility rejection has to run first.
    """
    document = _document(with_ending=False)
    reply = {"n1": {"body": "You stand at a fork in the path.", "ending_title": None}}

    with pytest.raises(ValidationError) as excinfo:
        merge_fill_batch(document, ["n1"], reply)

    assert "has no ending block" in str(excinfo.value)


def test_a_named_ending_title_on_a_non_ending_node_is_still_rejected() -> None:
    """The pre-existing rejection for a real title string is unchanged."""
    document = _document(with_ending=False)
    reply = {"n1": {"body": "You stand at a fork.", "ending_title": "Starlight Kept"}}

    with pytest.raises(ValidationError) as excinfo:
        merge_fill_batch(document, ["n1"], reply)

    assert "has no ending block" in str(excinfo.value)


def test_a_reply_omitting_ending_title_keeps_the_skeletons_ending() -> None:
    """The legitimate omit-the-key path must still carry the ending through.

    This is the case the None short-circuit was written for, and reordering
    the guards must not cost it: a reply that simply does not mention
    ``ending_title`` leaves every field of the skeleton's ending intact,
    title included, while the body is replaced.
    """
    document = _document(with_ending=True)
    reply = {"n1": {"body": "You made it home safe."}}

    merged = merge_fill_batch(document, ["n1"], reply)

    node = merged["nodes"][0]  # pyright: ignore[reportIndexIssue, reportUnknownVariableType]
    assert node["body"] == "You made it home safe."
    assert node["ending"] == {
        "id": "e1",
        "kind": "completion",
        "valence": "positive",
        "title": "Home Safe",
    }


def test_a_reply_omitting_ending_title_leaves_a_plain_node_endingless() -> None:
    """A node with no ending block gains no ``ending`` key from the merge.

    The complement of the null case: when neither the node nor the reply
    mentions an ending, the merged node must not acquire the key at all.
    """
    document = _document(with_ending=False)
    reply = {"n1": {"body": "You stand at a fork in the path."}}

    merged = merge_fill_batch(document, ["n1"], reply)

    assert "ending" not in merged["nodes"][0]  # pyright: ignore[reportIndexIssue, reportOperatorIssue]


def test_an_explicit_null_ending_title_on_an_ending_node_is_rejected() -> None:
    """A null title on a node that DOES own an ending is a malformed reply.

    Blanking a real ending's title is not a rewrite the whitelist permits;
    the reply should have omitted the key instead.
    """
    document = _document(with_ending=True)
    reply = {"n1": {"body": "You made it home safe.", "ending_title": None}}

    with pytest.raises(ValidationError) as excinfo:
        merge_fill_batch(document, ["n1"], reply)

    assert "missing or non-string ending title" in str(excinfo.value)


def test_a_named_ending_title_rewrites_only_the_title() -> None:
    """The permitted rewrite touches ``title`` and nothing else on the ending."""
    document = _document(with_ending=True)
    reply = {"n1": {"body": "You made it home safe.", "ending_title": "Starlight Kept"}}

    merged = merge_fill_batch(document, ["n1"], reply)

    assert merged["nodes"][0]["ending"] == {  # pyright: ignore[reportIndexIssue, reportUnknownVariableType]
        "id": "e1",
        "kind": "completion",
        "valence": "positive",
        "title": "Starlight Kept",
    }
