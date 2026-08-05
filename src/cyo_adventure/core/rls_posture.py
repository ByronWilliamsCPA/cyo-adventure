"""Shared RLS role-posture probe for the ADR-021 least-privilege cutover.

Answers one question about a live connection: can the role this process
actually connects as bypass row-level security? The ADR-022 Tier 1 per-family
policies are inert against any role that can, so "the migration shipped" and
"the policy protects anything" are independent facts, and only this probe
distinguishes them.

Deliberately engine-agnostic. The application runs two engines (ADR-021:
``core/database.py``'s ``_engine`` for the API and ``_worker_engine`` for RQ
workers) with independently-configured DSNs, and a cutover can complete on one
and be forgotten on the other. Both callers run the identical SQL through this
module so their verdicts are comparable:

- ``api/health.py::check_database_privilege`` probes the API engine and
  publishes the verdict on ``/health/ready``.
- ``generation/worker_main.py`` probes the worker engine once at startup and
  logs the verdict, because a worker process serves no HTTP and can therefore
  never be probed from outside.

Do not probe the worker engine from the API process. The sanctioned deployment
leaves ``WORKER_DATABASE_URL`` unset on the API container (see the ``#ASSUME``
note above ``_engine`` in ``core/database.py``), so there the worker engine
resolves to the API's own DSN and would report a reassuring verdict about a
connection the worker never makes.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from sqlalchemy import text

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

__all__ = ["CONNECTED_ROLE_QUERY", "RolePosture", "measure_role_posture"]

# The identity this process actually connects as, plus every way that role can
# bypass RLS (ADR-021). `current_user` is the effective role, so this reflects
# the live connection rather than any configured DSN.
#
# #CRITICAL: security: PostgreSQL has three independent RLS bypass paths and a
# check that tests only one reports "ok" for a connection that sees every row:
#   1. the `rolbypassrls` role attribute;
#   2. superuser (`rolsuper`), which bypasses regardless of `rolbypassrls`;
#   3. TABLE OWNERSHIP. RLS never applies to a table's owner unless the table
#      sets FORCE ROW LEVEL SECURITY, and this schema deliberately does not
#      (20260711200745_enable_rls_all_tables.sql). The baseline migration sets
#      `OWNER TO "postgres"` on the Tier 1 tables, so ownership, not
#      `rolbypassrls`, is the bypass path an un-cut-over environment actually
#      uses. The EXISTS clause below is what detects that state.
# #VERIFY: tests/unit/test_rls_posture.py covers each bypass path
# independently, including ownership with rolbypassrls false.
#
# #CRITICAL: security: the COALESCE default is `true` (fail closed). A role
# absent from pg_roles is a state this check cannot reason about, and the safe
# answer to "can this connection bypass RLS" when the answer is unknown is yes.
# Defaulting to false would report a reassuring "ok" for an unanalyzable role.
# #VERIFY: tests/unit/test_rls_posture.py::test_null_role_attribute_fails_closed
# asserts the missing-pg_roles-row case counts as a bypass, not as clean.
CONNECTED_ROLE_QUERY = """
SELECT
    current_user AS role_name,
    COALESCE(
        (SELECT rolbypassrls OR rolsuper FROM pg_roles WHERE rolname = current_user),
        true
    ) AS role_bypasses_rls,
    EXISTS (
        SELECT 1
        FROM pg_class c
        JOIN pg_namespace n ON n.oid = c.relnamespace
        WHERE n.nspname = 'public'
          AND c.relrowsecurity
          AND NOT c.relforcerowsecurity
          AND c.relowner = (SELECT oid FROM pg_roles WHERE rolname = current_user)
    ) AS owns_rls_table
"""


@dataclass(frozen=True, slots=True)
class RolePosture:
    """The RLS bypass verdict for one live database connection.

    Frozen because callers pass it between a probe and a reporting layer that
    formats it for an unauthenticated endpoint; a verdict that could be edited
    downstream would make the reported posture untraceable to the query.

    Attributes:
        role_name: The effective role (``current_user``). Safe to log, never
            safe to return on an unauthenticated response; see
            ``api/health.py::check_database_privilege``.
        via_role_attribute: The role holds ``rolbypassrls`` or ``rolsuper``, or
            is absent from ``pg_roles`` (fail-closed).
        via_table_ownership: The role owns at least one ``public`` table that
            has RLS enabled without ``FORCE ROW LEVEL SECURITY``.
    """

    role_name: str
    via_role_attribute: bool
    via_table_ownership: bool

    @property
    def bypasses_rls(self) -> bool:
        """Whether this connection defeats RLS by any of the three paths."""
        return self.via_role_attribute or self.via_table_ownership


async def measure_role_posture(session: AsyncSession) -> RolePosture:
    """Probe one open session for its connection's RLS bypass posture.

    Raises nothing of its own; a connection or query failure propagates so each
    caller can decide what an unmeasurable posture means for it. ``/health/ready``
    reports it as ``state="unknown"``; the worker logs it and starts anyway.

    #CRITICAL: external-resources: this issues a real query, so it inherits the
    caller's connection failure modes and must never be placed on a path that
    cannot tolerate a database round trip.
    #VERIFY: both callers run it once (per readiness probe, per worker start),
    never per request or per job.

    Args:
        session: An open session bound to the engine whose connection identity
            is in question. The verdict describes THAT engine's connection, not
            the process, so passing the wrong engine's session silently answers
            a different question than the caller asked.

    Returns:
        RolePosture: The verdict for the session's connection.
    """
    result = await session.execute(text(CONNECTED_ROLE_QUERY))
    row = result.one()
    # A NULL here means the query's COALESCE fail-closed default did not apply,
    # so treat it the same way the SQL does: unknown is not clean. This
    # duplicates the SQL guard on purpose, so editing one without the other
    # cannot silently turn an unanalyzable role into a reassuring verdict.
    via_role_attribute = row.role_bypasses_rls is None or bool(row.role_bypasses_rls)
    return RolePosture(
        role_name=str(row.role_name),
        via_role_attribute=via_role_attribute,
        via_table_ownership=bool(row.owns_rls_table),
    )
