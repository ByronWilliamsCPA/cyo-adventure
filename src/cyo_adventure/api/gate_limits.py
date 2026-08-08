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
    """
    return anyio.CapacityLimiter(settings.gate_max_concurrency)
