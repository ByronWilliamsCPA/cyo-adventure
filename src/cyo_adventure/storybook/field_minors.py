"""Which schema minor introduced which Storybook field (ADR-025 decision 3).

ADR-025 decision 3 says a story only carries fields defined at its published
minor. Nothing enforced it, and the two obvious enforcement points both cost
more than they are worth: a publish-path stamper needs every producer to
change, and a hand-update sweep would force-bump every catalog skeleton on
every minor.

The cheap enforcement is the converse, which is what ``L1-8`` checks: if a
document uses a field introduced at minor N, its ``schema_version`` must be at
least N. An under-declared document then fails the gate instead of being
silently admitted, and a skeleton using no new field stays correctly stamped at
the minor it was written for.

**Top-level fields only.** No field introduced at a minor is nested yet, so a
path-walking registry would be speculative. Adding a nested field at a future
minor means extending both this mapping's key format and ``_check_field_minors``
to walk it, deliberately.

**Keeping this registry honest.** Nothing links ``FIELD_MINORS`` to the
``Storybook`` model by construction, so a future field added at minor 2 whose
author forgets to register it here would silently get no floor. ``BASELINE_FIELDS``
below names every field that already existed at minor 0, so the lockstep test
in ``tests/unit/test_field_minor_floor.py`` can enumerate ``Storybook.model_fields``
and fail whenever a real field is in neither set, or a registered name is not a
real field.
"""

from __future__ import annotations

from typing import Final

# Fields absent at minor 0 are the only entries here; a field present since
# 2.0 has no floor to enforce and must not be listed.
FIELD_MINORS: Final[dict[str, int]] = {
    "accepts_character": 1,
}

# Every top-level Storybook field that existed at minor 0 (schema "2.0"), the
# original schema before ADR-025 decision 3 introduced the floor this module
# enforces. This is the baseline half of the lockstep test in
# tests/unit/test_field_minor_floor.py: every field on Storybook must appear
# either here or in FIELD_MINORS above, or the test fails. A field belongs
# here only if it was present at minor 0; a field added at any later minor
# belongs in FIELD_MINORS instead, never in both.
BASELINE_FIELDS: Final[frozenset[str]] = frozenset(
    {
        "schema_version",
        "id",
        "version",
        "title",
        "metadata",
        "variables",
        "start_node",
        "nodes",
    }
)
