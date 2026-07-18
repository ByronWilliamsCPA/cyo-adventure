"""enqueue_cover puts the cover entrypoint on the generation queue."""

from types import SimpleNamespace
from typing import TYPE_CHECKING, cast
from unittest.mock import MagicMock, patch

import pytest
from redis.exceptions import ConnectionError as RedisConnectionError

from cyo_adventure.covers.worker import _COVER_ENTRYPOINT, enqueue_cover

if TYPE_CHECKING:
    from cyo_adventure.core.config import Settings

pytestmark = pytest.mark.unit


def _settings() -> "Settings":
    """Return a minimal Settings stand-in with only the field enqueue reads."""
    return cast("Settings", SimpleNamespace(cover_job_timeout_seconds=180))


def test_enqueue_uses_cover_entrypoint() -> None:
    """A cover job is enqueued at the worker entrypoint with the job timeout."""
    queue = MagicMock()
    queue.enqueue.return_value = SimpleNamespace(id="job-1")
    with patch("cyo_adventure.covers.worker.get_queue", return_value=queue):
        job_id = enqueue_cover("s1", 2, _settings())
    assert job_id == "job-1"
    args, kwargs = queue.enqueue.call_args
    assert args[0] == _COVER_ENTRYPOINT
    assert args[1:] == ("s1", 2, None)
    assert kwargs["job_timeout"] == 180


def test_enqueue_forwards_correlation_id() -> None:
    """The caller's correlation id rides along as the third job argument."""
    queue = MagicMock()
    queue.enqueue.return_value = SimpleNamespace(id="job-2")
    with patch("cyo_adventure.covers.worker.get_queue", return_value=queue):
        enqueue_cover("s1", 2, _settings(), "corr-123")
    args, _ = queue.enqueue.call_args
    # The correlation id rides as the third job arg so the worker can bind it
    # into its log context (the worker runs outside CorrelationMiddleware).
    assert args[1:] == ("s1", 2, "corr-123")


@pytest.mark.unit
def test_enqueue_cover_broker_unreachable_propagates_connection_error() -> None:
    """A Redis outage during queue construction propagates to the caller."""
    # #ASSUME: external resources: api/covers.py relies on this raise to roll
    # cover_status off "generating"; swallowing it here would strand the row.
    with (
        patch(
            "cyo_adventure.covers.worker.get_queue",
            side_effect=RedisConnectionError("redis down"),
        ),
        pytest.raises(RedisConnectionError),
    ):
        enqueue_cover("s1", 2, _settings())


@pytest.mark.unit
def test_enqueue_cover_enqueue_call_failure_propagates_error() -> None:
    """A failure inside queue.enqueue itself propagates instead of returning an id."""
    queue = MagicMock()
    queue.enqueue.side_effect = RedisConnectionError("lost mid-enqueue")
    with (
        patch("cyo_adventure.covers.worker.get_queue", return_value=queue),
        pytest.raises(RedisConnectionError),
    ):
        enqueue_cover("s1", 2, _settings())
