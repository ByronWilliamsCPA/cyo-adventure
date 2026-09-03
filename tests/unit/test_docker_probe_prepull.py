# SPDX-FileCopyrightText: 2026 Byron Williams <byronawilliams@gmail.com>
#
# SPDX-License-Identifier: MIT
"""Tests for the serialised testcontainer image pull (issue #614).

The defect these guard against is a RACE, so it is invisible on a warm machine
and reproduces only on a cold CI runner with several xdist workers. That makes
it exactly the kind of fix that gets refactored away by someone who cannot see
what it was for: the pre-pull looks like a redundant call in front of a
``start()`` that would pull anyway.

What is pinned here is the ordering (pull before start), the lock (the pull is
inside it, which is the entire fix), the image set (ryuk counts, and it is what
the security tier lost the race on), and the best-effort contract (a pull that
fails must leave the canonical probe error to ``container.start()`` rather than
raising its own).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import pytest

from tests.integration import _docker_probe

if TYPE_CHECKING:
    from collections.abc import Iterator

pytestmark = [pytest.mark.unit]


class _FakeImages:
    """docker-py's ``client.images`` reduced to what the pre-pull uses."""

    def __init__(self, present: set[str], pull_fails: bool = False) -> None:
        self.present = present
        self.pull_fails = pull_fails
        self.pulled: list[str] = []
        self.inspected: list[str] = []

    def get(self, image: str) -> object:
        """Raise unless the image is already resolved locally."""
        self.inspected.append(image)
        if image not in self.present:
            msg = f"No such image: {image}"
            raise _docker_probe.DockerException(msg)
        return object()

    def pull(self, image: str) -> object:
        """Record the pull, or fail the way a blocked registry does."""
        if self.pull_fails:
            msg = f"denied: layer fetch for {image}"
            raise _docker_probe.DockerException(msg)
        self.pulled.append(image)
        self.present.add(image)
        return object()


class _FakeDockerClient:
    """Stands in for ``testcontainers``' DockerClient wrapper."""

    def __init__(self, images: _FakeImages) -> None:
        self.client = type("_Inner", (), {"images": images})()


class _FakeContainer:
    """A testcontainer that records whether it was started."""

    def __init__(self, image: str = "postgres:17-alpine") -> None:
        self.image = image
        self.started = False

    def start(self) -> object:
        """Mark the container started."""
        self.started = True
        return self


@pytest.fixture
def images() -> _FakeImages:
    """An empty local image store, so every image needs a pull."""
    return _FakeImages(present=set())


@pytest.fixture
def patched(
    monkeypatch: pytest.MonkeyPatch, images: _FakeImages
) -> Iterator[list[str]]:
    """Wire the fake Docker client in and record lock/pull interleaving.

    Yields:
        list[str]: an event trace, so ordering can be asserted rather than
        inferred from call counts.
    """
    events: list[str] = []

    monkeypatch.setattr(
        _docker_probe, "DockerClient", lambda: _FakeDockerClient(images)
    )

    real_pull = images.pull

    def traced_pull(image: str) -> object:
        events.append(f"pull:{image}")
        return real_pull(image)

    monkeypatch.setattr(images, "pull", traced_pull)

    import contextlib

    @contextlib.contextmanager
    def traced_lock() -> Iterator[None]:
        events.append("lock:acquire")
        try:
            yield
        finally:
            events.append("lock:release")

    monkeypatch.setattr(_docker_probe, "_pull_lock", traced_lock)
    return events


class TestTheImageSet:
    """Ryuk is not the container under test, and it still has to be pulled."""

    def test_the_container_image_is_included(self) -> None:
        """The obvious half."""
        container = _FakeContainer("postgres:17-alpine")

        assert "postgres:17-alpine" in _docker_probe._images_to_pull(container)

    def test_ryuk_is_included_when_enabled(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Issue #614's Security Tests job lost the race on ryuk, not Postgres.

        A fix that pre-pulled only the container's own image would have left
        half the reported failure in place.
        """
        config: Any = _docker_probe.testcontainers_config
        monkeypatch.setattr(config, "ryuk_disabled", False)
        monkeypatch.setattr(config, "ryuk_image", "testcontainers/ryuk:0.8.1")

        images = _docker_probe._images_to_pull(_FakeContainer())

        assert "testcontainers/ryuk:0.8.1" in images

    def test_ryuk_is_omitted_when_disabled(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Pulling a reaper that will never start is pure latency."""
        config: Any = _docker_probe.testcontainers_config
        monkeypatch.setattr(config, "ryuk_disabled", True)

        images = _docker_probe._images_to_pull(_FakeContainer())

        assert not [image for image in images if "ryuk" in image]


class TestThePullIsSerialisedAndPrecedesTheStart:
    """The two properties that actually close the race."""

    def test_every_pull_happens_inside_the_lock(
        self, patched: list[str], images: _FakeImages
    ) -> None:
        """The lock IS the fix; a pull outside it is the old racy behaviour."""
        _docker_probe._prepull(_FakeContainer())

        assert images.pulled, "nothing was pulled, so the trace proves nothing"
        assert patched[0] == "lock:acquire"
        assert patched[-1] == "lock:release"
        for index, event in enumerate(patched):
            if event.startswith("pull:"):
                held = patched[:index].count("lock:acquire") - patched[:index].count(
                    "lock:release"
                )
                assert held == 1, f"{event} ran with the lock not held"

    def test_the_pull_precedes_the_container_start(
        self, patched: list[str], images: _FakeImages
    ) -> None:
        """Pulling after the start would not remove the race, only move it."""
        container = _FakeContainer()

        def start() -> object:
            patched.append("start")
            container.started = True
            return container

        container.start = start  # type: ignore[method-assign]
        started, error = _docker_probe.start_or_probe_error(lambda: container)

        assert started is container
        assert error == ""
        assert "start" in patched
        assert patched.index("start") > patched.index("pull:postgres:17-alpine"), (
            "the image was pulled after the start, so the race is untouched"
        )

    def test_an_already_present_image_is_not_pulled(
        self, patched: list[str], images: _FakeImages
    ) -> None:
        """A warm runner must hold the lock for an inspect, not a download."""
        images.present.add("postgres:17-alpine")

        _docker_probe._prepull(_FakeContainer())

        assert "postgres:17-alpine" not in images.pulled
        assert "postgres:17-alpine" in images.inspected


class TestThePrePullIsBestEffort:
    """A pull failure must not replace the error the fixtures act on."""

    def test_a_failing_pull_does_not_raise(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Some environments have a live daemon but a blocked registry.

        ``_prepare_external_database``'s docstring documents exactly that case.
        Raising here would turn a skip-or-fail decision the fixtures own into
        an error about pulling.
        """
        images = _FakeImages(present=set(), pull_fails=True)
        monkeypatch.setattr(
            _docker_probe, "DockerClient", lambda: _FakeDockerClient(images)
        )

        _docker_probe._prepull(_FakeContainer())

    def test_an_unreachable_daemon_is_left_to_the_start_path(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The probe error the whole module exists to produce must survive."""

        def no_daemon() -> object:
            msg = "Error while fetching server API version"
            raise _docker_probe.DockerException(msg)

        monkeypatch.setattr(_docker_probe, "DockerClient", no_daemon)
        container = _FakeContainer()

        def start() -> object:
            msg = "Error while fetching server API version"
            raise _docker_probe.DockerException(msg)

        container.start = start  # type: ignore[method-assign]
        result, error = _docker_probe.start_or_probe_error(lambda: container)

        assert result is None
        assert "server API version" in error
