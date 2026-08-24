"""The gate's thread-pool hold is bounded.

Asserts the mechanism, not a duration: a timing assertion here would be
flaky on a loaded CI runner and would pass for the wrong reason on a fast
one.
"""

from __future__ import annotations

import ast
import inspect
import threading
from importlib import import_module
from pathlib import Path
from typing import TYPE_CHECKING

import anyio
import pydantic
import pytest

import cyo_adventure.api
from cyo_adventure.api.gate_limits import gate_limiter
from cyo_adventure.core.config import Settings
from cyo_adventure.core.exceptions import ConfigurationError

if TYPE_CHECKING:
    from types import ModuleType

_API_PACKAGE_DIR = Path(cyo_adventure.api.__file__).parent

# The modules this guard must cover are DISCOVERED, never listed. A hand-kept
# tuple named node_edit and generation and silently stopped covering
# api/remoderate.py the moment that module grew its own gate call, which is
# AL-604's lesson applied to the other axis: the entry-point set was made
# explicit, but the module set stayed a literal and went stale the same way.
# Discovery closes the class rather than the instance, so a new router that
# calls the gate is covered on the day it is written.

# Every name that enters the validator gate. Matching one literal name went
# stale the moment api/node_edit.py switched to the run_fill_gate wrapper
# (validator/gate.py), which is the shared "validate a filled book" posture;
# the guard failed loudly on an empty match rather than passing vacuously,
# but only because it asserts the call list is non-empty. Keep every gate
# entry point in this one set so a future wrapper is added here rather than
# escaping the shared limiter unobserved.
_GATE_ENTRY_POINTS = frozenset({"run_gate", "run_fill_gate"})


def _run_gate_dispatch_calls(source: str) -> list[ast.Call]:
    """Return every ``run_sync(<gate entry point>, ...)`` call in a module.

    Matches on the call shape (a call to a name ``run_sync`` whose first
    positional argument names one of ``_GATE_ENTRY_POINTS``) rather than on
    line numbers, so it survives reformatting and reordering.
    """
    tree = ast.parse(source)
    calls: list[ast.Call] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        if not (isinstance(node.func, ast.Name) and node.func.id == "run_sync"):
            continue
        if not (
            node.args
            and isinstance(node.args[0], ast.Name)
            and node.args[0].id in _GATE_ENTRY_POINTS
        ):
            continue
        calls.append(node)
    return calls


def _direct_gate_calls(source: str) -> list[ast.Call]:
    """Return every call that invokes a gate entry point INLINE.

    A gate entry point passed as ``run_sync``'s first positional argument is a
    reference, not a call, so it never appears here: only a genuine
    ``run_fill_gate(blob)`` in the module body does. That is the shape which
    runs the gate on the event loop, and it is what this guard exists to
    reject.
    """
    tree = ast.parse(source)
    return [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id in _GATE_ENTRY_POINTS
    ]


def _api_modules_touching_the_gate() -> list[ModuleType]:
    """Import every ``cyo_adventure.api`` module that references the gate.

    Discovered from the package directory rather than enumerated, so a router
    added later is covered without anyone remembering to add it here.
    """
    modules: list[ModuleType] = []
    for path in sorted(_API_PACKAGE_DIR.glob("*.py")):
        if path.name == "__init__.py" or path.name == "gate_limits.py":
            continue
        source = path.read_text(encoding="utf-8")
        if not any(entry in source for entry in _GATE_ENTRY_POINTS):
            continue
        modules.append(import_module(f"cyo_adventure.api.{path.stem}"))
    return modules


def _passes_shared_limiter(call: ast.Call) -> bool:
    """True if ``call`` passes ``limiter=gate_limiter()``, the shared singleton.

    Checks that the keyword's value is itself a call to the bare name
    ``gate_limiter`` with no arguments, not merely present, so a call site
    that passes some other limiter object (defeating the shared bound just
    as thoroughly as omitting the argument) is also caught.
    """
    for kw in call.keywords:
        if kw.arg != "limiter":
            continue
        return (
            isinstance(kw.value, ast.Call)
            and isinstance(kw.value.func, ast.Name)
            and kw.value.func.id == "gate_limiter"
            and not kw.value.args
            and not kw.value.keywords
        )
    return False


@pytest.mark.unit
@pytest.mark.asyncio
async def test_the_gate_limiter_is_smaller_than_the_anyio_default_pool() -> None:
    """A limiter at or above the pool size bounds nothing.

    Compares against AnyIO's own live default limiter
    (``anyio.to_thread.current_default_thread_limiter()``) rather than a
    hand-copied literal ``40``, so a future AnyIO default change cannot
    silently desync the two numbers. Also directly exercises
    ``core/config.py``'s ``le=39`` bound by constructing a ``Settings`` at
    the live pool size and expecting pydantic to reject it: the live-value
    assertion alone reads only the compiled-in default (4), so it cannot
    observe ``le=39`` being deleted (misconfiguration happens through the
    environment at runtime, not by importing a different default).
    """
    default_pool_size = anyio.to_thread.current_default_thread_limiter().total_tokens
    assert gate_limiter().total_tokens < default_pool_size
    with pytest.raises(pydantic.ValidationError):
        Settings(gate_max_concurrency=default_pool_size)


@pytest.mark.unit
def test_the_gate_limiter_is_smaller_than_the_database_connection_pool() -> None:
    """The live default limiter also respects the DB connection pool ceiling.

    Both ``run_gate`` call sites (api/node_edit.py, api/generation.py) hold a
    checked-out ``AsyncSession`` for the whole offloaded gate call, so the
    connection pool (``database_pool_size + database_max_overflow``, 15 by
    default) is a second, independent ceiling alongside the AnyIO thread
    pool asserted above. At the compiled-in defaults (gate_max_concurrency=4,
    pool 5+10=15) the connection pool does not bind, so this only proves the
    live default is compatible with it, not that the cross-field check
    exists; test_gate_max_concurrency_at_the_connection_pool_ceiling_rejected
    below exercises the check itself by shrinking the pool until it does
    bind.
    """
    total_db_connections = (
        Settings.model_fields["database_pool_size"].default
        + Settings.model_fields["database_max_overflow"].default
    )
    assert gate_limiter().total_tokens < total_db_connections


@pytest.mark.unit
def test_gate_max_concurrency_at_the_connection_pool_ceiling_rejected() -> None:
    """A limiter at or above the connection pool bounds nothing against it.

    Shrinks database_pool_size/database_max_overflow down to a total smaller
    than the AnyIO thread-pool ceiling (39), so this exercises the
    connection-pool cross-field check in isolation: a version of
    core/config.py that deleted
    ``_require_gate_concurrency_within_connection_pool`` but kept the
    unrelated ``le=39`` Field bound would still construct this Settings
    instance without error, since gate_max_concurrency=10 is well under 39.
    Mirrors test_the_gate_limiter_is_smaller_than_the_anyio_default_pool's
    use of ConfigurationError rather than pydantic.ValidationError, since
    ConfigurationError does not subclass ValueError and so is not wrapped by
    pydantic when raised from a model_validator (see the sibling
    _reject_dev_database_url_outside_local validator for the same pattern).
    """
    with pytest.raises(ConfigurationError):
        Settings(gate_max_concurrency=10, database_pool_size=5, database_max_overflow=4)


@pytest.mark.unit
def test_both_gate_call_sites_share_one_limiter() -> None:
    """Both run_gate offload sites pass the shared gate_limiter() singleton.

    Two limiters of N each is a limit of 2N, which is not the limit:
    node_edit and generation both offload run_gate, and separate limiters
    (or no limiter at all) would let the two routes together exhaust what
    one was sized to protect. This reads each module's own source via the
    AST rather than asserting ``gate_limiter() is gate_limiter()``, which is
    only a restatement of ``@lru_cache(maxsize=1)`` and observes neither
    call site: that version stayed green with ``limiter=gate_limiter()``
    deleted from both call sites entirely.
    """
    modules = _api_modules_touching_the_gate()
    assert modules, (
        "no cyo_adventure.api module references a gate entry point "
        f"({sorted(_GATE_ENTRY_POINTS)}); discovery is broken, not the code"
    )
    for module in modules:
        source = inspect.getsource(module)

        inline = _direct_gate_calls(source)
        assert not inline, (
            f"{module.__name__}: gate entry point called INLINE at line(s) "
            f"{[c.lineno for c in inline]}. run_gate is pure synchronous CPU "
            "(49.6s worst case); it must be offloaded via "
            "run_sync(..., limiter=gate_limiter()) or it stalls the event loop."
        )

        calls = _run_gate_dispatch_calls(source)
        assert calls, (
            f"{module.__name__} no longer dispatches a gate entry point "
            f"({sorted(_GATE_ENTRY_POINTS)}) via run_sync"
        )
        for call in calls:
            assert _passes_shared_limiter(call), (
                f"{module.__name__}: run_sync(gate, ...) call at line "
                f"{call.lineno} does not pass limiter=gate_limiter()"
            )


@pytest.mark.unit
@pytest.mark.asyncio
async def test_calls_beyond_the_limit_queue_rather_than_spawn() -> None:
    """Concurrency never exceeds the limiter's tokens.

    A ``threading.Barrier`` sized to one more than the limiter's tokens is
    the discriminator: it can only trip (release without raising
    ``BrokenBarrierError``) if that many workers are all inside ``_work``
    at the same instant. Under a correctly bounded limiter, no set of
    ``total_tokens`` concurrently-running workers can ever supply the
    ``(total_tokens + 1)``th party, so the barrier always times out and
    ``tripped`` stays clear; this holds regardless of scheduling, so the
    test does not rely on timing luck. Without the limiter, the tasks
    dispatch onto AnyIO's 40-thread default pool essentially at once and
    the barrier trips for real. The original version of this test
    incremented and decremented a counter across two adjacent, empty
    ``with lock`` blocks, so ``peak`` was 1 on essentially every run and
    stayed green with the limiter argument deleted; a ``threading.Barrier``
    with a short timeout is one of the two shapes offered for exactly this
    failure mode.
    """
    limiter = gate_limiter()
    barrier = threading.Barrier(limiter.total_tokens + 1, timeout=0.5)
    tripped = threading.Event()

    def _work() -> None:
        try:
            barrier.wait()
        except threading.BrokenBarrierError:
            return
        tripped.set()

    async def _run_bounded() -> None:
        # anyio.to_thread.run_sync takes `limiter` as a keyword-only
        # argument, but TaskGroup.start_soon forwards only positional
        # arguments to the callable it schedules, so the limiter is bound
        # here in a thin wrapper rather than passed through start_soon
        # directly.
        await anyio.to_thread.run_sync(_work, limiter=limiter)

    async with anyio.create_task_group() as tg:
        for _ in range(limiter.total_tokens * 3):
            tg.start_soon(_run_bounded)

    assert not tripped.is_set()
