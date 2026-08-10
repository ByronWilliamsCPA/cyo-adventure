"""Fire one real KWS parent-verification email by hand, against Test.

This is the manual trigger for the SEND leg. It exists so the three legs can be
exercised end to end before any product surface calls them: run this, watch the
parent's inbox, complete a method, and see what arrives on the redirect return
page (``api/kws_redirect.py``) and the ``parent-verified`` webhook
(``api/kws_webhook.py``). Everything it does goes through the same
``consent/service.py`` seam the application will use, so a finding here is a
finding about the real integration rather than about this script.

Run recipe::

    # preflight: resolves the guardian and prints the plan, sends nothing
    uv run --env-file .env python scripts/kws_send_test_verification.py \\
        --user-id <guardian-uuid> --email parent@example.com \\
        --location US --dry-run

    # the real send
    uv run --env-file .env python scripts/kws_send_test_verification.py \\
        --user-id <guardian-uuid> --email parent@example.com --location US

Three things to know before running it:

- **It sends a real email to a real inbox.** KWS Test differs from production
  in which credentials and which data partition are used, not in whether mail
  is delivered. Use an address you control.
- **The rate limit is 10 requests per hour per unique parent email**, and it
  applies in Test exactly as in production. A burned quota costs an hour of
  waiting, so ``--dry-run`` first is cheap insurance.
- **It writes a row.** ``kws_verification`` gets a committed ``sent`` row
  before the email goes out, so the database must be reachable. That row is
  what the webhook later resolves; without it a completed verification is
  unattributable.

What it deliberately does NOT do: send against the production KWS environment,
under any flag. See ``_require_test_environment`` for why the refusal has no
override.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
import uuid

from cyo_adventure.consent.service import (
    VerificationStartRequest,
    start_parent_verification,
)
from cyo_adventure.core.config import settings
from cyo_adventure.core.database import get_session
from cyo_adventure.core.exceptions import (
    ConfigurationError,
    ExternalServiceError,
    ValidationError,
)
from cyo_adventure.db.models import User

_CHILD_ROLE = "child"


def _mask_email(email: str) -> str:
    """Render an email address as something safe to print.

    The operator typed the address, so masking is not hiding it from them; it
    keeps the address out of terminal scrollback, CI logs, and any screenshot
    of this run. ``consent/`` never logs the address at all, and this script
    should not be the one place that undoes that.

    Args:
        email: The address to mask.

    Returns:
        str: The first character, an ellipsis, and the domain. Input without an
            ``@`` is reported as fully masked rather than passed through, since
            an unparseable address is exactly when a naive slice leaks it.
    """
    local, separator, domain = email.partition("@")
    if not separator or not local:
        return "***"
    return f"{local[0]}***@{domain}"


def _require_test_environment() -> None:
    """Refuse to run against the production KWS environment.

    #CRITICAL: data integrity: a ``production`` row is evidence that a real
    adult completed a real verification, and KWS reports nothing that would let
    the environment be re-derived afterwards. A hand-run script minting one
    would put a record in the consent ledger that cannot be told apart from a
    genuine one. ``config.py::_reject_production_kws_from_a_local_app`` catches
    only the local-machine case; a deployed tier may legitimately hold
    production credentials, so the refusal is restated here at the boundary
    where a human is typing an email address by hand. There is no override
    flag on purpose: the safe production path is the application's own flow,
    not this file.
    #VERIFY: run once with ``KWS_ENVIRONMENT=production`` and confirm the exit
    is non-zero with nothing sent and no row written.

    Raises:
        SystemExit: When the configured KWS environment is not ``test``.
    """
    if settings.kws_environment != "test":
        print(
            "[REFUSED] KWS_ENVIRONMENT is "
            f"'{settings.kws_environment}', not 'test'. This script only ever "
            "targets the Test environment: a production verification record "
            "cannot be distinguished from a genuine one after the fact."
        )
        raise SystemExit(1)


def _require_configured() -> None:
    """Refuse to run without a complete KWS credential set.

    Failing here rather than inside the client turns a mid-flight HTTP error
    into a one-line message before anything is written or sent.

    Raises:
        SystemExit: When the KWS integration is not fully configured.
    """
    if not settings.kws_configured:
        print(
            "[REFUSED] the KWS integration is not configured. Set "
            "KWS_ORGANIZATION_ID, KWS_API_ORIGIN, KWS_CLIENT_ID, and "
            "KWS_API_KEY (see .env.example)."
        )
        raise SystemExit(1)


async def _resolve_adult(user_id: uuid.UUID) -> str:
    """Confirm the attempt attributes to an existing adult, and say which.

    #ASSUME: data integrity: ``kws_verification.user_id`` is a foreign key, so
    an unknown id would fail anyway, but as an integrity error raised after the
    row was already being written. Checking first turns that into a readable
    refusal. The child-role check is the substantive one: verification is a
    claim about a PARENT, and attributing it to a child row would put a
    compliance-shaped lie in the ledger that no constraint would catch.
    #VERIFY: pass a child profile's user id and confirm the refusal fires
    before any send.

    Args:
        user_id: The guardian the attempt should attribute to.

    Returns:
        str: The resolved user's role, for display.

    Raises:
        SystemExit: When no such user exists, or when the user is a child.
    """
    async with get_session() as session:
        user = await session.get(User, user_id)

    if user is None:
        print(
            f"[REFUSED] no user {user_id} exists. The attempt must attribute "
            "to a real guardian: kws_verification.user_id is a foreign key."
        )
        raise SystemExit(1)

    if user.role == _CHILD_ROLE:
        print(
            f"[REFUSED] user {user_id} has role '{user.role}'. Parent "
            "verification is a claim about an adult and must attribute to the "
            "guardian, not the child it is being obtained for."
        )
        raise SystemExit(1)

    return str(user.role)


def _print_plan(args: argparse.Namespace, role: str) -> None:
    """Show the operator exactly what the run will do.

    Args:
        args: The parsed command line.
        role: The resolved user's role.
    """
    label = settings.kws_environment_label or "(unset)"
    methods = ", ".join(settings.kws_enabled_methods) or "(none)"
    print(f"  kws environment: {settings.kws_environment} (label: {label})")
    print(f"  enabled methods: {methods}")
    print(f"  guardian:        {args.user_id} (role: {role})")
    print(f"  parent email:    {_mask_email(args.email)}")
    print(f"  child location:  {args.location}")
    print(f"  language:        {args.language}")


async def _run(args: argparse.Namespace) -> int:
    """Preflight, then send.

    #CRITICAL: external resources: the send is not idempotent and is rate
    limited to 10 requests per hour per unique parent email, in Test exactly as
    in production. Nothing here retries, and nothing here should: a retry loop
    would burn the hour's quota against a failure the operator has not read
    yet.
    #VERIFY: on any non-zero exit, read the message before re-running, and
    re-run with a different address if the quota is the suspect.

    Args:
        args: The parsed command line.

    Returns:
        int: The process exit code.
    """
    _require_test_environment()
    _require_configured()
    role = await _resolve_adult(args.user_id)

    if args.dry_run:
        print("[DRY-RUN] would send one verification email:")
        _print_plan(args, role)
        print("[DRY-RUN] nothing sent, no row written.")
        return 0

    print("[LIVE] sending one verification email:")
    _print_plan(args, role)

    try:
        correlation = await start_parent_verification(
            VerificationStartRequest(
                user_id=args.user_id,
                email=args.email,
                location=args.location,
                language=args.language,
            )
        )
    except (ConfigurationError, ValidationError) as exc:
        print(f"[ERROR] refused before sending: {exc}")
        return 1
    except ExternalServiceError as exc:
        print(f"[ERROR] KWS rejected or failed the send: {exc}")
        print(
            "[ERROR] the kws_verification row was committed BEFORE the call "
            "and is deliberately left 'sent', not 'failed': if KWS delivered "
            "the email before failing us, the parent can still complete "
            "verification and the webhook will resolve this row."
        )
        return 1

    print(f"[LIVE] sent. attempt_id: {correlation.attempt_id}")
    print(
        "[LIVE] that id is the externalPayload, the kws_verification primary "
        "key, and what both return legs will quote. Watch for it in the "
        "redirect return page and the parent-verified webhook."
    )
    return 0


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse the command line.

    Args:
        argv: Arguments to parse. Defaults to ``sys.argv[1:]``.

    Returns:
        argparse.Namespace: The parsed arguments.
    """
    parser = argparse.ArgumentParser(
        description=(
            "Send one KWS parent-verification email against the Test "
            "environment. Sends real mail; rate limited to 10 per hour per "
            "address."
        )
    )
    parser.add_argument(
        "--user-id",
        type=uuid.UUID,
        required=True,
        help="The guardian this attempt attributes to. Must exist, must not be a child.",
    )
    parser.add_argument(
        "--email",
        required=True,
        help="The parent's email address. Never logged; printed masked only.",
    )
    parser.add_argument(
        "--location",
        required=True,
        help=(
            "The CHILD's location as ISO 3166-1 alpha-2 or ISO 3166-2, e.g. "
            "US, US-CA, GB. This selects which verification methods the parent "
            "is offered, so it is a compliance input and has no default."
        ),
    )
    parser.add_argument(
        "--language",
        default="en",
        help="The parent's language for KWS's emails and screens (default: en).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Resolve the guardian and print the plan without sending or writing.",
    )
    return parser.parse_args(argv)


def main() -> None:
    """Entry point."""
    sys.exit(asyncio.run(_run(_parse_args())))


if __name__ == "__main__":
    main()
