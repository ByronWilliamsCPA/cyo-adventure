"""Configuration settings for CYO Adventure.

Most settings are loaded from environment variables under the 'CYO_ADVENTURE_'
prefix. Several operator-facing names are also honored unprefixed via
validation_alias, matching what docker-compose*.yml and
docs/guides/configuration.md already set: ENVIRONMENT, LOG_LEVEL, JSON_LOGS,
DATABASE_URL, and the OLLAMA_*, OPENROUTER_*, OPENAI_API_KEY, and
PERSPECTIVE_API_KEY credentials. Pydantic-settings handles the parsing and
validation.
"""

from __future__ import annotations

from typing import Literal
from urllib.parse import urlsplit

from pydantic import AliasChoices, Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from cyo_adventure.core.exceptions import ConfigurationError

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
    # ENVIRONMENT and OLLAMA_* above). AliasChoices keeps the prefixed form
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
    # Supabase's :5432 session/direct DSN that Alembic uses), where server-side
    # prepared statements are safe and faster.
    # #CRITICAL: concurrency: with a transaction pooler and this flag unset,
    # the first reused/renamed prepared statement raises asyncpg
    # DuplicatePreparedStatementError / InvalidSQLStatementNameError and the
    # request 500s intermittently under concurrency, not at startup.
    # #VERIFY: enforced for the known Supavisor case by
    # _require_prepared_cache_disabled_for_pooler_dsn below; consumed by
    # core/database.py::_build_connect_args and _build_engine_kwargs.
    database_disable_prepared_cache: bool = False
    # Development default for local Redis; safe to leave unset in non-production
    # environments where no queue is configured. Production must override via
    # CYO_ADVENTURE_REDIS_URL.
    redis_url: str = "redis://localhost:6379/0"
    # #CRITICAL: timing: RQ's own default job_timeout is 180s; a live Ollama run
    # (see ollama_timeout_seconds's cold-start note) routinely exceeds that, so an
    # unset job_timeout lets RQ SIGALRM-kill a still-healthy generation job and
    # strand its row. 1800s (30 min) comfortably covers a cold-start plus the
    # full three-stage pipeline (structure, prose, up to 3 repairs) against the
    # slowest configured leg.
    # #VERIFY: generation/queue.py::enqueue_generation passes this as
    # job_timeout= on every enqueue call (both the guardian-triggered enqueue and
    # the stranded-job reclaim sweep's re-enqueue).
    generation_job_timeout_seconds: int = 1800
    # Provider selection. "mock" remains the default so CI and local runs never
    # make live LLM calls; production/staging set this to "openrouter" (the
    # primary per ADR-003 as amended 2026-06-22). Live adapters are constructed
    # lazily in build_provider(), so an unset live key fails at call time, not
    # startup.
    generation_provider: Literal[
        "mock", "anthropic", "ollama", "openrouter", "modal"
    ] = "mock"

    # Model ids are pinned in config, not code (ADR-003): a model swap is a
    # config change. OpenRouter rosters churn weekly, so pin first-party families
    # (Anthropic, Google) that survive churn, and rely on the fallback below when
    # a pinned id 404s.
    # Primary is Haiku 4.5: the 2026-06-22 yield run measured it at 70% over the
    # 20-brief sample (clears the >=60% gate) at ~3x lower cost than Sonnet, which
    # stays as the reliable quality fallback if Haiku is unavailable. (Results:
    # docs/planning/yield-results/phase-2b-2026-06-22-analysis.md.)
    # #ASSUME: external-resources: these ids must be currently reachable on the
    # selected provider; build_provider/adapters map an unavailable model to
    # ProviderError so the orchestrator can fall back.
    # #VERIFY: Phase 2b adapter raises ProviderError on HTTP 400/404 invalid-model.
    openrouter_model: str = "anthropic/claude-haiku-4.5"
    openrouter_fallback_model: str = "anthropic/claude-sonnet-4.6"
    # Default to qwen2.5:14b: a ~9GB general instruct model that, in live testing
    # (2026-06-23), was both fast and produced a valid, gate-passing story graph
    # (the repair loop converged). The larger 30B tags are too slow on the
    # single-parallel host (~1hr/story), and the reasoning models (`qwen3:30b`,
    # `qwen-assistant:latest`) waste the num_predict budget on thinking tokens and
    # can return empty content; the prose-tuned `story-assistant:latest` was fast
    # but produced structurally invalid graphs (over-depth, dangling refs). Override
    # via CYO_ADVENTURE_OLLAMA_MODEL for a locally-pulled tag.
    ollama_model: str = "qwen2.5:14b"
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

    # Dedicated timeout for the Ollama leg, separate from the cloud llm_timeout
    # because the homelab host has very different latency: it runs
    # OLLAMA_NUM_PARALLEL=1 (one request at a time, others queue) with a ~28s cold
    # start after OLLAMA_KEEP_ALIVE expires. With streaming this bounds the per-read
    # gap (time-to-first-byte), not total generation time, so it mainly needs to
    # cover a cold start plus waiting behind one queued request.
    # #ASSUME: external-resources: time-to-first-byte can be minutes when a prior
    # request holds the single execution slot; too short a timeout fails healthy calls.
    # #VERIFY: build_ollama_leg passes this (not llm_timeout_seconds) to the adapter.
    ollama_timeout_seconds: int = 300

    # Cascade switch. True (default) lets FallbackProvider fail over across legs.
    # The yield/leg-comparison runs set this False to measure each leg in
    # isolation (no failover masking a leg's true yield).
    provider_fallback_enabled: bool = True

    # Provider endpoints. OpenRouter's base url is stable; Ollama defaults to the
    # local host. The homelab Ollama is fronted by Traefik+Authentik, so
    # production points this at the HTTPS vhost WITHOUT a port (TLS terminates on
    # :443, so an explicit :11434 is wrong for that path) and supplies the
    # Basic-auth credential below. Read from the UNPREFIXED ``OLLAMA_BASE_URL`` to
    # match the operator's existing .env naming (same pattern as
    # ``openrouter_api_key``); ``populate_by_name`` keeps the field settable by
    # name in tests/DI.
    openrouter_base_url: str = "https://openrouter.ai/api/v1"
    ollama_base_url: str = Field(
        default="http://localhost:11434", validation_alias="OLLAMA_BASE_URL"
    )

    # OpenRouter credential. Read from the UNPREFIXED ``OPENROUTER_API_KEY`` env
    # var (validation_alias bypasses the cyo_adventure_ prefix) to match the
    # operator's existing key naming. Optional and None by default: only the
    # openrouter provider needs it, and the mock default never does, so a missing
    # key surfaces as a ConfigurationError in build_provider at call time rather
    # than blocking startup. Ollama (local) needs no credential.
    # #CRITICAL: security: this is a secret; never log its value or echo it in an
    # error message. build_provider checks presence only.
    # #VERIFY: ProviderError/ConfigurationError messages reference the key by name
    # only, never by value.
    openrouter_api_key: str | None = Field(
        default=None, validation_alias="OPENROUTER_API_KEY"
    )

    # Ollama HTTP Basic-auth credential, as a single ``user:password`` string to
    # match the operator's ``OLLAMA_AUTH`` .env entry (and the native HTTP Basic
    # shape). Read from the UNPREFIXED ``OLLAMA_AUTH``. The local-dev default
    # (http://localhost:11434) needs none, so it is optional and None by default;
    # the Traefik+Authentik-fronted homelab host requires it and answers an
    # unauthenticated request with a 302 redirect to the login flow (which the
    # adapter maps to a leg-fatal ProviderError). build_provider splits it on the
    # first ``:`` (RFC 7617: the userid has no colon, the password may), and the
    # adapter sends Basic auth only when both halves are present.
    # #CRITICAL: security: ollama_auth contains a password; never log its value or
    # echo it in an error message. It must be supplied from a secret manager
    # (env var / Infisical), never committed to source control.
    # #VERIFY: build_provider passes the split halves to httpx.BasicAuth and no
    # ProviderError message includes the credential.
    ollama_auth: str | None = Field(default=None, validation_alias="OLLAMA_AUTH")

    # Optional path to a CA bundle for verifying the Ollama host's TLS cert. The
    # homelab host is fronted by Traefik serving a privately-signed cert (Homelab
    # CA) until the public wildcard is in place, so the public CA store alone
    # cannot verify it. Point this at the Homelab root+intermediate bundle to
    # verify properly (NOT a verification bypass). build_provider loads it ON TOP
    # of the system CAs, so the same setting keeps working once the host serves a
    # publicly-trusted cert. Leave unset for a direct local Ollama (plain http).
    ollama_ca_bundle: str | None = Field(
        default=None, validation_alias="OLLAMA_CA_BUNDLE"
    )

    # --- Experimental Modal generation leg (ADR-010 item 2) ---
    # An offline-only leg: build_provider never wraps this in the production
    # FallbackProvider cascade. All three fields are None until an operator
    # deploys a Modal Auto Endpoint and sets them; build_modal_leg raises
    # ConfigurationError naming the missing setting if either the url or model
    # is absent at that point.
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
    # raises at build time, mirroring the deferred "anthropic" generation provider.
    review_provider: Literal["mock", "ollama", "openrouter", "modal"] = "mock"
    review_openrouter_model: str = "anthropic/claude-sonnet-4.6"
    review_ollama_model: str = "qwen2.5:14b"

    # Stage-0 deterministic classifier credentials. Both optional individually; a
    # missing key skips that classifier. Both unset is rejected below when review runs.
    openai_api_key: str | None = Field(default=None, validation_alias="OPENAI_API_KEY")
    perspective_api_key: str | None = Field(
        default=None, validation_alias="PERSPECTIVE_API_KEY"
    )

    # --- OIDC verification (ADR-009: Supabase Auth, guardian tier; PROJECT-PLAN P6-02) ---
    # Provider-agnostic names are deliberate (ADR-009's ejection path): these
    # point at Supabase's GoTrue issuer today but api/deps.py never imports a
    # Supabase SDK, only jwt.PyJWKClient against oidc_jwks_url. Read from
    # UNPREFIXED env vars, matching the openrouter_api_key/ollama_auth pattern.
    # Optional here so local dev needs no config; _require_oidc_config_outside_local
    # below fails fast outside "local", and api/deps.py's own import-time guard is a
    # second check against the same invariant for the mocked-settings test scenario.
    oidc_issuer: str | None = Field(default=None, validation_alias="OIDC_ISSUER")
    oidc_audience: str = Field(
        default="authenticated", validation_alias="OIDC_AUDIENCE"
    )
    oidc_jwks_url: str | None = Field(default=None, validation_alias="OIDC_JWKS_URL")

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
    # (172.25.0.0/16 as of this writing) and overrides FORWARDED_ALLOW_IPS to
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
        default="172.16.0.0/12", validation_alias="FORWARDED_ALLOW_IPS"
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
        """Fail fast when database_url is Supavisor's pooler port but the flag is off.

        Only catches the documented Supabase Supavisor case (port 6543); a
        PgBouncer transaction-mode DSN has no distinguishing port and cannot
        be detected from the URL alone, so this is a defense against the one
        foreseeable, greppable mistake, not a complete guarantee.

        Raises:
            ConfigurationError: when database_url's port is the Supavisor
                transaction-pooler port and database_disable_prepared_cache
                is False, since asyncpg then collides on cached/fixed-name
                prepared statements once the pooler reassigns a backend
                mid-session (see the #CRITICAL note on database_disable_prepared_cache).
        """
        port = urlsplit(self.database_url).port
        if (
            port == _SUPAVISOR_TRANSACTION_POOLER_PORT
            and not self.database_disable_prepared_cache
        ):
            msg = (
                "CYO_ADVENTURE_DATABASE_URL uses port 6543 (Supabase Supavisor's "
                "transaction-mode pooler) but "
                "CYO_ADVENTURE_DATABASE_DISABLE_PREPARED_CACHE is not set; refusing "
                "to start, since asyncpg will intermittently raise "
                "DuplicatePreparedStatementError / InvalidSQLStatementNameError "
                "under concurrency once the pooler reassigns a backend mid-session."
            )
            raise ConfigurationError(msg)
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
    def _require_classifier_when_reviewing(self) -> Settings:
        """Require at least one Stage-0 classifier whenever real review runs.

        When ``review_provider`` is not ``"mock"`` the moderation pipeline makes
        real LLM calls over children's content; it must be preceded by at least
        one deterministic classifier. Mirrors ``_reject_dev_database_url_outside_local``:
        a posture invariant enforced conditionally, not blanket.

        Raises:
            ConfigurationError: when review runs with both classifier keys unset.
        """
        # #CRITICAL: security: no real review of children's content without a
        # deterministic pre-filter; both keys unset under a live reviewer is fatal.
        # #VERIFY: test_non_mock_review_without_any_classifier_key_raises.
        if self.review_provider != "mock" and not (
            self.openai_api_key or self.perspective_api_key
        ):
            msg = (
                "at least one of OPENAI_API_KEY or PERSPECTIVE_API_KEY must be set "
                f"when review_provider is '{self.review_provider}'"
            )
            raise ConfigurationError(msg)
        return self


# A single, global instance of the settings
settings = Settings()
