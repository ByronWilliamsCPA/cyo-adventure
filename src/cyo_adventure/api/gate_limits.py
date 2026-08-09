"""Shared capacity limiter bounding concurrent ``run_gate`` worker-thread holds.

``UW-A47``: a character-enabled book's ``validator.gate.run_gate`` call is pure
synchronous CPU that can hold an AnyIO worker thread for as long as 49.58s (the
measured worst case on the largest catalog skeleton with the canonical 27-state
``accepts_character`` envelope, versus 0.77s with no envelope, a ~64x
multiplier). Both call sites that run the gate, ``api/node_edit.py`` and
``api/generation.py``, offload it with ``anyio.to_thread.run_sync``, which by
default dispatches onto AnyIO's process-wide worker pool (40 threads). That
pool is shared by every other ``run_sync`` caller in the process, so with no
bound, enough concurrent character-enabled gate calls exhaust the pool and
stall everything else waiting on a worker thread, not just these two routes.

This module does not make the gate faster and does not shorten the 49.58s
worst-case hold. It only bounds how many callers may hold a worker thread for
the gate at once, via a single, shared ``anyio.CapacityLimiter``, so a
saturation event degrades these two routes (a queued request still holds its
HTTP connection and may time out) instead of starving the whole service. The
latency half of the problem, memoising the per-entry-state Layer 2 walk that
drives the multiplier, is tracked separately as ``UW-A48``.

The AnyIO worker-thread pool is not the only resource this limiter bounds,
and as of ``database_pool_size``/``database_max_overflow`` defaulting to
5/10 (15 total), it is not even the tightest one. Both ``api/node_edit.py``
and ``api/generation.py`` call ``run_gate`` from inside a request handler
that has already checked out an ``AsyncSession`` (a DB connection) before
reaching the gate call, and that session stays checked out for the entire
offloaded, synchronous ``run_sync(run_gate, ...)`` hold, up to the 49.58s
worst case above. A limiter sized only against the 40-thread AnyIO default
(``settings.gate_max_concurrency``'s ``le=39`` Field bound) can therefore
still be large enough to check out more connections than the pool has,
which exhausts the connection pool for every other route in the process,
not just these two, well before the thread pool this module was built to
protect is threatened. ``core/config.py::Settings._require_gate_concurrency_within_connection_pool``
enforces the tighter, connection-pool-relative ceiling at startup
(``gate_max_concurrency < database_pool_size + database_max_overflow``), so
whichever of the two pools is smaller in a given deployment is the one
that actually binds.
"""

from __future__ import annotations

from functools import lru_cache

import anyio

from cyo_adventure.core.config import settings


@lru_cache(maxsize=1)
def gate_limiter() -> anyio.CapacityLimiter:
    """Return the single, process-wide capacity limiter for gate calls.

    ``lru_cache(maxsize=1)`` on a zero-argument function is a plain memoized
    singleton: the first call constructs the limiter from
    ``settings.gate_max_concurrency`` and every later call returns that same
    object. Both ``api/node_edit.py`` and ``api/generation.py`` must call this
    function (never construct their own ``CapacityLimiter``), or the bound
    becomes two independent limits instead of one shared one.

    #CRITICAL: concurrency: this limiter is process-wide, matching the
    process-wide AnyIO worker pool it protects. A per-request or per-session
    limiter would not bound anything, since a fresh instance has full
    capacity again.
    #VERIFY: tests/unit/test_gate_capacity_limiter.py::test_both_gate_call_sites_share_one_limiter.

    #EDGE: concurrency: the memoized limiter is bound to the FIRST event loop
    that uses it, for the process lifetime. ``anyio.CapacityLimiter(n)``
    returns an adapter that lazily creates the backend limiter on first
    acquire and caches it forever, so the object handed back here carries
    borrower state belonging to whichever loop touched it first. A server
    process runs exactly one loop, so this is inert in production; a test
    suite is the case that is not, because every ``pytest-asyncio`` test gets
    a fresh loop and a token left borrowed by a cancelled or timed-out
    acquire would persist into the next test with a borrower task from a dead
    loop. The cache is therefore cleared between tests rather than the
    singleton being weakened here.
    #VERIFY: no test discriminates this one, and saying so is the honest
    answer: a leaked borrower is an order-dependent flake between tests, not
    a property any single test can assert about itself. The mitigation
    removes the precondition instead of detecting the symptom: the autouse
    ``_reset_gate_limiter`` fixture in tests/conftest.py clears this memo
    around every test, so no limiter outlives the loop that created it. The
    only test that borrows tokens at all, and therefore the only one that
    could leak one, is tests/unit/test_gate_capacity_limiter.py::
    test_calls_beyond_the_limit_queue_rather_than_spawn.
    """
    return anyio.CapacityLimiter(settings.gate_max_concurrency)
