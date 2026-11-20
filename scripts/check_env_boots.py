#!/usr/bin/env python3
"""Preflight: would the backend boot with this environment?

Loads ``Settings`` the way the app does at startup and reports EVERY rule the
environment breaks in one pass, naming the setting and the rule but never a
value. Run it against the production env file before a redeploy: on
2026-08-12 a partial KWS configuration made the backend refuse to boot, and an
env file that booted one release may not boot the next, because new releases
add boot-time rules (``core/config.py``'s ``_require_*`` / ``_reject_*``
validators).

Usage::

    # Against an env file, in isolation from your shell (what a container sees
    # when compose injects that file via env_file:)
    uv run python scripts/check_env_boots.py /path/to/production.env

    # Against the current process environment
    uv run python scripts/check_env_boots.py

    # Also list which optional integrations are configured (names only)
    uv run python scripts/check_env_boots.py /path/to/production.env --integrations

Exit codes: 0 boots, 1 would refuse to boot, 2 usage error (file unreadable).

How "every failure in one pass" works: pydantic stops at the first failing
``model_validator(mode="after")``, so the app itself only ever names one
problem per boot attempt. This script builds the settings once with field
validation only (every field error is collected by pydantic in one pass),
then calls each after-validator individually on that instance and collects
every failure. A final full ``Settings()`` construction cross-checks the
result: if the two disagree, the script says so and fails rather than report a
verdict it cannot stand behind.

#CRITICAL: security: no value from the environment is printed. Field errors
are rendered without their input, and every message (from pydantic or from a
config rule) is scrubbed of every value present in the evaluated environment
before printing. The only values left visible are non-secret vocabulary
(booleans, small integers, and ENVIRONMENT tier names).
#VERIFY: tests/unit/test_check_env_boots_script.py plants secrets in failing
settings and asserts none appears in the output, text or JSON.

#ASSUME: external resources: an env file is parsed with python-dotenv, which
matches docker compose's ``env_file:`` for the KEY=value, quoting, and comment
forms this project's env files use. Compose-level ``environment:`` entries in
the compose file itself are NOT in the env file and are not seen here.
#VERIFY: if the production stack sets variables under ``environment:`` in the
homelab-infra compose file, pass them too (export them and run without a file
argument, or append them to a copy of the file).
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, cast
from unittest import mock

import pydantic
from dotenv import dotenv_values

if TYPE_CHECKING:
    from collections.abc import Callable, Iterable, Mapping, Sequence

    from cyo_adventure.core.config import Settings

EXIT_BOOTS = 0
EXIT_REFUSES = 1
EXIT_USAGE = 2

_REDACTED = "<redacted>"
# Values that are never secrets and that rule messages legitimately quote
# ("environment is 'production', not 'local'"). Everything else is scrubbed.
_NON_SECRET_VALUES = frozenset(
    {
        "true",
        "false",
        "yes",
        "no",
        "on",
        "off",
        "local",
        "dev",
        "staging",
        "production",
    }
)
_ENV_NAME_RE = re.compile(r"\b[A-Z][A-Z0-9_]{2,}\b")


@dataclass(frozen=True)
class Failure:
    """One reason the app would refuse to boot.

    Attributes:
        kind: ``"field"`` (a value failed parsing/validation) or ``"rule"``
            (a cross-setting boot rule in ``core/config.py``).
        rule: The pydantic error type or the validator's function name.
        settings: Environment variable names the failure concerns.
        message: Scrubbed explanation.
    """

    kind: str
    rule: str
    settings: tuple[str, ...]
    message: str


@dataclass(frozen=True)
class Integration:
    """One optional integration and whether it is configured.

    Attributes:
        name: Human name.
        configured: Whether the settings enable it.
        variables: The variables that switch it on.
    """

    name: str
    configured: bool
    variables: tuple[str, ...]


def _load_settings_class() -> type[Settings]:
    """Import ``Settings`` without letting the caller's environment break it.

    ``core/config.py`` builds a module-level ``settings = Settings()`` at
    import, so importing it under an invalid environment raises before this
    script can collect anything. The import runs against an empty
    environment (the safe local defaults); the environment under test is
    applied afterwards.

    Returns:
        type[Settings]: The application's settings class.
    """
    with mock.patch.dict(os.environ, {}, clear=True):
        # Deferred on purpose; see the docstring.
        from cyo_adventure.core.config import Settings  # noqa: PLC0415

    return Settings


def env_names_by_field(settings_cls: type[Settings]) -> dict[str, tuple[str, ...]]:
    """Map each settings field to the environment variable names that set it.

    Args:
        settings_cls: The settings class.

    Returns:
        dict: field name to variable names (prefixed and alias forms).
    """
    prefix = str(settings_cls.model_config.get("env_prefix", "")).upper()
    names: dict[str, tuple[str, ...]] = {}
    for field_name, info in settings_cls.model_fields.items():
        alias = info.validation_alias
        found: list[str] = []
        if isinstance(alias, str):
            found.append(alias.upper())
        elif isinstance(alias, pydantic.AliasChoices):
            found.extend(c.upper() for c in alias.choices if isinstance(c, str))
        if not found:
            found.append(f"{prefix}{field_name.upper()}")
        names[field_name] = tuple(dict.fromkeys(found))
    return names


def make_scrubber(values: Iterable[str]) -> Callable[[str], str]:
    """Build a function that removes every environment value from a message.

    Longest values are replaced first so a value containing another is not
    left half-redacted.

    Args:
        values: Every value in the environment under test.

    Returns:
        Callable[[str], str]: The scrubber.
    """
    secrets = sorted(
        {
            v
            for v in values
            if v.strip()
            and v.strip().lower() not in _NON_SECRET_VALUES
            and not (v.strip().isdigit() and len(v.strip()) <= 5)
        },
        key=len,
        reverse=True,
    )

    def scrub(text: str) -> str:
        for secret in secrets:
            text = text.replace(secret, _REDACTED)
        return text

    return scrub


def _field_only_class(settings_cls: type[Settings]) -> type[Settings]:
    """Subclass ``Settings`` with every after-validator turned into a no-op.

    Field validation (types, literals, field validators, env parsing) is
    unchanged; only the cross-setting boot rules are deferred so they can be
    run one by one.

    Args:
        settings_cls: The settings class.

    Returns:
        type[Settings]: The subclass.
    """
    names = list(settings_cls.__pydantic_decorators__.model_validators)

    def _passthrough(self: Settings) -> Settings:
        return self

    namespace: dict[str, object] = dict.fromkeys(names, _passthrough)
    namespace["__module__"] = __name__
    return cast(
        "type[Settings]", type("_FieldOnlySettings", (settings_cls,), namespace)
    )


def _rule_settings(message: str, known: set[str]) -> tuple[str, ...]:
    names: list[str] = _ENV_NAME_RE.findall(message)
    return tuple(dict.fromkeys(n for n in names if n in known))


def evaluate(
    settings_cls: type[Settings], environ: Mapping[str, str]
) -> tuple[list[Failure], Settings | None, Settings | None, str | None]:
    """Evaluate every boot rule against an environment.

    Args:
        settings_cls: The settings class.
        environ: The complete environment the app would see.

    Returns:
        tuple: failures; the field-validated settings (None when a field
        failed); the fully-validated settings when it boots (else None); and
        a cross-check problem description, if any.
    """
    scrub = make_scrubber(environ.values())
    field_env = env_names_by_field(settings_cls)
    known = {n for names in field_env.values() for n in names}
    failures: list[Failure] = []
    validators = settings_cls.__pydantic_decorators__.model_validators

    with mock.patch.dict(os.environ, dict(environ), clear=True):
        try:
            partial = _field_only_class(settings_cls)()
        except pydantic.ValidationError as exc:
            partial = None
            for err in exc.errors(include_input=False, include_url=False):
                loc = [str(p) for p in err["loc"]]
                field = loc[0] if loc else ""
                failures.append(
                    Failure(
                        kind="field",
                        rule=str(err["type"]),
                        settings=field_env.get(field, (field.upper(),)),
                        message=scrub(str(err["msg"])),
                    )
                )
        except Exception as exc:
            partial = None
            message = scrub(str(exc))
            failures.append(
                Failure(
                    kind="field",
                    rule=type(exc).__name__,
                    settings=_rule_settings(message, known),
                    message=message,
                )
            )

        if partial is not None:
            for name in validators:
                rule = cast("Callable[[Settings], object]", getattr(settings_cls, name))
                try:
                    _ = rule(partial)
                except Exception as exc:
                    message = scrub(str(exc))
                    failures.append(
                        Failure(
                            kind="rule",
                            rule=name,
                            settings=_rule_settings(message, known),
                            message=message,
                        )
                    )

        try:
            full: Settings | None = settings_cls()
        except Exception:
            full = None

    problem: str | None = None
    if full is None and not failures:
        problem = (
            "Settings() refuses this environment but no individual rule "
            "failed; the preflight cannot attribute the failure. Treat it as "
            "NOT booting and inspect core/config.py."
        )
    elif full is not None and failures:
        problem = (
            "individual rules failed but Settings() accepted this environment; "
            "the preflight's model of the boot rules is out of date."
        )
    if partial is not None:
        failures.extend(engine_failures(partial))
    return failures, partial, full, problem


def engine_failures(settings: Settings) -> list[Failure]:
    """Check both DSNs build an async engine, as ``core/database.py`` does at import.

    ``core/database.py`` constructs the API and worker engines at import time,
    so a DSN that is not a parseable async SQLAlchemy URL (for example a plain
    ``postgresql://`` with no ``+asyncpg`` driver) stops the process before any
    route is served, even though no config rule rejects it. No connection is
    opened.

    Args:
        settings: Field-validated settings.

    Returns:
        list[Failure]: One failure per DSN that cannot build an engine.
    """
    # Deferred: SQLAlchemy is only needed once the settings have validated.
    from sqlalchemy.ext.asyncio import create_async_engine  # noqa: PLC0415
    from sqlalchemy.pool import NullPool  # noqa: PLC0415

    found: list[Failure] = []
    dsns = [("CYO_ADVENTURE_DATABASE_URL", settings.database_url)]
    # An unset worker DSN falls back to the API DSN; checking it again would
    # report the same problem twice.
    if settings.worker_database_url:
        dsns.append(("CYO_ADVENTURE_WORKER_DATABASE_URL", settings.worker_database_url))
    for label, url in dsns:
        try:
            engine = create_async_engine(url, poolclass=NullPool)
        except Exception as exc:
            found.append(
                Failure(
                    kind="rule",
                    rule="engine_construction",
                    settings=(label,),
                    # Class name only: SQLAlchemy echoes the URL in some
                    # messages.
                    message=(
                        f"{label} cannot build an async SQLAlchemy engine "
                        f"({type(exc).__name__}); it must be a "
                        "postgresql+asyncpg:// URL"
                    ),
                )
            )
        else:
            engine.sync_engine.dispose()
    return found


def integrations(settings: Settings) -> list[Integration]:
    """List optional integrations and whether each is configured.

    Args:
        settings: Fully validated settings.

    Returns:
        list[Integration]: Names and booleans only.
    """
    return [
        Integration(
            "KWS parent verification (send leg)",
            settings.kws_configured,
            ("KWS_ORGANIZATION_ID", "KWS_API_ORIGIN", "KWS_CLIENT_ID", "KWS_API_KEY"),
        ),
        Integration(
            "KWS verification required",
            settings.kws_verification_required,
            ("CYO_ADVENTURE_KWS_VERIFICATION_REQUIRED",),
        ),
        Integration(
            "Supabase service-role key (auth identity erasure)",
            settings.supabase_service_role_key is not None,
            ("SUPABASE_SERVICE_ROLE_KEY",),
        ),
        Integration(
            "Cover art generation (Gemini)",
            bool(settings.gemini_api_key),
            ("GEMINI_API_KEY",),
        ),
        Integration(
            "Cover storage (R2)",
            bool(
                settings.r2_account_id
                and settings.r2_access_key_id
                and settings.r2_secret_access_key
            ),
            ("R2_ACCOUNT_ID", "R2_ACCESS_KEY_ID", "R2_SECRET_ACCESS_KEY"),
        ),
        Integration(
            "Modal generation leg",
            settings.modal_leg_configured,
            ("MODAL_BASE_URL", "MODAL_MODEL"),
        ),
        Integration(
            "OpenRouter",
            bool(settings.openrouter_api_key),
            ("OPENROUTER_API_KEY",),
        ),
        Integration(
            "OpenAI moderation classifier",
            bool(settings.openai_api_key),
            ("OPENAI_API_KEY",),
        ),
        Integration("Sentry", bool(settings.sentry_dsn), ("SENTRY_DSN",)),
    ]


def load_environment(env_file: Path | None) -> dict[str, str]:
    """Return the environment to evaluate.

    Args:
        env_file: A dotenv/compose env file, or None for the current
            environment.

    Returns:
        dict[str, str]: Variable name to value. A file is evaluated in
        isolation: the caller's shell variables are not mixed in, because a
        container started from that file would not have them either.
    """
    if env_file is None:
        return dict(os.environ)
    with mock.patch.dict(os.environ, {}, clear=True):
        # interpolate=True mirrors compose's ${VAR} expansion within the file;
        # run under an empty environment so the operator's shell cannot leak
        # into the expansion.
        raw = dotenv_values(env_file, interpolate=True)
    return {k: v for k, v in raw.items() if v is not None}


def _parse_args(argv: Sequence[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Report every reason the backend would refuse to boot with an "
            "environment, naming settings and rules but never values."
        )
    )
    _ = parser.add_argument(
        "env_file",
        nargs="?",
        type=Path,
        help="Env file to evaluate in isolation (default: current environment).",
    )
    _ = parser.add_argument(
        "--integrations",
        action="store_true",
        help="Also list which optional integrations are configured (names only).",
    )
    _ = parser.add_argument("--json", action="store_true", help="Emit JSON.")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    """Run the preflight.

    Args:
        argv: Arguments, defaulting to ``sys.argv[1:]``.

    Returns:
        int: The exit code.
    """
    args = _parse_args(argv)
    env_file = cast("Path | None", args.env_file)
    as_json = cast("bool", args.json)
    show_integrations = cast("bool", args.integrations)

    if env_file is not None and not env_file.is_file():
        print(f"ERROR: env file not found or not a file: {env_file}", file=sys.stderr)
        return EXIT_USAGE

    settings_cls = _load_settings_class()
    environ = load_environment(env_file)
    failures, partial, settings, problem = evaluate(settings_cls, environ)
    boots = not failures and problem is None and settings is not None
    # Integrations read from the field-validated settings, so they can be
    # listed even when a cross-setting rule refuses the boot.
    found = integrations(partial) if (show_integrations and partial) else []
    source = str(env_file) if env_file is not None else "current environment"

    if as_json:
        print(
            json.dumps(
                {
                    "source": source,
                    "boots": boots,
                    "failures": [
                        {
                            "kind": f.kind,
                            "rule": f.rule,
                            "settings": list(f.settings),
                            "message": f.message,
                        }
                        for f in failures
                    ],
                    "cross_check_problem": problem,
                    "integrations": [
                        {
                            "name": i.name,
                            "configured": i.configured,
                            "variables": list(i.variables),
                        }
                        for i in found
                    ],
                },
                indent=2,
            )
        )
    else:
        verdict = "BOOTS" if boots else "WOULD REFUSE TO BOOT"
        print(f"{verdict}: {source}")
        if failures:
            print(f"\n{len(failures)} failure(s):")
        for n, f in enumerate(failures, 1):
            names = ", ".join(f.settings) if f.settings else "(see message)"
            print(f"  {n}. [{f.kind}] {f.rule}\n     settings: {names}")
            print(f"     {f.message}")
        if problem:
            print(f"\nCROSS-CHECK: {problem}")
        if show_integrations and partial is None:
            print("\nIntegrations: not listed until every field validates.")
        elif found:
            print("\nIntegrations:")
            for i in found:
                state = "configured" if i.configured else "not configured"
                print(f"  {i.name}: {state} ({', '.join(i.variables)})")
    return EXIT_BOOTS if boots else EXIT_REFUSES


if __name__ == "__main__":
    sys.exit(main())
