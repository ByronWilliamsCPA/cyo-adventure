"""Configuration settings for CYO Adventure.

Most settings are loaded from environment variables under the 'CYO_ADVENTURE_'
prefix. Several operator-facing names are also honored unprefixed via
validation_alias, matching what docker-compose*.yml and
docs/guides/configuration.md already set: ENVIRONMENT, LOG_LEVEL, JSON_LOGS,
DATABASE_URL, WORKER_DATABASE_URL, and the OPENROUTER_*, MODAL_*,
OPENAI_API_KEY, and PERSPECTIVE_API_KEY credentials. Pydantic-settings
handles the parsing and validation.
"""

from __future__ import annotations

from pathlib import Path
from typing import Annotated, Literal, NamedTuple
from urllib.parse import urlsplit

from pydantic import (
    AliasChoices,
    Field,
    SecretStr,
    ValidationInfo,
    field_validator,
    model_validator,
)
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

from cyo_adventure.core.exceptions import ConfigurationError
from cyo_adventure.core.token_audience import TokenAudience

# Localhost-only development default (no credentials; relies on local peer/trust
# auth). Kept as a module constant so the fail-fast validator below can detect
# when it leaks into a non-local environment. Developers using password auth must
# set CYO_ADVENTURE_DATABASE_URL explicitly (see .env.example).
_DEV_DATABASE_URL = "postgresql+asyncpg://localhost/cyo_adventure"

# Supabase Supavisor's transaction-mode pooler port (ADR-009 Task 1.7). Used by
# the fail-fast validator below to catch a database_url/database_disable_prepared_cache
# mismatch; PgBouncer transaction mode has no fixed port and cannot be
# detected this way, so this only covers the documented Supavisor case.
_SUPAVISOR_TRANSACTION_POOLER_PORT = 6543

# Default FORWARDED_ALLOW_IPS trust boundary: the RFC 1918 172.16.0.0/12
# block backing the production reverse-proxy path (see the field's docstring
# below for the full trust-boundary rationale and why it cannot yet be
# narrowed). Not a target address or secret: it is the legitimate default
# CIDR uvicorn's --forwarded-allow-ips trusts, hardcoding it here is
# intentional.
_DEFAULT_FORWARDED_ALLOW_IPS_CIDR = "172.16.0.0/12"  # NOSONAR(S1313)

# The verification methods KWS's Control Panel offers per environment, as a
# closed set so a typo becomes a startup error rather than a silently wrong
# claim on a consent record. Names mirror the Control Panel's own rows.
# Availability is regional and KWS enforces it, not us: social_security_number
# is US-and-territories only, id_scan and face_scan are worldwide EXCEPT the US
# and its territories (and Korea), curp_number is Mexico, cpf_number is Brazil,
# cell_phone_certification and ipin_authentication are Korea, and the two card
# methods are worldwide except a sanctions list (debit_card additionally
# excludes the United Kingdom). For a US family that leaves exactly three
# options: social_security_number, credit_card, debit_card.
KwsVerificationMethod = Literal[
    "social_security_number",
    "id_scan",
    "curp_number",
    "cpf_number",
    "face_scan",
    "cell_phone_certification",
    "ipin_authentication",
    "credit_card",
    "debit_card",
]


def _check_pooler_port_requires_disabled_cache(
    *, label: str, url: str, disable_prepared_cache: bool
) -> None:
    """Fail fast when a single database DSN is Supavisor's pooler port but the flag is off.

    Extracted (ADR-021) so the model_validator below can apply the identical
    check to both database_url (the API engine) and
    worker_database_url_effective (the worker engine, core/database.py); a
    typo or drift between the two checks would silently reopen the
    prepared-statement collision for whichever DSN got skipped.

    Args:
        label: The operator-facing name of the DSN being checked, used only
            in the error message (never the secret-bearing URL itself).
        url: The DSN to inspect for the Supavisor pooler port.
        disable_prepared_cache: The resolved
            database_disable_prepared_cache flag value.

    Raises:
        ConfigurationError: when url's port is the Supavisor
            transaction-pooler port and disable_prepared_cache is False,
            since asyncpg then collides on cached/fixed-name prepared
            statements once the pooler reassigns a backend mid-session.
    """
    port = urlsplit(url).port
    if port == _SUPAVISOR_TRANSACTION_POOLER_PORT and not disable_prepared_cache:
        msg = (
            f"{label} uses port 6543 (Supabase Supavisor's transaction-mode "
            "pooler) but CYO_ADVENTURE_DATABASE_DISABLE_PREPARED_CACHE is not "
            "set; refusing to start, since asyncpg will intermittently raise "
            "DuplicatePreparedStatementError / InvalidSQLStatementNameError "
            "under concurrency once the pooler reassigns a backend mid-session."
        )
        raise ConfigurationError(msg)


# HS256 keys shorter than the 32-byte hash output are the ones PyJWT flags, so
# 32 bytes is the floor for any backend-signed token secret.
_MIN_TOKEN_SECRET_BYTES = 32

# Known scaffolding placeholders rejected regardless of length so a copied .env
# template can never sign real tokens. Compared casefolded against the stripped
# secret value; a secret is NEVER interpolated into an error message.
_TOKEN_SECRET_PLACEHOLDERS = frozenset(
    {
        "replace_me",
        "changeme",
        "change_me",
        "your_secret_here",
        "your-secret-here",
        "secret",
        "xxx",
        # The docker-compose.yml local-dev defaults are repository-known HMAC
        # keys; long enough to pass the byte floor, so they must be rejected by
        # exact value outside local (either secret slot, in case one is reused
        # for the other).
        "local-dev-child-session-secret-not-for-production",
        "local-dev-device-grant-secret-not-for-production",
    }
)


class _TokenSecretSpec(NamedTuple):
    """The message-only descriptors identifying one backend token secret.

    Bundles the three strings that differ between the child-session and
    device-grant validators so ``_require_strong_token_secret`` stays a small,
    single-secret helper (the checking logic itself never varies).
    """

    env_var: str  # operator-facing env var name, e.g. "CHILD_SESSION_SECRET"
    purpose: str  # what the secret signs, e.g. "child session tokens"
    ref: str  # traceability reference, e.g. "G1 / P6-04"


def _require_strong_token_secret(
    secret: SecretStr | None, spec: _TokenSecretSpec, environment: str
) -> None:
    """Fail fast on a missing or weak backend token-signing secret.

    Shared by the child-session and device-grant secret validators so the
    placeholder set, byte floor, and message shape can never drift apart
    (issue #254). Presence alone is not enough: an empty ``SecretStr("")``
    passes ``is None`` but makes ``jwt.encode`` raise ``InvalidKeyError`` (a
    500 on every mint), and a short or placeholder secret signs real, forgeable
    tokens with a weak HMAC key. PyJWT's ``InsecureKeyLengthWarning`` only
    errors under pytest ``filterwarnings``, not at runtime, so this check is the
    only thing stopping a shipped ``REPLACE_ME`` placeholder from reaching
    production.

    #CRITICAL: security: rejecting weak/placeholder keys here is the token
    forgery boundary; a short HMAC key lets an attacker mint valid tokens.
    #VERIFY: no branch echoes the secret value into the error; test_config
    rejects empty, whitespace, sub-32-byte, and placeholder secrets for each.

    Args:
        secret: The configured secret (may be ``None``).
        spec: The message-only descriptors for this secret (env var, purpose,
            traceability ref). None of the secret value is ever placed here.
        environment: The resolved deployment stage (for the message only).

    Raises:
        ConfigurationError: when ``secret`` is unset, empty, shorter than 32
            bytes, or a known placeholder.
    """
    if secret is None:
        msg = (
            f"{spec.env_var} must be set in non-local environments; refusing to "
            f"start in '{environment}' with no way to sign or verify "
            f"{spec.purpose} ({spec.ref})."
        )
        raise ConfigurationError(msg)

    value = secret.get_secret_value()
    stripped = value.strip()
    if (
        not stripped
        or len(value.encode("utf-8")) < _MIN_TOKEN_SECRET_BYTES
        or stripped.casefold() in _TOKEN_SECRET_PLACEHOLDERS
    ):
        msg = (
            f"{spec.env_var} is set but too weak: it must be a non-placeholder "
            f"value of at least {_MIN_TOKEN_SECRET_BYTES} bytes to safely sign "
            f"{spec.purpose}; refusing to start in '{environment}' ({spec.ref})."
        )
        raise ConfigurationError(msg)


class Settings(BaseSettings):
    """
    Configuration settings for the application, loaded from environment variables.

    Attributes:
        model_config: Pydantic settings configuration (env prefix and parsing).
        environment: Deployment stage; gates the database_url fail-fast check.
        log_level: The logging level for the application.
        json_logs: Flag to enable or disable JSON formatted logs.
        include_timestamp: Flag to include timestamps in logs.
        database_url: Async SQLAlchemy connection URL for PostgreSQL.
        redis_url: Redis connection URL for the RQ task queue.
        generation_provider: Which LLM provider to use for story generation.
        mock_story_fixture: DEV/TEST-ONLY selector for the mock provider's
            canned fixture ("safe" default, or "invalid" to trip the gate).
    """

    model_config = SettingsConfigDict(
        env_prefix="cyo_adventure_",
        case_sensitive=False,
        extra="ignore",
        # Allow population by field name in addition to validation_alias, so
        # openrouter_api_key can be set directly (tests, DI) as well as via the
        # unprefixed OPENROUTER_API_KEY env var.
        populate_by_name=True,
    )

    # validation_alias="ENVIRONMENT" makes the field read the unprefixed var so
    # docker-compose.prod.yml and .env.example (which both set ENVIRONMENT=...)
    # are honoured without the cyo_adventure_ prefix. populate_by_name=True in
    # model_config lets direct constructor calls (Settings(environment="dev")) and
    # tests still work without needing the alias.
    environment: Literal["local", "dev", "staging", "production"] = Field(
        default="local", validation_alias="ENVIRONMENT"
    )
    # log_level and json_logs are read from their UNPREFIXED names: both
    # docker-compose*.yml and docs/guides/configuration.md set LOG_LEVEL /
    # JSON_LOGS with no cyo_adventure_ prefix (same operator-facing convention as
    # ENVIRONMENT and OPENROUTER_*/MODAL_* above). AliasChoices keeps the prefixed form
    # working too and, listed first, wins if both are set. Without this, a
    # compose-injected LOG_LEVEL/JSON_LOGS was silently ignored at runtime.
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = Field(
        default="INFO",
        validation_alias=AliasChoices("CYO_ADVENTURE_LOG_LEVEL", "LOG_LEVEL"),
    )
    json_logs: bool = Field(
        default=False,
        validation_alias=AliasChoices("CYO_ADVENTURE_JSON_LOGS", "JSON_LOGS"),
    )
    include_timestamp: bool = True
    # #CRITICAL: security: this credential-less localhost default resolves as the
    # live DSN whenever CYO_ADVENTURE_DATABASE_URL is unset, including in CI. It is
    # a localhost-only development default (peer/trust auth) and must never reach
    # staging or production.
    # #VERIFY: enforced by _reject_dev_database_url_outside_local below.
    # Accept BOTH names. CYO_ADVENTURE_DATABASE_URL is the established contract
    # (migrations/env.py, integration tests, the validator message all name it),
    # so it stays first and wins if both are set; DATABASE_URL is the standard
    # name docker-compose*.yml injects, previously ignored because the field had
    # no alias and env_prefix only matched the prefixed form.
    database_url: str = Field(
        default=_DEV_DATABASE_URL,
        validation_alias=AliasChoices("CYO_ADVENTURE_DATABASE_URL", "DATABASE_URL"),
    )
    # Disable SQLAlchemy's asyncpg prepared-statement cache when the backend
    # connects through a transaction-mode connection pooler: Supabase Supavisor
    # on :6543 (ADR-009 Task 1.7) or PgBouncer in transaction mode. Such poolers
    # multiplex one backend connection across many client sessions, so a
    # server-side prepared statement created under one logical session can be
    # reused, or have its name collide, under another. Disabling the cache and
    # giving each prepared statement a unique name is the SQLAlchemy-documented
    # fix. Leave False for a direct PostgreSQL connection (local dev, or
    # Supabase's :5432 session/direct DSN used for direct connections and CLI
    # migrations), where server-side prepared statements are safe and faster.
    # #CRITICAL: concurrency: with a transaction pooler and this flag unset,
    # the first reused/renamed prepared statement raises asyncpg
    # DuplicatePreparedStatementError / InvalidSQLStatementNameError and the
    # request 500s intermittently under concurrency, not at startup.
    # #VERIFY: enforced for the known Supavisor case by
    # _require_prepared_cache_disabled_for_pooler_dsn below; consumed by
    # core/database.py::_build_connect_args and _build_engine_kwargs.
    database_disable_prepared_cache: bool = False
    # Worker-process database DSN (ADR-021). None (default) falls back to
    # database_url via worker_database_url_effective below, so an
    # environment that has not split credentials yet keeps single-role
    # behavior unchanged (the ADR's safety valve): merging this field alone
    # changes zero connection identities anywhere. Same AliasChoices/prefix
    # pattern as database_url, so both CYO_ADVENTURE_WORKER_DATABASE_URL and
    # the unprefixed WORKER_DATABASE_URL (docker-compose's naming
    # convention) bind, with the prefixed form winning if both are set.
    worker_database_url: str | None = Field(
        default=None,
        validation_alias=AliasChoices(
            "CYO_ADVENTURE_WORKER_DATABASE_URL", "WORKER_DATABASE_URL"
        ),
    )
    # Explicit pool sizing for the direct-connection QueuePool branch,
    # applied to both the API and worker engines (core/database.py). Closes
    # the CRITICAL-tagged debt already recorded against core/database.py
    # (ADR-009 Components Affected list, "now live and unsized"). Defaults
    # match the SQLAlchemy QueuePool defaults that were previously implicit,
    # so an environment that never sets these keeps its current pool ceiling.
    # #CRITICAL: concurrency: these bounds only apply to a direct
    # (non-pooler) connection; the Supavisor transaction-pooler branch uses
    # NullPool, which has no pool_size/max_overflow of its own, and
    # core/database.py::_build_engine_kwargs never passes them on that
    # branch (doing so would raise TypeError at engine construction).
    # #VERIFY: tests/unit/test_database.py::TestEngineKwargs pins both the
    # direct-branch wiring and the pooler-branch TypeError-avoidance guard.
    database_pool_size: int = Field(default=5, ge=1)
    database_max_overflow: int = Field(default=10, ge=0)
    # Development default for local Redis; safe to leave unset in non-production
    # environments where no queue is configured. Production must override via
    # CYO_ADVENTURE_REDIS_URL. Accepts BOTH names, mirroring database_url above:
    # CYO_ADVENTURE_REDIS_URL is the established contract and wins if both are
    # set; REDIS_URL is the standard name docker-compose*.yml injects, previously
    # ignored because the field had no alias (ADR-021 Phase 1).
    redis_url: str = Field(
        default="redis://localhost:6379/0",
        validation_alias=AliasChoices("CYO_ADVENTURE_REDIS_URL", "REDIS_URL"),
    )
    # Comma-separated Host-header allowlist for TrustedHostMiddleware
    # (defense-in-depth against Host/X-Forwarded-Host spoofing). Empty (the
    # default) leaves the middleware off, matching prior behavior; deployed
    # tiers set their fronting domain(s), e.g.
    # "cyoadventure.app,api.cyoadventure.app".
    allowed_hosts: str = Field(
        default="",
        validation_alias=AliasChoices("CYO_ADVENTURE_ALLOWED_HOSTS", "ALLOWED_HOSTS"),
    )
    # M5/Phase 5: RateLimitMiddleware's backend selector (middleware/security.py).
    # "redis" shares rate-limit counters across every worker process via this
    # same redis_url (the RQ queue's Redis instance, database index 0 by
    # default; a distinct logical DB can be pointed at via redis_url if
    # keyspace collision with RQ job data is a concern). "memory" keeps the
    # legacy process-local counter, useful for single-process local dev or
    # tests that must not depend on a reachable Redis. RateLimitMiddleware
    # itself always falls back to the in-memory counter on a Redis error
    # regardless of this setting: this only chooses the *preferred* backend,
    # not whether the fallback exists.
    # #CRITICAL: security: "redis" is the correct default for every deployed
    # (non-local) tier per docs/planning/roadmap.md Phase 5 -- an in-memory
    # counter is meaningless across the multi-process/multi-replica production
    # topology described in SECURITY.md.
    # #VERIFY: tests/unit/test_security.py::TestRateLimitBackendSetting
    # covers the default and the env-var override.
    rate_limit_backend: Literal["redis", "memory"] = Field(
        default="redis", validation_alias="CYO_ADVENTURE_RATE_LIMIT_BACKEND"
    )
    # #CRITICAL: timing: RateLimitMiddleware.dispatch runs on every request; a
    # slow/black-holed Redis connection must not add unbounded latency to the
    # request path while stuck waiting for a socket. Both socket_connect_timeout
    # and socket_timeout are set from this value on BOTH redis clients: the
    # middleware's (via add_security_middleware) and api/health.py's readiness
    # probe. Until the #516 sweep it reached only the health probe, so the
    # middleware ran at its constructor default and this env var was inert
    # for the request path this comment describes.
    # #VERIFY: tests/unit/test_security.py::test_redis_backend_falls_back_to_memory_on_connection_error
    # exercises the fallback path this bound protects, and
    # ::test_add_security_middleware_resolves_redis_timeout_from_settings
    # asserts the value actually reaches the middleware.
    # #EDGE: data-integrity: ge=0.0 exists because this value only started
    # reaching the middleware in the #516 sweep. While it was inert a negative
    # was harmless; now it is a socket timeout, so reject it at parse time
    # rather than at the first Redis call.
    rate_limit_redis_timeout_seconds: float = Field(
        default=0.5,
        ge=0.0,
        validation_alias="CYO_ADVENTURE_RATE_LIMIT_REDIS_TIMEOUT_SECONDS",
    )
    # #CRITICAL: timing: once a Redis error is observed, RateLimitMiddleware
    # stops retrying Redis for this many seconds and serves every request from
    # the in-memory fallback instead. Without this circuit breaker, a sustained
    # outage would pay rate_limit_redis_timeout_seconds of added latency on
    # EVERY request, not just the first.
    # #VERIFY: tests/unit/test_security.py::test_redis_backend_circuit_breaker_skips_retry_during_cooldown
    # proves the middleware HONOURS the window, and
    # ::test_add_security_middleware_resolves_redis_cooldown_from_settings
    # proves the application SUPPLIES it. Issue #516 existed because only the
    # first kind of test was present: it constructs the middleware directly, so
    # it passed for months while add_security_middleware never passed the value.
    # #CRITICAL: security: ge=0.0 is load-bearing, not defensive tidiness. The
    # breaker is armed by `self._redis_unavailable_until = current_time +
    # cooldown_seconds`; a negative value lands that instant in the PAST, so
    # every request re-tries a dead Redis and pays the full timeout. That is
    # precisely the failure the #CRITICAL note above says the breaker exists
    # to prevent, and it became reachable only when this sweep made the env
    # var live.
    # #VERIFY: tests/unit/test_config.py::test_rate_limit_redis_bounds_reject_negative
    rate_limit_redis_cooldown_seconds: float = Field(
        default=5.0,
        ge=0.0,
        validation_alias="CYO_ADVENTURE_RATE_LIMIT_REDIS_COOLDOWN_SECONDS",
    )
    # #CRITICAL: timing: RQ's own default job_timeout is 180s; a live multi-stage
    # run routinely exceeds that, so an unset job_timeout lets RQ SIGALRM-kill a
    # still-healthy generation job and strand its row. 1800s (30 min) comfortably
    # covers the full three-stage pipeline (structure, prose, up to 3 repairs)
    # against the slowest configured leg, walking the whole cascade if every leg
    # fails over. Since the Ollama retirement the slowest leg is Modal
    # (modal_timeout_seconds=180, cold-starting a vLLM server), well inside this
    # bound; the 300s Ollama leg this figure was originally sized around is gone.
    # #VERIFY: generation/queue.py::enqueue_generation passes this as
    # job_timeout= on every enqueue call (both the guardian-triggered enqueue and
    # the stranded-job reclaim sweep's re-enqueue).
    generation_job_timeout_seconds: int = 1800
    # Provider selection. "mock" remains the default so CI and local runs never
    # make live LLM calls; production sets this to "openrouter" (the primary
    # per ADR-003 as amended 2026-06-22). Staging also sets "openrouter" but
    # pins a cheap model rather than the production pair, so staging exercises
    # the real adapter path at bounded cost (see .env.staging.example); before
    # the Ollama retirement it ran the free local leg instead.
    # Live adapters are constructed lazily in build_provider(), so an unset
    # live key fails at call time, not startup.
    generation_provider: Literal["mock", "anthropic", "openrouter", "modal"] = "mock"

    # DEV/TEST-ONLY: which canned fixture the deterministic mock provider serves.
    # "safe" (default) is the gate-clean canned story ("The Forest Path") the
    # whole test/dev stack has always used, so the default is a zero-behavior
    # change. "invalid" makes build_provider's mock branch queue a structurally
    # broken Storybook that deterministically trips the validator gate to an
    # ERROR-severity block, so the full pipeline can be driven to a
    # HARD-BLOCK / needs-review outcome over the real HTTP path in local dev and
    # E2E tests (closes review finding S-5). It has NO effect on any non-mock
    # provider, and the mock provider is never selectable through the admin
    # provider allowlist, so this stays dev/test-only and never weakens prod.
    # #ASSUME: security: nothing rejects this setting, or
    # generation_provider="mock" itself, at startup outside local; neither has a
    # model_validator (unlike _reject_dev_database_url_outside_local below).
    # Safety rests on deployment convention (production sets
    # generation_provider="openrouter", see the note above) plus the DB
    # allowlist never carrying a "mock" row (ALLOWLIST_PROVIDERS in
    # generation/allowlist.py, mirrored by the
    # ck_provider_model_allowlist_provider CHECK in db/models.py), so no admin
    # can select it either. A deployed tier that set
    # CYO_ADVENTURE_GENERATION_PROVIDER=mock would serve canned stories, and
    # with "invalid" would hard-block every generation, raising no startup error.
    # #VERIFY: if this must be enforced rather than conventional, add a
    # model_validator rejecting generation_provider="mock" when environment is
    # not "local", same shape as _require_oidc_config_outside_local below; until
    # then, confirm each deployed .env sets an explicit non-mock provider.
    mock_story_fixture: Literal["safe", "invalid"] = "safe"

    # Model ids are pinned in config, not code (ADR-003): a model swap is a
    # config change. OpenRouter rosters churn weekly, so pin ids from families with
    # a stable roster presence, and rely on the fallback below when a pinned id
    # 404s. Note the criterion here is availability, not data policy: ADR-003's
    # 2026-07-28 amendment retired the vendor-identity rule that once limited
    # production generation to Anthropic and Google. Eligibility is now the PII
    # guard on every prompt plus the OpenRouter workspace ZDR/no-training
    # guardrail, so a lab is disqualified by the data policy its endpoint enforces
    # (or by not being allowlisted), never by which lab it is.
    # Primary is DeepSeek V4 Pro (D1, ruled 2026-08-23, `UW-C346`; the ruling and
    # its basis are in docs/planning/generation-review-workstream-plan-2026-08-22.md
    # section 3). The ruling is PROVISIONAL and rests on open weights keeping a
    # fine-tuning path available plus a low enough cost point to buy iteration
    # speed; it makes no appeal to per-model quality rankings, so R-8's finding
    # that those rankings are statistically unsupported does not undermine it.
    # It replaces Haiku 4.5, which the 2026-06-22 yield run measured at 70% over
    # a 20-brief sample (docs/planning/yield-results/phase-2b-2026-06-22-analysis.md);
    # that measurement is superseded as a SELECTION basis, not falsified, and the
    # >=60% yield gate it cleared still applies to the new leg.
    #
    # #CRITICAL: payment/financial: this slug's PRICES row is the price of ONE of
    # its endpoints (`azure/us`), not of the slug's default route, so it is only
    # a correct cost with the pin `core/pricing.py::ENDPOINT_PINS` supplies.
    # It is also deliberately absent from scripts/refresh_pricing.py::_WANTED,
    # whose own comment otherwise requires every priced OpenRouter model to be
    # listed there: that script reads the slug's DEFAULT route, so including this
    # row would overwrite the pinned price and understate every fill by ~25%.
    # Re-price it by hand from /models/deepseek/deepseek-v4-pro/endpoints.
    # #VERIFY: tests/unit/test_config.py::TestD1RuledGenerationDefaults::
    # test_both_ruled_defaults_are_fully_priced and
    # tests/unit/test_openrouter_provider_pin.py::
    # test_a_priced_pin_is_applied_when_the_caller_names_no_order.
    #
    # The FALLBACK stays on a different vendor family on purpose. D1 rules on the
    # fill and review legs and says nothing about this one, which exists for
    # failure-domain coverage: a second DeepSeek slug would fail together with
    # the first for any model-specific cause (a withdrawn slug, a guardrail
    # change, an endpoint outage), which is most of what this leg is for.
    # #VERIFY: tests/unit/test_config.py::TestD1RuledGenerationDefaults::
    # test_the_fallback_leg_is_a_different_vendor_family.
    #
    # #ASSUME: external-resources: these ids must be currently reachable on the
    # selected provider; build_provider/adapters map an unavailable model to
    # ProviderError so the orchestrator can fall back.
    # #VERIFY: Phase 2b adapter raises ProviderError on HTTP 400/404 invalid-model.
    openrouter_model: str = "deepseek/deepseek-v4-pro"
    openrouter_fallback_model: str = "anthropic/claude-sonnet-4.6"
    # Direct-Anthropic credential and defaults (WS-C PR1). Read from the
    # UNPREFIXED ANTHROPIC_API_KEY env var, matching the openrouter_api_key
    # precedent. Optional and None by default: only generation_provider=anthropic
    # (globally or per-job via build_provider's provider_override) needs it, so a
    # missing key surfaces as a ConfigurationError in build_anthropic_leg at call
    # time, not at startup.
    # #CRITICAL: security: this is a secret; never log its value or echo it in
    # an error message. build_anthropic_leg checks presence only.
    # #VERIFY: ConfigurationError messages reference the key by name only,
    # never by value (test_anthropic_key_value_not_leaked_in_error).
    anthropic_api_key: str | None = Field(
        default=None, validation_alias="ANTHROPIC_API_KEY"
    )
    # The Anthropic SDK's own built-in default base url; setting it explicitly
    # (rather than omitting it) keeps build_anthropic_leg's call to
    # AsyncAnthropic(base_url=...) unconditional and testable.
    anthropic_base_url: str = "https://api.anthropic.com"
    # Global default model when generation_provider=anthropic and no per-job
    # model_override is present (see build_provider). Mirrored in
    # generation/allowlist.py::DEFAULT_ALLOWLIST's first anthropic row.
    anthropic_model: str = "claude-sonnet-4-6"

    # Reasoning effort for live generation. "off" (default) sends NO `reasoning`
    # param: story generation is structured-JSON output, and a live smoke showed
    # that enabling reasoning on Claude (even "low") spends the whole max_tokens
    # budget on thinking tokens and returns finish_reason=length with empty
    # content. Set to low/medium/high only to deliberately opt a model into
    # extended thinking; the adapter forwards it as OpenRouter's `reasoning.effort`
    # (ignored by models that lack it).
    llm_effort: Literal["off", "low", "medium", "high"] = "off"

    # Per-call wall-clock timeout for a single live provider completion. Generation
    # responses are large (a full story is thousands of tokens), so the default is
    # generous; the adapter's transient-retry backoff stacks on top of this.
    # #ASSUME: external-resources: a live LLM call can hang; without a timeout a
    # stuck request would block a worker indefinitely.
    # #VERIFY: Phase 2b adapter passes this to httpx.AsyncClient(timeout=...).
    llm_timeout_seconds: int = 120

    # Cascade switch. True (default) lets FallbackProvider fail over across legs.
    # The yield/leg-comparison runs set this False to measure each leg in
    # isolation (no failover masking a leg's true yield).
    provider_fallback_enabled: bool = True

    # Provider endpoint. OpenRouter's base url is stable.
    openrouter_base_url: str = "https://openrouter.ai/api/v1"

    # OpenRouter credential. Read from the UNPREFIXED ``OPENROUTER_API_KEY`` env
    # var (validation_alias bypasses the cyo_adventure_ prefix) to match the
    # operator's existing key naming. Optional and None by default: only the
    # openrouter provider needs it, and the mock default never does, so a missing
    # key surfaces as a ConfigurationError in build_provider at call time rather
    # than blocking startup.
    # #CRITICAL: security: this is a secret; never log its value or echo it in an
    # error message. build_provider checks presence only.
    # #VERIFY: ProviderError/ConfigurationError messages reference the key by name
    # only, never by value.
    openrouter_api_key: str | None = Field(
        default=None, validation_alias="OPENROUTER_API_KEY"
    )

    # --- Modal generation leg (ADR-010 item 2) ---
    # Since the Ollama retirement this is the THIRD leg of the production
    # FallbackProvider cascade, replacing the local Ollama leg as the
    # non-OpenRouter backstop (ADR-003 as amended). It stays optional: all
    # four fields are None until an operator deploys a Modal Auto Endpoint and
    # sets them, and build_provider omits the leg entirely when the endpoint is
    # unconfigured rather than failing the cascade (see modal_leg_configured).
    # #CRITICAL: external-resources: with Modal unconfigured the cascade is two
    # OpenRouter legs, so a single-vendor OpenRouter outage takes generation
    # down with no backstop. Configuring Modal in production is what makes
    # Layer 2 failover span two vendors.
    # #VERIFY: generation/provider.py::build_provider logs
    # generation.cascade_single_vendor at WARNING when it builds the two-leg
    # cascade; tests/unit/test_providers.py pins both shapes.
    modal_base_url: str | None = Field(default=None, validation_alias="MODAL_BASE_URL")
    modal_model: str | None = Field(default=None, validation_alias="MODAL_MODEL")
    # #CRITICAL: security: these are secrets if the endpoint enforces auth; never
    # log their values or echo them in an error message. Modal Auto Endpoints use a
    # Modal-Key/Modal-Secret header pair for proxy auth, not a Bearer token
    # (confirmed against Modal's docs during the 2026-07-04 live deployment
    # attempt); both must be set together or neither, since a half-set credential
    # pair is a misconfiguration build_modal_leg should reject, not guess at.
    # #VERIFY: ModalProvider omits both headers entirely when either is None,
    # rather than sending a partial/placeholder credential.
    modal_proxy_key: str | None = Field(
        default=None, validation_alias="MODAL_PROXY_KEY"
    )
    modal_proxy_secret: str | None = Field(
        default=None, validation_alias="MODAL_PROXY_SECRET"
    )
    # Longer than llm_timeout_seconds (120s): Modal Auto Endpoints cold-start a
    # vLLM server on first request after idle, which the OpenRouter leg never
    # needs to tolerate.
    modal_timeout_seconds: int = 180

    # --- Slice-2 moderation review pipeline ---
    # Which backend the moderation LLM stages use. "mock" (default) runs no real
    # review and requires no classifier key. "modal" is deferred to slice 2b and
    # raises at build time. (The "anthropic" generation provider, once similarly
    # deferred, now ships as a real backend via WS-C PR1.) "ollama" was removed
    # with the Ollama retirement, so "openrouter" is the only live backend here
    # until the slice-2b Modal review leg lands.
    review_provider: Literal["mock", "openrouter", "modal"] = "mock"
    # DeepSeek V4 Flash per D1 (ruled 2026-08-23, `UW-C346`). Unlike the fill
    # leg above, this slug's PRICES row is its DEFAULT route, so it needs no
    # endpoint pin and `ENDPOINT_PINS` carries no entry for it.
    # #ASSUME: external-resources: the Stage-1 batch-size 8 recall parity
    # ratified on 2026-08-01 was measured against the THEN-current reviewer
    # (Sonnet 4.6) and the current batch prompt. Changing the reviewer model
    # invalidates that evidence by the terms the sweep itself recorded below,
    # so the ratified batch size is now resting on an unmeasured reviewer.
    # #VERIFY: re-run scripts/adversarial_harness.py --batch-size against this
    # reviewer before treating the 2026-08-01 parity as current; tracked as the
    # reviewer-swap half of `UW-C346`.
    review_openrouter_model: str = "deepseek/deepseek-v4-flash"
    # Nodes reviewed per Stage-1 safety call (design doc moderation-review-
    # redesign-2026-07-28.md, section 2.2 item 2). At 1 every chunk is a
    # single-node call, byte-identical to the pre-chunking behavior the
    # stage always had (pinned by tests/unit/test_moderation_stages.py::
    # test_safety_stage_batch_size_one_matches_unbatched_behavior, which
    # asserts the single-node system prompt, prompt text, and unscaled token
    # budget rather than comparing two runs of the same branch).
    # Default 8 was ratified by the owner-run Gate 3 recall comparison
    # (scripts/adversarial_harness.py --batch-size sweep, two independent
    # runs on 2026-08-01, artifact
    # docs/planning/safety/batch-sweep-results-2026-08-01.json): zero
    # item-level recall regressions vs size 1 on every scored class, and
    # zero structural-collapse (parse-failure) findings.
    # Read the evidence with its limits in view, they are not incidental:
    #   - REQUESTED size 8, REALIZED max 6. The adversarial corpus's largest
    #     age band holds 6 Stage-1 nodes, so no call in that run ever carried
    #     8 nodes. Sizes 4 and 8 were identical in 3 of the 4 bands. The
    #     ratified value is therefore extrapolated one step past what was
    #     measured; the harness now records realized_chunk_sizes so a future
    #     run cannot repeat this ambiguity silently.
    #   - Scoring was binary (is_caught against expected_min). One aggregate
    #     item softened block -> flag at sizes 4 and 8 while still clearing
    #     its expected_min, so it scored as no regression. The harness now
    #     reports that class of severity drift separately.
    # #ASSUME: external-resources: batched verdicts may be less accurate than
    # single-node calls on real passages. A reviewer asked to attribute N
    # verdicts to N node ids in one response can mis-attribute, merge, or
    # flatten them in ways a single-node call cannot; the 2026-08-01 sweep
    # found no such case on a 13-item corpus, which bounds the risk without
    # eliminating it.
    # #ASSUME: external-resources: the recall parity above was measured
    # against the openrouter reviewer and the current batch prompt; a
    # reviewer model or _SAFETY_SYSTEM_BATCH prompt change invalidates it.
    # #CRITICAL: security: raising this raises the fail-safe blast radius
    # proportionally. A chunk whose verdicts fail to parse collapses to ONE
    # structural FLAG covering every node in the chunk, so at 8 a single
    # malformed response withholds per-node safety detail for 8 nodes instead
    # of 1. Fail-safe direction is preserved (the story still cannot
    # auto-publish), but the reviewer's granularity is lost for the batch.
    # #VERIFY: re-run the adversarial-harness batch sweep after any reviewer
    # model or batch-prompt change before keeping the default above 1, and
    # confirm the run's realized_chunk_sizes actually reach the value set
    # here rather than merely requesting it.
    review_batch_size: int = Field(default=8, ge=1, le=50)
    # Escape hatch for `review_provider="mock"` outside `environment="local"`
    # (design doc section 2.4, moderation review redesign). The mock reviewer
    # runs no real safety review; a non-local process quietly booting with it
    # would persist unreviewed moderation reports as if they were reviewed
    # (gap G1). `_require_real_reviewer_outside_local` below refuses to boot
    # in that combination unless this is explicitly set. Note what this flag
    # does NOT do: it does not drive the moderation pipeline's stamp. That
    # stamp keys on `review_provider == "mock"` alone and fires in every
    # environment, hatch or no hatch, so a mock-moderated report is
    # self-identifying forever whether or not it needed permission to boot.
    # The two were once described as one mechanism, and the pipeline's stamp
    # was gated on `environment != "local"` to match; that shared gate is
    # what let twelve books through (gap G1, and the #CRITICAL block at
    # moderation/pipeline.py's `mock_reviewer` assignment).
    allow_mock_review: bool = False

    # Stage-0 deterministic classifier credentials. OpenAI is optional; a missing
    # key skips that classifier, and an unset key is rejected below when review
    # runs (see test_non_mock_review_with_only_perspective_key_raises).
    openai_api_key: str | None = Field(default=None, validation_alias="OPENAI_API_KEY")
    # Deprecated: Google Perspective was retired as a Stage-0 signal source
    # (ratified sunset); run_classifiers no longer calls it and no code path
    # reads this field. The field is kept, not removed, because deployed env
    # files still set PERSPECTIVE_API_KEY and this is a plain Optional[str]
    # field with no constraint to trip on an empty-string override; removing it
    # would only be a symbolic cleanup with real deploy-config risk for no
    # runtime benefit. Safe to delete once PERSPECTIVE_API_KEY is scrubbed from
    # every deployed env file.
    perspective_api_key: str | None = Field(
        default=None, validation_alias="PERSPECTIVE_API_KEY"
    )

    # --- OIDC verification (ADR-009: Supabase Auth, guardian tier; PROJECT-PLAN P6-02) ---
    # Provider-agnostic names are deliberate (ADR-009's ejection path): these
    # point at Supabase's GoTrue issuer today but api/deps.py never imports a
    # Supabase SDK, only jwt.PyJWKClient against oidc_jwks_url. Read from
    # UNPREFIXED env vars, matching the openrouter_api_key/modal_proxy_key pattern.
    # Optional here so local dev needs no config; _require_oidc_config_outside_local
    # below fails fast outside "local", and api/deps.py's own import-time guard is a
    # second check against the same invariant for the mocked-settings test scenario.
    oidc_issuer: str | None = Field(default=None, validation_alias="OIDC_ISSUER")
    # Default sourced from the registry member rather than repeating the
    # literal, so the two copies of "authenticated" cannot drift apart. The
    # member's own docstring already claims it "mirrors the default of
    # settings.oidc_audience"; referencing it here is what makes that claim
    # enforced rather than aspirational. The setting stays operator-overridable
    # (it is the one audience the backend does not mint), which is why it is a
    # default and not a constant, and why GUARDIAN_OIDC is deliberately absent
    # from the distinctness validator below (see its rationale and issue #251).
    oidc_audience: str = Field(
        default=TokenAudience.GUARDIAN_OIDC.value, validation_alias="OIDC_AUDIENCE"
    )
    oidc_jwks_url: str | None = Field(default=None, validation_alias="OIDC_JWKS_URL")
    # Signature-algorithm allowlist for bearer-token verification (ADR-013:
    # hybrid PQC readiness). Config-driven rather than hardcoded in
    # api/deps.py so a future post-quantum JOSE algorithm (e.g. ML-DSA, once
    # Supabase issues it and PyJWT verifies it) is an env change, not a code
    # change. Env form is a JSON list: OIDC_ALLOWED_ALGS='["RS256","ES256"]'.
    # #CRITICAL: security: the explicit allowlist is what defeats alg=none and
    # HS256 key-confusion forgeries; making it configurable must not reopen
    # them, so _reject_forgeable_jwt_algorithms below refuses an empty list,
    # "none", and the symmetric HMAC family at startup, never at request time.
    # #VERIFY: tests/unit/test_config.py::TestOidcAllowedAlgs covers all three
    # rejections plus the PQC-name acceptance path.
    oidc_allowed_algs: list[str] = Field(
        default_factory=lambda: ["RS256", "ES256"],
        validation_alias="OIDC_ALLOWED_ALGS",
    )

    @field_validator("oidc_allowed_algs")
    @classmethod
    def _reject_forgeable_jwt_algorithms(cls, algs: list[str]) -> list[str]:
        """Refuse allowlist values that would enable classic JWT forgeries.

        Deliberately a denylist (``none`` and the ``HS256``/``HS384``/``HS512``
        HMAC family), not an allowlist of known algorithm names: the point of
        the setting (ADR-013) is that a finalized post-quantum JOSE algorithm
        can be enabled by env var without touching this code.

        Args:
            algs: The configured algorithm allowlist.

        Returns:
            list[str]: The validated allowlist with surrounding whitespace
                stripped from each entry.

        Raises:
            ConfigurationError: If the list is empty (every token would be
                rejected), or contains ``none`` (unsigned tokens) or one of
                ``HS256``/``HS384``/``HS512`` (symmetric HMAC; with an
                asymmetric JWKS this enables public-key-as-HMAC-secret
                confusion).
        """
        if not algs:
            msg = (
                "OIDC_ALLOWED_ALGS must not be empty; with no accepted "
                "signature algorithm every bearer token would fail "
                "verification (ADR-013)."
            )
            raise ConfigurationError(msg)
        # Normalize once: surrounding whitespace is stripped so a padded entry
        # like " ES256 " is both checked against the denylist AND stored in its
        # usable form. Returning the raw list would let " ES256 " pass startup
        # and then fail PyJWT's exact-string registry lookup on every request
        # (fail-closed at runtime while healthy at boot: the worst failure mode).
        normalized = [alg.strip() for alg in algs]
        # The forbidden set is exactly "none" plus the JWS HMAC family (RFC 7518
        # section 3.1). Enumerating HS256/384/512 rather than an "HS" prefix keeps
        # a future asymmetric JOSE algorithm that happens to start with "HS" (e.g.
        # a hash-based HSS registration) enable-able by env var per ADR-013.
        forbidden = [
            alg
            for alg in normalized
            if alg.lower() == "none" or alg.upper() in {"HS256", "HS384", "HS512"}
        ]
        if forbidden:
            msg = (
                f"OIDC_ALLOWED_ALGS contains forbidden algorithm(s) {forbidden}: "
                "'none' accepts unsigned tokens and the symmetric HMAC family "
                "(HS256/HS384/HS512) enables public-key-as-HMAC-secret confusion "
                "against a JWKS verifier; only asymmetric algorithms are allowed "
                "(ADR-013)."
            )
            raise ConfigurationError(msg)
        return normalized

    # --- Child-scoped session tokens (G1 / PROJECT-PLAN P6-04) ---
    # The kid surface does NOT use Supabase users. A guardian mints a short-lived,
    # backend-signed (HS256) JWT scoped to role=child and one profile; api/deps.py
    # verifies it in a second branch (see core/child_session.py). This secret signs
    # and verifies those tokens; it is a backend secret the browser never sees, and
    # is DISTINCT from the Supabase JWKS used for guardians. Optional here so local
    # dev needs no config; _require_child_session_secret_outside_local below fails
    # fast outside "local", mirroring the OIDC validator.
    # #CRITICAL: security: this is the child-session signing key; never log its
    # value or echo it in an error message, and never reuse a Supabase key for it.
    # #VERIFY: core/child_session.py reads it only via get_secret_value() at
    # mint/verify time; no error message includes the secret.
    child_session_secret: SecretStr | None = Field(
        default=None, validation_alias="CHILD_SESSION_SECRET"
    )
    # Child-session lifetime in seconds. Default 43200 (12h) comfortably covers a
    # single offline reading session; a child session cannot be refreshed, so it
    # reads a downloaded story for the token's full lifetime (debt-register
    # offline-reading requirement). The model sets env_prefix="cyo_adventure_",
    # so the unprefixed CHILD_SESSION_TTL_SECONDS the .env templates document
    # only binds because of this explicit alias; without it the field is inert
    # and every deploy silently keeps the 12h default. Mirror the sibling
    # child_session_secret, which pins CHILD_SESSION_SECRET the same way.
    # #EDGE: data integrity: ge=1 rejects a zero/negative TTL that would mint
    # already-expired tokens (every child mint 401s); a misconfig fails fast at
    # startup rather than at first read.
    # #VERIFY: test_config parses CHILD_SESSION_TTL_SECONDS and rejects TTL<=0.
    child_session_ttl_seconds: int = Field(
        default=43_200,
        ge=1,
        validation_alias=AliasChoices(
            "CYO_ADVENTURE_CHILD_SESSION_TTL_SECONDS",
            "CHILD_SESSION_TTL_SECONDS",
        ),
    )

    # --- Device grant tokens (ADR-014 phase 1) ---
    # A guardian mints a durable, family-scoped, backend-signed (HS256) token
    # once per shared device; core/device_grant.py mints/verifies it, and
    # api/deps.py routes it to a third principal branch alongside the
    # guardian OIDC and child-session branches. This secret is DISTINCT from
    # both child_session_secret and the Supabase JWKS; a device grant must
    # never verify against either of the other two signing keys. Optional
    # here so local dev needs no config; _require_device_grant_secret_outside_local
    # below fails fast outside "local", mirroring child_session_secret.
    # #CRITICAL: security: this is the device-grant signing key; never log
    # its value or echo it in an error message, and never reuse the
    # child-session or any Supabase key for it.
    # #VERIFY: core/device_grant.py reads it only via get_secret_value() at
    # mint/verify time; no error message includes the secret.
    device_grant_secret: SecretStr | None = Field(
        default=None, validation_alias="DEVICE_GRANT_SECRET"
    )
    # Device-grant lifetime in seconds. Default 7,776,000 (90 days, ADR-014):
    # long enough that a shared family device stays authorized between
    # guardian visits, short enough to bound a lost/stolen device's exposure
    # given that revocation cannot be enforced offline (ADR-014, "Negative /
    # risks"). The model sets env_prefix="cyo_adventure_", so the unprefixed
    # DEVICE_GRANT_TTL_SECONDS the .env templates document only binds because
    # of this explicit alias; mirrors child_session_ttl_seconds.
    # #EDGE: data integrity: ge=1 rejects a zero/negative TTL that would mint
    # already-expired tokens; a misconfig fails fast at startup rather than
    # at first read.
    # #VERIFY: test_config parses DEVICE_GRANT_TTL_SECONDS and rejects TTL<=0.
    device_grant_ttl_seconds: int = Field(
        default=7_776_000,
        ge=1,
        validation_alias=AliasChoices(
            "CYO_ADVENTURE_DEVICE_GRANT_TTL_SECONDS",
            "DEVICE_GRANT_TTL_SECONDS",
        ),
    )

    # --- Proxy trust boundary (Task E1, audit Group A: A1 rate-limit keying / A2 HSTS) ---
    # #CRITICAL: security: this CIDR is a trust boundary, not just documentation.
    # It is consumed by uvicorn's --forwarded-allow-ips CLI flag (set from this same
    # env var in the Dockerfile CMD and docker-compose*.yml `command:`), which is
    # what actually decides whether X-Forwarded-For/X-Forwarded-Proto are honored;
    # this Settings field mirrors that value for introspection and tests, it does not
    # itself gate anything at request time. Before this fix, the backend never
    # trusted any proxy header: RateLimitMiddleware keyed on the nginx container's
    # own IP (security.py, all clients collapsed into one bucket) and
    # SecurityHeadersMiddleware's HSTS branch (request.url.scheme == "https") never
    # fired behind the TLS-terminating reverse proxy. This Settings default of
    # the RFC 1918 172.16.0.0/12 block backs the PRODUCTION path only
    # (docker-compose.prod.yml's FORWARDED_ALLOW_IPS default and the
    # Dockerfile's hardcoded CMD fallback): the separate homelab-infra repo's
    # production `cyo-adventure` stack's `backend-net` (the network the nginx
    # container that fronts this backend reaches it over) has no pinned
    # subnet and is auto-assigned by Docker from the 172.17.0.0-172.31.255.255
    # pool on each recreation, so no single narrower CIDR can be hardcoded
    # there yet; narrowing it once backend-net is pinned is tracked in issue
    # #138. This repo's own dev docker-compose.yml network IS pinned
    # (172.26.0.0/16 as of this writing) and overrides FORWARDED_ALLOW_IPS to
    # that exact narrower subnet at the compose layer instead of trusting the
    # whole /12 umbrella, since anything broader would needlessly cover
    # addresses that can never be this backend's real dev reverse-proxy peer;
    # that dev subnet is not itself authoritative for production. Never widen
    # this to "*" (uvicorn's own trust-everyone sentinel): that would let any
    # client spoof its own IP (defeating per-client rate limiting) or scheme
    # (forging HSTS).
    # #VERIFY: FORWARDED_ALLOW_IPS must never be set to "*" in any Dockerfile,
    # compose file, or deployment env. Principal-keying (auth subject rather than
    # IP) and a Redis-backed rate-limit store are tracked separately in issue #71
    # (R2 rate-limit policy); this setting only restores correct client-IP/scheme
    # visibility at the proxy boundary, it does not change how RateLimitMiddleware
    # keys or stores requests.
    forwarded_allow_ips: str = Field(
        default=_DEFAULT_FORWARDED_ALLOW_IPS_CIDR,
        validation_alias="FORWARDED_ALLOW_IPS",
    )

    # --- Cover generation (nano banana) + Cloudflare R2 storage ---
    # #CRITICAL: security: nano banana + R2 credentials; never log values.
    # #VERIFY: referenced in covers/provider.py, covers/storage.py, and the
    # api/covers.py pre-enqueue config guard.
    gemini_api_key: str | None = Field(default=None, validation_alias="GEMINI_API_KEY")
    # R2 account id; the S3-compatible endpoint is derived as
    # f"https://{r2_account_id}.r2.cloudflarestorage.com" (covers/storage.py).
    # #CRITICAL: external resources: this value is interpolated straight into a
    # hostname, so a leading space or trailing newline that survived a manual paste
    # produces `Invalid endpoint: https:// ***.r2.cloudflarestorage.com` with no
    # indication of which character is at fault. `_normalize_r2_credential` strips it
    # here; `covers/storage.py::_require_r2_configured` rejects a value that still
    # cannot be a hostname label. The shape check deliberately lives there and not in
    # a validator, because `settings = Settings()` runs at import: raising here would
    # turn a cover-art misconfiguration into a whole-app startup failure.
    # #VERIFY: tests/unit/test_cover_settings.py::test_r2_credentials_are_whitespace_trimmed
    r2_account_id: str | None = Field(default=None, validation_alias="R2_ACCOUNT_ID")
    r2_access_key_id: str | None = Field(
        default=None, validation_alias="R2_ACCESS_KEY_ID"
    )
    r2_secret_access_key: str | None = Field(
        default=None, validation_alias="R2_SECRET_ACCESS_KEY"
    )
    r2_bucket: str = Field(default="covers", validation_alias="R2_BUCKET")

    @field_validator(
        "r2_account_id",
        "r2_access_key_id",
        "r2_secret_access_key",
        mode="after",
    )
    @classmethod
    def _normalize_r2_credential(cls, value: str | None) -> str | None:
        """Trim a hand-pasted R2 value and treat a whitespace-only one as absent.

        These three values are transcribed by hand from the Cloudflare dashboard
        into a deployment secret, and a leading space or trailing newline survives
        that paste. None of them can legitimately carry surrounding whitespace: the
        account id becomes a hostname label and the two keys are signed material.

        Collapsing a whitespace-only value to ``None`` is what makes the existing
        falsy guard in ``covers/storage.py::_require_r2_configured`` honest. That
        guard already rejects ``""`` and ``None``, but ``"   "`` is truthy and used
        to sail past it into a malformed endpoint or an unsignable request.

        This normalizes and never raises. ``settings = Settings()`` runs at import,
        so a validator that rejected a bad value would take the whole application
        down over an optional cover-art credential; the rejecting check belongs in
        the cover-art path, where it raises a scoped ``CoverGenerationError``.

        Args:
            value: The raw field value, ``None`` when the variable is unset.

        Returns:
            str | None: The trimmed value, or ``None`` if it was blank once trimmed.
        """
        if value is None:
            return None
        return value.strip() or None

    # #CRITICAL: security: this is NOT an instruction to make the bucket
    # browser-reachable. Covers are served to clients exclusively as
    # short-lived presigned GET URLs minted per request
    # (covers/storage.py::generate_presigned_cover_url); the bucket must NOT
    # have a public custom domain or r2.dev access bound to it, per the
    # #CRITICAL: security invariant at the top of covers/storage.py. This
    # setting only supplies the base that upload_cover concatenates with the
    # object key to produce the value stored in the cover_image_url audit
    # column and consumed by scripts/backfill_covers_r2.py's URL
    # classification. Nothing in a read path dereferences it: api/covers.py's
    # _cover_url deliberately ignores cover_image_url and mints a presigned
    # URL instead. Treat it as a stable naming prefix for recorded provenance,
    # not a live endpoint, and expect it to resolve to nothing.
    # #VERIFY: covers/storage.py's upload_cover returns
    # f"{r2_public_base_url}/{key}" and no read path fetches that URL; if a
    # GET against it ever succeeds without credentials, the bucket is public
    # and the storage.py invariant is violated.
    r2_public_base_url: str | None = Field(
        default=None, validation_alias="R2_PUBLIC_BASE_URL"
    )
    covers_backup_dir: str | None = None

    # --- ADR-015 G7: guardian cost gate ---
    # Platform-wide default monthly story-request budget for a family whose
    # Family.monthly_story_quota is unset (NULL): resolved at read time by
    # story_requests/service.py::_resolve_family_quota, never copied onto the
    # row at family creation, so raising this default lifts every
    # not-yet-customized family automatically.
    # #CRITICAL: payment/financial: this is the platform-wide fallback for
    # the generation-spend gate; a value that is too high (or accidentally
    # unbounded) weakens ADR-015's guardian cost gate for every family that
    # has not set an explicit override.
    # #VERIFY: tests/unit/test_story_requests.py pins the None-falls-back
    # case against this default.
    default_monthly_story_quota: int = Field(default=10, ge=0)
    # #ASSUME: external resources: the "-preview" alias was retired on the
    # Gemini API (shutdown 2026-06-25); the stable Nano Banana Pro id is used.
    # #VERIFY: override via COVER_MODEL if Google renames the stable channel.
    cover_model: str = "gemini-3-pro-image"
    cover_max_width: int = 800
    cover_quality: int = 80
    cover_max_bytes: int = 256_000
    cover_job_timeout_seconds: int = 180

    # --- Notification push transport (S9/G10 SSE stream) ---
    # How often api/notifications.py's stream endpoint re-queries
    # notifications/service.py::list_guardian_notifications while a guardian
    # has an SSE connection open. Short enough that a newly-arrived alert
    # (a kid flag, a blocked story) reaches an open tab in near-real-time,
    # unlike the 30s client-side badge poll it complements.
    notification_stream_poll_seconds: float = Field(default=5.0, ge=0.5)
    # #ASSUME: timing dependencies: the stream self-closes after this many
    # seconds rather than staying open indefinitely, so the frontend's own
    # reconnect loop (NotificationBell.tsx) periodically re-establishes the
    # connection. This is a deliberate bound, not an oversight: it caps how
    # long any one open tab holds server resources, and it protects against
    # a reverse proxy or load balancer silently killing a long-idle
    # connection with no client-visible signal (a self-close the client
    # reconnects from is a clean handoff; a proxy-killed socket is not).
    # #VERIFY: tests/unit/test_notifications_api_unit.py's stream tests pin
    # the self-close behavior; tests/integration/test_authz_matrix.py's
    # role-matrix cases for GET /api/v1/notifications/stream each wait up to
    # this long for the allowed-role case, since httpx awaits the full
    # response body and there is no seeded event to end the stream sooner --
    # keep this value modest so that suite's runtime is not dominated by it.
    notification_stream_max_seconds: float = Field(default=30.0, ge=1.0)

    # --- Observability: Sentry (M5 / Phase 5) ---
    # Read from the UNPREFIXED SENTRY_DSN env var: .env.example already
    # documents this name (Observability section), matching the
    # OPENROUTER_API_KEY/MODAL_*/OIDC_* precedent for operator-facing names.
    # None (default) disables Sentry entirely; core/observability.py::init_sentry
    # is a documented no-op in that case, so leaving this unset is always safe
    # for local dev, CI, and any deployment that has not opted in.
    # #CRITICAL: security: this is not a secret in the traditional sense (a
    # Sentry DSN is a write-only ingest endpoint, not a credential that grants
    # read access), but it still identifies the project; never log it.
    # #VERIFY: init_sentry never logs the DSN value itself, only whether one
    # is configured.
    sentry_dsn: str | None = Field(default=None, validation_alias="SENTRY_DSN")
    # Fraction of transactions sampled for Sentry performance tracing
    # (0.0-1.0). Low by default: this deployment wants error tracking first,
    # not full APM, and a kids' reading app has no need for high trace volume
    # against the Sentry quota. Prefixed (cyo_adventure_) since this is an
    # internal tuning knob, not an operator-facing name mirrored from
    # another tool the way SENTRY_DSN is.
    # #ASSUME: external resources: sentry_sdk.init clamps an out-of-range
    # sample rate itself; the ge/le bounds below just fail fast on an
    # obviously-wrong config value instead of deferring to that clamp.
    # #VERIFY: tests/unit/test_config.py-style bounds check via Pydantic's
    # own ge/le validation (rejects <0 or >1 at startup).
    sentry_traces_sample_rate: float = Field(
        default=0.1,
        ge=0.0,
        le=1.0,
        validation_alias="CYO_ADVENTURE_SENTRY_TRACES_SAMPLE_RATE",
    )

    # --- Parent Verification Service (KWS, Epic; ADR-018) ---
    # SCOPE, before any of this is read as COPPA compliance. Epic's own
    # documentation states the PV Service "has not been designed to obtain
    # consent from verified parents or guardians or to address direct notice
    # requirements when required by applicable law (such as COPPA)"; it
    # establishes that an adult is an adult. The 16 CFR 312.5 consent leg and
    # the 312.4 direct-notice leg remain ours to build and evidence. Epic's
    # Consent Management Service is the product that combines both, and it is
    # not self-serve. These settings therefore configure an adult-verification
    # signal, not a finished VPC mechanism.
    #
    # Which KWS environment produced a verification. Stored on the verification
    # record and never inferred from kws_api_origin, so a Test verification can
    # never be read back as a real one. Defaults to "test" because the failure
    # modes are asymmetric: mislabelling a real consent as a test is
    # recoverable, and treating a sandbox verification as genuine parental
    # consent is not.
    # #CRITICAL: data integrity: this value is the only thing distinguishing a
    # sandbox verification record from evidence of real parental consent; the
    # KWS API itself reports nothing that identifies which environment answered.
    # #VERIFY: tests/unit/test_config.py::TestKwsSettings::
    # test_kws_environment_defaults_to_test and
    # ::test_production_kws_environment_rejected_from_a_local_app.
    kws_environment: Literal["test", "production"] = Field(
        default="test", validation_alias="KWS_ENVIRONMENT"
    )
    # Which of the Control Panel's environments this is. Up to 5 are allowed
    # (exactly one Production, at least one Test), each with its own label and
    # its own credentials, so kws_environment's type does not identify the
    # source on its own.
    kws_environment_label: str | None = Field(
        default=None, validation_alias="KWS_ENVIRONMENT_LABEL"
    )
    # Tenant and product identifiers. The organization id is constant across
    # environments; the client id and API key are issued per environment. That
    # asymmetry is what makes kws_environment a real partition rather than a
    # label we assert: reaching Production requires pasting a different
    # credential, not flipping this string.
    kws_organization_id: str | None = Field(
        default=None, validation_alias="KWS_ORGANIZATION_ID"
    )
    # Every webhook body carries both orgId and productId. Pin this once a
    # webhook reveals it so an inbound event for another product is rejected
    # rather than attributed to us.
    kws_product_id: str | None = Field(default=None, validation_alias="KWS_PRODUCT_ID")
    # Two DISTINCT hosts. The API origin is the "Service API host URL" from the
    # Integration Information tab; token minting is a Keycloak realm at
    # auth.kidswebservices.com/auth/realms/kws/protocol/openid-connect/token, so
    # a single base URL cannot express both.
    kws_api_origin: str | None = Field(default=None, validation_alias="KWS_API_ORIGIN")
    kws_auth_origin: str = Field(
        default="https://auth.kidswebservices.com",
        validation_alias="KWS_AUTH_ORIGIN",
    )
    # OAuth2 client-credentials pair, sent as HTTP Basic against the token
    # endpoint (client id is the username, API key the password). The Control
    # Panel calls the secret half an API key; it is the client secret.
    # #CRITICAL: security: a KWS API key mints tokens that can trigger
    # verification emails to arbitrary addresses in our organization's name;
    # never log it, which is why it is SecretStr rather than str.
    # #VERIFY: tests/unit/test_config.py::TestKwsSettings::
    # test_partial_kws_credentials_are_rejected.
    kws_client_id: str | None = Field(default=None, validation_alias="KWS_CLIENT_ID")
    kws_api_key: SecretStr | None = Field(default=None, validation_alias="KWS_API_KEY")
    # Sent as the User-Agent on every KWS API call. This is REQUIRED by KWS,
    # not cosmetic: a request with a missing or empty user-agent is rejected
    # with 403 "Request blocked". Defaulted (and constrained non-empty) rather
    # than left None so that failure mode cannot be reached by omission.
    kws_user_agent: str = Field(
        default="cyo-adventure",
        min_length=1,
        validation_alias="KWS_USER_AGENT",
    )
    # Webhook authenticity for the parent-verified event. KWS signs with a
    # Stripe-style scheme: an x-kws-signature header of the form
    # t=<epoch-seconds>,v1=<hex>, where the hex is HMAC-SHA256 over the literal
    # string "{t}.{raw request body}" keyed by this secret. The header may
    # carry MORE THAN ONE v1= component, which is how a secret rotation stays
    # non-breaking, so a verifier must accept a match against any of them.
    #
    # Left independently optional rather than required alongside the API
    # credentials, so token minting can be smoke-tested before a webhook URL
    # exists. Unset does NOT mean "trust unsigned webhooks": the receiver
    # rejects when this is unset, because an unverifiable consent event is
    # worse than a missed one once it becomes our evidence of a consent that
    # may never have happened.
    # #CRITICAL: security: this key is what separates a KWS-signed consent
    # event from one an attacker posted at our webhook URL.
    # #VERIFY: tests/unit/test_config.py::TestKwsSettings::
    # test_kws_secrets_are_secretstr.
    kws_webhook_secret: SecretStr | None = Field(
        default=None, validation_alias="KWS_WEBHOOK_SECRET"
    )
    # The redirect return leg uses a DIFFERENT secret AND a different
    # construction: HMAC-SHA256 over "{status}:{externalPayload}" with NO
    # timestamp, arriving as a signature query parameter. A verifier written
    # for the webhook is wrong here; the two do not share code.
    kws_verification_secret: SecretStr | None = Field(
        default=None, validation_alias="KWS_VERIFICATION_SECRET"
    )
    # Replay window for the signature's t= component, in seconds. KWS puts the
    # timestamp inside the signed string precisely so this can be enforced; a
    # verifier that checks only the MAC leaves a captured webhook replayable
    # forever.
    kws_webhook_max_skew_seconds: int = Field(
        default=300, ge=1, validation_alias="KWS_WEBHOOK_MAX_SKEW_SECONDS"
    )
    # Which verification methods are switched on for this environment, mirrored
    # from the Control Panel's "Verification methods" tab as a comma-separated
    # list, e.g. KWS_ENABLED_METHODS=credit_card,debit_card.
    #
    # This is EVIDENCE, not a preference, and it is the reason the setting
    # exists rather than the Control Panel being read live. The parent-verified
    # webhook's `status` object reports only `verified` and `transactionId`,
    # with no method, so the enabled set at the moment of verification is the
    # only thing that bounds which method could have run. Read live, that bound
    # evaporates the instant anyone toggles a row, retroactively, for every
    # record ever written. Declared here, it can be copied onto each
    # verification record and stays true afterwards.
    #
    # The set also has retroactive reach through AgeGraph: KWS pre-verifies a
    # parent whose hashed email it holds only when they were verified "using a
    # verification method enabled for the current product", so switching a
    # method on silently converts parents verified that way elsewhere into
    # pre-verified for us, with no new verification event on our side.
    #
    # #CRITICAL: data integrity: a record written while this is stale, or while
    # it is empty, carries no bound at all on how its parent was verified, and
    # the vendor cannot supply one after the fact.
    # #VERIFY: tests/unit/test_config.py::TestKwsEnabledMethods::
    # test_configured_kws_requires_declared_methods pins the empty case, and
    # ::test_unknown_method_rejected pins the typo case.
    kws_enabled_methods: Annotated[list[KwsVerificationMethod], NoDecode] = Field(
        default_factory=list, validation_alias="KWS_ENABLED_METHODS"
    )
    # Whether a verification from the Test environment counts as evidence for
    # the child-profile gates below. Staging runs the whole flow end to end
    # against KWS Test, so somewhere has to be allowed to rely on a Test row;
    # this setting is that permission, made explicit and per-tier.
    #
    # #CRITICAL: security: the default is False, and it is False rather than
    # True because of which mistake each default produces. Defaulted True, a
    # tier that simply never sets the variable would quietly accept sandbox
    # verifications as parental consent, and nothing in the record would show
    # it later. Defaulted False, the same omission makes staging refuse to
    # create profiles, which is loud, immediate, and harmless.
    # #VERIFY: tests/unit/test_config.py::TestKwsEvidenceSettings::
    # test_test_evidence_is_refused_by_default.
    kws_accept_test_evidence: bool = Field(
        default=False, validation_alias="KWS_ACCEPT_TEST_EVIDENCE"
    )
    # Whether the child-profile gates additionally require a usable
    # verification, on top of the existing consent record.
    #
    # Defaults False so the gate can land ahead of the flow that satisfies it:
    # switched on before guardians have any way to verify, it locks every
    # existing account out of profile creation. Turning it on is therefore a
    # deliberate per-tier act, taken once the start endpoint and its screens
    # are deployed on that tier.
    # #ASSUME: security: an operator who sets this True on a tier where KWS is
    # not configured gets a hard stop on profile creation rather than a
    # bypass. That is the intended direction of the failure.
    # #VERIFY: tests/unit/test_config.py::TestKwsEvidenceSettings::
    # test_verification_is_not_required_by_default.
    kws_verification_required: bool = Field(
        default=False, validation_alias="KWS_VERIFICATION_REQUIRED"
    )
    # Whether POST /v1/consent/kws/start may run while the flag above is off.
    #
    # This exists for exactly one job: exercising the ENDPOINT and the
    # guardian screens in front of it on staging while the gate is still off,
    # which is how the flow is proven before it becomes a control. Note what
    # it is NOT for: the Gate 1 procedure in docs/operations/kws-test-runbook.md
    # runs scripts/kws_send_test_verification.py, which calls
    # start_parent_verification directly and never reaches the endpoint, so
    # that procedure needs nothing from this setting. What the script cannot
    # exercise is the endpoint's own surface: its authorization allowlist, its
    # two anti-automation limits, and the screens that consume its answers.
    #
    # Deliberately a SEPARATE setting rather than a wider reading of
    # kws_configured. Credential presence is a fact about the deployment;
    # "this tier is allowed to email real people about a flow that gates
    # nothing" is a decision, and the two must be separately auditable.
    #
    # #CRITICAL: security: the start endpoint discloses an adult's email
    # address to Epic (ADR-018 D1, O-125), so its control has to be the same
    # flag the ADR names, not the incidental presence of credentials. This
    # escape hatch is refused outright against Production KWS
    # (_reject_start_override_against_production_kws), so widening the
    # endpoint can never be something a copied staging env file does.
    # #VERIFY: tests/unit/test_config.py::TestKwsStartOverride::
    # test_the_start_override_is_refused_against_production_kws.
    kws_allow_start_while_not_required: bool = Field(
        default=False, validation_alias="KWS_ALLOW_START_WHILE_NOT_REQUIRED"
    )
    # How long an unresolved attempt blocks a fresh send for the same adult.
    #
    # This is the double-click and retry-loop guard, and its size is a
    # trade-off between two real parents: one who clicked twice and must not
    # receive two emails, and one whose email went to spam and needs to try
    # again without contacting support. Minutes rather than hours because the
    # second parent has no other recovery path, and the hourly cap below is
    # what actually bounds the volume.
    #
    # #ASSUME: external resources: KWS applies its own limit of ten sends per
    # hour per email address, so this window and the cap below must stay well
    # under it; a vendor-side 429 is NOT retried (consent/kws_client.py) and
    # reaches the parent as a failed attempt.
    # #VERIFY: tests/unit/test_config.py::TestKwsStartLimits::
    # test_the_open_attempt_window_and_hourly_cap_have_conservative_defaults.
    kws_open_attempt_minutes: int = Field(
        default=15, ge=1, validation_alias="KWS_OPEN_ATTEMPT_MINUTES"
    )
    # How many attempts one adult may start in a rolling hour.
    #
    # #CRITICAL: security: this is the anti-automation bound on an endpoint
    # that causes an outbound email, and it is enforced per ACCOUNT rather
    # than per IP because the middleware limiter (60/min/IP) is orders of
    # magnitude too loose to protect a mailbox and cannot see who is calling.
    # The counter is the kws_verification table itself: rows are inserted
    # before the send and never deleted, so the count is exact, shared by
    # every replica, and survives a restart, none of which is true of an
    # in-process counter.
    # #VERIFY: tests/integration/test_consent_api.py::
    # test_start_refuses_once_the_hourly_cap_is_reached.
    kws_start_max_attempts_per_hour: int = Field(
        default=3, ge=1, validation_alias="KWS_START_MAX_ATTEMPTS_PER_HOUR"
    )

    @field_validator(
        "kws_environment",
        "kws_auth_origin",
        "kws_user_agent",
        "kws_webhook_max_skew_seconds",
        "kws_open_attempt_minutes",
        "kws_start_max_attempts_per_hour",
        "kws_accept_test_evidence",
        "kws_verification_required",
        "kws_allow_start_while_not_required",
        "kws_environment_label",
        "kws_organization_id",
        "kws_product_id",
        "kws_api_origin",
        "kws_client_id",
        mode="before",
    )
    @classmethod
    def _empty_kws_override_means_unset(
        cls, value: object, info: ValidationInfo
    ) -> object:
        """Treat an empty override as absence, not as a value.

        #CRITICAL: external resources: the house compose idiom for an optional
        variable is ``${VAR:-}``, which injects ``""`` rather than leaving the
        variable unset. That one idiom produces TWO different failures here,
        and only the loud one was covered when this validator was written.

        The loud one: the constrained and enumerated fields
        (``kws_user_agent``'s ``min_length=1``, the three ``ge=1`` ints,
        ``kws_environment``'s ``Literal``, and the two ``bool``s) reject ``""``
        outright, so it is a hard ``ValidationError`` at ``Settings()``
        construction and the CONTAINER DOES NOT BOOT.

        The quiet one is worse, and cost a KWS Test delivery on 2026-08-10 to
        find. The identifier fields default to ``None`` to mean "not pinned
        yet", and their consumers test that with ``is None``. An empty string
        is not ``None``, so the escape hatch closes and the field becomes a
        value that can never match: ``api/kws_webhook.py::_product_matches``
        compared ``event.product_id == ""``, answered False, and the receiver
        ignored a correctly signed, freshly delivered ``parent-verified``
        event with ``200 handled=False``. Nothing raised, nothing retried, and
        the verification row stayed at ``sent`` forever. A guard whose "off"
        position is unreachable is worse than no guard, because it reads as
        protection in the code and as silence in the logs.

        The list must cover EVERY field in the KWS block, and it is easy to
        add a field and forget this decorator: the two rate-limit ints and the
        two booleans were all added later and all missed it, invisibly,
        because reaching the failure needs a compose file that passes
        ``${KWS_OPEN_ATTEMPT_MINUTES:-}`` and no tier does yet.
        ``test_every_kws_setting_tolerates_an_empty_override`` enumerates the
        block instead of pinning a list, so the next omission fails a test
        rather than a deploy.

        Exactly two exclusions, both deliberate:

        * ``kws_api_key``, ``kws_webhook_secret`` and ``kws_verification_secret``
          are ``SecretStr`` credentials that already treat ``""`` as missing
          (``_kws_credential_state`` for the first, the signature verifiers for
          the other two), so normalising them would only move the check.
        * ``kws_enabled_methods`` is left to fail loudly. It is evidence rather
          than configuration: the parent-verified webhook reports no method, so
          the declared set at send time is the only bound on which method could
          have run. Silently defaulting an empty override would mint rows whose
          evidence field is a guess, and refusal to boot IS the control.
        #VERIFY: tests/unit/test_config.py::TestKwsSettings::
        test_empty_kws_user_agent_falls_back_to_the_default,
        ::test_empty_kws_skew_seconds_falls_back_to_the_default,
        ::test_empty_kws_identifier_is_unset_not_a_value and
        ::test_every_kws_setting_tolerates_an_empty_override, which
        enumerates the block rather than pinning a fixed list.

        Args:
            value: The raw field input.
            info: The field being validated, used to find its default.

        Returns:
            object: The field's default when the input is an empty or
                whitespace-only string, otherwise the input unchanged.
        """
        # info.field_name is Optional in pydantic's signature but is always set
        # for a field validator; the guard keeps the fallback from becoming a
        # KeyError if that ever stops holding, in which case the constrained
        # field rejects the empty string exactly as it did before.
        if isinstance(value, str) and not value.strip() and info.field_name:
            return cls.model_fields[info.field_name].get_default()
        return value

    @field_validator("kws_enabled_methods", mode="before")
    @classmethod
    def _split_kws_enabled_methods(cls, value: object) -> object:
        """Accept a comma-separated env value instead of a JSON array.

        ``NoDecode`` on the field suppresses pydantic-settings' default JSON
        decoding of complex types, which would otherwise force operators to
        write ``KWS_ENABLED_METHODS='["credit_card"]'``. The names being
        mirrored come from a Control Panel screen, so the transcription should
        be as close to what is on that screen as possible; a JSON array is one
        more place for a stray quote to turn a compliance-relevant declaration
        into a startup failure at best.

        Args:
            value: The raw field input, a string when it came from the
                environment and a list when constructed programmatically.

        Returns:
            object: A list of trimmed names for the string case, otherwise the
                input unchanged for Pydantic to validate as usual.
        """
        if isinstance(value, str):
            return [part.strip() for part in value.split(",") if part.strip()]
        return value

    @field_validator("kws_enabled_methods")
    @classmethod
    def _canonicalize_kws_enabled_methods(
        cls, methods: list[KwsVerificationMethod]
    ) -> list[KwsVerificationMethod]:
        """Dedupe and sort, so the declaration has one canonical form.

        This value is copied onto verification records and compared across
        them. Without canonicalisation, ``credit_card,debit_card`` and
        ``debit_card,credit_card`` would be two different declarations of the
        same fact, and a diff between two records would show a change where
        none happened.

        Args:
            methods: The validated method names.

        Returns:
            list[KwsVerificationMethod]: The same names, deduped and sorted.
        """
        return sorted(set(methods))

    # --- ADR-028 UW-A47: bound the run_gate worker-thread hold ---
    # How many concurrent api/gate_limits.py::gate_limiter() holders may
    # occupy an AnyIO worker thread at once. AnyIO's default worker pool is
    # process-wide and shared by every run_sync caller (40 threads by
    # default); a character-enabled book's run_gate call holds one of those
    # threads for as long as 49.58s (see the #CRITICAL markers in
    # api/node_edit.py and api/generation.py), and that figure is unchanged
    # by this setting: it bounds concurrency, not per-call duration.
    # 4 is a judgment call, not a measurement: it leaves 36 of the 40 pool
    # threads free for every other run_sync caller in the process (including
    # the generation worker's own gate runs) while still letting more than
    # one guardian save an edit at the same time.
    #
    # The AnyIO thread pool is not the tightest constraint, though: both
    # call sites hold a checked-out AsyncSession (a DB connection) for the
    # entire offloaded call, and database_pool_size + database_max_overflow
    # defaults to 15 (5 + 10), smaller than the 40-thread pool this Field's
    # le=39 alone guards against. The real ceiling is therefore the smaller
    # of the two pools; today that is the connection pool. le=39 stays as
    # the static, thread-pool-relative bound; the tighter, database-relative
    # bound is enforced by _require_gate_concurrency_within_connection_pool
    # below, as a model_validator rather than a second literal here, because
    # database_pool_size/database_max_overflow are themselves configurable
    # per environment and a hardcoded number would drift from them silently.
    # #CRITICAL: concurrency: set this at or above 40 (the AnyIO default
    # pool size) and it bounds nothing against the thread pool, because the
    # limiter would no longer be smaller than the pool it is meant to
    # protect; set it at or above database_pool_size + database_max_overflow
    # and it bounds nothing against the connection pool instead, which binds
    # first at the current defaults (15 versus 40).
    # #VERIFY: tests/unit/test_gate_capacity_limiter.py::test_the_gate_limiter_is_smaller_than_the_anyio_default_pool,
    # ::test_the_gate_limiter_is_smaller_than_the_database_connection_pool,
    # ::test_gate_max_concurrency_at_the_connection_pool_ceiling_rejected.
    gate_max_concurrency: int = Field(default=4, ge=1, le=39)

    # --- ADR-030: the engagement-correlation analysis job ---
    #
    # The kill switch. Off, the job does not read the database, does not
    # compute, and does not write; it is not a mode that produces a redacted
    # artifact, because a redaction path that only runs when the flag is off is
    # a path nobody exercises. ADR-030 is `proposed` and not yet ratified, so
    # this shipping inert is the mitigation the owner's assumed-approval ruling
    # depends on: turning it on is a deliberate per-tier act taken after
    # ratification.
    # #CRITICAL: security: default False. On, the job aggregates real children's
    # reading outcomes into a file on disk.
    # #VERIFY: tests/unit/test_config.py::TestEngagementCorrelationAnalysis::
    # test_the_engagement_analysis_is_off_by_default.
    analysis_engagement_correlation_enabled: bool = Field(
        default=False, validation_alias="ANALYSIS_ENGAGEMENT_CORRELATION_ENABLED"
    )
    # Where the artifact is written. No default, deliberately: ADR-030 Decision
    # 6 gives this artifact no in-repository default path, and a job with no
    # configured destination does not run.
    #
    # Typed as ``str`` and not ``Path`` so that an empty value stays
    # representable and is treated as unset by the validator below.
    # ``${VAR:-}`` in a compose file yields an empty string rather than an
    # absent variable, a shape this project has already been bitten by on
    # constrained settings fields.
    # #VERIFY: tests/unit/test_config.py::TestEngagementCorrelationAnalysis::
    # test_an_empty_output_path_counts_as_unset_and_is_refused.
    analysis_engagement_correlation_output_dir: str = Field(
        default="",
        validation_alias="ANALYSIS_ENGAGEMENT_CORRELATION_OUTPUT_DIR",
    )

    @field_validator("analysis_engagement_correlation_enabled", mode="before")
    @classmethod
    def _empty_engagement_flag_is_off(cls, value: object) -> object:
        """Read an empty override of the kill switch as "off", not as an error.

        ``${ANALYSIS_ENGAGEMENT_CORRELATION_ENABLED:-}`` in a compose file
        yields ``""`` rather than an absent variable, and a bare ``bool`` field
        rejects ``""`` outright, so the container would not boot. The whole
        service failing to start is not the right answer to an unset flag on an
        analysis job that is off by default; folding an empty value to the
        default is, and the default is the safe arm.

        Args:
            value: The raw environment value.

        Returns:
            object: ``False`` for an empty or whitespace-only string, otherwise
                the input unchanged.
        """
        if isinstance(value, str) and not value.strip():
            return False
        return value

    @property
    def worker_database_url_effective(self) -> str:
        """The DSN the worker engine (core/database.py::get_worker_engine) actually uses.

        Both an unset ``worker_database_url`` (``None``) and an explicitly
        empty string fall back to ``database_url``. The empty-string case
        matters because compose interpolation of an unset variable
        (``${WORKER_DATABASE_URL:-}``) injects ``""`` rather than leaving the
        variable unset entirely; treating ``""`` as "no DSN configured" (not
        as a configured-but-empty DSN) is what keeps that interpolation safe
        (ADR-021).

        Returns:
            str: ``worker_database_url`` when it is a non-empty string,
                otherwise ``database_url``.
        """
        return self.worker_database_url or self.database_url

    @property
    def modal_leg_configured(self) -> bool:
        """Whether the Modal endpoint is configured well enough to build a leg.

        ``build_modal_leg`` raises :class:`ConfigurationError` when either the
        base url or the model is absent. Since the Ollama retirement the Modal
        leg is part of the default ``openrouter`` cascade, so that raise would
        turn every unconfigured environment (local dev, CI, any deploy that has
        not stood up a Modal Auto Endpoint) into a hard generation failure.
        This predicate lets ``build_provider`` include the leg only when it can
        actually be built, and degrade to the two OpenRouter legs otherwise.

        Only the url and model are checked, matching exactly what
        ``build_modal_leg`` requires. The proxy credential pair is deliberately
        excluded: an endpoint with no proxy auth is a valid configuration, and
        a half-set pair stays a hard :class:`ConfigurationError` rather than
        being silently downgraded to "leg absent".

        Whitespace-only values count as absent. A compose interpolation of an
        unset variable (``${MODAL_MODEL:- }``) or a stray space in a dotenv
        entry would otherwise read as truthy here and put a leg with no usable
        model into the cascade, which then fails on every call rather than
        being cleanly omitted.

        Returns:
            bool: True when both ``modal_base_url`` and ``modal_model`` hold a
                non-empty, non-whitespace value.
        """
        return bool((self.modal_base_url or "").strip()) and bool(
            (self.modal_model or "").strip()
        )

    @model_validator(mode="after")
    def _reject_dev_database_url_outside_local(self) -> Settings:
        """Fail fast if the dev default DSN leaks into a non-local environment.

        Raises:
            ConfigurationError: when ``environment`` is not ``local`` but
                ``database_url`` is still the credential-free dev default DSN,
                which means ``CYO_ADVENTURE_DATABASE_URL`` was not provided.
        """
        if self.environment != "local" and self.database_url == _DEV_DATABASE_URL:
            msg = (
                "CYO_ADVENTURE_DATABASE_URL (or the unprefixed DATABASE_URL) must "
                "be set in non-local environments; refusing to start in "
                f"'{self.environment}' with the development default localhost "
                "database URL."
            )
            raise ConfigurationError(msg)
        return self

    @model_validator(mode="after")
    def _require_prepared_cache_disabled_for_pooler_dsn(self) -> Settings:
        """Fail fast when a database DSN is Supavisor's pooler port but the flag is off.

        Checks BOTH ``database_url`` (the API engine) and
        ``worker_database_url_effective`` (the worker engine, ADR-021): a
        worker DSN on Supavisor's transaction-pooler port has the identical
        prepared-statement collision failure mode as the API DSN, and
        ``core/database.py::_create_engine`` builds both engines from the
        same ``database_disable_prepared_cache`` flag, so a mismatch on
        either DSN is equally fatal. Only catches the documented Supabase
        Supavisor case (port 6543); a PgBouncer transaction-mode DSN has no
        distinguishing port and cannot be detected from the URL alone, so
        this is a defense against the one foreseeable, greppable mistake,
        not a complete guarantee.

        Raises:
            ConfigurationError: when either DSN's port is the Supavisor
                transaction-pooler port and database_disable_prepared_cache
                is False, since asyncpg then collides on cached/fixed-name
                prepared statements once the pooler reassigns a backend
                mid-session (see the #CRITICAL note on database_disable_prepared_cache).
        """
        _check_pooler_port_requires_disabled_cache(
            label="CYO_ADVENTURE_DATABASE_URL",
            url=self.database_url,
            disable_prepared_cache=self.database_disable_prepared_cache,
        )
        _check_pooler_port_requires_disabled_cache(
            label="CYO_ADVENTURE_WORKER_DATABASE_URL",
            url=self.worker_database_url_effective,
            disable_prepared_cache=self.database_disable_prepared_cache,
        )
        return self

    @model_validator(mode="after")
    def _require_oidc_config_outside_local(self) -> Settings:
        """Fail fast if OIDC verification config is missing outside local.

        PROJECT-PLAN P6-02: mirrors _reject_dev_database_url_outside_local.
        Outside "local" the dev auth stub is not a valid fallback (api/deps.py
        only trusts it when environment == "local"), so a non-local process
        with no oidc_issuer/oidc_jwks_url would have no way to authenticate
        any request; refuse to start rather than serve 401s to everything.

        Raises:
            ConfigurationError: when ``environment`` is not ``local`` and
                either ``oidc_issuer`` or ``oidc_jwks_url`` is unset.
        """
        if self.environment != "local" and not (
            self.oidc_issuer and self.oidc_jwks_url
        ):
            msg = (
                "OIDC_ISSUER and OIDC_JWKS_URL must both be set in non-local "
                f"environments; refusing to start in '{self.environment}' with no "
                "way to verify a bearer token (ADR-009)."
            )
            raise ConfigurationError(msg)
        return self

    @model_validator(mode="after")
    def _require_child_session_secret_outside_local(self) -> Settings:
        """Fail fast on a missing or weak child-session signing secret outside local.

        Mirrors _require_oidc_config_outside_local (G1 / P6-04): outside "local"
        the kid surface authenticates with backend-signed child JWTs, which can
        neither be minted nor verified without this secret, so a non-local
        process with no secret could not authenticate any child session; refuse
        to start rather than silently disable the kid surface.

        Presence alone is not enough. An empty SecretStr("") passes a plain
        ``is None`` check but makes ``jwt.encode`` raise InvalidKeyError, 500ing
        every mint (a kid-surface outage). A short or placeholder secret is worse:
        it signs real, forgeable child tokens with a weak HMAC key. PyJWT's
        InsecureKeyLengthWarning only errors under pytest ``filterwarnings``, not
        at runtime, so this validator is the only thing that stops a
        ``CHILD_SESSION_SECRET=REPLACE_ME`` (shipped in .env.staging.example)
        from reaching production. HS256 keys shorter than the 32-byte hash output
        are the ones PyJWT flags, so 32 bytes is the floor.

        #CRITICAL: security: rejecting weak/placeholder keys here is the child-
        session forgery boundary; a short HMAC key lets an attacker mint valid
        child tokens for any profile.
        #VERIFY: the error message never echoes the secret value; test_config
        rejects empty, whitespace, sub-32-byte, and placeholder secrets.

        Raises:
            ConfigurationError: when ``environment`` is not ``local`` and
                ``child_session_secret`` is unset, empty, shorter than 32 bytes,
                or a known placeholder.
        """
        if self.environment == "local":
            return self

        _require_strong_token_secret(
            self.child_session_secret,
            _TokenSecretSpec(
                env_var="CHILD_SESSION_SECRET",
                purpose="child session tokens",
                ref="G1 / P6-04",
            ),
            self.environment,
        )
        return self

    @model_validator(mode="after")
    def _require_device_grant_secret_outside_local(self) -> Settings:
        """Fail fast on a missing or weak device-grant signing secret outside local.

        Mirrors ``_require_child_session_secret_outside_local`` (ADR-014
        phase 1): outside "local" a device grant can neither be minted nor
        verified without this secret, so a non-local process with no secret
        could not authorize any device; refuse to start rather than silently
        disable device authorization.

        The same weak/placeholder-secret reasoning applies as for
        ``child_session_secret``: an empty ``SecretStr("")`` passes a plain
        ``is None`` check but makes ``jwt.encode`` raise ``InvalidKeyError``,
        500ing every mint, and a short or placeholder secret signs real,
        forgeable device grants with a weak HMAC key.

        #CRITICAL: security: rejecting weak/placeholder keys here is the
        device-grant forgery boundary; a short HMAC key lets an attacker mint
        a valid device grant for any family.
        #VERIFY: the error message never echoes the secret value; test_config
        rejects empty, whitespace, sub-32-byte, and placeholder secrets.

        Raises:
            ConfigurationError: when ``environment`` is not ``local`` and
                ``device_grant_secret`` is unset, empty, shorter than 32
                bytes, or a known placeholder.
        """
        if self.environment == "local":
            return self

        _require_strong_token_secret(
            self.device_grant_secret,
            _TokenSecretSpec(
                env_var="DEVICE_GRANT_SECRET",
                purpose="device grant tokens",
                ref="ADR-014",
            ),
            self.environment,
        )
        return self

    @model_validator(mode="after")
    def _require_distinct_token_families(self) -> Settings:
        """Assert the three token families stay separable (issue #251).

        The guardian OIDC, child-session, and device-grant branches are kept
        non-interchangeable by two invariants that were previously only
        conventions:

        1. The three ``aud`` values are pairwise distinct, so a token minted for
           one branch can never satisfy another branch's audience check. The
           child/device values come from the central ``TokenAudience`` registry
           (distinct by construction); the guardian value is the configurable
           ``oidc_audience``, so the real risk is an operator setting
           ``OIDC_AUDIENCE`` to one of the backend values and collapsing the
           separation.
        2. The child-session and device-grant secrets differ. Both branches pin
           HS256; a shared secret would let a token minted for one verify in the
           other once audiences ever aligned, so distinct keys are the
           load-bearing separation and a copy-paste of one secret into both is a
           real misconfiguration.

        Runs in every environment (not just non-local): an audience collision or
        duplicated secret is a bug regardless of stage, and both checks are pure
        comparisons with no secret value ever placed in the message.

        #CRITICAL: security: this is the token-family separation invariant;
        collapsing audiences or sharing the HS256 secret defeats the
        cross-branch confusion defense.
        #VERIFY: test_config asserts a colliding OIDC_AUDIENCE and an identical
        child/device secret are both rejected.

        Raises:
            ConfigurationError: when ``oidc_audience`` collides with a backend
                token audience, or the child-session and device-grant secrets
                are identical.
        """
        backend_audiences = (
            TokenAudience.CHILD_SESSION.value,
            TokenAudience.DEVICE_GRANT.value,
        )
        # The two backend audiences must themselves be distinct, not just
        # distinct from oidc_audience: if the TokenAudience members were ever
        # edited to share a literal they would collapse to one, and checking
        # only `oidc_audience in backend_audiences` would still pass while the
        # child/device separation was silently gone. Assert it directly so the
        # "three pairwise-distinct audiences" invariant this validator documents
        # actually holds end to end (issue #251).
        if len(set(backend_audiences)) != len(backend_audiences):
            msg = (
                "The backend token audiences (child-session, device-grant) must "
                "be pairwise distinct; a shared value collapses the child/device "
                "audience separation (issue #251)."
            )
            raise ConfigurationError(msg)
        if self.oidc_audience in backend_audiences:
            msg = (
                "OIDC_AUDIENCE must be distinct from the backend token "
                "audiences (cyo-child-session, cyo-device-grant); a collision "
                "would let a guardian token satisfy a child/device audience "
                "check (issue #251)."
            )
            raise ConfigurationError(msg)

        child = self.child_session_secret
        device = self.device_grant_secret
        if (
            child is not None
            and device is not None
            and child.get_secret_value() == device.get_secret_value()
        ):
            msg = (
                "CHILD_SESSION_SECRET and DEVICE_GRANT_SECRET must be distinct: "
                "both branches sign HS256, so a shared key removes the "
                "cross-family signature separation (issue #251)."
            )
            raise ConfigurationError(msg)
        return self

    @model_validator(mode="after")
    def _require_explicit_environment_when_deployed(self) -> Settings:
        """Fail fast when ENVIRONMENT is unset but deployment markers are present.

        ``environment`` defaults to ``"local"``, and every ``_require_*_outside_local``
        guard above (plus the rate-limiter gate in ``app.py``) treats ``"local"``
        as "relax the production control": the dev auth stub is trusted
        (api/deps.py trusts the bearer string as its subject only when
        ``environment == "local"``) and the in-memory rate limiter is disabled.
        A deployed tier that forgets to set ENVIRONMENT therefore does not fail;
        it silently boots with those safeguards off. The other guards cannot
        catch this because they short-circuit on ``environment == "local"``,
        including a *defaulted* local.

        Detect the fail-open case directly: if ENVIRONMENT was never explicitly
        provided (absent from ``model_fields_set``) yet OIDC verification config
        is present, the process is a real deployment silently defaulting to
        "local". OIDC config is the safe marker: local dev, CI, and the
        integration/e2e suites never set it, so there is no false-positive
        surface, while every deployed tier must set it (see
        ``_require_oidc_config_outside_local``). An operator who genuinely wants
        a local process still sets nothing and is unaffected; one who explicitly
        sets ``ENVIRONMENT=local`` is honoured (the field is then in
        ``model_fields_set``), since that is a deliberate choice, not a silent
        default.

        #CRITICAL: security: a deployment defaulting to "local" trusts the dev
        auth stub and disables the rate limiter; refusing to boot converts that
        silent fail-open into a startup error.
        #VERIFY: tests/unit/test_config.py::TestExplicitEnvironmentWhenDeployed
        covers the raise, the explicit-local pass, and the local-dev pass.

        Raises:
            ConfigurationError: when ENVIRONMENT was not explicitly set but
                ``oidc_issuer`` or ``oidc_jwks_url`` is configured, which marks a
                real deployment silently defaulting to ``"local"``.
        """
        if "environment" not in self.model_fields_set and (
            self.oidc_issuer or self.oidc_jwks_url
        ):
            msg = (
                "ENVIRONMENT is unset but OIDC verification config is present, so "
                "the process is a deployment silently defaulting to 'local' (dev "
                "auth stub trusted, in-memory rate limiter disabled). Set "
                "ENVIRONMENT explicitly to 'dev', 'staging', or 'production'; "
                "refusing to start."
            )
            raise ConfigurationError(msg)
        return self

    @model_validator(mode="after")
    def _require_classifier_when_reviewing(self) -> Settings:
        """Require a live Stage-0 classifier whenever real review runs.

        When ``review_provider`` is not ``"mock"`` the moderation pipeline makes
        real LLM calls over children's content; it must be preceded by at least
        one deterministic classifier. Mirrors ``_reject_dev_database_url_outside_local``:
        a posture invariant enforced conditionally, not blanket.

        ``PERSPECTIVE_API_KEY`` deliberately does not satisfy this check.
        Google is sunsetting Perspective on 2026-12-31 with no migration path,
        after which the key still parses and still passes any presence test
        while the API itself returns nothing. OpenAI Moderation is therefore
        the only classifier whose configuration is evidence of a working
        pre-filter. Perspective itself was retired as a Stage-0 signal source
        on 2026-08-25 (ratified sunset): ``classifiers.py`` no longer calls
        it at all, so a present ``PERSPECTIVE_API_KEY`` is inert configuration
        rather than an optional second opinion.

        Raises:
            ConfigurationError: when review runs without ``OPENAI_API_KEY``.
        """
        # #CRITICAL: security: no real review of children's content without a
        # deterministic pre-filter. Counting a sunset provider here would make
        # this invariant pass vacuously the day Perspective goes dark, running a
        # live reviewer over children's prose with zero classifiers in front of
        # it and no configuration change to signal the regression.
        # #VERIFY: test_non_mock_review_without_any_classifier_key_raises,
        # test_non_mock_review_with_only_perspective_key_raises.
        if self.review_provider != "mock" and not self.openai_api_key:
            msg = (
                "OPENAI_API_KEY must be set when review_provider is "
                f"'{self.review_provider}'. PERSPECTIVE_API_KEY no longer "
                "satisfies this requirement: Perspective sunsets 2026-12-31 "
                "and a set key is not evidence of a working classifier."
            )
            raise ConfigurationError(msg)
        return self

    @model_validator(mode="after")
    def _require_real_reviewer_outside_local(self) -> Settings:
        """Refuse a mock moderation reviewer outside ``environment="local"``.

        Mirrors ``_require_classifier_when_reviewing``: a posture invariant
        enforced conditionally, not blanket. The mock reviewer (Stage 1-4
        LLM review) runs no real safety judgment at all; a deployed process
        booting with it would persist moderation reports that read as
        reviewed but never were (gap G1, design doc section 2.4). Set
        ``CYO_ADVENTURE_ALLOW_MOCK_REVIEW=1`` for the narrow legitimate case
        (catalog seeding, local-parity smoke runs against a non-local
        database). Setting it changes what may boot, not how the resulting
        report is labelled: ``moderation/pipeline.py`` stamps every report
        the mock produces as non-independent plus a structural advisory
        finding whenever ``review_provider == "mock"``, in local too and
        with or without this flag, so such a report is never mistaken for
        real review.

        Raises:
            ConfigurationError: when ``review_provider == "mock"``,
                ``environment != "local"``, and ``allow_mock_review`` is False.
        """
        # #CRITICAL: security: no unreviewed children's content persisted as
        # a real moderation report outside local dev, without an explicit,
        # self-documenting opt-in.
        # #VERIFY: tests/unit/test_config.py::
        # TestValidatorRequireRealReviewerOutsideLocal::
        # test_non_local_environment_with_mock_review_without_hatch_raises and
        # ::test_non_local_environment_with_mock_review_and_hatch_boots.
        if (
            self.review_provider == "mock"
            and self.environment != "local"
            and not self.allow_mock_review
        ):
            msg = (
                "review_provider is 'mock' but environment is "
                f"'{self.environment}', not 'local'. The mock reviewer runs no "
                "real safety review; set CYO_ADVENTURE_ALLOW_MOCK_REVIEW=1 if "
                "this is an intentional non-evidence run (for example catalog "
                "seeding). Note that the flag only permits the boot: every "
                "report the mock produces is stamped "
                "reviewer_independent=false with a structural advisory "
                "finding regardless of it, in local too."
            )
            raise ConfigurationError(msg)
        return self

    @model_validator(mode="after")
    def _require_modal_proxy_credentials_together(self) -> Settings:
        """Fail fast on a half-set Modal proxy credential pair.

        ``build_modal_leg`` already rejects a half-set
        ``MODAL_PROXY_KEY``/``MODAL_PROXY_SECRET`` pair, and while Modal was an
        offline-only leg that raise was well contained: it fired only when an
        operator explicitly selected ``generation_provider=modal``.

        # #CRITICAL: external-resources: the Ollama retirement made Modal the
        # third leg of the DEFAULT openrouter cascade, which widens that raise's
        # blast radius from "explicit Modal runs" to "all story generation" -- a
        # deployment with a base url, a model, and one half of the proxy pair
        # would build its cascade straight into a ConfigurationError on every
        # job. Checking it here converts that runtime failure into a startup
        # failure, so the misconfiguration is caught before the deploy is
        # serving rather than on the first generation request.
        # #VERIFY: tests/unit/test_config.py::TestModalProxyCredentialPairing
        # pins both half-set directions as rejected and both complete states
        # (neither set, both set) as accepted.

        Deliberately NOT folded into ``modal_leg_configured``: that predicate
        answers "can a leg be built at all", and treating a half-set credential
        as "no leg" would silently drop the backstop for what is really an
        operator typo. This stays a hard error, just an earlier one.

        Returns:
            Settings: ``self``, unchanged, when the pair is coherent.

        Raises:
            ConfigurationError: When exactly one of the two is set.
        """
        has_key = bool(self.modal_proxy_key)
        has_secret = bool(self.modal_proxy_secret)
        if has_key != has_secret:
            present = "MODAL_PROXY_KEY" if has_key else "MODAL_PROXY_SECRET"
            missing = "MODAL_PROXY_SECRET" if has_key else "MODAL_PROXY_KEY"
            msg = (
                f"{present} is set but {missing} is not; Modal proxy auth needs "
                "both or neither. Since the Ollama retirement the Modal leg is "
                "part of the default generation cascade, so a half-set pair "
                "would fail every generation job, not just an explicit Modal run."
            )
            raise ConfigurationError(msg)
        return self

    @model_validator(mode="after")
    def _require_gate_concurrency_within_connection_pool(self) -> Settings:
        """Fail fast if gate_max_concurrency could exhaust the DB connection pool.

        ``gate_max_concurrency``'s ``le=39`` Field bound only checks it against
        AnyIO's 40-thread worker pool, the mechanism ``api/gate_limits.py`` was
        originally written to protect. But both ``run_gate`` call sites
        (``api/node_edit.py::edit_node``, ``api/generation.py::validate_version``)
        hold a checked-out ``AsyncSession`` (and therefore a DB connection) for
        the entire ``run_sync(run_gate, ...)`` call, not just an AnyIO thread. A
        checked-out connection is capped at ``database_pool_size +
        database_max_overflow`` (15 by default: 5 + 10), which is smaller than
        the 39 the thread-bound check alone would allow. A burst of concurrent
        gate calls sized to the thread pool, not the connection pool, exhausts
        every connection in the process and starves every other route, not just
        these two, well before the thread pool the limiter was built for is
        ever threatened.

        This is a cross-field check (not a second ``le=`` on the Field itself)
        because the real ceiling is derived from ``database_pool_size`` and
        ``database_max_overflow``, both of which are themselves configurable
        per environment; a hardcoded literal here would silently stop matching
        the real pool the moment either of those changes. The strict ``<``
        (not ``<=``) leaves at least one connection free for every other
        concurrent request in the process while every gate slot is in use,
        mirroring the existing thread-pool reasoning ("leaves 36 of the 40 pool
        threads free").

        Raises:
            ConfigurationError: when ``gate_max_concurrency`` is not strictly
                smaller than ``database_pool_size + database_max_overflow``.
        """
        # #CRITICAL: concurrency: a limiter sized to the AnyIO thread pool
        # alone is not sufficient, because both gate call sites hold a DB
        # session across the offloaded call; the binding constraint is
        # whichever of the two pools (threads, connections) is smaller, and
        # today that is the connection pool (15) versus the thread pool (40).
        # #VERIFY: tests/unit/test_gate_capacity_limiter.py::
        # test_the_gate_limiter_is_smaller_than_the_database_connection_pool,
        # ::test_gate_max_concurrency_at_the_connection_pool_ceiling_rejected.
        total_db_connections = self.database_pool_size + self.database_max_overflow
        if self.gate_max_concurrency >= total_db_connections:
            msg = (
                f"gate_max_concurrency ({self.gate_max_concurrency}) must be "
                "strictly smaller than database_pool_size + "
                f"database_max_overflow ({total_db_connections}); both "
                "api/node_edit.py and api/generation.py hold a checked-out DB "
                "session for the entire run_gate call, so a limiter sized "
                "only against the AnyIO thread pool can still exhaust the "
                "connection pool and starve every other route in the process."
            )
            raise ConfigurationError(msg)
        return self

    def _kws_credential_state(self) -> tuple[tuple[str, ...], tuple[str, ...]]:
        """Split the KWS API-call credentials into those provided and those missing.

        Four values are needed before any KWS API call can be made: the tenant
        id, the service host, and the client-credentials pair. An empty string
        counts as missing, not as a configured-but-empty value, because compose
        interpolation of an unset variable (``${KWS_API_KEY:-}``) injects ``""``
        rather than leaving the variable unset (the same reasoning as
        ``worker_database_url_effective``).

        Returns:
            tuple[tuple[str, ...], tuple[str, ...]]: the operator-facing
                variable names that are present, and those that are missing.
        """
        api_key = self.kws_api_key.get_secret_value() if self.kws_api_key else None
        pairs = (
            ("KWS_ORGANIZATION_ID", self.kws_organization_id),
            ("KWS_API_ORIGIN", self.kws_api_origin),
            ("KWS_CLIENT_ID", self.kws_client_id),
            ("KWS_API_KEY", api_key),
        )
        present = tuple(name for name, value in pairs if value)
        missing = tuple(name for name, value in pairs if not value)
        return present, missing

    @property
    def kws_configured(self) -> bool:
        """Whether the Parent Verification Service can be called at all.

        False (the default) means the integration is unconfigured and no KWS
        call is ever made, matching the GEMINI_API_KEY / R2_* pattern: there is
        no separate enable flag, presence of credentials is the switch.

        Returns:
            bool: True when all four API-call credentials are present.
        """
        _, missing = self._kws_credential_state()
        return not missing

    @model_validator(mode="after")
    def _require_kws_credentials_together(self) -> Settings:
        """Fail fast on a partially configured KWS integration.

        A partial credential set is the worst of both worlds: ``kws_configured``
        reads False, so the app boots and behaves as though KWS were
        deliberately switched off, while the operator who pasted three of the
        four values believes verification is live. Nothing downstream can tell
        those two states apart, because both present as "no KWS". Refusing to
        boot converts a silent no-op into a startup error naming the gap.

        #CRITICAL: security: an operator who believes parental verification is
        running when it is not would ship an unverified consent path; failing
        at startup is the only point where the two states are still
        distinguishable.
        #VERIFY: tests/unit/test_config.py::TestKwsSettings::
        test_partial_kws_credentials_are_rejected and
        ::test_empty_string_kws_credentials_count_as_unset.

        Raises:
            ConfigurationError: when some but not all of the four KWS API-call
                credentials are provided.
        """
        present, missing = self._kws_credential_state()
        if present and missing:
            msg = (
                "KWS is partially configured: "
                f"{', '.join(present)} set but {', '.join(missing)} missing. "
                "Set all four or none; a partial set boots silently as though "
                "the Parent Verification Service were switched off, which is "
                "indistinguishable from a deliberate opt-out."
            )
            raise ConfigurationError(msg)
        return self

    @model_validator(mode="after")
    def _require_declared_kws_methods_when_configured(self) -> Settings:
        """Refuse a configured KWS integration that declares no enabled methods.

        An empty ``kws_enabled_methods`` alongside working credentials is not a
        harmless omission: verifications will succeed, records will be written,
        and every one of them will carry an empty bound on how the parent was
        verified. The vendor cannot supply that bound afterwards, because the
        webhook never reports a method, so the omission is unrecoverable rather
        than merely untidy. Requiring the declaration up front is the only
        point at which the operator still has the Control Panel open in front
        of them.

        The check deliberately does not attempt to reconcile the declaration
        against the Control Panel: there is no API to read it from, so this is
        an asserted fact, and asserting it explicitly is the whole point.

        #CRITICAL: data integrity: consent records written under an empty
        declaration cannot be retroactively bounded to any verification method.
        #VERIFY: tests/unit/test_config.py::TestKwsEnabledMethods::
        test_configured_kws_requires_declared_methods and
        ::test_unconfigured_kws_may_declare_nothing.

        Raises:
            ConfigurationError: when the KWS credentials are complete but no
                verification method has been declared.
        """
        if self.kws_configured and not self.kws_enabled_methods:
            msg = (
                "KWS is configured but KWS_ENABLED_METHODS is empty. Mirror "
                "the Control Panel's Verification methods tab for this "
                "environment (e.g. 'credit_card,debit_card'): the "
                "parent-verified webhook reports no method, so this "
                "declaration is the only bound on how a parent was verified, "
                "and no interface returns it to us afterwards."
            )
            raise ConfigurationError(msg)
        return self

    @model_validator(mode="after")
    def _reject_test_evidence_against_production_kws(self) -> Settings:
        """Refuse to accept Test verifications while pointed at Production KWS.

        The two settings have no legitimate combination. ``kws_environment``
        is Production only where real parents verify, and there
        ``kws_accept_test_evidence`` can only be a staging variable that rode
        into the wrong tier's configuration; left standing it would widen what
        counts as parental consent, silently and with nothing in the resulting
        records to show for it.

        Keyed on ``kws_environment`` rather than on ``environment`` on
        purpose. Staging declares ``ENVIRONMENT=production`` (so that its
        posture matches production's), which makes any guard written against
        ``environment`` unable to tell the two tiers apart. ``kws_environment``
        does tell them apart, and it is also the value the evidence is
        recorded under, so it is the honest thing to key on.

        #CRITICAL: security: this is the guard that keeps a copied staging
        env file from turning sandbox verifications into consent evidence in
        production.
        #VERIFY: tests/unit/test_config.py::TestKwsEvidenceSettings::
        test_the_real_staging_shape_is_allowed_not_just_a_staging_label. Cite
        that one, not the refusal test: the refusal test and its allow-case
        counterpart move ``environment`` and ``kws_environment`` in lockstep,
        so both still pass if this guard is rewritten against ``environment``.
        Only the mismatched pair (``environment="production"`` with
        ``kws_environment="test"``) can observe the difference.

        Raises:
            ConfigurationError: when ``kws_accept_test_evidence`` is set while
                ``kws_environment`` is ``"production"``.
        """
        if self.kws_accept_test_evidence and self.kws_environment == "production":
            msg = (
                "KWS_ACCEPT_TEST_EVIDENCE=true is refused while "
                "KWS_ENVIRONMENT='production': a Test verification is a "
                "sandbox event, not evidence about a real parent, and the "
                "combination can only mean a staging variable reached a "
                "production tier."
            )
            raise ConfigurationError(msg)
        return self

    @model_validator(mode="after")
    def _reject_start_override_against_production_kws(self) -> Settings:
        """Refuse the start-endpoint escape hatch while pointed at Production KWS.

        ``kws_allow_start_while_not_required`` exists so staging can exercise
        the endpoint and its screens while the gate is still off. Against
        Production KWS that combination has no legitimate reading: it would
        mean real parents' email addresses are being disclosed to Epic by a
        flow that no gate depends on, which is the exact posture O-125 is open
        about.

        Keyed on ``kws_environment`` for the same reason
        ``_reject_test_evidence_against_production_kws`` is: staging declares
        ``ENVIRONMENT=production``, so an ``environment``-shaped guard cannot
        tell the two tiers apart and would be a control in name only.

        #CRITICAL: security: refusal to boot is the control. A tier that
        acquires this variable by copying staging's env file stops, rather
        than quietly re-opening an endpoint whose whole gate this PR moved.
        #VERIFY: tests/unit/test_config.py::TestKwsStartOverride::
        test_the_start_override_is_refused_against_production_kws and
        ::test_the_start_override_is_allowed_against_test_kws. Cite the pair:
        the refusal alone passes for a guard written against ``environment``,
        because the allow-case is what pins the ``kws_environment`` keying.

        Raises:
            ConfigurationError: when ``kws_allow_start_while_not_required`` is
                set while ``kws_environment`` is ``"production"``.
        """
        if (
            self.kws_allow_start_while_not_required
            and self.kws_environment == "production"
        ):
            msg = (
                "KWS_ALLOW_START_WHILE_NOT_REQUIRED=true is refused while "
                "KWS_ENVIRONMENT='production': it would disclose real "
                "parents' email addresses to Epic for a flow that gates "
                "nothing on this tier. Set KWS_VERIFICATION_REQUIRED=true "
                "instead, or unset this variable."
            )
            raise ConfigurationError(msg)
        return self

    @model_validator(mode="after")
    def _reject_production_kws_from_a_local_app(self) -> Settings:
        """Refuse to point a local process at the production KWS environment.

        A verification recorded with ``kws_environment="production"`` is
        evidence that a real adult completed a real verification, and the KWS
        API reports nothing that would let us re-derive the environment later
        (the parent-verified webhook's ``status`` object carries only
        ``verified`` and ``transactionId``). A developer machine writing such
        records would therefore contaminate the consent ledger with rows that
        cannot be told apart from genuine ones afterwards.

        The check is deliberately one-directional: ``kws_environment="test"``
        in a deployed tier is allowed, because a real environment exercising
        the sandbox is a normal staging posture and mislabelling a real consent
        as a test is the recoverable direction of the error.

        #CRITICAL: data integrity: production consent records minted from a
        local process are indistinguishable from genuine ones and cannot be
        retroactively identified.
        #VERIFY: tests/unit/test_config.py::TestKwsSettings::
        test_production_kws_environment_rejected_from_a_local_app and
        ::test_test_kws_environment_allowed_in_a_deployed_tier.

        Raises:
            ConfigurationError: when ``kws_environment`` is ``"production"``
                while the app's own ``environment`` is ``"local"``.
        """
        if self.kws_environment == "production" and self.environment == "local":
            msg = (
                "KWS_ENVIRONMENT='production' is refused while ENVIRONMENT is "
                "'local': a verification recorded from a developer machine "
                "would be indistinguishable from real parental consent, and "
                "KWS reports nothing that would let the environment be "
                "re-derived later. Use the Test environment's credentials."
            )
            raise ConfigurationError(msg)
        return self

    @model_validator(mode="after")
    def _reject_engagement_analysis_output_inside_repository(self) -> Settings:
        """Refuse to boot the ADR-030 job without a destination outside a checkout.

        ADR-030 Decision 6 decides that the engagement-correlation artifact may
        never be committed to this repository. It is public, and a push is not
        retractable: an aggregate over five families of real children, once
        pushed, stays reachable in history after any deletion. Decision 7 makes
        refusal to boot the control rather than operator discipline, in the same
        posture as the KWS validators, so a tier that acquires a bad output path
        by copying another tier's environment file stops instead of quietly
        writing children's reading aggregates into a checkout that something
        later stages.

        Three properties are pinned by ADR-030 Decision 7 because each has a
        plausible reading that would make this pass where it should refuse:

        - the ``.git`` probe is file-or-directory existence, not directory
          existence. This repository's worktrees at ``.worktrees/<slug>`` mark
          themselves with a ``.git`` **file** holding a ``gitdir:`` pointer, and
          worktrees are where concurrent sessions here actually work, so an
          ``is_dir()`` check would accept every one of them;
        - an empty-string path counts as unset and takes the refusal branch,
          rather than counting as a configured path that resolves to the current
          working directory;
        - the path is resolved before its parents are walked, because walking an
          unresolved path finds no ``.git`` above a symlink whose target sits
          inside a checkout.

        Honest about its scope: this defends the developer-workstation case,
        which is where the mistake actually happens. A deployed container has no
        working tree to write into and passes trivially.

        #CRITICAL: security: refusal to boot is the control.
        #VERIFY: tests/unit/test_config.py::TestEngagementCorrelationAnalysis::
        test_an_output_path_inside_a_git_working_tree_is_refused and
        ::test_an_output_path_outside_a_git_working_tree_is_accepted. Cite the
        pair: the refusal alone passes for a validator that refuses
        unconditionally.

        Returns:
            Settings: This instance, when the configuration is acceptable.

        Raises:
            ConfigurationError: when the job is enabled and the output directory
                is unset, empty, or resolves at or below a git working tree.
        """
        if not self.analysis_engagement_correlation_enabled:
            return self
        configured = self.analysis_engagement_correlation_output_dir.strip()
        if not configured:
            msg = (
                "ANALYSIS_ENGAGEMENT_CORRELATION_ENABLED=true requires "
                "ANALYSIS_ENGAGEMENT_CORRELATION_OUTPUT_DIR to name a directory "
                "outside any git working tree (ADR-030 Decision 6). An empty "
                "value counts as unset: this artifact has no default path."
            )
            raise ConfigurationError(msg)
        resolved = Path(configured).expanduser().resolve()
        for candidate in (resolved, *resolved.parents):
            marker = candidate / ".git"
            # exists() OR is_symlink(): exists() covers both the ordinary
            # directory and a worktree's .git FILE, and is_symlink() adds the
            # broken-symlink case exists() answers False for.
            if marker.exists() or marker.is_symlink():
                msg = (
                    "ANALYSIS_ENGAGEMENT_CORRELATION_OUTPUT_DIR resolves inside "
                    f"a git working tree ({candidate}): the "
                    "engagement-correlation artifact aggregates real children's "
                    "reading outcomes and may never reach a repository, whose "
                    "history is not retractable (ADR-030 Decision 6). Choose a "
                    "directory outside any checkout."
                )
                raise ConfigurationError(msg)
        return self


# A single, global instance of the settings
settings = Settings()
