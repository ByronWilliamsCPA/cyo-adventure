"""Erase a deleted family's data from the systems the database cannot reach.

``DELETE /v1/me/family`` removes every application row by database cascade, but
two things live outside Postgres and survived it (PROJECT-PLAN Phase 7 gaps):

* the AI cover images in the R2 bucket, one object per story version, and
* the guardian's Supabase Auth identity, which holds their email address.

Both are irreversible external deletes, so neither may run inside the request:
the transaction can still roll back. :func:`collect_external_targets` reads what
must go BEFORE the cascade removes the rows that name it, and
:func:`purge_external_data` is queued with ``register_after_commit`` so it runs
only once the delete has committed.

Both purges are best-effort and loud. A failure is logged at error level with
the opaque identifiers needed to finish the job by hand; it never fails the
request, because the application data is already gone and a "failed" response
would only invite a retry that finds nothing.
"""

from __future__ import annotations

import asyncio
import uuid
from dataclasses import dataclass
from typing import TYPE_CHECKING, Final

import httpx
from sqlalchemy import select

from cyo_adventure.covers.storage import cover_object_key, delete_cover
from cyo_adventure.db.models import Storybook, StorybookVersion, User
from cyo_adventure.utils.logging import get_logger

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    from sqlalchemy.ext.asyncio import AsyncSession

    from cyo_adventure.core.config import Settings

logger = get_logger(__name__)

# api/admin_users.py gives an invited-but-never-signed-in user a placeholder
# subject with this prefix. It names no Supabase user, so there is nothing to
# delete, and it must never be sent to the admin API.
PENDING_SUBJECT_PREFIX: Final[str] = "pending-invite:"

# A child login row carries a synthetic subject (api/child_sessions.py), never a
# Supabase user id: children are not identity-provider accounts.
_CHILD_ROLE: Final[str] = "child"

# cover_status values for which an R2 object may exist. "none" never had one.
_NO_COVER_STATUS: Final[str] = "none"

_ADMIN_TIMEOUT_SECONDS: Final[float] = 10.0


@dataclass(frozen=True)
class ErasureTargets:
    """What an erased family leaves behind outside the database.

    Attributes:
        family_id: The erased family, for log correlation only.
        cover_keys: R2 object keys of every cover the family's books may own.
        auth_subjects: Supabase user ids (the JWT ``sub``) of every real login
            in the family; placeholder invite subjects are excluded.
    """

    family_id: uuid.UUID
    cover_keys: tuple[str, ...]
    auth_subjects: tuple[str, ...]


async def collect_external_targets(
    session: AsyncSession, family_id: uuid.UUID
) -> ErasureTargets:
    """Read the external objects a family owns, before its rows are deleted.

    # #CRITICAL: data-integrity: this MUST run before the family delete. The
    # cascade removes the storybook_version and user rows that are the only
    # record of which R2 keys and Supabase users belong to this family.
    # #VERIFY: tests/integration/test_deletion_drill.py::
    # test_delete_my_family_queues_external_erasure_for_covers_and_identity.

    Args:
        session: The request session, inside the deleting transaction.
        family_id: The family about to be erased.

    Returns:
        ErasureTargets: The cover keys and auth subjects to purge after commit.
    """
    version_rows = await session.execute(
        select(
            StorybookVersion.storybook_id,
            StorybookVersion.version,
            StorybookVersion.cover_object_salt,
        )
        .join(Storybook, Storybook.id == StorybookVersion.storybook_id)
        .where(
            Storybook.family_id == family_id,
            StorybookVersion.cover_status != _NO_COVER_STATUS,
        )
    )
    cover_keys = tuple(
        cover_object_key(storybook_id, version, salt)
        for storybook_id, version, salt in version_rows.tuples().all()
    )
    subject_rows = await session.scalars(
        select(User.authn_subject).where(
            User.family_id == family_id, User.role != _CHILD_ROLE
        )
    )
    auth_subjects = tuple(
        subject
        for subject in subject_rows.all()
        if not subject.startswith(PENDING_SUBJECT_PREFIX)
    )
    return ErasureTargets(
        family_id=family_id, cover_keys=cover_keys, auth_subjects=auth_subjects
    )


async def delete_auth_identity(
    subject: str,
    settings: Settings,
    *,
    client: httpx.AsyncClient | None = None,
) -> bool:
    """Delete one Supabase Auth user through the GoTrue admin API.

    # #CRITICAL: security: ``subject`` is interpolated into a URL path and the
    # request carries the service-role key, so it must be a UUID before it goes
    # anywhere. Anything else (a path traversal, a placeholder) is refused here.
    # #VERIFY: tests/unit/test_erasure.py::test_delete_auth_identity_refuses_a_non_uuid_subject.
    # #CRITICAL: external-resources: the admin API lives under the OIDC issuer
    # (``<project>/auth/v1``), so the target host is the one that already issues
    # the tokens this app trusts; no second URL is configured.
    # #VERIFY: tests/unit/test_erasure.py::test_delete_auth_identity_calls_the_admin_api_under_the_issuer.

    Args:
        subject: The Supabase user id (the JWT ``sub``).
        settings: App settings (OIDC issuer and the service-role key).
        client: An HTTP client to use, for tests; one is created otherwise.

    Returns:
        bool: True when the user is gone (deleted now, or already absent: 404),
        False when it could not be deleted. Never raises.
    """
    key = settings.supabase_service_role_key
    # An empty value is "unset", not a credential: a compose-style
    # ``${SUPABASE_SERVICE_ROLE_KEY:-}`` injects "" and pydantic stores
    # ``SecretStr("")``, which would otherwise be sent as ``Bearer `` and be
    # rejected for every subject, hiding the missing-key diagnosis runbook 5.6
    # relies on.
    if key is None or not key.get_secret_value().strip() or not settings.oidc_issuer:
        logger.warning("erasure_auth_identity_unconfigured")
        return False
    try:
        user_id = uuid.UUID(subject)
    except ValueError:
        logger.warning("erasure_auth_identity_subject_not_a_uuid")
        return False
    url = f"{settings.oidc_issuer.rstrip('/')}/admin/users/{user_id}"
    secret = key.get_secret_value()
    headers = {"Authorization": f"Bearer {secret}", "apikey": secret}
    try:
        if client is None:
            async with httpx.AsyncClient(timeout=_ADMIN_TIMEOUT_SECONDS) as owned:
                response = await owned.delete(url, headers=headers)
        else:
            response = await client.delete(url, headers=headers)
    except httpx.HTTPError:
        logger.exception("erasure_auth_identity_request_failed")
        return False
    if response.status_code in {200, 204, 404}:
        return True
    logger.error(
        "erasure_auth_identity_rejected",
        status_code=response.status_code,
        auth_subject=str(user_id),
    )
    return False


async def _attempt(
    delete_fn: Callable[[str, Settings], Awaitable[bool]],
    target: str,
    settings: Settings,
    *,
    kind: str,
) -> bool:
    """Run one deleter; an unexpected exception counts as a failed delete.

    # #CRITICAL: data-integrity: the deleters report expected failures as
    # ``False``, but ``delete_cover`` catches only boto errors, so an ``OSError``
    # from client construction can still escape. Left to propagate it would end
    # the whole purge, skipping every remaining cover AND every identity (the
    # privacy-critical part), and the generic after-commit log names no target.
    # #VERIFY: tests/unit/test_erasure.py::
    # test_purge_callback_survives_a_deleter_that_raises.

    Args:
        delete_fn: The cover or identity deleter.
        target: The R2 key or Supabase user id to delete.
        settings: App settings for the deleter.
        kind: ``"cover"`` or ``"auth_identity"``, for the log line.

    Returns:
        bool: True when the deleter reported success, False on a reported
        failure or an exception.
    """
    try:
        return await delete_fn(target, settings)
    except Exception:  # NOSONAR(S2221)
        # The target is logged because the rows that named it are already gone:
        # this line is the only record an operator has to finish the delete.
        logger.exception("erasure_external_delete_raised", kind=kind, target=target)
        return False


def build_purge_callback(
    targets: ErasureTargets,
    settings: Settings,
    *,
    delete_cover_fn: Callable[[str, Settings], Awaitable[bool]] = delete_cover,
    delete_identity_fn: Callable[
        [str, Settings], Awaitable[bool]
    ] = delete_auth_identity,
) -> Callable[[], Awaitable[None]]:
    """Return the after-commit coroutine function that purges ``targets``.

    Args:
        targets: What :func:`collect_external_targets` found.
        settings: App settings for R2 and Supabase.
        delete_cover_fn: Cover-object deleter, for tests.
        delete_identity_fn: Auth-identity deleter, for tests.

    Returns:
        A no-argument coroutine function suitable for ``register_after_commit``.
    """

    async def purge() -> None:
        try:
            failed_covers = [
                key
                for key in targets.cover_keys
                if not await _attempt(delete_cover_fn, key, settings, kind="cover")
            ]
            failed_subjects = [
                subject
                for subject in targets.auth_subjects
                if not await _attempt(
                    delete_identity_fn, subject, settings, kind="auth_identity"
                )
            ]
        except asyncio.CancelledError:
            # A deploy or shutdown cancelled the loop mid-purge. We cannot know
            # which deletes finished, so name every target: a delete that
            # already happened is idempotent to repeat by hand, a lost one is not
            # recoverable from anywhere else.
            # #CRITICAL: security: the identities hold the guardians' emails.
            # #VERIFY: tests/unit/test_erasure.py::
            # test_purge_callback_logs_every_target_when_cancelled.
            logger.exception(
                "erasure_external_purge_incomplete",
                family_id=str(targets.family_id),
                failed_cover_keys=list(targets.cover_keys),
                failed_auth_subjects=list(targets.auth_subjects),
                reason="cancelled",
            )
            raise
        if failed_covers or failed_subjects:
            # #CRITICAL: security: a surviving auth identity keeps the
            # guardian's email after an erasure they were told succeeded.
            # #VERIFY: these identifiers are what an operator needs to finish
            # the job by hand (docs/operations/runbook.md, 5.6).
            logger.error(
                "erasure_external_purge_incomplete",
                family_id=str(targets.family_id),
                failed_cover_keys=failed_covers,
                failed_auth_subjects=failed_subjects,
            )
            return
        logger.info(
            "erasure_external_purge_complete",
            family_id=str(targets.family_id),
            covers=len(targets.cover_keys),
            auth_identities=len(targets.auth_subjects),
        )

    return purge
