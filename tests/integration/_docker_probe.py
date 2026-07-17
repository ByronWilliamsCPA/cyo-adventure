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

# #EDGE: external-resources: assumes the only objects resurrected by the
# failed probe are sockets owned by the discarded docker-py client.
# #VERIFY: the suppression window is a single gc.collect() call inside
# ``catch_warnings``; project-code ResourceWarnings raised outside this
# window still escalate to errors as configured.
"""

from __future__ import annotations

import gc
import warnings
from typing import TYPE_CHECKING, Protocol, TypeVar

from docker.errors import DockerException

if TYPE_CHECKING:
    from collections.abc import Callable


class _Startable(Protocol):
    """The minimal testcontainer surface this module needs."""

    def start(self) -> object:
        """Start the container, raising if the Docker daemon is unreachable."""
        ...


_ContainerT = TypeVar("_ContainerT", bound=_Startable)


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
        container.start()
    except (DockerException, OSError) as exc:
        message = str(exc)
    else:
        return container, ""
    _reap_probe_sockets()
    return None, message
