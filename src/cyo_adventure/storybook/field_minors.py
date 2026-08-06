"""Which schema minor introduced which Storybook field (ADR-025 decision 3).

ADR-025 decision 3 says a story only carries fields defined at its published
minor. Nothing enforced it, and the two obvious enforcement points both cost
more than they are worth: a publish-path stamper needs every producer to
change, and a hand-update sweep would force-bump all 61 catalog skeletons on
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
"""

from __future__ import annotations

from typing import Final

# Fields absent at minor 0 are the only entries here; a field present since
# 2.0 has no floor to enforce and must not be listed.
FIELD_MINORS: Final[dict[str, int]] = {
    "accepts_character": 1,
}
