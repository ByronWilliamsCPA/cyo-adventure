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
  profile/family they own; admin structurally never owns a child profile
  (``_resolve_profiles`` in ``api/deps.py`` returns an empty set for admin),
  so admin deterministically gets 403 here too, but via the ownership check,
  not a role gate.

Every one of these gates runs *before* any database row is loaded (confirmed
by reading each handler), so a caller outside ``allowed_roles`` always gets
an exact 403, never a 404-before-403 ambiguity. No ``(403, 404)`` exception
list is needed in this codebase; that is itself the audited invariant this
suite pins (see the module-level assertion in
``test_protected_endpoint_role_matrix``).

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
from typing import TYPE_CHECKING, Any

import pytest

from cyo_adventure.api.deps import Role
from cyo_adventure.app import app
from tests.integration.conftest import Seed, Stranger, auth

if TYPE_CHECKING:
    from collections.abc import Callable

    from httpx import AsyncClient

pytestmark = [pytest.mark.integration, pytest.mark.security, pytest.mark.asyncio]

ALL_ROLES: frozenset[Role] = frozenset({Role.GUARDIAN, Role.CHILD, Role.ADMIN})

# Public routes that require no bearer token at all (FastAPI's own docs/schema
# endpoints, plus the k8s health probes in api/health.py). Excluded from
# ROUTE_TABLE and from the completeness check below.
_PUBLIC_ROUTES: frozenset[tuple[str, str]] = frozenset(
    {
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


def _storybook_version_path(seed: Seed) -> dict[str, str]:
    return {"storybook_id": seed.storybook_id, "version": str(seed.version)}


def _child_profile_path(seed: Seed) -> dict[str, str]:
    return {"profile_id": str(seed.child_profile_id)}


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


def _story_request_spec_body(_seed: Seed) -> dict[str, Any]:
    return {"age_band": "8-11", "length": "short"}


def _authoring_plan_body(_seed: Seed) -> dict[str, Any]:
    return {
        "method": "skeleton_fill",
        "mechanism": "skill",
        "prep_model": "authz-matrix-model",
    }


def _send_back_body(_seed: Seed) -> dict[str, Any]:
    return {"reason": "authorization matrix regression check"}


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
    # -- profiles.py ---------------------------------------------------------
    RouteSpec("GET", "/api/v1/profiles", ALL_ROLES),
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
    # -- reading.py: reading-state (ownership-scoped) ------------------------
    RouteSpec(
        "GET",
        "/api/v1/reading-state/{profile_id}/{storybook_id}",
        frozenset({Role.GUARDIAN, Role.CHILD}),
        path_params=_reading_state_path,
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
    # -- child_sessions.py: guardian-or-admin mint (child rejected) ----------
    RouteSpec(
        "POST",
        "/api/v1/child-sessions",
        frozenset({Role.GUARDIAN, Role.ADMIN}),
        json_body=_child_session_body,
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
    # -- assignments.py: guardian-only (admin rejected too) ------------------
    RouteSpec(
        "POST",
        "/api/v1/storybooks/{storybook_id}/assignments",
        frozenset({Role.GUARDIAN}),
        path_params=_storybook_path,
        json_body=_assignment_body,
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
    RouteSpec(
        "GET",
        "/api/v1/storybooks/{storybook_id}/review",
        frozenset({Role.ADMIN}),
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
    # -- generation.py: guardian-only -------------------------------------------
    RouteSpec(
        "POST",
        "/api/v1/storybooks/{storybook_id}/versions/{version}/validate",
        frozenset({Role.GUARDIAN}),
        path_params=_storybook_version_path,
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
    """

    def walk(routes: object) -> list[tuple[str, str]]:
        out: list[tuple[str, str]] = []
        for route in routes:  # type: ignore[attr-defined]
            if type(route).__name__ == "_IncludedRouter":
                out.extend(walk(route.original_router.routes))
            elif hasattr(route, "path") and hasattr(route, "methods"):
                out.extend((method, route.path) for method in route.methods or [])
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
    ("GET", "/api/v1/library"),
    ("PATCH", "/api/v1/profiles/{profile_id}"),
    ("GET", "/api/v1/reading-state/{profile_id}/{storybook_id}"),
    ("PUT", "/api/v1/reading-state/{profile_id}/{storybook_id}"),
    ("GET", "/api/v1/series-next/{profile_id}/{storybook_id}"),
    ("POST", "/api/v1/completions"),
    ("GET", "/api/v1/storybooks/{storybook_id}/assignments"),
    ("POST", "/api/v1/storybooks/{storybook_id}/assignments"),
    ("GET", "/api/v1/storybooks/{storybook_id}/content-summary"),
]

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
    ("GET", "/api/v1/library"),
    ("GET", "/api/v1/reading-state/{profile_id}/{storybook_id}"),
    ("PUT", "/api/v1/reading-state/{profile_id}/{storybook_id}"),
    ("GET", "/api/v1/series-next/{profile_id}/{storybook_id}"),
    ("POST", "/api/v1/completions"),
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
    assert not (200 <= resp.status_code < 300), (
        f"{method} {path_template} let a stranger-family guardian succeed: "
        f"{resp.status_code} {resp.text}"
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
    assert not (200 <= resp.status_code < 300), (
        f"{method} {path_template} let a stranger-family child succeed: "
        f"{resp.status_code} {resp.text}"
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
    """
    spec = ROUTE_TABLE[(method, path_template)]
    url, query, body = spec.resolve(seed)
    url = url.replace(str(seed.child_profile_id), str(stranger.child_profile_id))
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
    assert not (200 <= resp.status_code < 300), (
        f"{method} {path_template} let family A's child reach family C's "
        f"profile: {resp.status_code} {resp.text}"
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
