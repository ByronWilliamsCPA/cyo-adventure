---
title: "Security Event Catalog"
schema_type: common
status: published
owner: core-maintainer
purpose: >-
  The structured security events CYO Adventure emits, what each one means, which alert rule
  keys on it, and the retention and volume bounds that keep the log store safe to write to.
tags:
  - security
  - monitoring
  - observability
  - guide
---

This is the catalog of security-relevant structured log events the backend emits, and the
operational contract around them: what fires each event, what an operator should do about it,
how long the lines are kept, and what stops an attacker from using them to fill a disk.

It documents what exists in this repository today. Where a piece of the chain is not built yet
(a shipped alert rule, a retention job on the live host), that gap is called out rather than
described as if it were in place. This closes the observability half of the `OPS-005` control;
the emission side lives in `app.py::_handle_project_error` and
`middleware/security.py::RateLimitMiddleware`.

## 1. Why these events exist separately from `project_error`

Every `ProjectBaseError` that reaches the global handler already logs a generic `project_error`
line carrying the error class, message, and status code. That line is a debugging aid, not a
detection surface: keying an alert on it means parsing `status_code` out of a stream that is
dominated by ordinary 404s and validation failures.

The security events below are named distinctly so a detection rule can match on the event name
alone. They also carry request attribution (client address, path, method) that the raise site
itself never has access to, because auth errors are raised deep in service code that holds no
`Request`.

Both lines are emitted for the same auth failure. That is deliberate duplication: the generic
line keeps the full internal payload for debugging, the security line carries the pruned,
alertable view. Do not "deduplicate" them by removing one.

## 2. Event catalog

### `security_auth_failed`

| | |
| --- | --- |
| Level | `warning` |
| Emitted by | `app.py::_handle_project_error` |
| Fires on | Any `AuthenticationError` reaching the global handler (HTTP 401) |
| Fields | `reason`, `code`, `client_ip`, `path`, `method` |

A caller presented no credential, a malformed one, or one that failed verification. `reason` is
always a fixed, developer-authored literal from this codebase, never caller input. `code` is the
machine-readable `error_code`, `AUTH_FAILED` unless a call site overrides it.

**Alert on**: a sustained rate from a single `client_ip` (credential stuffing), or a broad
low-rate spread across many IPs against the same `path` (password spraying). A handful of these
per hour is normal: expired sessions and stale service-worker caches produce them.

### `security_authz_denied`

| | |
| --- | --- |
| Level | `warning` |
| Emitted by | `app.py::_handle_project_error` |
| Fires on | Any `AuthorizationError` reaching the global handler (HTTP 403) |
| Fields | `reason`, `code`, `client_ip`, `path`, `method`, `details` |

An authenticated caller was denied a resource. This is the higher-signal of the two: a
successfully authenticated principal repeatedly reaching for resources outside its family is
the shape of an account takeover or an enumeration sweep, not a user mistake.

`details` is the **client-safe** projection (`_client_safe_error`), with the `value` and
`context` keys pruned. That pruning is not cosmetic: it is what stops a future
`AuthorizationError(details={"value": <caller input>})` call site from silently widening what
this event discloses.

`code` is `FORBIDDEN` at every call site except `api/child_sessions.py`, which raises
`error_code="PIN_MISMATCH"` on a failed child PIN. **Alert separately on `PIN_MISMATCH`**: a
repeated PIN mismatch against one profile is a child-account brute force, and it is the one
case where the generic 403 rate would bury the signal.

### `security_rate_limit_exceeded`

| | |
| --- | --- |
| Level | `warning` |
| Emitted by | `middleware/security.py::RateLimitMiddleware` |
| Fires on | An rpm or burst limit trip, on either the memory or Redis backend |
| Fields | `limit_type` (`rpm`/`burst`), `client_ip`, `requests_per_minute` or `burst_size`, `suppressed_since_last` |

**This event is throttled to one line per client IP per 60 seconds.** `suppressed_since_last`
carries how many trips were swallowed since the previous emitted line, so the true intensity is
still recoverable from a single record.

The throttle is load-bearing, not a tidiness measure. A rejected request returns before it is
appended to the sliding window, so the requests-per-minute cap does **not** bound how many trips
a flooding client can generate: at N requests/second a sustained flood produces roughly N
trips/second. Logging each one unthrottled would turn the rate limiter into a log-volume
amplifier pointed at the host's disk. If you widen or remove the throttle, you must first
confirm the log store is rotated (section 4).

**Alert on**: `suppressed_since_last` above a few hundred (a real flood, not a chatty client),
or any trip from an IP that has also produced `security_auth_failed` lines.

### `rate_limit_backend_unavailable`

| | |
| --- | --- |
| Level | `warning` |
| Emitted by | `middleware/security.py::RateLimitMiddleware.dispatch` |
| Fires on | Redis being unreachable, sending the limiter to its in-memory fallback |

A degraded-mode signal rather than an attack signal. The in-memory fallback is per-process, so
with more than one replica the effective limit is multiplied by the replica count. **Alert on
any occurrence**: it means the rate limit is weaker than configured for as long as it persists.

### `security_event_write_failed`

| | |
| --- | --- |
| Level | `error` |
| Emitted by | `security_audit.py::record_security_event` |
| Fires on | The durable `security_event` row (section 5) failing to write |
| Fields | `event_type`, `error_type` |

The other side of section 5's fail-open contract. The durable write is deliberately allowed to
fail rather than turn a real 401/403/429 into a 500, so this line is the **only** signal that
the audit table is missing rows. Left unmonitored, fail-open is indistinguishable from
nothing-happened: the table simply goes quiet and looks like an absence of attacks.

`event_type` is the event whose row was lost, so a burst of these correlates directly with
which detection surface has gone blind. `error_type` is the exception's class name and nothing
else. Neither `str(exc)` nor a traceback is ever attached, because a DBAPI-level SQLAlchemy
error renders its bound parameters into its own `__str__`, which would put `client_ip` and the
rest of the row straight into the log store this table exists to reduce reliance on.

**Alert on any occurrence.** Unlike the events above, this one has no legitimate steady-state
rate: a healthy deployment emits zero. A sustained run of them means the database is
unreachable, the service role has lost its `INSERT` grant on `security_event`, or the write is
exceeding its timeout under load.

### `generation_worker.role_least_privileged` / `generation_worker.role_bypasses_rls` / `generation_worker.rls_posture_unknown`

| | |
| --- | --- |
| Level | `warning` (all three) |
| Emitted by | `generation/worker_main.py::_log_worker_role_posture` |
| Fires on | Once per worker process start, before the stranded-job reclaim sweep |
| Fields | `role`, `worker_dsn_explicitly_set`; plus `via_role_attribute` / `via_table_ownership` on the bypass event, `error` on the unknown event |

The worker half of the ADR-021 least-privilege cutover signal. A worker process serves no HTTP, so
`/health/ready`'s `database_privilege` check cannot see it, and
`CYO_ADVENTURE_WORKER_DATABASE_URL` falls back to `CYO_ADVENTURE_DATABASE_URL` in silence when
unset. Without these lines, "the worker is on `cyo_worker`" and "the worker still shares the API
credential" are indistinguishable without catching a generation job mid-flight and reading
`pg_stat_activity`.

Unusually for this catalog, **the affirmative outcome is also an event**. Silence on success would
make a completed cutover and a worker running an image with no probe at all produce identical
logs, which is the exact ambiguity the probe exists to remove. That is also why all three are
WARNING rather than INFO: at the production `LOG_LEVEL=WARNING` default (section 4) an INFO line
is dropped before it is written, so an INFO affirmative event is not a quieter signal, it is no
signal.

**Alert on** `role_bypasses_rls`, and *also* on `role_least_privileged` carrying
`worker_dsn_explicitly_set: false` (equivalently, `role != "cyo_worker"`). The fallback DSN
connects as `cyo_api`, which has `rolbypassrls = false` and owns no Tier 1 table, so a forgotten
worker credential emits the **affirmative** event; an alert keyed only on the bypass event reports
green for it. `rls_posture_unknown` means the posture is unmeasured, not clean, and warrants the
same follow-up as a bypass until proven otherwise.

These three do **not** write a `security_event` row (section 5). They describe process
configuration at startup, not an attributable request, and the table's columns (`client_ip`,
`path`, `method`, `status_code`) have no meaning for them.

## 3. What is deliberately NOT an event

Input validation rejections (HTTP 422, `ValidationError`) do **not** emit a security event, and
a test pins that they do not. They are attacker-drivable at unbounded rate from an
unauthenticated caller, and they are overwhelmingly generated by ordinary client bugs. Adding
them would reintroduce exactly the amplification the rate-limit throttle above exists to close,
in exchange for a signal with a near-100% false-positive rate. If a specific validation path
turns out to carry real attack signal, instrument that path with its own named event and its
own throttle, rather than making the generic handler chatty.

`api/deps.py`, the auth seam, contains no logger calls by design. All 89
`AuthenticationError`/`AuthorizationError` raise sites across 35 files pass through the single
global handler, which is where attribution is available. Logging in `deps.py` as well would
duplicate the event in a differently-shaped form.

## 4. Retention, rotation, and the log store

Security events are WARNING-level, so they are emitted at the production `LOG_LEVEL=WARNING`
default. They go to stdout as JSON (`JSON_LOGS=true`) and are captured by the container runtime.

**Rotation is a hard requirement, not a nicety.** Docker's default `json-file` driver never
rotates. `docker-compose.prod.yml` now sets `max-size: 50m` / `max-file: 5` on the `app` and
`worker` services, capping each at 250MB per replica.

> **Gap**: that bound applies only to deployments driven by this compose file. `homelab-infra`
> is the deployment orchestrator of record for the live environment, so **production remains
> unbounded until the equivalent logging options are set there.** Verify with
> `docker inspect -f '{{.HostConfig.LogConfig}}' <container>` on the live host; a result of
> `{json-file map[]}` means no bound is in effect.

These events contain `client_ip`, which is personal data, and `path`, which can embed a profile
identifier. They are therefore subject to the same handling as any other child-linked data
under [the privacy model](../planning/privacy-model.md) and
[ADR-018](../planning/adr/adr-018-childrens-privacy-compliance.md). The `max-file` cap above
gives a size-based bound but **not** a time-based deletion guarantee; ADR-018 requires a hard
deletion timeline per data class, and the container log store does not yet have one.

## 5. The durable counterpart: `security_event`

Every event in section 2 also writes one row to the append-only `security_event` Postgres
table (`security_audit.py::record_security_event`, called immediately after the matching
log line, OPS-005 follow-up). The log line is the real-time/alerting surface this document
otherwise covers; the table is what `docs/compliance/breach-notification-runbook.md` queries
to reconstruct a timeline once the log line above has rolled off (section 4's rotation
bound).

The two are not a field-for-field mirror. The table carries `event_type`, `reason`
(the auth/authz message, or `rpm`/`burst` for a rate-limit row), `client_ip`, `code`,
`path`, `method`, `status_code`, and `resource`; it does **not** carry
`suppressed_since_last`, `requests_per_minute`, or `burst_size` -- the rate-limit throttle
in section 2 bounds the table's write volume exactly as it bounds the log's (the durable
write sits *inside* the same `if suppressed is not None:` guard as the log line, not
beside it), but the per-window intensity detail stays log-only.

Every string column is truncated at the writer to the column's own width, including
`path`/`client_ip`/`method`/`resource` (attacker-reachable, unlike the developer-authored
`reason`/`code`): an untruncated oversized value would otherwise raise a Postgres error at
INSERT time, silently dropping the very audit row an attacker sending an oversized path
would most want dropped. The write itself is bounded to a short timeout and fails open on
any database error (connection refused, timeout, or a missing/insufficient-privilege
service-role grant) so a database outage never turns a real 401/403/429 into a 500.

**Privacy**: rows carry `client_ip` (personal data) and `path` (which can embed a profile
identifier), same as the log line, but the append-only trigger means these rows have no
deletion path at all yet -- there is no retention/purge job for this table today. See the
creating migration's header comment; this is tracked as a gap against ADR-018, not
something this table already satisfies.

## 6. Alerting

No alert rules ship in this repository today. The events above are shaped to be alertable
(distinct names, structured fields, bounded volume), but wiring them to a notification channel
is a deployment-side task in `homelab-infra` and is not yet done. Treat section 2's "Alert on"
guidance as the specification for those rules, not a description of rules that exist.

Until they exist, the events are useful for post-incident reconstruction only. That gap is
tracked as [`UW-D28`](../planning/unscheduled-work-register.md) against issue
[#557](https://github.com/ByronWilliamsCPA/cyo-adventure/issues/557), along with the two
follow-ups this document raises but does not close: an alert rule for
`security_event_write_failed` (without one, the fail-open write in section 5 makes a silent
audit gap look identical to an absence of attacks), and a retention or purge mechanism for the
`security_event` table's IP-bearing rows.
