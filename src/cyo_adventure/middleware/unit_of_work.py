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

from typing import TYPE_CHECKING, Final

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession
    from starlette.types import ASGIApp, Message, Receive, Scope, Send

# Key under which the request's unit of work is published on the ASGI scope's
# shared ``state`` dict. Starlette's ``Request.state`` is backed by that same
# dict, so the dependency writes it as ``request.state`` and this middleware
# reads it straight off the scope, with no second Request object involved.
UNIT_OF_WORK_STATE_KEY: Final[str] = "cyo_unit_of_work"


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
        # #VERIFY: tests/unit/test_unit_of_work.py asserts a single commit for
        # one request, and that a settled unit of work ignores both calls.
        """
        if self._settled:
            return
        self._settled = True
        await self.session.commit()

    async def rollback(self) -> None:
        """Roll back unless already settled.

        A rollback after a commit is not an undo, so it is dropped rather than
        issued: once the middleware has committed, the response is already on
        its way out and a failure in the response-body phase cannot unmake it.
        """
        if self._settled:
            return
        self._settled = True
        await self.session.rollback()

    async def close(self) -> None:
        """Release the session and its pooled connection."""
        await self.session.close()


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

    Args:
        app: The wrapped ASGI application.
    """

    def __init__(self, app: ASGIApp) -> None:
        """Store the wrapped app."""
        # Named ``app`` deliberately: tests/integration/conftest.py walks the
        # middleware stack via ``.app`` to find RateLimitMiddleware, and a
        # differently-named attribute would silently break that chain.
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

        async def send_with_commit(message: Message) -> None:
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
                    await uow.commit()
            await send(message)

        await self.app(scope, receive, send_with_commit)
