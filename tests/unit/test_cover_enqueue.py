"""enqueue_cover puts the cover entrypoint on the generation queue."""

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from cyo_adventure.covers.worker import _COVER_ENTRYPOINT, enqueue_cover

pytestmark = pytest.mark.unit


def test_enqueue_uses_cover_entrypoint():
    queue = MagicMock()
    queue.enqueue.return_value = SimpleNamespace(id="job-1")
    settings = SimpleNamespace(cover_job_timeout_seconds=180)
    with patch("cyo_adventure.covers.worker.get_queue", return_value=queue):
        job_id = enqueue_cover("s1", 2, settings)
    assert job_id == "job-1"
    args, kwargs = queue.enqueue.call_args
    assert args[0] == _COVER_ENTRYPOINT
    assert args[1:] == ("s1", 2, None)
    assert kwargs["job_timeout"] == 180


def test_enqueue_forwards_correlation_id():
    queue = MagicMock()
    queue.enqueue.return_value = SimpleNamespace(id="job-2")
    settings = SimpleNamespace(cover_job_timeout_seconds=180)
    with patch("cyo_adventure.covers.worker.get_queue", return_value=queue):
        enqueue_cover("s1", 2, settings, "corr-123")
    args, _ = queue.enqueue.call_args
    # The correlation id rides as the third job arg so the worker can bind it
    # into its log context (the worker runs outside CorrelationMiddleware).
    assert args[1:] == ("s1", 2, "corr-123")
