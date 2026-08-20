---
title: Handoff, Modal DeepSeek V4 Pro smoke test
description: State of the Modal-vs-OpenRouter provider comparison after the 2026-08-20 session.
---

# Handoff: Modal DeepSeek V4 Pro smoke test (2026-08-20)

Continuation of the provider-options research: measure cost/latency of a dedicated Modal endpoint for
`deepseek-ai/DeepSeek-V4-Pro` against OpenRouter (`deepseek/deepseek-v4-pro`) under the workspace
ZDR/no-training guardrail (ADR-003 as amended). Privacy is settled (Modal inference endpoints are ZDR
by design); the open question is measured cost and latency. `generation_provider=modal` remains
experimental-only per
[ADR-010](adr/adr-010-modal-review-and-gated-generation.md); nothing here is to be wired into the
production provider cascade.

Note: an earlier, unrelated artifact `yield-results/modal-standard-smoke-test.json` records a
standard-scale fill smoke test through a previous Modal deployment (1 story, 3 attempts, 25.5 s);
it predates the dedicated DeepSeek V4 Pro endpoint this handoff concerns.

## Session outcome summary

The Modal leg is NOT yet run. It is blocked on endpoint creation, which was in progress at session
end. The OpenRouter comparison leg IS complete, and it surfaced an adapter-shape defect that will
apply to both providers (see below).

## Environment and credential findings (cost real iteration; do not rediscover)

1. **Two Modal token types exist and are not interchangeable.** `ak-`/`as-` pairs are API tokens
   (CLI/SDK auth). Endpoint HTTP calls need a `wk-`/`ws-` proxy token pair, sent as `Modal-Key` /
   `Modal-Secret` headers. Create via dashboard (Settings, Proxy Auth Tokens) or
   `modal workspace proxy-tokens create`. The secret is shown only at creation. On RBAC workspaces
   the token must also be allowed into the environment:
   `modal workspace proxy-tokens allow wk-... main`.
2. **`core/config.py::Settings` expects `MODAL_PROXY_KEY` / `MODAL_PROXY_SECRET`**
   (`src/cyo_adventure/core/config.py`, around lines 585-599), plus `MODAL_BASE_URL` and optional
   `MODAL_MODEL`. `MODAL_BASE_URL` is the endpoint URL from the Modal dashboard or
   `modal endpoint list`; there is no guessable URL pattern for managed endpoints.
3. **Remote-session env vars load only at container start.** Values added to the Claude environment
   configuration do not appear in an already-running session; the network allowlist, by contrast,
   is enforced live at the gateway. A session started before a credential change must hand off to a
   fresh session to see it.
4. **The Modal CLI cannot run from the remote session.** It speaks gRPC directly to api.modal.com,
   which does not traverse the environment's HTTP CONNECT proxy. Endpoint creation and listing must
   happen on a developer machine:

   ```bash
   modal endpoint create --name deepseek-v4-pro --model deepseek-ai/DeepSeek-V4-Pro --env main
   modal endpoint list --env main   # status + endpoint URL once provisioned
   ```

5. **Network allowlist** for the remote environment now admits `modal.com`, `*.modal.run`, and
   `openrouter.ai` (all verified 200 through the gateway on 2026-08-20).
6. **Security follow-up: rotate the OpenRouter API key.** The key value was echoed into the
   2026-08-20 session transcript by a shell-expansion mistake during an env check. Rotate it at
   openrouter.ai and update the environment variable once the comparison finishes.

## OpenRouter leg results (2026-08-20, complete)

POST `https://openrouter.ai/api/v1/chat/completions`, model `deepseek/deepseek-v4-pro`, body
included `"provider": {"zdr": true, "quantizations": ["fp8"]}`, prompt "Reply with the single word:
ok", `max_tokens: 10`.

| Call | HTTP | Latency | Backend | prompt/completion tokens | Reported cost | `message.content` |
| ---- | ---- | ------- | ------- | ------------------------ | ------------- | ----------------- |
| 1    | 200  | 2.29 s  | Novita  | 90 / 9 (7 reasoning)     | $0.0001728    | `"ok"`            |
| 2    | 200  | 1.90 s  | Novita  | 90 / 10 (10 reasoning)   | $0.000176     | `null` (length)   |
| 3    | 200  | 1.55 s  | Novita  | 90 / 10 (10 reasoning)   | $0.000176     | `null` (length)   |

Findings:

- The `zdr` + `quantizations` provider preference fields are accepted live and all three calls
  routed to the same backend (Novita). This validates the fields proposed for
  `OpenRouterProvider` in `generation/providers/openrouter.py`.
- `usage` is complete and includes per-call `cost` and `completion_tokens_details.reasoning_tokens`.

## Adapter-shape defect (applies to both providers)

DeepSeek V4 Pro is a reasoning model: it spends completion tokens in a `reasoning` field before any
`content`. With a small `max_tokens`, generation halts mid-reasoning (`finish_reason: "length"`) and
`choices[0].message.content` is `null`. Consequences for `generation/providers/_base.py`:

- `dig_content`-style extraction that requires non-empty `content` must treat `content: null` with
  `finish_reason: "length"` as a budget problem (retry with a larger budget), not a malformed
  response.
- Token/cost accounting must account for `completion_tokens` including reasoning tokens.
- The same check must be repeated against the Modal endpoint response shape once it is live; also
  verify `usage.prompt_tokens` / `usage.completion_tokens` are present at all there.

## Remaining work (the Modal leg)

Preconditions: endpoint provisioned (weights are roughly 1 TB, first spin-up is slow),
`MODAL_BASE_URL` known, `wk-`/`ws-` pair available as `MODAL_PROXY_KEY` / `MODAL_PROXY_SECRET`.

1. Cold call, timed, `curl --max-time 900`:
   POST `$MODAL_BASE_URL/v1/chat/completions` with headers `Modal-Key` / `Modal-Secret` and body
   `{"model": "deepseek-ai/DeepSeek-V4-Pro", "messages": [{"role": "user", "content": "Reply with
   the single word: ok"}], "max_tokens": 10}`. Record wall clock, HTTP status, full JSON body.
2. Repeat twice immediately for warm latency.
3. Optionally one extra call with `max_tokens: 100` to confirm non-null `content` clears the
   reasoning-budget issue. Keep total spend trivial.
4. Shape-check the response against `dig_content` / `dig_usage` expectations.
5. Read the billed GPU-seconds for the cold start off the Modal dashboard; that number settles the
   cost-per-catalog-fill estimate in the provider-options research.
6. Append results to this document on branch `claude/modal-deepseek-v4-smoke-test-x38avp`.

If auth fails with 401/403, the token pair is the wrong type (see finding 1).

## Second session (2026-08-20, Modal leg attempt): blocked on the endpoint URL

Credential preflight passed, with one naming caveat:

- The proxy-token pair is present in the session environment but under nonstandard names:
  `MODAL_KEY` (value starts `wk-`) and `MIDAL_SECRET` (value starts `ws-`; note the `MIDAL` typo in
  the variable name). The pair is the correct wk-/ws- proxy type. Before any code-level test through
  `core/config.py::Settings`, rename them in the environment configuration to `MODAL_PROXY_KEY` /
  `MODAL_PROXY_SECRET`, and remember env values load only at container start (finding 3).

`MODAL_BASE_URL` is absent, and the session could not recover the endpoint URL from anywhere:

- Not in the environment under any name (all variable names audited), not in the repo or any
  `claude/*` branch, and no `~/.modal.toml` in the container.
- Hostname guessing is unverifiable, confirming finding 2: `https://williaby--deepseek-v4-pro.modal.run/`
  returns the generic edge 404 `modal-http: invalid function call`, byte-identical to a control
  request against a nonexistent workspace hostname, so a 404 there proves nothing about the
  endpoint's existence or name.
- `api.modal.com` is not an HTTP gateway for managed endpoints: `GET /v1/models` and
  `POST /v1/chat/completions` (with `Modal-Key`/`Modal-Secret` headers) both return HTTP 200 with
  zero-byte bodies, consistent with a gRPC-only host behind a load balancer.

The Modal leg therefore remains unrun. Unblocking requires exactly one value from a developer
machine or the dashboard: the endpoint URL from `modal endpoint list --env main`. Everything else
(allowlist, credentials, call plan) is verified and ready.

Update, later the same session: the owner reports the endpoint spin-up attempt (from mobile)
FAILED, and creation logs are not visible from a mobile device. So the blocker is now one step
earlier than the URL: the endpoint does not exist yet. Nothing in the remote session can advance
this; the session cannot reach Modal's gRPC API (finding 4) and holds only the wk-/ws- proxy pair,
which cannot authenticate the CLI even if it could.

Next steps, from a developer machine:

1. Re-run `modal endpoint create --name deepseek-v4-pro --model deepseek-ai/DeepSeek-V4-Pro
   --env main` and read the failure output. Likely suspects for a first spin-up failure at this
   model size: GPU capacity or quota for the required instance class, workspace billing limits, an
   RBAC restriction on env `main`, or a stale half-created endpoint with the same name (check
   `modal endpoint list --env main` and the dashboard before recreating).
2. Once `modal endpoint list --env main` shows the endpoint live, put its URL in the remote
   environment configuration as `MODAL_BASE_URL`, and rename the token vars to
   `MODAL_PROXY_KEY` / `MODAL_PROXY_SECRET` (fixing the `MIDAL_SECRET` typo) in the same edit,
   since env values load only at container start (finding 3).
3. Start a fresh session with the smoke-test prompt; the call plan in "Remaining work" above is
   unchanged and everything else (allowlist, token types, response-shape expectations, OpenRouter
   baseline) is already verified.
