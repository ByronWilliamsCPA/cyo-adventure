"""Unit tests for the shared RLS role-posture probe (ADR-021, no live DB).

The probe itself is engine-agnostic on purpose: ``api/health.py`` runs it
against the API engine and ``generation/worker_main.py`` runs it against the
worker engine, and both must reach the identical verdict from the identical
SQL. These tests pin the verdict table, not either caller.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from cyo_adventure.core.rls_posture import measure_role_posture


def _fake_session(
    *,
    role_name: str = "cyo_api",
    role_bypasses_rls: bool | None = False,
    owns_rls_table: bool = False,
) -> AsyncSession:
    """Build an AsyncSession stub whose single query returns one posture row."""
    row = SimpleNamespace(
        role_name=role_name,
        role_bypasses_rls=role_bypasses_rls,
        owns_rls_table=owns_rls_table,
    )
    result = Mock()
    result.one = Mock(return_value=row)
    session = AsyncMock(spec=AsyncSession)
    session.execute = AsyncMock(return_value=result)
    return session


@pytest.mark.unit
@pytest.mark.asyncio
async def test_least_privileged_role_reports_no_bypass() -> None:
    """A role with neither attribute nor ownership bypasses nothing."""
    posture = await measure_role_posture(_fake_session(role_name="cyo_worker"))

    assert posture.role_name == "cyo_worker"
    assert posture.via_role_attribute is False
    assert posture.via_table_ownership is False
    assert posture.bypasses_rls is False


@pytest.mark.unit
@pytest.mark.asyncio
async def test_role_attribute_bypass_is_detected() -> None:
    """rolbypassrls or rolsuper on the connected role is a bypass."""
    posture = await measure_role_posture(_fake_session(role_bypasses_rls=True))

    assert posture.via_role_attribute is True
    assert posture.bypasses_rls is True


@pytest.mark.unit
@pytest.mark.asyncio
async def test_table_ownership_bypass_is_detected_without_role_attribute() -> None:
    """Ownership alone is a bypass, and is the path an un-cut-over env uses.

    This is the case a ``rolbypassrls``-only probe misses entirely: RLS never
    applies to a table's owner, and this schema does not set FORCE ROW LEVEL
    SECURITY, so owning a Tier 1 table defeats every policy on it.
    """
    posture = await measure_role_posture(
        _fake_session(
            role_name="postgres", role_bypasses_rls=False, owns_rls_table=True
        )
    )

    assert posture.via_role_attribute is False
    assert posture.via_table_ownership is True
    assert posture.bypasses_rls is True


@pytest.mark.unit
@pytest.mark.asyncio
async def test_null_role_attribute_fails_closed() -> None:
    """A NULL attribute (role absent from pg_roles) counts as a bypass.

    The SQL COALESCEs to true; this asserts the Python side agrees, so editing
    one without the other cannot turn an unanalyzable role into a clean bill.
    """
    posture = await measure_role_posture(_fake_session(role_bypasses_rls=None))

    assert posture.via_role_attribute is True
    assert posture.bypasses_rls is True
