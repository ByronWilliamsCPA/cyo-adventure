"""Unit tests for the request unit of work and its commit-ordering middleware.

The defect these cover (issue #461) is an ORDERING defect, not a
does-it-commit-at-all defect: the old dependency did commit, just after the
response had been sent. An end-to-end HTTP assertion cannot see that, because
an in-process ASGI transport drives the app to completion (dependency teardown
included) before the client's ``await`` returns, so every such test is green
either way. The honest observation point is the ASGI message stream, so the
ordering tests below record ``commit`` and ``http.response.start`` into one
list from a probe middleware sitting outside the middleware under test.
"""

from __future__ import annotations

import asyncio
import json
from typing import TYPE_CHECKING, Any

import pytest
from fastapi import Depends, FastAPI, HTTPException
from fastapi.responses import JSONResponse
from httpx import ASGITransport, AsyncClient
from sqlalchemy.exc import IntegrityError

from cyo_adventure.api import deps
from cyo_adventure.middleware.unit_of_work import (
    _INTERNAL_ERROR_BODY,
    UNIT_OF_WORK_STATE_KEY,
    RequestUnitOfWork,
    UnitOfWorkMiddleware,
)

if TYPE_CHECKING:
    from collections.abc import Callable, Coroutine

    from starlette.types import Message, Receive, Scope, Send


class _RecordingSession:
    """An async session double appending each lifecycle call to a shared log."""

    def __init__(self, log: list[str]) -> None:
        """Record into ``log``, which the caller shares with the send probe."""
        self.log = log

    async def commit(self) -> None:
        """Record a commit."""
        self.log.append("commit")

    async def rollback(self) -> None:
        """Record a rollback."""
        self.log.append("rollback")

    async def close(self) -> None:
        """Record a close."""
        self.log.append("close")


class _FailingSession(_RecordingSession):
    """A session whose commit fails the way a constraint violation does.

    ``IntegrityError`` rather than a bare ``RuntimeError`` because the
    middleware handles ``SQLAlchemyError`` specifically; a non-SQLAlchemy error
    takes the propagate-to-ServerErrorMiddleware path instead, which
    :class:`_ExplodingSession` covers.
    """

    async def commit(self) -> None:
        """Record the attempt, then fail the way a real commit can."""
        self.log.append("commit")
        raise IntegrityError("INSERT ...", (), Exception("duplicate key"))


class _ExplodingSession(_RecordingSession):
    """A session whose commit fails with a non-SQLAlchemy error."""

    async def commit(self) -> None:
        """Record the attempt, then fail in a way the middleware does not map."""
        self.log.append("commit")
        msg = "commit exploded"
        raise RuntimeError(msg)


def _uow(log: list[str]) -> RequestUnitOfWork:
    """Build a unit of work over a recording session double."""
    session: Any = _RecordingSession(log)
    return RequestUnitOfWork(session)


async def _receive() -> Message:  # pragma: no cover - never awaited by these apps
    """Stand in for the ASGI receive channel; no test app reads the request body."""
    return {"type": "http.request", "body": b"", "more_body": False}


def _http_scope() -> Scope:
    """Build a minimal HTTP scope with no pre-existing state dict."""
    return {"type": "http", "method": "GET", "path": "/", "headers": []}


def _probe(
    app: Callable[[Scope, Receive, Send], Coroutine[Any, Any, None]],
    log: list[str],
) -> Callable[[Scope, Receive, Send], Coroutine[Any, Any, None]]:
    """Wrap ``app`` in an outer middleware logging every message it emits.

    Outer is the point: it observes messages only after the middleware under
    test has finished with them, so the log records the real relative order of
    the commit and the response start.
    """

    async def probed(scope: Scope, receive: Receive, send: Send) -> None:
        async def logging_send(message: Message) -> None:
            log.append(str(message["type"]))
            await send(message)

        await app(scope, receive, logging_send)

    return probed


async def _discard(message: Message) -> None:
    """Swallow an outbound ASGI message."""


@pytest.mark.unit
@pytest.mark.asyncio
async def test_commit_lands_before_the_response_starts() -> None:
    """The commit completes before ``http.response.start`` is forwarded.

    This is the regression assertion for issue #461: with the old
    teardown-time commit the same log would read response.start first, so a
    client could act on a 201 whose row no other connection could yet see.
    """
    log: list[str] = []

    async def endpoint(scope: Scope, receive: Receive, send: Send) -> None:
        scope["state"][UNIT_OF_WORK_STATE_KEY] = _uow(log)
        await send({"type": "http.response.start", "status": 201, "headers": []})
        await send({"type": "http.response.body", "body": b"{}"})

    app = _probe(UnitOfWorkMiddleware(endpoint), log)
    await app(_http_scope(), _receive, _discard)

    assert log == ["commit", "http.response.start", "http.response.body"]


@pytest.mark.unit
@pytest.mark.asyncio
async def test_commits_once_per_request() -> None:
    """A request commits exactly once even though two layers can reach it."""
    log: list[str] = []

    async def endpoint(scope: Scope, receive: Receive, send: Send) -> None:
        uow = _uow(log)
        scope["state"][UNIT_OF_WORK_STATE_KEY] = uow
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b"{}"})
        # Stands in for the dependency's own teardown-time commit attempt,
        # which still runs after the response under FastAPI 0.106+.
        await uow.commit()

    app = UnitOfWorkMiddleware(endpoint)
    await app(_http_scope(), _receive, _discard)

    assert log.count("commit") == 1


@pytest.mark.unit
@pytest.mark.asyncio
async def test_request_without_a_unit_of_work_is_untouched() -> None:
    """A request that never opens a session passes through unchanged."""
    log: list[str] = []

    async def endpoint(scope: Scope, receive: Receive, send: Send) -> None:
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b"ok"})

    app = _probe(UnitOfWorkMiddleware(endpoint), log)
    await app(_http_scope(), _receive, _discard)

    assert log == ["http.response.start", "http.response.body"]


@pytest.mark.unit
@pytest.mark.asyncio
async def test_non_http_scope_is_delegated_unwrapped() -> None:
    """Lifespan and websocket scopes reach the app with the original send."""
    seen: list[Send] = []

    async def endpoint(scope: Scope, receive: Receive, send: Send) -> None:
        seen.append(send)

    app = UnitOfWorkMiddleware(endpoint)
    await app({"type": "lifespan"}, _receive, _discard)

    assert seen == [_discard]


class TestUnitOfWorkSettleOnce:
    """Direct tests for the settle-once state machine."""

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_rollback_after_commit_is_dropped(self) -> None:
        """A rollback cannot undo a commit, so it is not issued."""
        log: list[str] = []
        uow = _uow(log)
        await uow.commit()
        await uow.rollback()
        assert log == ["commit"]
        assert uow.settled

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_commit_after_rollback_is_dropped(self) -> None:
        """A commit cannot resurrect an abandoned unit of work."""
        log: list[str] = []
        uow = _uow(log)
        await uow.rollback()
        await uow.commit()
        assert log == ["rollback"]

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_close_always_runs(self) -> None:
        """Closing releases the connection whatever the settled state."""
        log: list[str] = []
        uow = _uow(log)
        await uow.commit()
        await uow.close()
        assert log == ["commit", "close"]


def _app_with_fake_session(
    monkeypatch: pytest.MonkeyPatch, session: _RecordingSession
) -> FastAPI:
    """Build a two-route app whose unit of work runs over ``session``.

    Wired the way ``create_app`` wires it (middleware added first, so it is the
    innermost user middleware), which is what puts it outside Starlette's
    ``ExceptionMiddleware`` and therefore blind to raised-versus-returned 4xx.
    """
    monkeypatch.setattr(deps, "get_session", lambda: session)
    app = FastAPI()
    app.add_middleware(UnitOfWorkMiddleware)

    @app.get("/raises")
    async def raises(_: object = Depends(deps.get_db_session)) -> JSONResponse:
        """Raise the way a guard does when authorization fails."""
        raise HTTPException(status_code=403, detail="nope")

    @app.get("/returns-404")
    async def returns_404(_: object = Depends(deps.get_db_session)) -> JSONResponse:
        """Report a 4xx by returning it, having done real work first."""
        return JSONResponse({"detail": "absent"}, status_code=404)

    return app


@pytest.mark.unit
@pytest.mark.asyncio
async def test_raised_http_exception_rolls_back(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A handler-raised 4xx rolls back and never commits.

    The rollback happens in the dependency, while the exception is still
    propagating, so it settles the unit of work before any response exists for
    the middleware to commit against.
    """
    log: list[str] = []
    app = _app_with_fake_session(monkeypatch, _RecordingSession(log))
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/raises")

    assert response.status_code == 403
    assert log == ["rollback", "close"]


@pytest.mark.unit
@pytest.mark.asyncio
async def test_returned_4xx_still_commits(monkeypatch: pytest.MonkeyPatch) -> None:
    """A deliberately returned 4xx commits, because nothing failed.

    This is why the commit/rollback decision cannot move wholesale into the
    middleware: from out there this response and the raised 403 above are the
    same thing, a 4xx, and treating them alike would discard the writes of
    every handler that reports a 4xx after doing real work.
    """
    log: list[str] = []
    app = _app_with_fake_session(monkeypatch, _RecordingSession(log))
    # Probed from outside the whole app, so this is the end-to-end form of the
    # ordering assertion: the old teardown-time commit produced
    # response.start, commit, close, in that order.
    transport = ASGITransport(app=_probe(app, log))
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/returns-404")

    assert response.status_code == 404
    assert log == ["commit", "http.response.start", "http.response.body", "close"]


@pytest.mark.unit
@pytest.mark.asyncio
async def test_commit_failure_becomes_a_500(monkeypatch: pytest.MonkeyPatch) -> None:
    """A failing commit reaches the client as a 500, not as a false success.

    Because the commit runs before ``http.response.start`` is forwarded, no
    status has been committed to the wire yet, so the handler's success
    response can still be replaced with a 500. Committing after the send would
    leave the client holding a 2xx for work that never landed.

    The 500 carries the standard JSON envelope rather than Starlette's
    plain-text default, because this middleware sends it rather than raising:
    a sent response travels back out through the CORS, gzip, and correlation
    layers that wrap this one, and a raised exception skips all of them.
    """
    log: list[str] = []
    app = _app_with_fake_session(monkeypatch, _FailingSession(log))
    transport = ASGITransport(app=app, raise_app_exceptions=False)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/returns-404")

    assert response.status_code == 500
    assert response.headers["content-type"] == "application/json"
    assert response.content == _INTERNAL_ERROR_BODY
    assert log.count("commit") == 1
    # The regression assertion for the settle-before-await defect: a failed
    # commit must leave the unit of work rollback-eligible, so the abort is
    # explicit rather than left to the connection pool's reset-on-return.
    assert log == ["commit", "rollback", "close"]


@pytest.mark.unit
@pytest.mark.asyncio
async def test_non_sqlalchemy_commit_failure_still_rolls_back(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An unmapped commit error propagates, and the dependency still aborts.

    The middleware handles ``SQLAlchemyError`` only, so this one unwinds to
    Starlette's ``ServerErrorMiddleware``. That path is deliberately not
    swallowed, but it must not cost the rollback: the dependency's ``except``
    clause sees the exception on its way past.
    """
    log: list[str] = []
    app = _app_with_fake_session(monkeypatch, _ExplodingSession(log))
    transport = ASGITransport(app=app, raise_app_exceptions=False)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/returns-404")

    assert response.status_code == 500
    assert log == ["commit", "rollback", "close"]


@pytest.mark.unit
@pytest.mark.asyncio
async def test_failed_commit_leaves_the_unit_of_work_unsettled() -> None:
    """A commit that raises does not consume the single settle.

    Settling before the await would mark a failed commit as settled and make
    every later rollback a silent no-op.
    """
    log: list[str] = []
    session: Any = _FailingSession(log)
    uow = RequestUnitOfWork(session)

    with pytest.raises(IntegrityError):
        await uow.commit()

    assert not uow.settled
    await uow.rollback()
    assert log == ["commit", "rollback"]
    assert uow.settled


@pytest.mark.unit
def test_internal_error_body_matches_the_app_envelope() -> None:
    """The middleware's 500 body is byte-identical to the app's envelope.

    Duplicated rather than imported because ``app`` imports this middleware;
    this asserts the duplication cannot drift.
    """
    from cyo_adventure.app import _INTERNAL_ERROR

    assert json.loads(_INTERNAL_ERROR_BODY) == _INTERNAL_ERROR


def _bare_request() -> Any:
    """Build a Request over a minimal HTTP scope, with no middleware above it."""
    from starlette.requests import Request

    return Request(_http_scope())


@pytest.mark.unit
@pytest.mark.asyncio
async def test_response_that_never_starts_commits_in_the_dependency() -> None:
    """With no ``http.response.start``, the dependency's fallback commits.

    This is the path the fallback exists for: no response message means the
    middleware never gets its chance, so the unit of work must still settle
    rather than leaking an open transaction back to the pool.
    """
    log: list[str] = []
    session: Any = _RecordingSession(log)

    async with deps.request_unit_of_work(_bare_request(), session):
        pass

    assert log == ["commit", "close"]


@pytest.mark.unit
@pytest.mark.asyncio
async def test_cancelled_request_closes_without_settling() -> None:
    """A cancelled request neither commits nor rolls back, but always closes.

    ``CancelledError`` is a ``BaseException``, so the ``except Exception``
    rollback clause never sees it. The abort then comes from the pool's
    reset-on-return when ``close`` hands the connection back, which is why
    ``close`` lives in a ``finally``.
    """
    log: list[str] = []
    session: Any = _RecordingSession(log)
    # Built outside the block so the only call inside it is the one under
    # test (S5778, enforced by the check-pytest-raises-scope hook).
    request = _bare_request()

    with pytest.raises(asyncio.CancelledError):
        async with deps.request_unit_of_work(request, session):
            raise asyncio.CancelledError

    assert log == ["close"]
