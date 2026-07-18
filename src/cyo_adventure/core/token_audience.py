"""Central registry of bearer-token audiences (issue #251).

The backend accepts three families of bearer token, each pinned to a distinct
``aud`` claim so a token minted for one branch can never be silently accepted by
another:

- guardian/admin Supabase OIDC tokens (``authenticated``),
- backend-signed child-session tokens (``cyo-child-session``),
- backend-signed device-grant tokens (``cyo-device-grant``).

The load-bearing separation is each branch's distinct signing key + algorithm
pin (a mis-routed token fails signature verification); the audience pin is
defense-in-depth on top of that. Before this module the three audience strings
lived in three unrelated places with no enforced invariant that they are
pairwise distinct. Collecting them here as a single ``StrEnum`` gives routing a
closed-world set and lets ``core/config.py`` assert the invariant at startup
without importing the token modules (which would be circular, since they import
``settings``).

This module intentionally has NO imports from the rest of the package so any
module (including ``core/config.py``) can depend on it.
"""

from __future__ import annotations

from enum import StrEnum


class TokenAudience(StrEnum):
    """The closed set of bearer-token audiences the backend routes on.

    Each member's value is the literal ``aud`` claim carried in the token and
    checked by the matching verifier. ``StrEnum`` members compare equal to and
    hash like their string value, so these can be used directly as the
    ``audience=`` argument to ``jwt.encode``/``jwt.decode`` and in the
    unverified-audience routing switch with no ``.value`` unwrapping.
    """

    # Supabase-issued guardian/admin session tokens. Mirrors the default of
    # ``settings.oidc_audience``; that setting stays configurable, and the
    # config validator asserts its value never collides with the two below.
    GUARDIAN_OIDC = "authenticated"
    CHILD_SESSION = "cyo-child-session"
    DEVICE_GRANT = "cyo-device-grant"
