# SPDX-FileCopyrightText: 2026 Byron Williams <byronawilliams@gmail.com>
#
# SPDX-License-Identifier: MIT
"""Start a testcontainer, or report the Docker probe error without leaking.

When testcontainers probes an absent Docker daemon, docker-py builds an
``APIClient`` whose connection attempt fails after the underlying unix
socket object already exists. That half-built socket stays reachable only
through the raised exception's traceback frames; once the exception is
dropped, the garbage collector finalizes the socket and emits a
``ResourceWarning``. Under this project's ``filterwarnings = ["error"]``
that warning surfaces later, at an arbitrary point in the run, as a
``PytestUnraisableExceptionWarning`` and fails the session even though
every test passed (observed in Docker-less environments: 2075 passed,
exit code 1).

:func:`start_or_probe_error` fixes this by structure: the exception (and
the traceback frames pinning the socket) goes out of scope inside this
module, after which the leftover socket is collected immediately with
``ResourceWarning`` suppressed for the duration of that collection only.

This module also serialises the IMAGE PULL that precedes every container
start. ``_pg_url`` and ``redis_url`` are both ``scope="session"``, and under
pytest-xdist each worker runs its own session, so N workers independently
construct and start their own container. On a cold runner they therefore race
to resolve the same image concurrently, and a loser gets a 404 from ``docker
inspect`` while a sibling's container comes up fine (issue #614: 966 setup
errors on one integration run, with ``gw0`` PASSING while ``gw1`` ERRORED on
``No such image: postgres:16-alpine`` in the same second; no property of a
commit can produce opposite outcomes across workers of one run).

The upstream fix is a pre-pull step in the workflow before ``pytest`` runs, but
the ``pytest`` invocation and the ``-n`` worker count live in the reusable
workflow in ``ByronWilliamsCPA/.github``, which this repository cannot edit.
:func:`start_or_probe_error` therefore does the same thing from inside the
suite: the pull happens once, serially, behind a cross-process file lock, so
the race is removed by construction rather than retried around. Fixture
scoping is untouched, so the session-scoped schema DDL still runs once per
worker as intended.

# #EDGE: external-resources: assumes the only objects resurrected by the
# failed probe are sockets owned by the discarded docker-py client.
# #VERIFY: the suppression window is a single gc.collect() call inside
# ``catch_warnings``; project-code ResourceWarnings raised outside this
# window still escalate to errors as configured.
"""

from __future__ import annotations

import contextlib
import gc
import os
import tempfile
import time
import warnings
from pathlib import Path
from typing import TYPE_CHECKING, Protocol, TypeVar

from docker.errors import DockerException
from testcontainers.core.config import testcontainers_config
from testcontainers.core.docker_client import DockerClient

if TYPE_CHECKING:
    from collections.abc import Callable, Iterator

# One file per runner, not per worker: the point is that every worker
# contends for the SAME lock. tempfile.gettempdir() is shared by all workers of
# a run because they share the runner's filesystem.
_PULL_LOCK = Path(tempfile.gettempdir()) / "cyo-adventure-testcontainer-pull.lock"

# #EDGE: concurrency: a worker that dies holding the lock would block its
# siblings for the rest of the job. The wait is therefore bounded and the
# fallback is to proceed unlocked, which is no worse than the pre-#614
# behaviour (a race), rather than to hang the suite.
# #VERIFY: _pull_lock never blocks longer than this, and yields either way,
# but a give-up past this deadline must warn: see _pull_lock's own
# #CRITICAL marker for the test that pins this.
_PULL_LOCK_TIMEOUT_SECONDS = 300.0


class _Startable(Protocol):
    """The minimal testcontainer surface this module needs."""

    image: str

    def start(self) -> object:
        """Start the container, raising if the Docker daemon is unreachable."""
        ...


_ContainerT = TypeVar("_ContainerT", bound=_Startable)


def _warn_unserialized(message: str) -> None:
    """Emit a RuntimeWarning that survives this project's strict filter.

    A bare ``warnings.warn`` would, under ``filterwarnings = ["error"]``
    (pyproject.toml), raise at the call site instead of merely warning. Called
    from inside :func:`_pull_lock` that would abort the generator before its
    ``yield`` ever ran, silently cancelling the documented "proceed unlocked"
    fallback rather than surfacing it. Downgrading the filter to ``"always"``
    inside a nested ``catch_warnings()`` block keeps the message a warning
    (still collected into pytest's end-of-run warnings summary) without
    letting it interrupt control flow. This is the same
    ``catch_warnings`` + ``simplefilter`` shape :func:`_reap_probe_sockets`
    uses for the opposite purpose (silencing rather than guaranteeing).

    Args:
        message: Human-readable description of what degraded and why.
    """
    with warnings.catch_warnings():
        warnings.simplefilter("always", RuntimeWarning)
        warnings.warn(message, RuntimeWarning, stacklevel=3)


@contextlib.contextmanager
def _pull_lock() -> Iterator[None]:
    """Hold an exclusive cross-process lock for the duration of the block.

    ``fcntl`` is POSIX-only and this project's compatibility matrix includes
    Windows, so the import is local and its absence degrades to no lock rather
    than to an ImportError. Without the lock the pull is merely racy, which is
    the behaviour every platform had before issue #614; the runners that
    actually hit the race are Linux.

    Every fallback path below is deliberate: hanging the suite over a stale
    lock, or a full ``/tmp``, would be worse than a re-emergence of the #614
    race. What must never happen again is a fallback that could have been the
    lock failing going unreported, so the two that can, a full lock file and a
    timed-out acquire, each emit their own :func:`_warn_unserialized` before
    yielding. The missing-``fcntl`` degrade above is the exception and stays
    silent on purpose: it fires on every pull on Windows, where it is the
    platform's normal steady state rather than a symptom, and warning per pull
    would train readers to ignore the two warnings that do mean something.

    Yields:
        None: the caller runs its critical section while the lock is held,
        or, on a reported degrade, without it.
    """
    try:
        import fcntl  # POSIX-only import, deliberately not at module level
    except ImportError:
        yield
        return

    # #CRITICAL: external-resources: a full or read-only /tmp raises OSError
    # here, before flock is ever attempted. Left unguarded, that exception
    # would propagate out of this generator, out of _prepull's `with` block,
    # and into start_or_probe_error's `except (DockerException, OSError)`
    # handler, whose docstring documents that branch as meaning the Docker
    # daemon was unreachable. A lock-file problem must never be relabelled as
    # a Docker-daemon problem.
    # #VERIFY: test_an_unopenable_lock_file_degrades_with_its_own_warning
    # in tests/unit/test_docker_probe_prepull.py forces os.open to raise and
    # asserts the warning names the lock file, not Docker.
    try:
        # O_CREAT, not Path.touch(): the descriptor is what flock() locks,
        # and it must be opened even when a sibling created the file
        # microseconds ago.
        fd = os.open(_PULL_LOCK, os.O_CREAT | os.O_RDWR, 0o600)
    except OSError as exc:
        _warn_unserialized(
            f"_pull_lock: could not open the lock file at {_PULL_LOCK} "
            f"({exc}); this is a LOCK-FILE problem, not a Docker-daemon "
            "problem, and the image pull is proceeding UNSERIALIZED. Do not "
            "read a later 'No such image' error as evidence the daemon is "
            "unreachable."
        )
        yield
        return

    deadline = time.monotonic() + _PULL_LOCK_TIMEOUT_SECONDS
    held = False
    try:
        while True:
            try:
                # BlockingIOError (EAGAIN/EWOULDBLOCK), not bare OSError: that
                # is the specific, documented signal LOCK_NB uses for "a
                # sibling holds this lock". Any other OSError here is a
                # genuinely unexpected failure (a bad fd, a filesystem that
                # does not support flock) and must not be spent against the
                # contention retry budget below; it is re-raised immediately.
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                if time.monotonic() >= deadline:
                    # #EDGE: concurrency: a worker that dies holding the lock
                    # would block its siblings for the rest of the job. The
                    # wait is therefore bounded and the fallback is to
                    # proceed unlocked, which is no worse than the
                    # pre-#614 behaviour (a race), rather than to hang the
                    # suite. That degrade used to be silent; it no longer is.
                    # #VERIFY: test_a_lock_that_times_out_warns_before_yielding_unlocked
                    # in tests/unit/test_docker_probe_prepull.py drives a
                    # fake clock past the deadline and asserts on
                    # pytest.warns, not merely on execution continuing.
                    _warn_unserialized(
                        "_pull_lock: gave up after "
                        f"{_PULL_LOCK_TIMEOUT_SECONDS:.0f}s waiting for the "
                        "cross-process testcontainer pull lock; the image "
                        "pull is proceeding UNSERIALIZED. A sibling xdist "
                        "worker still holds it, or died holding it; either "
                        "way this run has returned to #614's original race "
                        "for this pull."
                    )
                    break
                time.sleep(0.2)
            else:
                held = True
                break
        yield
    finally:
        if held:
            fcntl.flock(fd, fcntl.LOCK_UN)
        os.close(fd)


def _images_to_pull(container: _Startable) -> list[str]:
    """Return the images this container start will need resolved.

    Ryuk is included because it is not the container under test but is started
    alongside it by testcontainers' reaper, and issue #614 saw the security
    tier lose the race on ``testcontainers/ryuk`` rather than on Postgres.

    Args:
        container: The constructed, not-yet-started testcontainer.

    Returns:
        list[str]: Image references, most important first.
    """
    images = [str(container.image)]
    if not testcontainers_config.ryuk_disabled:
        images.append(str(testcontainers_config.ryuk_image))
    return images


def _prepull(container: _Startable) -> None:
    """Resolve every image this container needs, once, under the lock.

    Best-effort by design. A pull that fails (no daemon, or a registry the
    environment blocks -- see ``_prepare_external_database``'s note on layer
    fetches 403ing) must NOT raise here: the caller's ``container.start()`` is
    what produces this suite's canonical probe error, and pre-empting it would
    replace a message the fixtures know how to act on with a message about
    pulling. So a failure here simply leaves the image unresolved and lets the
    start path report it.

    # #CRITICAL: concurrency: the lock is the entire fix. Pulling without it
    # reintroduces the concurrent ``docker inspect``/pull race that made one
    # xdist worker error while its sibling passed on the same commit (#614).
    # #VERIFY: a lock that fails to acquire must be REPORTED, not silently
    # skipped: see test_a_lock_that_times_out_warns_before_yielding_unlocked
    # and test_an_unopenable_lock_file_degrades_with_its_own_warning in
    # tests/unit/test_docker_probe_prepull.py. Checking that the pulls below
    # sit lexically inside the ``with _pull_lock():`` block is not enough;
    # that placement is satisfied whether or not the lock was ever held.

    Args:
        container: The constructed, not-yet-started testcontainer.
    """
    try:
        client = DockerClient()
    except (DockerException, OSError):
        # No reachable daemon. `container.start()` reports this properly.
        return

    with _pull_lock():
        for image in _images_to_pull(container):
            try:
                # `get` first: on a warm runner (a re-run, or the second
                # worker through the lock) this is a local inspect and the
                # pull is skipped entirely, so the lock is held for
                # milliseconds rather than for a network round trip.
                client.client.images.get(image)
            except (DockerException, OSError):
                try:
                    client.client.images.pull(image)
                except (DockerException, OSError):
                    # Leave THIS image unresolved and move on to the next
                    # one; the start path owns the error for whichever image
                    # is still missing when container.start() runs. A
                    # `return` here would abandon every image after the
                    # first failure, including ryuk: #614's actual casualty
                    # was ryuk (second in _images_to_pull), not Postgres, so
                    # giving up on the first miss would protect nothing.
                    continue


def _reap_probe_sockets() -> None:
    """Collect the failed probe's leaked sockets with ResourceWarning muted."""
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", ResourceWarning)
        gc.collect()


def start_or_probe_error(
    factory: Callable[[], _ContainerT],
) -> tuple[_ContainerT | None, str]:
    """Build and start a testcontainer, or return the probe failure message.

    Args:
        factory: Zero-argument callable constructing the (unstarted)
            testcontainer, e.g. ``lambda: PostgresContainer(...)``.

    Returns:
        ``(container, "")`` when the container started, or ``(None, message)``
        when the Docker daemon was unreachable. The caller decides whether the
        failure means ``pytest.skip`` (local development) or ``pytest.fail``
        (CI, where a silent skip would hide a regression).
    """
    try:
        container = factory()
        # #614: serialise image resolution BEFORE the start, so N xdist
        # workers cannot race the same pull. Best-effort: see `_prepull`.
        _prepull(container)
        container.start()
    except (DockerException, OSError) as exc:
        message = str(exc)
    else:
        return container, ""
    _reap_probe_sockets()
    return None, message
