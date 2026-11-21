"""WP-2.3: no kid-surface route can serialise a Story Plan (ADR-033 Decision 1).

The plan is an authoring-side record on ``StorybookVersion.story_plan`` and on
admin-only ``GenerationJob.report``. A reader route serialises only through
its declared response model, so this walks the OpenAPI response schema of
every route in ``api/library.py`` and ``api/reading.py`` and asserts no
reachable schema has a plan-shaped property. The one route that returns an
untyped ``dict`` (the version blob) is pinned by behaviour in
``test_library_api_unit.py::TestGetStorybookVersion::test_story_plan_is_never_returned_with_the_blob``.
"""

from __future__ import annotations

from typing import cast

import pytest
from fastapi.routing import APIRoute

from cyo_adventure.api import library, reading
from cyo_adventure.app import app

# Property names only a plan, or a plan job's report, carries.
_PLAN_PROPERTIES = frozenset(
    {
        "story_plan",
        "story_plan_checks",
        "story_plan_pitches",
        "pitch",
        "threads",
        "truth",
        "facts",
        "must_not_assert",
    }
)


def _kid_routes() -> list[tuple[str, str]]:
    """Return ``(path, method)`` for every route of the two kid-surface routers."""
    found: list[tuple[str, str]] = []
    for router in (library.router, reading.router):
        for route in router.routes:
            if isinstance(route, APIRoute):
                found.extend((route.path, m.lower()) for m in route.methods)
    return found


def _walk(schema: object, components: dict[str, object], seen: set[str]) -> set[str]:
    """Return every property name reachable from a schema, following $refs."""
    names: set[str] = set()
    if isinstance(schema, dict):
        typed = cast("dict[str, object]", schema)
        ref = typed.get("$ref")
        if isinstance(ref, str):
            key = ref.rsplit("/", 1)[-1]
            if key not in seen:
                seen.add(key)
                names |= _walk(components.get(key), components, seen)
        properties = typed.get("properties")
        if isinstance(properties, dict):
            names |= set(cast("dict[str, object]", properties))
        for value in typed.values():
            names |= _walk(value, components, seen)
    elif isinstance(schema, list):
        for item in cast("list[object]", schema):
            names |= _walk(item, components, seen)
    return names


def test_kid_routes_are_found() -> None:
    """The walk below covers real routes (a renamed router must fail here)."""
    paths = {path for path, _ in _kid_routes()}
    assert "/api/v1/library" in paths
    assert any(path.startswith("/api/v1/reading-state") for path in paths)


@pytest.mark.parametrize(("path", "method"), _kid_routes())
def test_no_kid_route_response_can_carry_a_story_plan(path: str, method: str) -> None:
    """No response schema reachable from a kid route has a plan property."""
    spec = app.openapi()
    components = cast(
        "dict[str, object]", spec.get("components", {}).get("schemas", {})
    )
    operation = cast("dict[str, object]", spec["paths"][path][method])
    responses = operation.get("responses", {})
    reachable = _walk(responses, components, set())
    assert not reachable & _PLAN_PROPERTIES, (path, method)
