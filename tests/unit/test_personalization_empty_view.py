"""Unit pin for the values route's universal empty payload (reviewer item I2).

``_empty_values_view`` is the single constructor every predicate-failure
branch of ``GET /storybooks/{id}/personalization-values`` returns, and its
fixed shape IS the route's anti-oracle guarantee: were any empty payload able
to carry populated ``slot_bindings``, a caller could distinguish "this book is
not addressable by you" from "addressable, but no values for you" for any
book whose contract declares personalizable slots. The integration suite
(tests/integration/test_personalization_api.py) exercises the route's
branches against a live database; this file pins the constructor's shape and
its no-argument signature where no database is needed, so a refactor that
re-threads bindings into an empty payload fails here first.
"""

from __future__ import annotations

import inspect

from cyo_adventure.api.personalization import _empty_values_view
from cyo_adventure.storybook.sentinels import SENTINEL_RE


def test_empty_view_is_uniform_and_carries_no_bindings() -> None:
    """Every field of the empty payload is fixed; slot_bindings is always {}."""
    view = _empty_values_view()

    assert view.subject_profile_id is None
    assert view.ring is None
    assert view.policy_version is None
    assert view.values == {}
    assert view.slot_bindings == {}
    assert view.sentinel_pattern == SENTINEL_RE.pattern


def test_empty_view_takes_no_arguments() -> None:
    """The constructor accepts nothing: bindings CANNOT be threaded into it.

    The pre-fix signature took an optional ``slot_bindings`` map, which is
    exactly the seam that let post-reachability branches leak populated
    bindings on an empty payload. Pinning the empty signature turns any
    reintroduction of that seam into a test failure rather than a review
    finding.
    """
    assert len(inspect.signature(_empty_values_view).parameters) == 0
