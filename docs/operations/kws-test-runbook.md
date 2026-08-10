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
| Run the script inside the staging backend container | `docker exec -i cyo-staging-backend` with the script piped over stdin, since `scripts/` is not in the image | No credential leaves the host; the container already holds the right `DATABASE_URL` and KWS credentials. **Preferred**, and the only option whose commands are given in full below. |
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

Record every answer in ADR-018's D1 section with the date, and update the register row it bears on.

The identifiers below are stable and are cited from ADR-018 and from register rows O-122 through
O-124, so they keep their meanings. What changed on 2026-08-10 is the **order they should be run
in**, following the owner ruling that KWS card or debit verification is the sole VPC method and the
typed-name attestation is never relied on as the enumerated method:

| Run | Answers | Address needed | Blocked on |
|---|---|---|---|
| 1 | **Q2**, and Q3 for free | a real inbox with **no** prior Epic verification | branding published to Test; card alerts enabled first; execution inside the staging container |
| 2 | Q1 | an address that **has** completed an Epic verification | the same execution path |
| none | Q4 | none | **answered from vendor documentation 2026-08-10; no run needed** |

Q2 moved to the front because the ruling removed the fallback. It was the question that could
*retire* the O-122 accepted exception; with no second method behind it, it is now the question that
decides whether the chosen method is available at all. Q3 needs no run of its own: it is answered by
capturing the raw request on any real webhook delivery, so run 1 answers both. Q4 left the run list
entirely on 2026-08-10: Epic's own API pages document the shape verbatim, which is better evidence
than a single observed redirect would have been, and it cost no send budget.

**Both remaining runs are blocked on publishing branding to the Test environment.** Until that is
done, `send-email` answers `400 ERR_INVALID_REQUEST` with "you need to publish your branding in the
developer portal before you can call this api". The Developer Portal's Branding page requires a
**Global brand name** and a **Privacy Policy URL**, then offers **Publish to Test**. This is an
operator action in the portal; no code change unblocks it.

Note that Q1 and Q2 want opposite addresses and cannot share one. An address Epic has already
verified inherits through AgeGraph, so no method runs and there is no card transaction to observe.

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
- **Sharpened 2026-08-10 by vendor documentation.** Epic's PV Service pages describe the
  pre-verified path as one where the parent "doesn't receive a verification request" and instead
  sees a Web UI screen saying they already verified, followed by a confirmation email carrying
  **an intentional random delay of up to two hours**. Those pages document `parent-verified` only
  under the first-time flow's success branch and say nothing about a webhook on the pre-verified
  path. That is absence of evidence rather than evidence of absence, so it does not answer Q1; it
  raises the prior that the answer is bad. Two failure modes now need distinguishing on the run,
  and a run that stops watching after a few minutes cannot tell them apart:
  **no delivery ever**, which strands the row at `sent` forever, versus **a delivery deferred by
  up to two hours**, which is survivable but means no Gate 2 surface may treat the absence of a
  webhook shortly after a send as a negative result.

### Q2 (run first): does the card method capture and refund, or authorise only?

16 CFR 312.5(b)(2)(ii) requires the card be used "in connection with a transaction" and that it
"provides notification of each discrete transaction to the primary account holder." Whether a
zero-charge authorisation triggers cardholder notification is the unanswered question at the
centre of the payment-card route.

- **Setup**: complete a verification using the card method, with a card whose statement and
  notification settings you can inspect. **Enable transaction alerts before the run, not after**:
  whether a notification would have fired cannot be established retroactively, and a run that
  answers everything except the notification limb has answered nothing that matters.
- **What to watch**: whether a charge appears and is reversed, the amount, and critically
  **whether the cardholder receives a notification**.
- **Why it matters, restated 2026-08-10.** This was the only one of the four that could *retire* the
  O-122 accepted exception rather than merely characterise it. The owner ruling that KWS card or
  debit verification is the **sole** VPC method, with the typed-name attestation retained as consent
  content and never relied on as the enumerated method, promotes it further: it is now the
  **viability gate**. If Epic's card method produces a notified discrete transaction, (b)(2)(ii) is
  reachable through the vendor without our building card handling. If it produces a zero-charge
  authorisation with no notification to the primary account holder, the second limb of (b)(2)(ii) is
  unmet and there is no fallback method behind it, because the ruling removed the one that existed.
  Answer this before any Gate 2 work is scheduled.

### Q3: is the webhook signature in the header or the query string?

`consent/kws_signature.py` implements a Stripe-style `t=`/`v1=` scheme over the raw body with
bounded skew. That shape came from vendor documentation and a protocol reading, not from an
observed delivery.

- **What to watch**: the exact header name and value, or the query parameters, on a real delivery.
  Capture the raw request, not a parsed summary.
- **Why it matters**: a signature we cannot verify is answered `401`, which is the correct
  direction to fail but means a real verification is silently dropped. This is the one question
  whose wrong answer breaks the integration outright rather than weakening a claim about it.

### Q4 (ANSWERED 2026-08-10, no run needed): what shape is the redirect's `status` value in?

**Answer: a URL-encoded JSON object.** Epic's PV Service API pages give the return URL verbatim,
and decoded it reads `status={"verified":true,"transactionId":"<transactionId>","errorCode":null}`,
alongside `externalPayload` and `signature` as separate query parameters.

`api/kws_redirect.py::_reports_verified` already tries that JSON reading **first**, so the
implementation was correct before the question was answered. What changed is the evidence behind
it: the code carried an `#ASSUME` saying Epic documented that a `status` parameter comes back but
not what it contains, and that is no longer true. The marker was downgraded to `#EDGE` and moved
onto the bare-token fallback, which is the only part still speculative. The fallback stays, because
it is what makes an undocumented variant fail closed to *not verified*.

Documentation beat a live run to this answer, and it is the better evidence of the two: one
observed redirect shows one case, whereas the published contract covers the `errorCode` and
unverified branches a single successful run would never exercise. It also cost none of the
ten-per-hour send budget. Nothing here is contingent on the Control Panel return-URL registration,
which remains outstanding for its own reasons.

## Running it

Run it **inside the staging `backend` container**, on the homelab host. That container already holds
the staging `DATABASE_URL` and the KWS credentials, so the row lands in the database the webhook
will resolve against and no credential leaves the host. This is the only invocation that satisfies
the trap described above; the local one below is recorded so it is recognisable, not so it is used.

Three mechanical facts about the runtime image, all verified against the live container on
2026-08-10, and each of which breaks the obvious command:

- **The script is not in the image.** `.dockerignore` line 179 excludes `scripts/` under the comment
  "Validation and scripts (not needed in runtime)", so the Dockerfile's `COPY . .` never carries it
  and `/app/scripts/` does not exist. Any procedure of the form
  `docker exec <c> /app/.venv/bin/python scripts/kws_send_test_verification.py` is impossible, not
  merely awkward. **Pipe the script over stdin instead** and let Python read it from `-`.
- **It ships no shell.** The Dockerfile uses a DHI hardened base, so `docker exec ... bash` and
  `... sh` both fail. This rules out the usual `cat > /tmp/x.py` workaround as well; the stdin route
  is what remains. Exec the interpreter directly.
- **`uv` is not installed**, only the virtualenv it built. The interpreter is at
  `/app/.venv/bin/python`.

Run these from the repo worktree on the workstation. The redirect feeds the local file into `ssh`,
which forwards it to `docker exec -i`, which forwards it to Python's stdin. `docker exec` needs
`-i` for this; without it the script arrives empty and Python exits silently with nothing done.

```bash
cd .worktrees/kws-test-integration

# preflight: resolves the guardian, prints the plan, sends nothing, writes nothing
ssh byron@docker-host 'docker exec -i cyo-staging-backend /app/.venv/bin/python - \
    --user-id <guardian-uuid> --email parent@example.com --location US --dry-run' \
    < scripts/kws_send_test_verification.py

# the real send: drop --dry-run only after the plan reads correctly
ssh byron@docker-host 'docker exec -i cyo-staging-backend /app/.venv/bin/python - \
    --user-id <guardian-uuid> --email parent@example.com --location US' \
    < scripts/kws_send_test_verification.py
```

**The container name is the tier selector, and the two tiers differ by one word.** Staging is
`cyo-staging-backend`; production is `cyo-adventure-backend`. Verified 2026-08-10, the production
container **fails closed** on this script: `_require_configured` refuses with exit 1 because the
four KWS API credentials are not all present in that environment. That is a real safety property,
but it is a property of production's current configuration rather than a guard, and it will stop
holding the moment the KWS block lands in production's compose. Read the `kws environment` and
`label` lines the dry-run prints; they are the confirmation that the right container answered.

`--user-id` must be a guardian in **staging's** database, which is a different Supabase project from
production's (staging resolves through `aws-1-us-west-2`, production through `aws-0-us-east-1`).
A production UUID failing to resolve is the harmless failure; a UUID that happens to exist in both
is the dangerous one, so read the `--dry-run` plan rather than assuming the resolve proved the tier.

`--email` is the address the verification is sent to and is independent of the guardian's own stored
email, which is what makes it possible to answer Q1 and Q2 from the same guardian record using two
different inboxes.

> **The local invocation is the trap, not an alternative.** Running
> `uv run --env-file .env python scripts/kws_send_test_verification.py ...` from the worktree
> executes against whatever `DATABASE_URL` the shell has, which is local Postgres. The send
> succeeds, the parent receives mail, and the webhook then arrives at staging holding an attempt id
> staging has no row for, so it answers `200 handled=False` and writes nothing. Use it only if you
> have deliberately pointed the shell at staging's database per the first row of the table above.

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
