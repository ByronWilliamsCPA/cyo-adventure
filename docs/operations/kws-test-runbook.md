---
title: "KWS Test-Environment Runbook"
schema_type: common
status: published
owner: core-maintainer
purpose: >-
  How to run the KWS parent-verification integration against Epic's Test environment, and the
  four questions those runs exist to answer before any production wiring is considered.
tags:
  - compliance
  - deployment
  - guide
  - monitoring
---

This is the procedure for Gate 1 of the KWS production plan: gathering empirical evidence about
Epic's Kids Web Services Parent Verification Service by running the built integration against the
**Test** environment. It is not a production procedure, and following it never produces a valid
verifiable parental consent record.

Background and the decision this feeds: [ADR-018](../planning/adr/adr-018-childrens-privacy-compliance.md)
decision D1. Wire protocol and trust properties:
[the sequence diagram](../architecture/diagrams/seq-kws-verification.puml). Register coverage:
`docs/security/assurance-register.md` rows O-122, O-123, O-124.

## What a Test run is worth

A Test-environment verification is **not** a valid VPC under COPPA, and no deployed tier can
detect that it was one after the fact. The `kws_verification` row it writes is indistinguishable
in shape from a production row; the only thing separating them is which credentials were in the
environment at send time. That is why:

- `scripts/kws_send_test_verification.py::_require_test_environment` refuses to run unless
  `KWS_ENVIRONMENT` is `test`, with no override flag.
- `core/config.py::_reject_production_kws_from_a_local_app` refuses production KWS credentials on
  a local app. Note its limit: it fires only when `ENVIRONMENT == "local"`, and **staging declares
  `ENVIRONMENT=production`**, so it cannot fire on either deployed tier. The guard is
  one-directional by design and register row O-123 records that as `evidence invalid` rather than
  claiming coverage it does not have.

Treat every row these runs produce as test data, and do not let one become the basis of a consent
decision.

## The trap that will waste a run: which database the row lands in

The send leg writes a committed `kws_verification` row **before** calling KWS, because KWS will
not replay a delivery and an unmatched attempt is unattributable forever. The webhook then
resolves that row by its id.

The two halves can land in different databases. `scripts/kws_send_test_verification.py` runs on
whatever `DATABASE_URL` the invoking shell has, which locally is the local Postgres. The
`parent-verified` webhook is delivered to the URL registered in Epic's Control Panel, which is
**staging's** hostname, so it resolves against the **staging** Supabase project.

If the row is written locally and the webhook lands on staging, the webhook answers `200` with
`handled=False` and writes nothing. That is a correct, deliberate response to an attempt id it
holds no row for (see `api/kws_webhook.py`'s "Everything this route declines to treat as an
error"), so **nothing in the logs will look like a failure**. You will have burned one of ten
hourly sends and gathered no evidence.

Pick one before sending:

| Approach | What it needs | Trade-off |
|---|---|---|
| Point the local shell at staging's database | `DATABASE_URL` for staging's `cyo_api` role in a local env file | Fastest. Puts a staging DB credential on the workstation, so treat it as a secret and remove it after. |
| Run the script inside the staging backend container | Portainer or `docker exec` into `backend` on staging | No credential leaves the host; the container already holds the right `DATABASE_URL` and KWS credentials. Preferred. |
| Register a second return/webhook URL against a tunnel to the workstation | A public tunnel and a Control Panel registration | Most work, and mints a second pair of HMAC secrets to manage. Only worth it for iterating on the handler code. |

Whichever you pick, `--dry-run` first. It resolves the guardian and prints the plan without
sending or writing, so it catches a wrong `--user-id` or an unconfigured credential set for free.

## Budget: ten sends per hour, per address

The rate limit is **10 requests per hour per unique parent email**, and it applies in Test exactly
as in production. Nothing in the code retries, deliberately. Plan the questions below so each send
answers something, and use a distinct address if you need to reset the quota rather than waiting.

The address must be a real inbox you control: Test differs from production in credentials and data
partition, not in whether mail is delivered.

## The four questions

Ordered by how much each would change D1. Record every answer in ADR-018's D1 section with the
date, and update the register row it bears on.

### Q1: does `parent-verified` fire on the AgeGraph inheritance path?

Epic's AgeGraph can treat a parent as already verified from a prior verification elsewhere in
Epic's ecosystem, with no method running for us at all. This is an accepted risk, not a defect,
but its blast radius depends on whether we are told.

- **Setup**: use an email address that has previously completed an Epic parent verification.
- **What to watch**: whether a `parent-verified` delivery arrives at all, how quickly, and whether
  `payload.status.transactionId` is present.
- **Why it matters**: if the webhook fires identically for an inherited verification, then a row
  reading `verified` proves only that Epic believes the address belongs to an adult, on evidence
  gathered at an unknown time by an unknown method. That is the whole content of register row
  O-124's "snapshot, never a live read" constraint, and confirming it turns an assumption into a
  finding.

### Q2: does the card method capture and refund, or authorise only?

16 CFR 312.5(b)(2)(ii) requires the card be used "in connection with a transaction" and that it
"provides notification of each discrete transaction to the primary account holder." Whether a
zero-charge authorisation triggers cardholder notification is the unanswered question at the
centre of the payment-card route.

- **Setup**: complete a verification using the card method, with a card whose statement and
  notification settings you can inspect.
- **What to watch**: whether a charge appears and is reversed, the amount, and critically
  **whether the cardholder receives a notification**.
- **Why it matters**: this is the only one of the four that could *retire* the O-122 accepted
  exception rather than merely characterise it. If Epic's card method produces a notified discrete
  transaction, the enumerated method at (b)(2)(ii) is reachable through the vendor without our
  building card handling.

### Q3: is the webhook signature in the header or the query string?

`consent/kws_signature.py` implements a Stripe-style `t=`/`v1=` scheme over the raw body with
bounded skew. That shape came from vendor documentation and a protocol reading, not from an
observed delivery.

- **What to watch**: the exact header name and value, or the query parameters, on a real delivery.
  Capture the raw request, not a parsed summary.
- **Why it matters**: a signature we cannot verify is answered `401`, which is the correct
  direction to fail but means a real verification is silently dropped. This is the one question
  whose wrong answer breaks the integration outright rather than weakening a claim about it.

### Q4: what shape is the redirect's `status` value actually in?

`api/kws_redirect.py::_reports_verified` tries a JSON reading first
(`{"verified": true, ...}`) and falls back to the bare tokens `verified` / `true` / `success`.
Both are guesses; Epic's documentation does not pin the shape, and the code says so in an
`#ASSUME` tag.

- **What to watch**: the literal `status` query-parameter value on the return URL, before any
  parsing.
- **Why it matters**: anything unrecognised reads as *not verified*, which is the safe direction
  (the page writes nothing either way), but it means a genuinely verified parent may see the
  unconfirmed page. That is a UX defect on the surface Gate 2 will build against, so answer it
  before building.

## Running it

```bash
# from the worktree; the primary checkout may predate the merge and have no such script
cd .worktrees/kws-test-integration

# preflight: resolves the guardian, prints the plan, sends nothing, writes nothing
uv run --env-file .env python scripts/kws_send_test_verification.py \
    --user-id <guardian-uuid> --email parent@example.com --location US --dry-run

# the real send
uv run --env-file .env python scripts/kws_send_test_verification.py \
    --user-id <guardian-uuid> --email parent@example.com --location US
```

`--location` is the **child's** location as ISO 3166-1 alpha-2 or ISO 3166-2, and it selects which
methods the parent is offered. It is a compliance input and deliberately has no default.

On success the script prints an `attempt_id`. That single value is the `kws_verification` primary
key, the `externalPayload` sent to Epic, and what both return legs quote back, so it is the thread
to follow through the redirect page and the webhook logs.

## Checking the deployed wiring first

```bash
uv run python scripts/kws_probe_endpoints.py --origin https://cyo-staging.williamshome.family
```

Both routes should report ready. If they report "route is live but `KWS_*_SECRET` is unset", the
Control Panel registration has not happened yet and no verification can complete. If they 404,
check `/api/v1/health/`'s `version` and `uptime_seconds` before suspecting the wiring: a Portainer
stack update without the re-pull option reuses the local image and reports success having changed
nothing.

## What Gate 1 does not do

It does not choose the route. KWS versus a direct Stripe integration stays open, and building
against Test is what makes that comparison decidable on observed behaviour instead of on
documentation. It does not close ADR-018 D1, and it does not convert any accepted risk into a
mitigated one.
