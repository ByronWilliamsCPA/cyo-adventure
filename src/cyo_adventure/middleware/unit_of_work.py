"""Commit the request-scoped unit of work before the response is sent.

A FastAPI ``yield`` dependency's teardown runs *after* the response has been
sent (FastAPI 0.106+). A unit of work that commits there therefore leaves a
window in which a client has already received ``201 Created`` while the row it
created is not yet visible to any other connection: the next request, on a
different pooled connection, can observe a 403 or 404 on a resource the client
was just told exists (issue #461).

The fix splits the unit of work across two layers, because neither layer alone
can see both facts it needs:

* **Where to commit** is an ASGI-level fact. ``http.response.start`` is the
  last moment before any byte reaches the client, and it is emitted after the
  handler has returned and after FastAPI has serialized the response body, so
  a commit there is both late enough to be complete and early enough to be
  honest. Only a middleware wrapping ``send`` can see that message.
* **Whether to commit** is a request-handling fact. This middleware sits
  *outside* Starlette's ``ExceptionMiddleware``, so by the time a response
  reaches it, a handler's raised error has already been rendered as a 4xx/5xx
  response and is indistinguishable from a handler that deliberately returned
  one. Only the dependency, whose ``except`` clause sees the exception itself,
  can tell a failed unit of work from a successful one that reports a 4xx.

:class:`RequestUnitOfWork` joins the halves. It settles exactly once, so
whichever half acts first decides the outcome and the other becomes a no-op:
the dependency's rollback on an exception happens while the exception is still
propagating (before any response exists), and the middleware's commit happens
on a response that no rollback preceded.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Final

import structlog
from sqlalchemy.exc import SQLAlchemyError

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession
    from starlette.types import ASGIApp, Message, Receive, Scope, Send

# structlog directly rather than cyo_adventure.utils.logging.get_logger, for
# the same reason middleware/security.py does: utils.logging imports
# middleware.correlation, and middleware/__init__ imports this module, so the
# wrapper would close an import cycle. structlog.get_logger(__name__) is what
# the wrapper calls internally, minus the import-time dependency, and still
# honors whatever structlog.configure() setup_logging installed.
logger = structlog.get_logger(__name__)

# Key under which the request's unit of work is published on the ASGI scope's
# shared ``state`` dict. Starlette's ``Request.state`` is backed by that same
# dict, so the dependency writes it as ``request.state`` and this middleware
# reads it straight off the scope, with no second Request object involved.
UNIT_OF_WORK_STATE_KEY: Final[str] = "cyo_unit_of_work"

# Mirrors ``app._INTERNAL_ERROR``, duplicated rather than imported because
# ``app`` imports this module. tests/unit/test_unit_of_work.py asserts the two
# stay identical, so the duplication cannot drift unnoticed.
_INTERNAL_ERROR_BODY: Final[bytes] = json.dumps(
    {"error": "InternalError", "message": "internal error"}
).encode()


class RequestUnitOfWork:
    """One request's transaction, settled exactly once by whichever half acts.

    Args:
        session: The request-scoped session this unit of work owns.
    """

    def __init__(self, session: AsyncSession) -> None:
        """Wrap ``session`` in an unsettled unit of work."""
        self.session = session
        self._settled = False

    @property
    def settled(self) -> bool:
        """Whether this unit of work has already committed or rolled back."""
        return self._settled

    async def commit(self) -> None:
        """Commit unless already settled.

        # #CRITICAL: data integrity: settle-once is what keeps the commit
        # exactly-once now that two layers can reach it (the middleware before
        # the response is sent, the dependency's teardown after). A second
        # commit here would commit whatever the response-body phase happened
        # to leave on the session, outside any handler's intent.
        # #CRITICAL: data integrity: the flag is set AFTER the await, not
        # before. Settling first would mark a FAILED commit as settled and turn
        # the dependency's ``except`` rollback into a silent no-op, leaving the
        # session in a transaction that only the connection pool's
        # ``reset_on_return`` would abort. An unsettled unit of work is exactly
        # what makes a failed commit still rollback-eligible.
        # #VERIFY: tests/unit/test_unit_of_work.py asserts a single commit for
        # one request, that a settled unit of work ignores both calls, and that
        # a failing commit leaves the unit of work rollback-eligible.
        """
        if self._settled:
            return
        await self.session.commit()
        self._settled = True

    async def rollback(self) -> None:
        """Roll back unless already settled.

        A rollback after a SUCCESSFUL commit is not an undo, so it is dropped
        rather than issued: the response is already on its way out and a
        failure in the response-body phase cannot unmake the commit. A rollback
        after a FAILED commit is a different thing entirely and does run, since
        a failed commit leaves the unit of work unsettled.

        # #CRITICAL: data integrity: this is the only path that explicitly
        # aborts a transaction the application decided not to keep. Dropping it
        # would leave abort duty to the pool's ``reset_on_return`` default,
        # which is implicit, unpinned by this repo, and silent when it changes.
        # #VERIFY: tests/unit/test_unit_of_work.py asserts both the
        # dropped-after-commit and issued-after-failed-commit cases.
        """
        if self._settled:
            return
        await self.session.rollback()
        self._settled = True

    async def close(self) -> None:
        """Release the session and its pooled connection.

        # #CRITICAL: external resources: close runs in the dependency's
        # ``finally``, so it is the one call guaranteed on every path,
        # including a ``BaseException`` such as ``CancelledError`` that the
        # ``except Exception`` rollback clause never sees. Returning the
        # connection is what bounds pool exhaustion under load.
        # #VERIFY: tests/unit/test_unit_of_work.py asserts close runs whatever
        # the settled state, including after a cancelled request.
        """
        await self.session.close()


async def _send_internal_error(send: Send) -> None:
    """Send the standard 500 envelope in place of a response that cannot land.

    Sent rather than raised on purpose. This middleware is the INNERMOST user
    layer, so an exception from here unwinds past CORS, GZip, and correlation
    straight to Starlette's ``ServerErrorMiddleware``, which answers
    ``text/plain`` with no correlation id and no CORS headers: a browser then
    reports a CORS failure instead of a 500, and the client cannot join its
    error to the server log line. A response, by contrast, travels back OUT
    through every one of those layers and picks all of it up.

    Args:
        send: The ASGI send channel for this request.
    """
    await send(
        {
            "type": "http.response.start",
            "status": 500,
            "headers": [
                (b"content-type", b"application/json"),
                (b"content-length", str(len(_INTERNAL_ERROR_BODY)).encode()),
            ],
        }
    )
    await send({"type": "http.response.body", "body": _INTERNAL_ERROR_BODY})


class UnitOfWorkMiddleware:
    """Commit the request's unit of work before its first byte is sent.

    A pure ASGI middleware (not ``BaseHTTPMiddleware``): the commit has to
    happen on the ``http.response.start`` message specifically, and only a
    ``send`` wrapper can observe that message. ``BaseHTTPMiddleware.dispatch``
    hands back an already-assembled response object, which is one layer too
    coarse to express "after the body is serialized, before it is sent".

    Requests that never open a session (a health probe, a rate-limit
    rejection, anything the router answers without touching the database)
    publish no unit of work, so this middleware does nothing for them.

    When the commit itself fails, the handler's response is discarded and
    replaced with the standard 500 envelope (see :func:`_send_internal_error`).
    Only ``SQLAlchemyError`` is handled that way, which covers every failure a
    real commit produces (integrity, operational, DBAPI). Anything else
    propagates and reaches the client as Starlette's plain-text 500, which is
    ungraceful but honest, and stays visible rather than being swallowed by a
    catch broad enough to hide a bug in this middleware.

    Args:
        app: The wrapped ASGI application.
    """

    def __init__(self, app: ASGIApp) -> None:
        """Store the wrapped app."""
        # Named ``app`` deliberately: it is the attribute every Starlette
        # middleware exposes for the next layer down, and stack walks rely on
        # it. tests/integration/conftest.py's ``_reset_rate_limiter`` is one
        # such walk; it happens to reach RateLimitMiddleware several layers
        # before this class, so renaming would not break that particular walk,
        # but any walk that has to traverse PAST this middleware would stop
        # here with no error at all.
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        """Commit any published unit of work at ``http.response.start``."""
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        # Established here rather than read opportunistically: the dependency
        # writes through Starlette's ``Request.state``, which does
        # ``scope.setdefault("state", {})``, so creating the dict now
        # guarantees both sides share one object no matter which runs first.
        state: dict[str, object] = scope.setdefault("state", {})
        replaced_response = False

        async def send_with_commit(message: Message) -> None:
            nonlocal replaced_response
            if replaced_response:
                # The commit failed and this middleware has already sent its
                # own response. Every later message belongs to the response
                # that failure discarded, so forwarding any of it would append
                # a second body to one already on the wire.
                return
            if message["type"] == "http.response.start":
                uow = state.get(UNIT_OF_WORK_STATE_KEY)
                if isinstance(uow, RequestUnitOfWork):
                    # #CRITICAL: data integrity: this await must complete
                    # BEFORE the message is forwarded. Forwarding first (or
                    # scheduling the commit as a task) restores the very race
                    # this middleware exists to close: the client would again
                    # be able to act on a 201 whose row is not yet visible to
                    # another connection.
                    # #VERIFY: tests/unit/test_unit_of_work.py asserts the
                    # recorded order is commit-then-response-start, observed
                    # from a probe middleware outside this one.
                    try:
                        await uow.commit()
                    except SQLAlchemyError:
                        replaced_response = True
                        await uow.rollback()
                        logger.exception("unit_of_work_commit_failed")
                        await _send_internal_error(send)
                        return
            await send(message)

        await self.app(scope, receive, send_with_commit)
