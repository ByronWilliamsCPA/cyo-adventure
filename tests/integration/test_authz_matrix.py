"""Parametrized role x endpoint x method authorization matrix (org standard §14.7).

This module enumerates every route the FastAPI app actually registers (via
``app.routes``, not a hand-maintained route list) and cross-checks it against
an explicit, hand-authored expectation table (``ROUTE_TABLE``) of which roles
may pass each endpoint's own authorization gate. A route that is neither in
``ROUTE_TABLE`` nor in the public allowlist fails
``test_route_table_matches_discovered_routes`` immediately, so a new endpoint
added without an authorization decision cannot silently ship unguarded.

Deriving the table
-------------------
Every ``allowed_roles`` entry below was derived by reading the role gate in
the corresponding ``src/cyo_adventure/api/*.py`` handler (``is_admin``,
``is_guardian``, or an ``authorize_profile``/``authorize_family`` ownership
check; see ``api/deps.py`` for ``Principal``, ``authorize_profile``, and
``authorize_family``). Three role-gate shapes appear in this codebase:

* **Admin-only** (``_require_admin`` / ``if not ctx.principal.is_admin``):
  guardian and child are both rejected. Neither is "closer" to admin than
  the other; there is no partial-credit tier.
* **Guardian-only** (``_require_guardian`` / ``if not ctx.principal.is_guardian``):
  admin is rejected too (e.g. ``assignments.py``, ``generation.py``,
  ``profiles.py`` explicitly reject a global admin from family-scoped
  guardian actions; this is NOT a strict admin > guardian > child hierarchy).
* **Ownership-scoped, no role gate** (``authorize_profile`` /
  ``authorize_family`` only, e.g. ``reading.py``, ``ratings.py``,
  ``library.py::list_library``): both guardian and child may act on a
  profile/family they own; an admin-only adult structurally never owns a
  child profile (``_resolve_profiles`` in ``api/deps.py`` returns an empty
  set for the admin base role), so an admin-only token deterministically
  gets 403 here too, but via the ownership check, not a role gate.

Dual-role capability model
---------------------------
``role`` is the base persona and the admin capability is the orthogonal
``Principal.is_admin`` flag (``User.is_admin``), so one adult can be a
guardian, an admin, or both. The three base-persona tokens above pin the
single-role behavior unchanged; ``seed.dual_token`` (guardian base role +
admin capability) additionally pins that a dual-role principal passes the
UNION of the guardian and admin gates (see
``test_dual_role_token_passes_guardian_and_admin_gates``).

Every one of these gates whose authorization check is a cheap pre-check
(``is_admin``/``is_guardian``, or an ownership check against an id already in
hand) runs *before* any database row is loaded, so a caller outside
``allowed_roles`` gets an exact 403, never a 404-before-403 ambiguity. No
``(403, 404)`` exception list is needed for those routes; that is the
audited invariant this suite pins (see the module-level assertion in
``test_protected_endpoint_role_matrix``).

Three routes are the documented exception: ``characters.py``'s
``update_character``, ``activate_character``, and ``retire_character``
(``PATCH``/``POST .../activate``/``POST .../retire`` on
``/api/v1/characters/{character_id}``) load the row *before* calling
``authorize_profile``, because the id in the path is the character, not the
profile the ownership check needs -- there is no cheap pre-check available
(see the ``RouteSpec`` comment above the three character entries below for
why a real, seed-owned character id is required). For these three, a
disallowed role can legitimately see a 404 as well as a 403, which is why
they need their own cross-family IDOR coverage rather than relying on the
role-gate-before-load invariant above: see ``_CROSS_FAMILY_ROUTE_KEYS`` and
``_CROSS_FAMILY_CHILD_ROUTE_KEYS`` below.

Validator-legal requests
-------------------------
FastAPI resolves path/query/body parameters and the ``Context``/
``CurrentPrincipal`` dependency together; an invalid body would 422 before
the handler's own role check ever runs (masking the true 401/403). Every
``json_body``/``path_params``/``query_params`` builder below therefore
constructs a body that satisfies its Pydantic model's validators, using
seed-owned ids (``seed.child_profile_id``, ``seed.storybook_id``) wherever a
handler performs a *second*, ownership-specific check
(``authorize_profile``/``authorize_family``) after its role gate, so an
"allowed" role is never incidentally 403'd by an unrelated ownership
mismatch (e.g. ``assign_storybook`` and ``update_profile`` both re-check
``authorize_profile`` on their body/path id after the role gate).
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

import pytest

from cyo_adventure.api.deps import Role
from cyo_adventure.app import app
from tests.integration.conftest import Seed, Stranger, auth, mint_device_token

if TYPE_CHECKING:
    from collections.abc import Callable

    from httpx import AsyncClient

pytestmark = [pytest.mark.integration, pytest.mark.security, pytest.mark.asyncio]

ALL_ROLES: frozenset[Role] = frozenset({Role.GUARDIAN, Role.CHILD, Role.ADMIN})

# Public routes that require no bearer token at all (FastAPI's own docs/schema
# endpoints, plus the k8s health probes in api/health.py). Excluded from
# ROUTE_TABLE and from the completeness check below.
#
# The health router is mounted TWICE (UW-L04): the canonical
# ``/api/v1/health/*`` (in the OpenAPI schema, reachable through
# `frontend/nginx.conf`'s ``location /api/`` proxy) and the un-prefixed
# ``/health/*`` loopback alias the production container healthcheck still
# probes directly. Both sets of paths are genuinely unauthenticated routes
# the app serves, so both stay listed here.
#
# The two KWS routes (ADR-018) are a different case and must not be read as
# "unguarded". Neither carries a bearer token because neither caller holds a
# session: one is Epic's server calling us, the other is a parent's browser
# arriving from Epic's hosted flow. Each authenticates by HMAC instead, and
# each refuses before it parses anything when the signature is absent or
# wrong:
#   POST /api/v1/webhooks/kws/parent-verified  KWS_WEBHOOK_SECRET, Stripe-style
#       t=/v1= over the raw body, with a bounded clock skew. This is the ONLY
#       route that writes consent state.
#       Covered by tests/unit/test_kws_webhook.py.
#   GET  /api/v1/consent/kws/return            KWS_VERIFICATION_SECRET, HMAC
#       over "status:external_payload". That string carries no timestamp, so
#       it is replayable by construction, which is exactly why this route is
#       display-only and writes nothing.
#       Covered by tests/unit/test_kws_redirect.py.
# Listing them here says "no ROUTE_TABLE role expectation applies", not "no
# authorization applies". If either ever gains a session-authenticated form,
# it belongs in ROUTE_TABLE instead.
_PUBLIC_ROUTES: frozenset[tuple[str, str]] = frozenset(
    {
        ("POST", "/api/v1/webhooks/kws/parent-verified"),
        ("GET", "/api/v1/consent/kws/return"),
        ("GET", "/docs"),
        ("HEAD", "/docs"),
        ("GET", "/docs/oauth2-redirect"),
        ("HEAD", "/docs/oauth2-redirect"),
        ("GET", "/redoc"),
        ("HEAD", "/redoc"),
        ("GET", "/openapi.json"),
        ("HEAD", "/openapi.json"),
        ("GET", "/health/"),
        ("GET", "/health/live"),
        ("GET", "/health/ready"),
        ("GET", "/health/startup"),
        ("GET", "/api/v1/health/"),
        ("GET", "/api/v1/health/live"),
        ("GET", "/api/v1/health/ready"),
        ("GET", "/api/v1/health/startup"),
    }
)


# ---------------------------------------------------------------------------
# Path/query/body builders (all take the seed fixture; a plain literal is
# wrapped in a one-line lambda where no seed data is needed).
# ---------------------------------------------------------------------------


def _no_params(_seed: Seed) -> dict[str, str]:
    return {}


def _no_body(_seed: Seed) -> dict[str, Any] | None:
    return None


def _storybook_path(seed: Seed) -> dict[str, str]:
    return {"storybook_id": seed.storybook_id}


def _storybook_assignment_path(seed: Seed) -> dict[str, str]:
    # The per-child unassign path carries BOTH ids. The profile id must be one
    # the guardian actually owns: api/assignments.py::unassign_storybook runs
    # authorize_profile after its guardian-only gate, so a random uuid would
    # 403 the allowed role and make the matrix assert the wrong thing.
    # seed.child_profile_id is family A's, matching seed.guardian_token, and
    # matches what _assignment_body supplies to the POST twin.
    return {
        "storybook_id": seed.storybook_id,
        "profile_id": str(seed.child_profile_id),
    }


def _storybook_version_path(seed: Seed) -> dict[str, str]:
    return {"storybook_id": seed.storybook_id, "version": str(seed.version)}


def _storybook_version_node_path(seed: Seed) -> dict[str, str]:
    # #ASSUME: data integrity: this endpoint's own role/family gate runs
    # before the node is ever looked up (api/node_edit.py::_load_edit_target,
    # then the status/version checks), so an unknown node id at worst yields
    # a 404 for an allowed role -- a business-rule outcome distinct from the
    # 403 this matrix asserts on, per RouteSpec's own docs above. The literal
    # id is not required to exist in the seeded story.
    return {
        "storybook_id": seed.storybook_id,
        "version": str(seed.version),
        "node_id": "n_start",
    }


def _node_edit_body(_seed: Seed) -> dict[str, Any]:
    return {"body": "Authz-matrix probe body text."}


def _child_profile_path(seed: Seed) -> dict[str, str]:
    return {"profile_id": str(seed.child_profile_id)}


def _personalization_body(_seed: Seed) -> dict[str, Any]:
    return {
        "real_name_ring1_enabled": False,
        "real_name_ring2_enabled": False,
        "slots": [],
    }


def _personalization_receive_body(_seed: Seed) -> dict[str, Any]:
    # True is the column default, so an allowed role's write is a no-op and
    # this matrix run leaves no seed family opted out for later tests.
    return {"enabled": True}


def _ring2_consent_body(_seed: Seed) -> dict[str, Any]:
    # family_connection_id is a fresh, never-persisted uuid: the role gate
    # (_require_guardian) and the ownership check (authorize_profile on
    # profile_id) both run before the connection is ever looked up, so an
    # allowed GUARDIAN token legitimately resolves to a 404 here (mirrors
    # _random_uuid_path's own rationale).
    return {
        "family_connection_id": str(uuid.uuid4()),
        "covered_slot_types": ["pet_name"],
        "policy_version": "v1",
        "signer_name": "Authz Matrix Guardian",
        "accepted": True,
    }


def _ring2_consent_delete_path(seed: Seed) -> dict[str, str]:
    return {
        "profile_id": str(seed.child_profile_id),
        "connection_id": str(uuid.uuid4()),
    }


def _reading_state_path(seed: Seed) -> dict[str, str]:
    return {
        "profile_id": str(seed.child_profile_id),
        "storybook_id": seed.storybook_id,
    }


def _library_query(seed: Seed) -> dict[str, str]:
    return {"profile_id": str(seed.child_profile_id)}


def _threshold_query(_seed: Seed) -> dict[str, str]:
    return {"category": "authz-matrix-category"}


def _completion_body(seed: Seed) -> dict[str, Any]:
    return {
        "profile_id": str(seed.child_profile_id),
        "storybook_id": seed.storybook_id,
        "version": seed.version,
        "ending_id": "authz-matrix-ending",
    }


def _rating_body(seed: Seed) -> dict[str, Any]:
    return {
        "profile_id": str(seed.child_profile_id),
        "storybook_id": seed.storybook_id,
        "value": 3,
    }


def _flag_body(seed: Seed) -> dict[str, Any]:
    return {
        "profile_id": str(seed.child_profile_id),
        "storybook_id": seed.storybook_id,
        "version": seed.version,
        "reason": "did_not_like",
    }


def _flag_resolve_body(_seed: Seed) -> dict[str, Any]:
    return {"resolution": "dismissed"}


def _device_download_body(seed: Seed) -> dict[str, Any]:
    return {
        "device_id": "authz-matrix-device",
        "profile_id": str(seed.child_profile_id),
        "storybook_id": seed.storybook_id,
    }


def _device_download_query(seed: Seed) -> dict[str, str]:
    return {"device_id": "authz-matrix-device", "storybook_id": seed.storybook_id}


def _reading_time_body(_seed: Seed) -> dict[str, Any]:
    return {
        "date": datetime.now(tz=UTC).date().isoformat(),
        "seconds_delta": 30,
        "flush_id": str(uuid.uuid4()),
    }


def _reading_state_body(seed: Seed) -> dict[str, Any]:
    return {
        "version": seed.version,
        "current_node": "authz-matrix-node",
        "state_revision": 0,
    }


def _story_request_body(seed: Seed) -> dict[str, Any]:
    return {
        "profile_id": str(seed.child_profile_id),
        "request_text": "A story about a brave fox for the authorization matrix.",
    }


def _child_session_body(seed: Seed) -> dict[str, Any]:
    # A profile the guardian owns (authorize_profile runs after the role gate);
    # seed.child_profile_id is family A's, matching seed.guardian_token.
    return {"profile_id": str(seed.child_profile_id)}


def _story_request_authored_body(_seed: Seed) -> dict[str, Any]:
    # family_id deliberately omitted: a guardian's family is server-derived,
    # and an admin without one gets a 422 from _resolve_authored_family, both
    # of which are "not (401, 403)" outcomes for the two allowed roles.
    return {
        "request_text": "An authored request for the authorization matrix.",
        "age_band": "8-11",
        "length": "short",
    }


def _kws_verification_start_body(_seed: Seed) -> dict[str, Any]:
    # No email field exists on this body by design: the recipient comes from
    # the caller's own verified token, never from the request.
    return {"location": "US", "language": "en"}


def _story_request_spec_body(_seed: Seed) -> dict[str, Any]:
    return {"age_band": "8-11", "length": "short"}


def _authoring_plan_body(_seed: Seed) -> dict[str, Any]:
    return {
        "method": "skeleton_fill",
        "mechanism": "skill",
        "prep_model": "authz-matrix-model",
    }


def _send_back_body(_seed: Seed) -> dict[str, Any]:
    return {
        "reason": "authorization matrix regression check",
        "reason_code": "other",
    }


def _recall_body(_seed: Seed) -> dict[str, Any]:
    # `other`, not `threshold_change`, for the same reason _send_back_body uses
    # `other`: the code decides notification severity, and this suite is only
    # proving the role gate, so it should pick the value that asserts nothing
    # about why a recall happened.
    return {"reason_code": "other"}


def _assignment_body(seed: Seed) -> dict[str, Any]:
    # Must be a profile the guardian actually owns (authorize_profile runs a
    # second time per-id, after the guardian-only gate); seed.child_profile_id
    # is family A's, matching seed.guardian_token.
    return {"profile_ids": [str(seed.child_profile_id)]}


def _threshold_upsert_body(_seed: Seed) -> dict[str, Any]:
    return {"min_verdict": "advisory", "min_score": 0.5}


def _noise_floor_body(_seed: Seed) -> dict[str, Any]:
    return {"value": 0.5}


def _allowlist_create_body(_seed: Seed) -> dict[str, Any]:
    return {
        "provider": "anthropic",
        "model_id": "authz-matrix-model",
        "display_name": "Authz Matrix",
    }


def _allowlist_update_body(_seed: Seed) -> dict[str, Any]:
    return {"enabled": True, "display_name": "Authz Matrix Updated"}


def _profile_create_body(_seed: Seed) -> dict[str, Any]:
    return {"display_name": "Authz Matrix Kid", "age_band": "8-11"}


def _profile_update_body(_seed: Seed) -> dict[str, Any]:
    return {}


def _character_list_query(seed: Seed) -> dict[str, str]:
    return {"profile_id": str(seed.child_profile_id)}


def _character_create_body(seed: Seed) -> dict[str, Any]:
    return {
        "profile_id": str(seed.child_profile_id),
        "name": "Authz Matrix Character",
        "archetype": "scout",
        "look": "avatar_03",
    }


def _character_path(seed: Seed) -> dict[str, str]:
    return {"character_id": str(seed.character_id)}


def _character_update_body(_seed: Seed) -> dict[str, Any]:
    return {}


def _admin_user_create_body(seed: Seed) -> dict[str, Any]:
    # A fresh random suffix per call: two RouteSpec resolutions for this
    # endpoint against the same schema (e.g. the base matrix plus the
    # dual-role check) must never collide on the create_user's
    # duplicate-pending-invite-email guard (409).
    return {
        "email": f"authz-matrix-{uuid.uuid4()}@example.com",
        "family_id": str(seed.family_id),
        "role": "guardian",
    }


def _guardian_invite_body(_seed: Seed) -> dict[str, Any]:
    # Same fresh-suffix reasoning as _admin_user_create_body: this endpoint
    # shares create_pending_invite's duplicate-invite-email guard (409), which
    # now spans BOTH invite kinds, so a fixed address would collide across
    # resolutions. No family_id field exists on GuardianInviteBody at all: the
    # target family is always the caller's own (api/me.py::invite_guardian).
    return {"email": f"authz-matrix-invite-{uuid.uuid4()}@example.com"}


def _admin_user_update_body(_seed: Seed) -> dict[str, Any]:
    return {}


def _admin_profile_create_body(seed: Seed) -> dict[str, Any]:
    return {
        "family_id": str(seed.family_id),
        "display_name": "Authz Matrix Kid",
        "age_band": "8-11",
    }


def _admin_profile_update_body(_seed: Seed) -> dict[str, Any]:
    return {}


def _admin_family_create_body(_seed: Seed) -> dict[str, Any]:
    return {"name": "Authz Matrix Family"}


def _admin_family_update_body(_seed: Seed) -> dict[str, Any]:
    return {}


def _family_connection_create_body(_seed: Seed) -> dict[str, Any]:
    # Both ids are fresh, never-persisted uuids: the role gate runs before
    # either family is looked up, so an allowed role legitimately resolves to
    # a 404 (mirrors _random_uuid_path's rationale) rather than needing real
    # seed-owned families.
    return {
        "family_id": str(uuid.uuid4()),
        "connected_family_id": str(uuid.uuid4()),
    }


def _concept_create_body(_seed: Seed) -> dict[str, Any]:
    return {
        "brief": {
            "premise": "A fox explores a quiet forest at dawn.",
            "protagonist": {"name": "Robin", "age": 9, "role": "young explorer"},
            "age_band": "8-11",
            "reading_level_target": 3.0,
            "tier": 1,
            "tone": "adventurous",
            "target_node_count": 5,
            "ending_count": 1,
            "structure_pattern": "time_cave",
        }
    }


def _random_uuid_path(name: str) -> Callable[[Seed], dict[str, str]]:
    """Build a path_params resolver naming a fresh, never-persisted uuid.

    Used for ids where the handler's role gate runs before any lookup, so the
    id's realness does not matter for an authorization assertion; the
    "allowed role" case then legitimately resolves to a 404/422/409 (never
    401/403), which is exactly what ``test_protected_endpoint_role_matrix``
    treats as a pass.
    """

    def _build(_seed: Seed) -> dict[str, str]:
        return {name: str(uuid.uuid4())}

    return _build


# ---------------------------------------------------------------------------
# The route table
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class RouteSpec:
    """One (method, path) endpoint's authorization expectation.

    Attributes:
        allowed_roles: Roles that pass the endpoint's own authorization gate.
            Membership here says nothing about business-rule success (an
            allowed role may still see a 404/409/422 depending on the id it
            supplies); it only asserts the request is not rejected for
            insufficient privilege.
        path_params: Builds the path's ``.format()`` kwargs from the seed.
        query_params: Builds query-string kwargs from the seed.
        json_body: Builds a validator-legal JSON body from the seed, or
            ``None`` for a route with no request body.
    """

    method: str
    path_template: str
    allowed_roles: frozenset[Role]
    path_params: Callable[[Seed], dict[str, str]] = _no_params
    query_params: Callable[[Seed], dict[str, str]] = _no_params
    json_body: Callable[[Seed], dict[str, Any] | None] = _no_body

    def resolve(self, seed: Seed) -> tuple[str, dict[str, str], dict[str, Any] | None]:
        """Return the concrete (url, query_params, json_body) for one request."""
        url = self.path_template.format(**self.path_params(seed))
        return url, self.query_params(seed), self.json_body(seed)


_ROUTE_SPECS: list[RouteSpec] = [
    # -- families.py: admin-only (is_admin) --------------------------------
    RouteSpec("GET", "/api/v1/admin/families", frozenset({Role.ADMIN})),
    RouteSpec(
        "POST",
        "/api/v1/admin/families",
        frozenset({Role.ADMIN}),
        json_body=_admin_family_create_body,
    ),
    RouteSpec(
        "PATCH",
        "/api/v1/admin/families/{family_id}",
        frozenset({Role.ADMIN}),
        path_params=_random_uuid_path("family_id"),
        json_body=_admin_family_update_body,
    ),
    # -- admin_users.py: admin-only (_require_admin) -----------------------
    RouteSpec("GET", "/api/v1/admin/users", frozenset({Role.ADMIN})),
    RouteSpec(
        "POST",
        "/api/v1/admin/users",
        frozenset({Role.ADMIN}),
        json_body=_admin_user_create_body,
    ),
    RouteSpec(
        "PATCH",
        "/api/v1/admin/users/{user_id}",
        frozenset({Role.ADMIN}),
        path_params=_random_uuid_path("user_id"),
        json_body=_admin_user_update_body,
    ),
    # -- admin_profiles.py: admin-only (_require_admin) ---------------------
    RouteSpec("GET", "/api/v1/admin/profiles", frozenset({Role.ADMIN})),
    RouteSpec(
        "POST",
        "/api/v1/admin/profiles",
        frozenset({Role.ADMIN}),
        json_body=_admin_profile_create_body,
    ),
    RouteSpec(
        "PATCH",
        "/api/v1/admin/profiles/{profile_id}",
        frozenset({Role.ADMIN}),
        path_params=_random_uuid_path("profile_id"),
        json_body=_admin_profile_update_body,
    ),
    # -- family_connections.py: admin-only (_require_admin) -----------------
    RouteSpec("GET", "/api/v1/admin/family-connections", frozenset({Role.ADMIN})),
    RouteSpec(
        "POST",
        "/api/v1/admin/family-connections",
        frozenset({Role.ADMIN}),
        json_body=_family_connection_create_body,
    ),
    RouteSpec(
        "DELETE",
        "/api/v1/admin/family-connections/{connection_id}",
        frozenset({Role.ADMIN}),
        path_params=_random_uuid_path("connection_id"),
    ),
    # -- family_connections.py: guardian consent (ADR-016, register G17);
    # _require_guardian rejects admin-only too (mirrors notifications.py's
    # guardian-only feed, not a role-hierarchy exception). connection_id is a
    # fresh, never-persisted uuid in the two id-bearing specs: the role gate
    # runs before the row lookup, so an allowed GUARDIAN token legitimately
    # resolves to a 404 (mirrors _random_uuid_path's own rationale) rather
    # than needing a real seed-owned connection.
    RouteSpec("GET", "/api/v1/family-connections/mine", frozenset({Role.GUARDIAN})),
    RouteSpec(
        "POST",
        "/api/v1/family-connections/{connection_id}/consent",
        frozenset({Role.GUARDIAN}),
        path_params=_random_uuid_path("connection_id"),
    ),
    RouteSpec(
        "DELETE",
        "/api/v1/family-connections/{connection_id}/consent",
        frozenset({Role.GUARDIAN}),
        path_params=_random_uuid_path("connection_id"),
    ),
    # -- recommendations.py: ownership-scoped, admin bypass (K17, ADR-016) --
    RouteSpec(
        "GET",
        "/api/v1/recommendations/{profile_id}",
        frozenset({Role.GUARDIAN, Role.CHILD, Role.ADMIN}),
        path_params=_child_profile_path,
    ),
    # -- moderation_thresholds.py: admin-only (_require_admin) -------------
    RouteSpec("GET", "/api/v1/admin/moderation-thresholds", frozenset({Role.ADMIN})),
    RouteSpec(
        "PUT",
        "/api/v1/admin/moderation-thresholds/{age_band}",
        frozenset({Role.ADMIN}),
        path_params=lambda _seed: {"age_band": "8-11"},
        query_params=_threshold_query,
        json_body=_threshold_upsert_body,
    ),
    RouteSpec(
        "DELETE",
        "/api/v1/admin/moderation-thresholds/{age_band}",
        frozenset({Role.ADMIN}),
        path_params=lambda _seed: {"age_band": "8-11"},
        query_params=_threshold_query,
    ),
    RouteSpec("GET", "/api/v1/admin/moderation/dashboard", frozenset({Role.ADMIN})),
    RouteSpec("GET", "/api/v1/admin/audit", frozenset({Role.ADMIN})),
    RouteSpec(
        "POST",
        "/api/v1/admin/rescreen",
        frozenset({Role.ADMIN}),
        json_body=lambda _seed: {},
    ),
    # -- remoderate.py: admin-only (_require_admin) -------------------------
    # #CRITICAL: security: this route re-runs the FULL moderation pipeline
    # (real reviewer calls) synchronously on a PUBLISHED book, and the seeded
    # storybook IS published (tests/integration/conftest.py, status=
    # "published"). Handing it seed.storybook_id would make the admin leg of
    # the role matrix actually moderate a book: slow, network-touching, and
    # mutating the shared fixture row. A deliberately unknown id keeps the
    # authorization assertion intact while making the pipeline unreachable,
    # because api/remoderate.py::trigger_remoderate calls _require_admin
    # BEFORE any query: a non-admin is rejected 403 at the gate, and an admin
    # falls through to a 404 that never reaches run_moderation_pipeline.
    # #VERIFY: if this route ever stops gating before the lookup, the admin
    # leg starts running a real pipeline here; keep the gate-first ordering.
    RouteSpec(
        "POST",
        "/api/v1/admin/remoderate/{storybook_id}/{version}",
        frozenset({Role.ADMIN}),
        path_params=lambda _seed: {
            "storybook_id": "authz-matrix-no-such-storybook",
            "version": "1",
        },
    ),
    RouteSpec("GET", "/api/v1/admin/moderation/noise-floor", frozenset({Role.ADMIN})),
    RouteSpec(
        "PUT",
        "/api/v1/admin/moderation/noise-floor",
        frozenset({Role.ADMIN}),
        json_body=_noise_floor_body,
    ),
    RouteSpec("GET", "/api/v1/admin/moderation/suggestions", frozenset({Role.ADMIN})),
    # -- provider_allowlist.py: admin-only (_require_admin) -----------------
    RouteSpec("GET", "/api/v1/admin/provider-allowlist", frozenset({Role.ADMIN})),
    RouteSpec(
        "POST",
        "/api/v1/admin/provider-allowlist",
        frozenset({Role.ADMIN}),
        json_body=_allowlist_create_body,
    ),
    RouteSpec(
        "PUT",
        "/api/v1/admin/provider-allowlist/{entry_id}",
        frozenset({Role.ADMIN}),
        path_params=_random_uuid_path("entry_id"),
        json_body=_allowlist_update_body,
    ),
    RouteSpec(
        "DELETE",
        "/api/v1/admin/provider-allowlist/{entry_id}",
        frozenset({Role.ADMIN}),
        path_params=_random_uuid_path("entry_id"),
    ),
    # -- reading.py: ownership-scoped (authorize_profile/authorize_family) --
    RouteSpec(
        "POST",
        "/api/v1/completions",
        frozenset({Role.GUARDIAN, Role.CHILD}),
        json_body=_completion_body,
    ),
    # Phase 3d: ownership-scoped read, mirrors ratings.py::list_ratings.
    RouteSpec(
        "GET",
        "/api/v1/completions/{profile_id}",
        frozenset({Role.GUARDIAN, Role.CHILD}),
        path_params=_child_profile_path,
    ),
    # -- generation.py: guardian-only (is_guardian), admin rejected too -----
    RouteSpec(
        "POST",
        "/api/v1/concepts",
        frozenset({Role.GUARDIAN}),
        json_body=_concept_create_body,
    ),
    RouteSpec(
        "POST",
        "/api/v1/concepts/{concept_id}/generate",
        frozenset({Role.GUARDIAN}),
        path_params=_random_uuid_path("concept_id"),
    ),
    RouteSpec("GET", "/api/v1/generation-jobs", frozenset({Role.GUARDIAN})),
    RouteSpec(
        "GET",
        "/api/v1/generation-jobs/{job_id}",
        frozenset({Role.GUARDIAN}),
        path_params=_random_uuid_path("job_id"),
    ),
    # generation.py: admin-only operator endpoint to force-fail a stranded job
    # (guardian and child are both rejected; see test_force_fail_requires_admin).
    RouteSpec(
        "POST",
        "/api/v1/admin/generation-jobs/{job_id}/force-fail",
        frozenset({Role.ADMIN}),
        path_params=_random_uuid_path("job_id"),
    ),
    # -- assignments.py: guardian-only browse surface -----------------------
    RouteSpec("GET", "/api/v1/guardian/books", frozenset({Role.GUARDIAN})),
    # -- library.py --------------------------------------------------------
    RouteSpec(
        "GET",
        "/api/v1/library",
        frozenset({Role.GUARDIAN, Role.CHILD}),
        query_params=_library_query,
    ),
    # -- me.py: identity introspection, no role gate ------------------------
    RouteSpec("GET", "/api/v1/me", ALL_ROLES),
    # -- me.py: Phase 3c/3b, guardian-only (role checked before any DB read) -
    RouteSpec("GET", "/api/v1/me/export", frozenset({Role.GUARDIAN})),
    RouteSpec("DELETE", "/api/v1/me/family", frozenset({Role.GUARDIAN})),
    # G14 guardian self-service co-parent invite. GUARDIAN only: an admin
    # invites through POST /admin/users instead (this endpoint has no
    # family_id, so an admin calling it could only invite into their own
    # family, which is not what the admin console means). Deliberately NOT in
    # _CROSS_FAMILY_ROUTE_KEYS: there is no cross-family id to resolve, the
    # target family is always ctx.principal.family_id.
    RouteSpec(
        "POST",
        "/api/v1/me/family/invite-guardian",
        frozenset({Role.GUARDIAN}),
        json_body=_guardian_invite_body,
    ),
    # -- progress.py: W3.1, child-only ("me", no path param; see that
    # module's docstring for why no guardian/admin variant exists yet) ------
    RouteSpec("GET", "/api/v1/me/progress", frozenset({Role.CHILD})),
    # -- reading_time.py: W3.3, child-only, same "me" shape as progress.py --
    RouteSpec(
        "POST",
        "/api/v1/me/reading-time",
        frozenset({Role.CHILD}),
        json_body=_reading_time_body,
    ),
    # -- profiles.py ---------------------------------------------------------
    RouteSpec("GET", "/api/v1/profiles", ALL_ROLES),
    # W1.4: same allowed-role set as GET /profiles by construction -- both
    # endpoints derive their visible profile set from the identical
    # api/profiles.py::_listable_profiles helper, so whichever roles may list
    # profiles at all may also read this boolean-only pill status for them.
    RouteSpec("GET", "/api/v1/profiles/story-status", ALL_ROLES),
    RouteSpec(
        "POST",
        "/api/v1/profiles",
        frozenset({Role.GUARDIAN}),
        json_body=_profile_create_body,
    ),
    RouteSpec(
        "PATCH",
        "/api/v1/profiles/{profile_id}",
        frozenset({Role.GUARDIAN}),
        # A profile the guardian owns: _require_guardian runs first, but
        # authorize_profile runs right after and would 403 an allowed
        # guardian on an id it does not own.
        path_params=_child_profile_path,
        json_body=_profile_update_body,
    ),
    # Phase 3b: guardian-only, family-ownership-scoped (authorize_family, not
    # authorize_profile -- see delete_profile's docstring for why a
    # deactivated profile must still be reachable here).
    RouteSpec(
        "DELETE",
        "/api/v1/profiles/{profile_id}",
        frozenset({Role.GUARDIAN}),
        path_params=_child_profile_path,
    ),
    # -- characters.py: ownership-scoped (authorize_profile), ADR-028.
    # GET/create/update/activate/retire carry no role gate at all -- a child
    # may manage their own characters exactly like a guardian can -- so
    # ADMIN legitimately 403s via the empty profile_ids an admin principal
    # resolves to, not via any role check in the handler. Only DELETE is
    # guardian-only (_require_guardian): irreversible progression loss.
    RouteSpec(
        "GET",
        "/api/v1/characters",
        frozenset({Role.GUARDIAN, Role.CHILD}),
        query_params=_character_list_query,
    ),
    RouteSpec(
        "POST",
        "/api/v1/characters",
        frozenset({Role.GUARDIAN, Role.CHILD}),
        json_body=_character_create_body,
    ),
    RouteSpec(
        "PATCH",
        "/api/v1/characters/{character_id}",
        frozenset({Role.GUARDIAN, Role.CHILD}),
        # A character the caller owns: load-then-authorize has no cheap
        # pre-check, so a disallowed role's request must reach a REAL row
        # to 403 rather than 404 first (see RouteSpec's own docs above).
        path_params=_character_path,
        json_body=_character_update_body,
    ),
    RouteSpec(
        "POST",
        "/api/v1/characters/{character_id}/activate",
        frozenset({Role.GUARDIAN, Role.CHILD}),
        path_params=_character_path,
    ),
    RouteSpec(
        "POST",
        "/api/v1/characters/{character_id}/retire",
        frozenset({Role.GUARDIAN, Role.CHILD}),
        path_params=_character_path,
    ),
    # _require_guardian runs first with no I/O, so a disallowed role legitimately
    # 403s before any row lookup; a random id is safe here (mirrors
    # delete_profile's own DELETE entry above).
    RouteSpec(
        "DELETE",
        "/api/v1/characters/{character_id}",
        frozenset({Role.GUARDIAN}),
        path_params=_random_uuid_path("character_id"),
    ),
    # -- personalization.py: ring-1/ring-2 CRUD, guardian-only
    # (_require_guardian rejects admin-only too, same shape as profiles.py) --
    RouteSpec(
        "GET",
        "/api/v1/profiles/{profile_id}/personalization",
        frozenset({Role.GUARDIAN}),
        path_params=_child_profile_path,
    ),
    RouteSpec(
        "PUT",
        "/api/v1/profiles/{profile_id}/personalization",
        frozenset({Role.GUARDIAN}),
        path_params=_child_profile_path,
        json_body=_personalization_body,
    ),
    RouteSpec(
        "POST",
        "/api/v1/profiles/{profile_id}/ring2-consent",
        frozenset({Role.GUARDIAN}),
        path_params=_child_profile_path,
        json_body=_ring2_consent_body,
    ),
    RouteSpec(
        "DELETE",
        "/api/v1/profiles/{profile_id}/ring2-consent/{connection_id}",
        frozenset({Role.GUARDIAN}),
        # A fresh, never-persisted connection_id: _require_sharer_side runs
        # after the role gate and after the (real) profile lookup, so an
        # allowed GUARDIAN token legitimately resolves to a 404 for an
        # unknown connection (mirrors _random_uuid_path's own rationale).
        path_params=_ring2_consent_delete_path,
    ),
    # -- personalization.py: the viewer-side receive switch (ADR-023 8.6).
    # Guardian-only and scoped to the caller's OWN family: there is no id in
    # the path or body, so it needs no cross-family case (nothing to point
    # at another household with) and no path_params.
    RouteSpec(
        "GET",
        "/api/v1/families/me/personalization-receive",
        frozenset({Role.GUARDIAN}),
    ),
    RouteSpec(
        "PUT",
        "/api/v1/families/me/personalization-receive",
        frozenset({Role.GUARDIAN}),
        json_body=_personalization_receive_body,
    ),
    # -- personalization.py: the single values-resolution route. A genuinely
    # new authorization shape (ADR-023 plan section 8.5): it does NOT
    # authorize on the subject profile at all, only on the caller's own
    # family membership plus whatever FamilyConnection the server resolves.
    # There is no role gate, so every role (including a device grant, though
    # DEVICE has no seed fixture here) passes through to the predicate, which
    # renders the universal empty payload rather than a 403 on any mismatch.
    RouteSpec(
        "GET",
        "/api/v1/storybooks/{storybook_id}/personalization-values",
        ALL_ROLES,
        path_params=_storybook_path,
    ),
    # -- ratings.py: ownership-scoped ----------------------------------------
    RouteSpec(
        "POST",
        "/api/v1/ratings",
        frozenset({Role.GUARDIAN, Role.CHILD}),
        json_body=_rating_body,
    ),
    RouteSpec(
        "GET",
        "/api/v1/ratings/{profile_id}",
        frozenset({Role.GUARDIAN, Role.CHILD}),
        path_params=_child_profile_path,
    ),
    # -- flags.py: K15 kid flag, ownership-scoped like ratings.py -------------
    RouteSpec(
        "POST",
        "/api/v1/flags",
        frozenset({Role.GUARDIAN, Role.CHILD}),
        json_body=_flag_body,
    ),
    RouteSpec("GET", "/api/v1/admin/flags", frozenset({Role.ADMIN})),
    RouteSpec(
        "POST",
        "/api/v1/admin/flags/{flag_id}/resolve",
        frozenset({Role.ADMIN}),
        path_params=_random_uuid_path("flag_id"),
        json_body=_flag_resolve_body,
    ),
    # -- offline_downloads.py: G15 storage/download view ----------------------
    RouteSpec(
        "PUT",
        "/api/v1/device-downloads",
        frozenset({Role.GUARDIAN, Role.CHILD}),
        json_body=_device_download_body,
    ),
    RouteSpec(
        "DELETE",
        "/api/v1/device-downloads",
        frozenset({Role.GUARDIAN, Role.CHILD, Role.ADMIN, Role.DEVICE}),
        query_params=_device_download_query,
    ),
    RouteSpec(
        "GET",
        "/api/v1/device-downloads",
        frozenset({Role.GUARDIAN, Role.ADMIN}),
    ),
    # -- notifications.py: guardian-only feed (S9/G10), same shape as
    # generation-jobs above: no path params, family-scoped via
    # ctx.principal.family_id, admin rejected too (not a family-scoped role).
    RouteSpec("GET", "/api/v1/notifications", frozenset({Role.GUARDIAN})),
    # -- notifications.py: SSE push transport, same guardian-only gate as the
    # poll endpoint above (stream_notifications resolves and role-checks the
    # principal directly rather than via Context, but the bearer contract and
    # the guardian-only rejection are identical). An allowed-role request
    # here does not return until Settings.notification_stream_max_seconds
    # elapses (no seeded event ends the stream sooner): see that setting's
    # docstring in core/config.py for why the default is kept modest.
    RouteSpec("GET", "/api/v1/notifications/stream", frozenset({Role.GUARDIAN})),
    # -- reading.py: reading-state (ownership-scoped) ------------------------
    RouteSpec(
        "GET",
        "/api/v1/reading-state/{profile_id}/{storybook_id}",
        frozenset({Role.GUARDIAN, Role.CHILD}),
        path_params=_reading_state_path,
    ),
    # -- reading_history.py: ownership-scoped, admin bypass (register K6/G9) -
    RouteSpec(
        "GET",
        "/api/v1/reading-history/{profile_id}",
        frozenset({Role.GUARDIAN, Role.CHILD, Role.ADMIN}),
        path_params=_child_profile_path,
    ),
    # -- reading_history.py: guardian-or-admin, always the caller's own
    # family (no path/query id, so there is no cross-family surface here) --
    RouteSpec(
        "GET",
        "/api/v1/families/me/reading-summary",
        frozenset({Role.GUARDIAN, Role.ADMIN}),
    ),
    # -- story_requests.py: ADR-015 G7/G3 budget snapshot, same shape as
    # reading-summary above (adults-only, always the caller's own family) --
    RouteSpec(
        "GET",
        "/api/v1/families/me/budget",
        frozenset({Role.GUARDIAN, Role.ADMIN}),
    ),
    RouteSpec(
        "PUT",
        "/api/v1/reading-state/{profile_id}/{storybook_id}",
        frozenset({Role.GUARDIAN, Role.CHILD}),
        path_params=_reading_state_path,
        json_body=_reading_state_body,
    ),
    RouteSpec(
        # Same gate as reading-state GET: authorize_profile then the
        # _load_readable_storybook read gate on the CURRENT book, both before
        # any series row is read (api/reading.py::get_series_next).
        "GET",
        "/api/v1/series-next/{profile_id}/{storybook_id}",
        frozenset({Role.GUARDIAN, Role.CHILD}),
        path_params=_reading_state_path,
    ),
    # -- approval.py: admin-only (global, cross-family) ----------------------
    RouteSpec("GET", "/api/v1/review-queue", frozenset({Role.ADMIN})),
    # -- story_requests.py ----------------------------------------------------
    RouteSpec(
        "POST",
        "/api/v1/story-requests",
        frozenset({Role.GUARDIAN, Role.CHILD}),
        json_body=_story_request_body,
    ),
    RouteSpec("GET", "/api/v1/story-requests", ALL_ROLES),
    # The global review queue: the explicit admin surface for what used to be
    # an is_admin scope fork inside GET /story-requests.
    RouteSpec("GET", "/api/v1/admin/story-requests", frozenset({Role.ADMIN})),
    # -- child_sessions.py: guardian-or-admin mint (child rejected) ----------
    RouteSpec(
        "POST",
        "/api/v1/child-sessions",
        frozenset({Role.GUARDIAN, Role.ADMIN}),
        json_body=_child_session_body,
    ),
    # -- device_grants.py: guardian-or-admin management (child rejected;
    # a DEVICE principal is also rejected by this same gate, but DEVICE is
    # not in ALL_ROLES so it is not exercised by this matrix; see
    # test_device_grants.py::test_device_token_cannot_mint_another_device_grant
    # for that coverage) -------------------------------------------------
    RouteSpec(
        "POST",
        "/api/v1/device-grants",
        frozenset({Role.GUARDIAN, Role.ADMIN}),
    ),
    RouteSpec(
        "GET",
        "/api/v1/device-grants",
        frozenset({Role.GUARDIAN, Role.ADMIN}),
    ),
    RouteSpec(
        "DELETE",
        "/api/v1/device-grants/{grant_id}",
        frozenset({Role.GUARDIAN, Role.ADMIN}),
        path_params=_random_uuid_path("grant_id"),
    ),
    # -- onboarding.py: JIT provisioning; any verified subject (P6-03) -------
    # Onboarding runs BEFORE a principal exists (its whole purpose is to accept
    # a verified subject that has no User row yet), so it has no role gate: each
    # seed opaque token already resolves to a User row and returns 200. The one
    # credential it does refuse (403) is a child SESSION JWT (child audience),
    # not the opaque child token the matrix carries; that refusal is covered in
    # test_onboarding_api.py::test_child_session_token_cannot_onboard.
    RouteSpec("POST", "/api/v1/onboarding", ALL_ROLES),
    # -- consent.py: KWS parent verification start (ADR-018 D1) -------------
    # Same authentication posture as onboarding, and for the same reason: it
    # uses OnboardingIdentityDep rather than Context because verification sits
    # BEFORE admin approval, so a caller awaiting approval (not `active`) is
    # exactly who this endpoint exists for. Hence no role gate here.
    #
    # The child row IS refused (403) by the endpoint's own second gate, but not
    # on this tier: `settings.kws_configured` is checked first and an
    # unconfigured test deployment returns 400 before the role is ever read, so
    # every role lands on "not (401, 403)". The child refusal is pinned where
    # it can actually be observed, in test_consent_api.py::
    # test_a_child_row_cannot_start_a_verification.
    RouteSpec(
        "POST",
        "/api/v1/consent/kws/start",
        ALL_ROLES,
        json_body=_kws_verification_start_body,
    ),
    RouteSpec(
        "POST",
        "/api/v1/story-requests/authored",
        frozenset({Role.GUARDIAN, Role.ADMIN}),
        json_body=_story_request_authored_body,
    ),
    RouteSpec(
        "POST",
        "/api/v1/story-requests/{request_id}/approve",
        frozenset({Role.GUARDIAN, Role.ADMIN}),
        path_params=_random_uuid_path("request_id"),
        json_body=_story_request_spec_body,
    ),
    RouteSpec(
        "POST",
        "/api/v1/story-requests/{request_id}/authoring-plan",
        frozenset({Role.ADMIN}),
        path_params=_random_uuid_path("request_id"),
        json_body=_authoring_plan_body,
    ),
    RouteSpec(
        "POST",
        "/api/v1/story-requests/{request_id}/decline",
        frozenset({Role.GUARDIAN, Role.ADMIN}),
        path_params=_random_uuid_path("request_id"),
    ),
    # -- approval.py: admin-only publish state machine -----------------------
    # Admin master library: browse every storybook in any lifecycle status.
    RouteSpec("GET", "/api/v1/admin/storybooks", frozenset({Role.ADMIN})),
    RouteSpec(
        "POST",
        "/api/v1/storybooks/{storybook_id}/approve",
        frozenset({Role.ADMIN}),
        path_params=_storybook_path,
    ),
    RouteSpec(
        "POST",
        "/api/v1/storybooks/{storybook_id}/archive",
        frozenset({Role.ADMIN}),
        path_params=_storybook_path,
    ),
    RouteSpec(
        "POST",
        "/api/v1/storybooks/{storybook_id}/recall",
        frozenset({Role.ADMIN}),
        path_params=_storybook_path,
        json_body=_recall_body,
    ),
    # `RS-C2`/`RS-C3`: the decisions the review queue structurally cannot list.
    # Admin-only for the same reason the queue is: the rows name moderation
    # findings across every family.
    RouteSpec("GET", "/api/v1/admin/outstanding-decisions", frozenset({Role.ADMIN})),
    # -- assignments.py: guardian-only (admin rejected too) ------------------
    RouteSpec(
        "POST",
        "/api/v1/storybooks/{storybook_id}/assignments",
        frozenset({Role.GUARDIAN}),
        path_params=_storybook_path,
        json_body=_assignment_body,
    ),
    RouteSpec(
        "DELETE",
        "/api/v1/storybooks/{storybook_id}/assignments/{profile_id}",
        frozenset({Role.GUARDIAN}),
        path_params=_storybook_assignment_path,
    ),
    RouteSpec(
        "GET",
        "/api/v1/storybooks/{storybook_id}/assignments",
        frozenset({Role.GUARDIAN}),
        path_params=_storybook_path,
    ),
    RouteSpec(
        "GET",
        "/api/v1/storybooks/{storybook_id}/content-summary",
        frozenset({Role.GUARDIAN, Role.ADMIN}),
        path_params=_storybook_path,
    ),
    # register G6 edit half: admin (cross-family), or guardian for their own
    # family's story (api/approval.py::_load_review_target, mirroring
    # node_edit.py::_load_edit_target's role gate + authorize_family below).
    RouteSpec(
        "GET",
        "/api/v1/storybooks/{storybook_id}/review",
        frozenset({Role.ADMIN, Role.GUARDIAN}),
        path_params=_storybook_path,
    ),
    RouteSpec(
        "POST",
        "/api/v1/storybooks/{storybook_id}/send-back",
        frozenset({Role.ADMIN}),
        path_params=_storybook_path,
        json_body=_send_back_body,
    ),
    RouteSpec(
        "POST",
        "/api/v1/storybooks/{storybook_id}/submit",
        frozenset({Role.ADMIN}),
        path_params=_storybook_path,
    ),
    # -- library.py: get_storybook_version, no hard role gate ----------------
    RouteSpec(
        "GET",
        "/api/v1/storybooks/{storybook_id}/versions/{version}",
        ALL_ROLES,
        path_params=_storybook_version_path,
    ),
    # -- covers.py: admin-only -------------------------------------------------
    RouteSpec(
        "POST",
        "/api/v1/storybooks/{storybook_id}/versions/{version}/cover",
        frozenset({Role.ADMIN}),
        path_params=_storybook_version_path,
    ),
    RouteSpec(
        "GET",
        "/api/v1/storybooks/{storybook_id}/versions/{version}/cover",
        frozenset({Role.ADMIN}),
        path_params=_storybook_version_path,
    ),
    # covers.py::approve_cover calls _require_admin before any row is loaded,
    # and covers/service.py::approve_cover re-checks `principal.is_admin` as
    # defense in depth; a non-admin therefore never reaches the version
    # lookup, so the exact-403 invariant this suite pins holds here too. An
    # admin on the seed row falls through to the status check
    # (BusinessLogicError, rule="cover_approve_not_pending") because the seed
    # cover is not "pending_review": a business-rule outcome, not a privilege
    # rejection, which is exactly what `allowed_roles` scopes.
    RouteSpec(
        "POST",
        "/api/v1/storybooks/{storybook_id}/versions/{version}/cover/approve",
        frozenset({Role.ADMIN}),
        path_params=_storybook_version_path,
    ),
    # -- generation.py: guardian-only -------------------------------------------
    RouteSpec(
        "POST",
        "/api/v1/storybooks/{storybook_id}/versions/{version}/validate",
        frozenset({Role.GUARDIAN}),
        path_params=_storybook_version_path,
    ),
    # -- node_edit.py: admin, or guardian for their own family's story
    # (api/node_edit.py::_load_edit_target: role gate before load, then
    # authorize_family for a non-admin) --------------------------------------
    RouteSpec(
        "PATCH",
        "/api/v1/storybooks/{storybook_id}/versions/{version}/nodes/{node_id}",
        frozenset({Role.ADMIN, Role.GUARDIAN}),
        path_params=_storybook_version_node_path,
        json_body=_node_edit_body,
    ),
]

ROUTE_TABLE: dict[tuple[str, str], RouteSpec] = {
    (spec.method, spec.path_template): spec for spec in _ROUTE_SPECS
}

# Every route above is unique; a duplicate key would silently drop an entry.
assert len(ROUTE_TABLE) == len(_ROUTE_SPECS), "duplicate (method, path) in _ROUTE_SPECS"

_TOKEN_BY_ROLE: dict[Role, Callable[[Seed], str]] = {
    Role.GUARDIAN: lambda seed: seed.guardian_token,
    Role.CHILD: lambda seed: seed.child_token,
    Role.ADMIN: lambda seed: seed.admin_token,
}

_ROUTE_IDS = [f"{method} {path}" for method, path in sorted(ROUTE_TABLE)]


def _discover_routes() -> set[tuple[str, str]]:
    """Flatten the FastAPI app's route tree into (method, path) pairs.

    FastAPI wraps ``app.include_router(...)`` mounts as an internal
    ``_IncludedRouter`` node rather than inlining child routes directly into
    ``app.routes``; ``original_router.routes`` is the private attribute that
    recovers them. This is FastAPI-version-specific internals, not a public
    API; a future FastAPI upgrade that changes this structure will make this
    walk return too few routes, which the minimum-count assertion below
    turns into a loud failure instead of a silently-empty (falsely passing)
    completeness check.

    ``route.path`` on a leaf route only reflects the prefix baked into the
    router's OWN declaration (e.g. ``APIRouter(prefix="/api/v1/admin")`` in
    ``admin_users.py``); a prefix supplied at the ``include_router(...,
    prefix=...)`` call site instead lives on the ``_IncludedRouter`` node's
    ``include_context.prefix`` and is applied lazily at request-dispatch
    time, never written back onto the leaf route. Every router except
    ``health`` bakes its full ``/api/v1/...`` prefix into its own
    declaration and is included with no extra prefix, so this was invisible
    until ``health.router`` (declared with only ``prefix="/health"``) became
    the first router mounted with an include-time prefix
    (``app.include_router(health.router, prefix="/api/v1")``, UW-L04): without
    accumulating ``include_context.prefix`` while walking, this function
    could never discover ``/api/v1/health/*`` at all, silently failing the
    completeness check the moment those routes were added to
    ``_PUBLIC_ROUTES`` below.
    """

    def walk(routes: object, prefix: str = "") -> list[tuple[str, str]]:
        out: list[tuple[str, str]] = []
        for route in routes:  # type: ignore[attr-defined]
            if type(route).__name__ == "_IncludedRouter":
                out.extend(
                    walk(
                        route.original_router.routes,
                        prefix + route.include_context.prefix,
                    )
                )
            elif hasattr(route, "path") and hasattr(route, "methods"):
                out.extend(
                    (method, prefix + route.path) for method in route.methods or []
                )
        return out

    return set(walk(app.routes))


async def test_route_table_matches_discovered_routes() -> None:
    """A route with no authorization decision must fail this test.

    Every route FastAPI actually serves must appear in exactly one of
    ``ROUTE_TABLE`` (an authorization decision was made) or
    ``_PUBLIC_ROUTES`` (an explicit decision that no auth is required). A
    route in neither means someone added an endpoint without deciding who
    may call it; a route in ``ROUTE_TABLE``/``_PUBLIC_ROUTES`` that no longer
    exists is a stale entry that should be removed.
    """
    discovered = _discover_routes()
    # #ASSUME: external-resources: this floor (46 protected + 12 public = 58
    # minus a handful of doc/redirect duplicates) guards against the FastAPI
    # internals this walk relies on silently returning zero routes on a
    # version upgrade, which would otherwise make the set-equality checks
    # below vacuously pass.
    # #VERIFY: raising the app's route count (a new router) only ever grows
    # this number; a future FastAPI upgrade that breaks `_discover_routes`
    # trips this floor first, before the set-difference assertions run.
    assert len(discovered) >= 40, (
        "route discovery found too few routes; FastAPI's internal route-tree "
        "structure may have changed (see _discover_routes docstring)"
    )
    covered = set(ROUTE_TABLE) | _PUBLIC_ROUTES
    missing = discovered - covered
    extra = covered - discovered
    assert not missing, (
        "routes with no authorization expectation in test_authz_matrix.py "
        f"(add to ROUTE_TABLE or _PUBLIC_ROUTES): {sorted(missing)}"
    )
    assert not extra, (
        "test_authz_matrix.py has stale entries for routes that no longer "
        f"exist: {sorted(extra)}"
    )


@pytest.mark.parametrize(
    ("method", "path_template"), sorted(ROUTE_TABLE), ids=_ROUTE_IDS
)
async def test_protected_endpoint_without_token_is_401(
    client: AsyncClient, seed: Seed, method: str, path_template: str
) -> None:
    """Every protected route rejects a request carrying no bearer token."""
    spec = ROUTE_TABLE[(method, path_template)]
    url, query, body = spec.resolve(seed)
    resp = await client.request(method, url, params=query, json=body)
    assert resp.status_code == 401, (
        f"{method} {path_template} without a bearer token expected 401, got "
        f"{resp.status_code}: {resp.text}"
    )


@pytest.mark.parametrize(
    ("method", "path_template"), sorted(ROUTE_TABLE), ids=_ROUTE_IDS
)
async def test_protected_endpoint_role_matrix(
    client: AsyncClient, seed: Seed, method: str, path_template: str
) -> None:
    """Exercise every role against one route: exact 403 below/outside the gate.

    A role outside ``spec.allowed_roles`` always gets exactly 403 in this
    codebase (never a 404-before-403 ambiguity): every role gate this table
    was derived from (``is_admin``/``is_guardian``/``authorize_profile``/
    ``authorize_family``) runs before any database row is loaded, confirmed
    by reading each handler in ``src/cyo_adventure/api/*.py`` (see the module
    docstring). A role inside ``allowed_roles`` must never be rejected for
    privilege (401/403); its actual business-rule outcome (200/201/404/409/
    422) is out of scope for this authorization-only suite.
    """
    spec = ROUTE_TABLE[(method, path_template)]
    url, query, body = spec.resolve(seed)
    for role in sorted(ALL_ROLES):
        token = _TOKEN_BY_ROLE[role](seed)
        resp = await client.request(
            method, url, params=query, json=body, headers=auth(token)
        )
        if role in spec.allowed_roles:
            assert resp.status_code not in (401, 403), (
                f"{method} {path_template} unexpectedly rejected allowed "
                f"role={role.value}: {resp.status_code} {resp.text}"
            )
        else:
            assert resp.status_code == 403, (
                f"{method} {path_template} expected exactly 403 for "
                f"disallowed role={role.value}, got {resp.status_code}: "
                f"{resp.text}"
            )


@pytest.mark.parametrize(
    ("method", "path_template"), sorted(ROUTE_TABLE), ids=_ROUTE_IDS
)
async def test_dual_role_token_passes_guardian_and_admin_gates(
    client: AsyncClient, seed: Seed, method: str, path_template: str
) -> None:
    """A guardian-with-admin-capability passes the union of both role gates.

    ``seed.dual_token`` resolves to ``(role=guardian, is_admin=True)``: its
    guardian base role resolves the family's profile set (so ownership-scoped
    routes work) and passes guardian-only gates, while the capability flag
    passes admin-only gates. Any route that admits guardian OR admin must
    therefore never reject this token for privilege; a route that admits
    neither (child-only, none exist today) must still 403 it exactly.
    """
    spec = ROUTE_TABLE[(method, path_template)]
    url, query, body = spec.resolve(seed)
    resp = await client.request(
        method, url, params=query, json=body, headers=auth(seed.dual_token)
    )
    if spec.allowed_roles & {Role.GUARDIAN, Role.ADMIN}:
        assert resp.status_code not in (401, 403), (
            f"{method} {path_template} rejected the dual-role principal, "
            f"which holds both capabilities: {resp.status_code} {resp.text}"
        )
    else:
        assert resp.status_code == 403, (
            f"{method} {path_template} expected exactly 403 for the "
            f"dual-role principal on a route admitting neither guardian nor "
            f"admin, got {resp.status_code}: {resp.text}"
        )


# ---------------------------------------------------------------------------
# Cross-family IDOR checks
# ---------------------------------------------------------------------------
#
# The role matrix above proves that an out-of-role token is rejected; it never
# proves that an in-role token from a DIFFERENT family is rejected for the
# SAME resource (an IDOR: a guardian in family B is ``Role.GUARDIAN``, so it
# passes every role gate, and only the ownership check -- authorize_profile /
# authorize_family / the book visibility gate -- can stop it). The seed
# fixture already mints ``other_guardian_token`` (family B's guardian) for
# exactly this purpose but, until now, nothing in this module ever sent a
# request with it. The routes below are a representative sample of every
# ownership-check shape in ROUTE_TABLE: a path-param profile id
# (ratings/reading-state/profiles), a query-param profile id (library), a
# request-body profile id (completions), and a path-param storybook/family id
# with no profile at all (assignments, content-summary). Every id the spec's
# builders produce belongs to family A (the ``seed`` fixture); resolving them
# with family B's guardian token is the cross-family attack this section pins.

_CROSS_FAMILY_ROUTE_KEYS: list[tuple[str, str]] = [
    ("GET", "/api/v1/ratings/{profile_id}"),
    ("POST", "/api/v1/ratings"),
    ("POST", "/api/v1/flags"),
    ("GET", "/api/v1/library"),
    ("PATCH", "/api/v1/profiles/{profile_id}"),
    ("GET", "/api/v1/reading-state/{profile_id}/{storybook_id}"),
    ("PUT", "/api/v1/reading-state/{profile_id}/{storybook_id}"),
    ("GET", "/api/v1/series-next/{profile_id}/{storybook_id}"),
    ("POST", "/api/v1/completions"),
    ("GET", "/api/v1/storybooks/{storybook_id}/assignments"),
    ("POST", "/api/v1/storybooks/{storybook_id}/assignments"),
    ("DELETE", "/api/v1/storybooks/{storybook_id}/assignments/{profile_id}"),
    ("GET", "/api/v1/storybooks/{storybook_id}/content-summary"),
    ("GET", "/api/v1/reading-history/{profile_id}"),
    ("GET", "/api/v1/storybooks/{storybook_id}/review"),
    ("PATCH", "/api/v1/storybooks/{storybook_id}/versions/{version}/nodes/{node_id}"),
    ("GET", "/api/v1/recommendations/{profile_id}"),
    # personalization.py: the four guardian-gated CRUD routes. These reach a
    # child's real name, sibling names, pet name, kinship label, and
    # dedication, the most sensitive per-child data in the schema, and until
    # now not one of them had a cross-family IDOR assertion anywhere in the
    # suite: they were role-gated only, so a family-B guardian passed every
    # check this file ran.
    ("GET", "/api/v1/profiles/{profile_id}/personalization"),
    ("PUT", "/api/v1/profiles/{profile_id}/personalization"),
    ("POST", "/api/v1/profiles/{profile_id}/ring2-consent"),
    ("DELETE", "/api/v1/profiles/{profile_id}/ring2-consent/{connection_id}"),
    # characters.py (ADR-028): the five non-DELETE routes. GET/POST are
    # profile-addressed (query/body profile_id); PATCH/activate/retire are
    # id-addressed (load-then-authorize, see the module docstring's
    # documented exception and the RouteSpec comment above the character
    # entries) and need the character_id itself swapped, not a profile_id, so
    # they cannot go through the generic profile_id substitution the reverse
    # (family-A-to-stranger) test below uses -- they are covered here in the
    # forward (attacker-to-family-A) direction only, plus DELETE's own
    # explicit test in test_characters_api.py (DELETE's RouteSpec uses
    # _random_uuid_path, so a sweep entry would 404 unconditionally). This
    # list only ever authenticates as a GUARDIAN principal
    # (seed.other_guardian_token / stranger.guardian_token below); CHILD-token
    # cross-family coverage for GET/POST /api/v1/characters lives in
    # _CROSS_FAMILY_CHILD_ROUTE_KEYS below, not here.
    ("GET", "/api/v1/characters"),
    ("POST", "/api/v1/characters"),
    ("PATCH", "/api/v1/characters/{character_id}"),
    ("POST", "/api/v1/characters/{character_id}/activate"),
    ("POST", "/api/v1/characters/{character_id}/retire"),
]

# GET /storybooks/{id}/personalization-values is deliberately NOT in the list
# above, and its absence is a decision rather than an oversight: it has no 403
# or 404 branch at all by design (plan section 8.4 renders every predicate
# failure as one identical empty payload, precisely so the route cannot be
# used to probe another family), so the 403-or-404 assertion below cannot
# express its contract. Its cross-family behavior is pinned instead by
# test_personalization_api.py::
# test_values_cross_family_private_book_returns_the_empty_payload.

# Every key referenced above must actually be an authorized (guardian-eligible)
# route in ROUTE_TABLE, so this section fails loudly instead of silently
# skipping a route that got renamed or removed.
assert all(key in ROUTE_TABLE for key in _CROSS_FAMILY_ROUTE_KEYS), (
    "a _CROSS_FAMILY_ROUTE_KEYS entry is missing from ROUTE_TABLE"
)
assert all(
    Role.GUARDIAN in ROUTE_TABLE[key].allowed_roles for key in _CROSS_FAMILY_ROUTE_KEYS
), "a _CROSS_FAMILY_ROUTE_KEYS entry is not guardian-eligible"

_CROSS_FAMILY_IDS = [f"{method} {path}" for method, path in _CROSS_FAMILY_ROUTE_KEYS]


@pytest.mark.parametrize(
    ("method", "path_template"), _CROSS_FAMILY_ROUTE_KEYS, ids=_CROSS_FAMILY_IDS
)
async def test_cross_family_guardian_is_rejected(
    client: AsyncClient, seed: Seed, method: str, path_template: str
) -> None:
    """A family-B guardian must never reach a family-A resource (IDOR).

    ``other_guardian_token`` holds ``Role.GUARDIAN`` -- it passes every role
    gate in ``test_protected_endpoint_role_matrix`` for these routes -- but its
    ``Principal.family_id``/``profile_ids`` belong to family B, while every id
    the spec resolves against ``seed`` belongs to family A. The only thing
    that can reject this request is the endpoint's own ownership check
    (``authorize_profile``/``authorize_family``/the assignments visibility
    gate), which is exactly the code path this test exercises. Every route
    handler here was confirmed by reading (see the module docstring and
    ``api/assignments.py``/``api/ratings.py``/``api/library.py``/
    ``api/reading.py``/``api/profiles.py``) to reject with 403 before loading
    or mutating any row it does not own; 404 is accepted too (never asserted
    away) because it is not a weaker outcome, just a different one this suite
    also treats as "not authorized" for a route that hides existence.
    """
    spec = ROUTE_TABLE[(method, path_template)]
    url, query, body = spec.resolve(seed)
    resp = await client.request(
        method, url, params=query, json=body, headers=auth(seed.other_guardian_token)
    )
    assert resp.status_code in (403, 404), (
        f"{method} {path_template} expected 403/404 for a cross-family "
        f"guardian, got {resp.status_code}: {resp.text}"
    )
    assert not (200 <= resp.status_code < 300), (
        f"{method} {path_template} let a cross-family guardian succeed: "
        f"{resp.status_code} {resp.text}"
    )


# ---------------------------------------------------------------------------
# P6-10: third, stranger-family IDOR extension
# ---------------------------------------------------------------------------
#
# The checks above prove family B (``seed.other_guardian_token``) cannot reach
# family A's resources. That alone cannot distinguish a correct "belongs to
# the caller's family" ownership check from a buggy "is not family B"
# special-case, an accidental id-adjacency pass, or a filter that defaults to
# "not mine" instead of "is mine" -- all of which a two-family suite can miss.
# A third, totally unrelated family (C, the ``stranger`` fixture: no shared
# storybook, assignment, story request, or profile with A or B) closes that
# gap. The three tests below attack in both directions (stranger -> family A,
# and family A -> stranger) so neither a "reject the other one I know about"
# bug nor a one-way ownership check slips through.

_CROSS_FAMILY_CHILD_ROUTE_KEYS: list[tuple[str, str]] = [
    ("GET", "/api/v1/ratings/{profile_id}"),
    ("POST", "/api/v1/ratings"),
    ("POST", "/api/v1/flags"),
    ("GET", "/api/v1/library"),
    ("GET", "/api/v1/reading-state/{profile_id}/{storybook_id}"),
    ("PUT", "/api/v1/reading-state/{profile_id}/{storybook_id}"),
    ("GET", "/api/v1/series-next/{profile_id}/{storybook_id}"),
    ("POST", "/api/v1/completions"),
    ("GET", "/api/v1/reading-history/{profile_id}"),
    ("GET", "/api/v1/recommendations/{profile_id}"),
    # characters.py (ADR-028): GET/POST are profile-addressed (query/body
    # profile_id), exactly like the ratings/library/reading-state routes
    # above, so they slot into the same generic profile_id substitution the
    # reverse test below uses and need no special-casing. Before this fix
    # they were absent, with a comment claiming they were "already covered by
    # the forward-direction-only _CROSS_FAMILY_ROUTE_KEYS above" -- that was
    # false for the CHILD role: that list is exercised only with
    # seed.other_guardian_token / stranger.guardian_token, both GUARDIAN
    # principals, so no test anywhere sent a CHILD token from an unrelated
    # family at these two routes until they were added here.
    # PATCH/activate/retire are id-addressed (load-then-authorize, see the
    # module docstring's documented exception) and need the character_id
    # itself swapped, not a profile_id -- the reverse test below does that
    # swap explicitly (url.replace(seed.character_id, stranger.character_id)).
    ("GET", "/api/v1/characters"),
    ("POST", "/api/v1/characters"),
    ("PATCH", "/api/v1/characters/{character_id}"),
    ("POST", "/api/v1/characters/{character_id}/activate"),
    ("POST", "/api/v1/characters/{character_id}/retire"),
]

# Every key referenced above must actually be a child-eligible route in
# ROUTE_TABLE, so this section fails loudly instead of silently skipping a
# route that got renamed, removed, or had its role gate changed.
assert all(key in ROUTE_TABLE for key in _CROSS_FAMILY_CHILD_ROUTE_KEYS), (
    "a _CROSS_FAMILY_CHILD_ROUTE_KEYS entry is missing from ROUTE_TABLE"
)
assert all(
    Role.CHILD in ROUTE_TABLE[key].allowed_roles
    for key in _CROSS_FAMILY_CHILD_ROUTE_KEYS
), "a _CROSS_FAMILY_CHILD_ROUTE_KEYS entry is not child-eligible"

_CROSS_FAMILY_CHILD_IDS = [
    f"{method} {path}" for method, path in _CROSS_FAMILY_CHILD_ROUTE_KEYS
]


async def test_stranger_family_tokens_reach_own_resources(
    client: AsyncClient, stranger: Stranger
) -> None:
    """Positive control: family C's own tokens succeed on family C's resources.

    Every stranger-family test below asserts a rejection, so all of them
    would pass vacuously if the ``stranger`` fixture were broken in a way
    that made every family-C request fail (an unseeded user row, a token
    that never authenticates, a profile in the wrong family). Proving the
    same guardian and child tokens get 200 on their OWN family's routes
    pins the rejections below on the ownership checks, not on a defective
    fixture.
    """
    resp = await client.get("/api/v1/profiles", headers=auth(stranger.guardian_token))
    assert resp.status_code == 200, resp.text
    ids = {row["id"] for row in resp.json()["profiles"]}
    assert str(stranger.child_profile_id) in ids

    resp = await client.get(
        "/api/v1/library",
        params={"profile_id": str(stranger.child_profile_id)},
        headers=auth(stranger.child_token),
    )
    assert resp.status_code == 200, resp.text


@pytest.mark.parametrize(
    ("method", "path_template"), _CROSS_FAMILY_ROUTE_KEYS, ids=_CROSS_FAMILY_IDS
)
async def test_cross_family_guardian_from_stranger_family_is_rejected(
    client: AsyncClient,
    seed: Seed,
    stranger: Stranger,
    method: str,
    path_template: str,
) -> None:
    """A third, unrelated family's guardian must never reach family A (IDOR).

    Same shape as ``test_cross_family_guardian_is_rejected`` above, but the
    attacking token belongs to family C (``stranger``), which shares no
    storybook, assignment, or profile with family A or B. This is exactly the
    case where a "reject only family B" bug (as opposed to a correct "reject
    anyone outside my family" check) would pass a two-family suite while this
    test catches it.
    """
    spec = ROUTE_TABLE[(method, path_template)]
    url, query, body = spec.resolve(seed)
    resp = await client.request(
        method, url, params=query, json=body, headers=auth(stranger.guardian_token)
    )
    assert resp.status_code in (403, 404), (
        f"{method} {path_template} expected 403/404 for a stranger-family "
        f"guardian, got {resp.status_code}: {resp.text}"
    )


@pytest.mark.parametrize(
    ("method", "path_template"),
    _CROSS_FAMILY_CHILD_ROUTE_KEYS,
    ids=_CROSS_FAMILY_CHILD_IDS,
)
async def test_cross_family_child_from_stranger_family_is_rejected(
    client: AsyncClient,
    seed: Seed,
    stranger: Stranger,
    method: str,
    path_template: str,
) -> None:
    """A third, unrelated family's child token must never reach family A.

    ``stranger.child_token`` holds ``Role.CHILD`` scoped to profile C: it
    passes every role gate for these routes, but every id the spec resolves
    against ``seed`` belongs to family A/profile A, so only the endpoint's
    ownership check (``authorize_profile``) can reject it.
    """
    spec = ROUTE_TABLE[(method, path_template)]
    url, query, body = spec.resolve(seed)
    resp = await client.request(
        method, url, params=query, json=body, headers=auth(stranger.child_token)
    )
    assert resp.status_code in (403, 404), (
        f"{method} {path_template} expected 403/404 for a stranger-family "
        f"child, got {resp.status_code}: {resp.text}"
    )


@pytest.mark.parametrize(
    ("method", "path_template"),
    _CROSS_FAMILY_CHILD_ROUTE_KEYS,
    ids=_CROSS_FAMILY_CHILD_IDS,
)
async def test_family_a_child_cannot_reach_stranger_family_profile(
    client: AsyncClient,
    seed: Seed,
    stranger: Stranger,
    method: str,
    path_template: str,
) -> None:
    """Family A's child token must never reach family C's profile (reverse IDOR).

    The previous two tests attack family A with an outside token; this one
    reverses direction: ``seed.child_token`` (scoped to profile A) tries to
    act on profile C's resources. ``seed.storybook_id`` (family A's own book)
    is left in place for the storybook leg of reading-state/series-next/
    completions -- only ``profile_id`` is swapped to family C's -- so a pass
    here proves the ownership check keys on the profile id itself, not merely
    on "is this the caller's own storybook".

    The three id-addressed character routes in
    ``_CROSS_FAMILY_CHILD_ROUTE_KEYS`` address by ``character_id``, not
    ``profile_id``, so the ``child_profile_id`` swap above does nothing for
    them; the ``character_id`` swap below is what turns those three cases
    into an attempt against family C's character rather than a same-family,
    own-resource request that would otherwise return 200.
    """
    spec = ROUTE_TABLE[(method, path_template)]
    url, query, body = spec.resolve(seed)
    url = url.replace(str(seed.child_profile_id), str(stranger.child_profile_id))
    url = url.replace(str(seed.character_id), str(stranger.character_id))
    if "profile_id" in query:
        query = {**query, "profile_id": str(stranger.child_profile_id)}
    if body and "profile_id" in body:
        body = {**body, "profile_id": str(stranger.child_profile_id)}
    resp = await client.request(
        method, url, params=query, json=body, headers=auth(seed.child_token)
    )
    assert resp.status_code in (403, 404), (
        f"{method} {path_template} expected 403/404 for family A's child "
        f"reaching family C's profile, got {resp.status_code}: {resp.text}"
    )


async def test_profile_list_excludes_other_families(
    client: AsyncClient, seed: Seed, stranger: Stranger
) -> None:
    """GET /api/v1/profiles as family A must list neither family B's nor C's ids.

    A status-code-only suite cannot catch a handler that returns 200 but
    accidentally unions in another family's rows (e.g. a missing/loosened
    WHERE clause); this asserts on the response body's id set directly. Family
    C is included alongside the already-seeded family B so a filter that only
    special-cases "not B" (rather than "is mine") is caught too.
    """
    resp = await client.get("/api/v1/profiles", headers=auth(seed.guardian_token))
    assert resp.status_code == 200, resp.text
    ids = {row["id"] for row in resp.json()["profiles"]}
    assert str(seed.other_child_profile_id) not in ids
    assert str(stranger.child_profile_id) not in ids
    assert str(seed.child_profile_id) in ids


# ---------------------------------------------------------------------------
# ADR-014 phase 2: DEVICE principal allowlist (#CRITICAL security invariant)
# ---------------------------------------------------------------------------
#
# ``Role.DEVICE`` is deliberately excluded from ``ALL_ROLES`` (see the module
# docstring's ``device_grants.py`` note): a device grant is not a login and
# has no seed-owned dev-stub token, so it cannot ride the parametrized
# ``_TOKEN_BY_ROLE`` machinery above. It is instead exercised here with a
# REAL, minted device grant JWT (``mint_device_token``, the same mechanism a
# guardian uses in production), against a representative sample spanning
# every admin-only, guardian-only, and guardian-or-admin gate shape in
# ROUTE_TABLE, plus the two endpoints ADR-014 explicitly widens to accept a
# device principal. ADR-014's own "Negative / risks" section calls this out
# by name: "#VERIFY: every guardian/admin endpoint is tested for 403 with a
# device token, and the mint/profiles endpoints are tested for correct
# family scoping" (the family-scoping half is covered in
# test_child_sessions.py and test_profiles.py; this section covers the
# universal-403-elsewhere half).

_DEVICE_REJECTED_ROUTE_KEYS: list[tuple[str, str]] = [
    # admin-only
    ("GET", "/api/v1/admin/families"),
    ("GET", "/api/v1/admin/moderation-thresholds"),
    ("GET", "/api/v1/admin/moderation/dashboard"),
    ("GET", "/api/v1/admin/provider-allowlist"),
    ("GET", "/api/v1/review-queue"),
    ("GET", "/api/v1/families/me/budget"),
    ("POST", "/api/v1/storybooks/{storybook_id}/approve"),
    # guardian-only
    ("POST", "/api/v1/concepts"),
    ("GET", "/api/v1/guardian/books"),
    ("POST", "/api/v1/profiles"),
    ("PATCH", "/api/v1/profiles/{profile_id}"),
    ("POST", "/api/v1/storybooks/{storybook_id}/assignments"),
    ("DELETE", "/api/v1/storybooks/{storybook_id}/assignments/{profile_id}"),
    # guardian-or-admin
    ("POST", "/api/v1/story-requests/authored"),
    ("POST", "/api/v1/child-sessions"),
    ("POST", "/api/v1/device-grants"),
    ("GET", "/api/v1/device-grants"),
    ("DELETE", "/api/v1/device-grants/{grant_id}"),
]

# Every key above must be a real ROUTE_TABLE entry that does NOT admit
# DEVICE, so this section fails loudly instead of silently skipping a route
# that got renamed, removed, or had its role gate changed. The
# /api/v1/child-sessions entry is deliberately included with a note: it is
# a MIXED route (device is allowed for its OWN family; the rejection this
# sweep proves is for a body naming a DIFFERENT family's profile, which is
# exactly what `_child_session_body` resolves against `seed`'s family A).
assert all(key in ROUTE_TABLE for key in _DEVICE_REJECTED_ROUTE_KEYS), (
    "a _DEVICE_REJECTED_ROUTE_KEYS entry is missing from ROUTE_TABLE"
)

_DEVICE_REJECTED_IDS = [
    f"{method} {path}" for method, path in _DEVICE_REJECTED_ROUTE_KEYS
]


@pytest.mark.parametrize(
    ("method", "path_template"), _DEVICE_REJECTED_ROUTE_KEYS, ids=_DEVICE_REJECTED_IDS
)
async def test_device_token_rejected_on_guardian_and_admin_endpoints(
    client: AsyncClient, seed: Seed, stranger: Stranger, method: str, path_template: str
) -> None:
    """A device grant token is exactly 403 on a representative admin/guardian sweep.

    Parametrized (one request per test, like the role matrix above) rather
    than looped in a single test: the app's per-IP burst limiter
    (``RateLimitMiddleware``, 10 req/s) would otherwise 429 partway through a
    15-route loop sharing one client, and the ``client`` fixture resets the
    limiter's bucket per test invocation anyway. Every route below is either
    role-gated (``is_guardian``/``is_admin``, checked before any database row
    is loaded) or, for ``POST /api/v1/child-sessions``, targets a profile
    OUTSIDE the minted grant's own family (``stranger.child_profile_id``), so
    the family-scoping check added in ADR-014 phase 2 is what rejects it, not
    the role gate. A device token must never pass either kind of check.
    """
    spec = ROUTE_TABLE[(method, path_template)]
    url, query, body = spec.resolve(seed)
    if path_template == "/api/v1/child-sessions":
        body = {"profile_id": str(stranger.child_profile_id)}
    device_token = await mint_device_token(client, seed.guardian_token)
    resp = await client.request(
        method, url, params=query, json=body, headers=auth(device_token)
    )
    assert resp.status_code == 403, (
        f"{method} {path_template} expected 403 for a device grant token, "
        f"got {resp.status_code}: {resp.text}"
    )


async def test_device_token_allowed_on_child_session_mint(
    client: AsyncClient, seed: Seed
) -> None:
    """A device grant mints a child session for its own family's profile.

    The other half of ADR-014's allowlist: the exact two endpoints a device
    principal MAY reach, positively confirmed here (both a 201 mint and a
    200 profile list), complementing the universal-403 sweep above.
    """
    device_token = await mint_device_token(client, seed.guardian_token)
    resp = await client.post(
        "/api/v1/child-sessions",
        json={"profile_id": str(seed.child_profile_id)},
        headers=auth(device_token),
    )
    assert resp.status_code == 201, resp.text


async def test_device_token_allowed_on_profiles_list(
    client: AsyncClient, seed: Seed
) -> None:
    """A device grant lists its own family's profiles (200, not 403)."""
    device_token = await mint_device_token(client, seed.guardian_token)
    resp = await client.get("/api/v1/profiles", headers=auth(device_token))
    assert resp.status_code == 200, resp.text


async def test_device_token_allowed_on_profile_story_status(
    client: AsyncClient, seed: Seed
) -> None:
    """W1.4: a device grant reads the picker's story-status pill (200, not 403).

    The picker calls this endpoint pre-child-session, exactly the device-grant
    scenario ADR-014 phase 2 introduced ``GET /profiles`` for; this pins the
    same allowance for its story-status sibling.
    """
    device_token = await mint_device_token(client, seed.guardian_token)
    resp = await client.get("/api/v1/profiles/story-status", headers=auth(device_token))
    assert resp.status_code == 200, resp.text
