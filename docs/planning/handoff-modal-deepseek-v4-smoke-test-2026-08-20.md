---
title: Handoff, Modal DeepSeek V4 Pro smoke test
description: State of the Modal-vs-OpenRouter provider comparison after the 2026-08-20 and 2026-08-21
  sessions, including the shared Kimi-K3 validation and the failed DeepSeek V4 Pro endpoint provisioning.
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
   `modal endpoint list`. (Historical note: this finding originally said there is no guessable URL
   pattern; the 2026-08-21 session resolved the pattern as
   `https://<workspace>--<endpoint-name>.<region>.modal.direct`, see the Modal leg results below.)
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
   `openrouter.ai` (all verified 200 through the gateway on 2026-08-20), plus `*.modal.direct`,
   the domain managed endpoints actually serve on (verified working through the gateway on
   2026-08-21; see the Modal leg results below).
6. **Security follow-up: revoke the OpenRouter API key NOW.** The key value was echoed into the
   2026-08-20 session transcript by a shell-expansion mistake during an env check, so the
   credential stays usable until revoked. The comparison this rotation originally waited on is
   finished: revoke the exposed key at openrouter.ai immediately, create a replacement, update the
   environment variable, and record completion here. Do not copy the exposed value into any
   further artifact.

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

- `dig_content`-style extraction that requires non-empty `content` should treat `content: null`
  with `finish_reason: "length"` as a budget problem, not a malformed response. Note the
  implemented contract today is different: `OpenRouterProvider.complete` marks a
  `finish_reason: "length"` empty response leg-fatal, so the retry loop stops after one attempt
  (retries never enlarge `max_tokens`) and `FallbackProvider` moves to the next leg. The
  larger-budget follow-up retry is a PROPOSED change; whoever picks it up must implement and test
  it, or explicitly keep the leg-fatal behavior and document it as the accepted policy.
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

## Modal leg results (2026-08-21, run against a shared Kimi-K3 endpoint)

The DeepSeek V4 Pro endpoint still fails to provision, so the Modal leg ran as a path validation
against a shared endpoint the owner spun up for testing: `moonshotai/Kimi-K3` at
`https://williaby--ep-kimi-k3-server.us-west.modal.direct`. Same transport, same auth, same
OpenAI-compatible surface; the latency and shape findings transfer, the model does not. Kimi K3 is
also a reasoning model, so it reproduces the reasoning-budget behavior directly.

**URL pattern discovered (resolves finding 2's "not guessable"):** managed endpoints live on
`https://<workspace>--<endpoint-name>.<region>.modal.direct`, NOT `*.modal.run`. That is why every
`*.modal.run` guess returned the generic edge 404. The `modal.direct` domain works through the
remote environment's gateway as of this session. `GET <base>/v1/models` with `Modal-Key` /
`Modal-Secret` headers is a cheap auth-and-liveness preflight (200 with a model card here,
`{"error":"proxy auth required"}` / 401 without credentials); the wk-/ws- pair in this session's
env authenticated live, closing finding 1's loop.

**Startup:** not measurable from here; the endpoint was already warm when this session first
called it. The owner's dashboard log showed just under 7 seconds to start, and as a SHARED
endpoint it bills per token, with no dedicated GPU-second cost for startup. That changes the cost
model relative to the dedicated-endpoint assumption in the earlier research: the
cost-per-catalog-fill estimate needs a per-token price comparison against OpenRouter, not a
GPU-second amortization, unless we end up on a dedicated deployment after all.

Prompt "Reply with the single word: ok", `max_tokens: 10` except the last row. All calls HTTP 200:

| Call | Model / provider | Latency | prompt/completion tokens (reasoning) | `message.content` |
| ---- | ---------------- | ------- | ------------------------------------ | ----------------- |
| Modal 1 (pre-warmed) | Kimi-K3, Modal shared | 1.27 s | 92 / 10 (13) | `""` (length) |
| Modal warm 1 | Kimi-K3, Modal shared | 2.44 s | 92 / 10 (10) | `""` (length) |
| Modal warm 2 | Kimi-K3, Modal shared | 1.36 s | 92 / 10 (12) | `""` (length) |
| Modal, max_tokens 100 | Kimi-K3, Modal shared | 1.60 s | 92 / 42 (31) | `"ok"` (stop) |
| OpenRouter 1-3 (2026-08-20) | DeepSeek V4 Pro, Novita | 1.55-2.29 s | 90 / 9-10 | `"ok"` then `null` x2 |

Warm latency is in the same band as OpenRouter for a trivial completion. Raw JSON bodies were
captured in the session scratchpad (kimi-cold/warm1/warm2/mt100.json); key fields are reproduced
below.

**Shape check against `generation/providers/_base.py`:**

- `dig_usage`: PASSES as-is. `usage.prompt_tokens` and `usage.completion_tokens` are present as
  ints on every call. No `cost` field (unlike OpenRouter), so `cost_usd` stays None and spend
  accounting must come from Modal billing, not the response.
- `dig_content`: structurally fine, but the budget-exhaustion signature DIFFERS from OpenRouter.
  OpenRouter returned `content: null` (dig_content returns None); Modal returns `content: ""`, an
  empty STRING, which dig_content passes through as a valid str. Any "treat null content +
  finish_reason length as a budget problem" fix must also treat EMPTY content the same way, or the
  Modal path will hand an empty story fragment downstream as if it were prose.
- Reasoning accounting also differs: Modal reports `usage.reasoning_tokens` at the top level of
  `usage` (OpenRouter nests it as `completion_tokens_details.reasoning_tokens`), reports
  `prompt_tokens_details.cached_tokens`, and interleaves the reasoning text itself as
  `message.reasoning_content` (the model card advertises `interleaved.field: reasoning_content`).
  The unconstrained reply cost 42 completion tokens (31 of them reasoning) on the max_tokens 100
  call, while the max_tokens 10 calls spent their entire 10-token budget on reasoning (10-13
  reasoning tokens reported) and produced empty content; budget sizing must cover reasoning plus
  content, matching the OpenRouter finding.

**Read on usability:** the Modal leg is usable as-is through the existing `MODAL_*` config
surface: OpenAI-compatible chat completions at `<MODAL_BASE_URL>/v1/chat/completions`,
`Modal-Key`/`Modal-Secret` headers with the wk-/ws- pair, and `dig_usage` working unchanged. The
two adapter-level items before any real use: treat empty-string content like null content under
`finish_reason: "length"`, and do not expect a `cost` field. Still experimental-only per ADR-010;
nothing is wired into the production cascade. The DeepSeek V4 Pro comparison proper remains open
until that endpoint provisions; rerun this exact call plan against it when it does (the shape
checks above then need re-verifying on that model's responses).

## DeepSeek V4 Pro endpoint verdict (2026-08-21): not viable as a managed endpoint

A second provisioning attempt got further than the first: endpoint
`ep-k7GKhWPbAoEy4PZ19TvKXf` at
`https://williaby--ep-deepseek-v4-pro-server.us-west.modal.direct`, with the dashboard reporting
"App deployed in 194.827s". It never left the "Starting up" phase. From this session the endpoint
answered HTTP 503 with an empty body to every authenticated request (`/v1/models` and
`/v1/chat/completions`) across more than 15 minutes of continuous 10-20s retries. The owner then
confirmed the root cause from the Modal side: the 8 GPUs the model requires could not be
provisioned on this workspace.

Verdict: DeepSeek V4 Pro is NOT viable as a Modal managed endpoint for us today. The blocking
constraint is GPU capacity for an 8-GPU deployment, not auth, transport, or adapter shape (all
proven against the shared Kimi-K3 endpoint above). Client-side note for any retry: during
provisioning the endpoint 503s immediately rather than queueing requests, so a single long
`--max-time` call never captures cold start; time-to-ready has to be measured by polling, and
callers hitting a not-yet-ready endpoint need 503 retry handling.

Planned follow-up, deliberately out of scope here: experiment with DeepSeek V4 Pro as a Modal
container (a custom app deployment like the earlier `cyo-standard` one) rather than a managed
endpoint. Until then, the DeepSeek comparison column stays OpenRouter-only, and the measured Modal
numbers in the table above stand in via Kimi-K3. Remember to stop the stuck endpoint in the
dashboard so it does not keep retrying provisioning.
