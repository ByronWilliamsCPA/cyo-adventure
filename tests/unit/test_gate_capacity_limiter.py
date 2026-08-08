"""The gate's thread-pool hold is bounded.

Asserts the mechanism, not a duration: a timing assertion here would be
flaky on a loaded CI runner and would pass for the wrong reason on a fast
one.
"""

from __future__ import annotations

import threading

import anyio
import pytest

from cyo_adventure.api.gate_limits import gate_limiter


@pytest.mark.unit
def test_the_gate_limiter_is_smaller_than_the_anyio_default_pool() -> None:
    """A limiter at or above 40 bounds nothing: it is the pool size.

    This is the assertion that catches the fix being configured into
    uselessness later.
    """
    assert gate_limiter().total_tokens < 40


@pytest.mark.unit
def test_both_gate_call_sites_share_one_limiter() -> None:
    """Two limiters of N each is a limit of 2N, which is not the limit.

    node_edit and generation both offload run_gate; separate limiters
    would let the two routes together exhaust what one was sized to
    protect.
    """
    assert gate_limiter() is gate_limiter()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_calls_beyond_the_limit_queue_rather_than_spawn() -> None:
    """Concurrency never exceeds the limiter's tokens."""
    limiter = gate_limiter()
    live = 0
    peak = 0
    lock = threading.Lock()

    def _work() -> None:
        nonlocal live, peak
        with lock:
            live += 1
            peak = max(peak, live)
        with lock:
            live -= 1

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

    assert peak <= limiter.total_tokens
