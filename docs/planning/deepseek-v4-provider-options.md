# DeepSeek V4 Pro provider options (2026-08-20)

Working note for the provider-options investigation on branch `claude/deepseek-v4-provider-options-wd2mwy`.
Research only so far: no code changes. The next step is a live smoke test; the landing prompt for that
session is at the bottom of this document.

## Problem

`deepseek/deepseek-v4-pro` is our cheapest reliable leg for offline authoring workloads: the 2026-08-12
billing probe measured $0.0398 per call at fill rate 1.00 ($40 per 1,000 books), with 0% reasoning share,
and a full 59-book catalog fill costs about $6.42 (`generation/skeleton.py` cost note,
`docs/planning/vendor-comparison/README.md`). We reach it through OpenRouter because the workspace-level
ZDR/no-training guardrail is what makes any lab eligible at all (ADR-003 as amended 2026-07-28: eligibility
is the PII guard plus the endpoint's data policy, never lab identity).

The problem is OpenRouter's provider marketplace, not the model:

- One slug is served by several backends at different quantizations, so an unpinned run is not
  reproducible. Run-6's fp4/fp8 confound made this concrete: no provider on this account serves both
  checkpoints at fp4, so quantization and provider could not be separated
  (`docs/planning/vendor-comparison/README.md`, run-6 section).
- Backend churn and transport failures cost real runs (the `kimi-k3` leg died at the transport layer;
  pinned providers can disappear from the roster or the workspace data policy between runs).
- A pin (`provider.order` plus `allow_fallbacks: false`, already implemented in
  `generation/providers/openrouter.py`) trades availability for reproducibility: when the pinned backend
  is down, the leg is down.

## Options assessed

### 1. Tighten the OpenRouter request (cheapest change)

OpenRouter's `provider` request object supports more than the `order`/`allow_fallbacks` pair the adapter
sends today. Two fields directly address our failure mode and compose with the workspace guardrail:

- `provider.zdr: true` restricts routing to zero-data-retention endpoints for that request, making the
  ZDR constraint per-request and visible in code review rather than only a workspace setting.
- `provider.quantizations: ["fp8"]` restricts routing to backends serving the stated quantization,
  which closes the run-6 confound without pinning a single backend (routing can still fail over among
  fp8 backends).

Status: to verify live (step 4 of the smoke-test prompt below). If it works as documented, this is a
small additive change to `OpenRouterProvider` and keeps the per-token cost model unchanged.

### 2. Dedicated Modal endpoint (hard ZDR, quantization control)

Modal Endpoints serve catalog open-weight models (DeepSeek family included; `deepseek-ai/DeepSeek-V4-Pro`
is selectable) on dedicated infrastructure, OpenAI-compatible API, authenticated with a workspace proxy
token (`Authorization: Bearer wk-...ws-...` or the `Modal-Key`/`Modal-Secret` header pair). An endpoint
named `deepseek-v4-pro` has been configured in workspace `williaby`, environment `main`.

Fit with the codebase: `generation/providers/modal.py` already speaks exactly this protocol, and
`core/config.py` already carries `MODAL_BASE_URL` / `MODAL_MODEL` / `MODAL_PROXY_KEY` /
`MODAL_PROXY_SECRET`. Selecting `generation_provider=modal` is experimental-only by design (ADR-010
item 2): it is never wrapped into the production fallback cascade, which is the correct posture for this
evaluation too.

Privacy: a dedicated endpoint runs in our own containers; prompts and completions are not shared
multi-tenant state and Modal does not train on customer data. ZDR is structural rather than a policy
toggle. (Confirm terms language before relying on this for anything beyond the PII-guarded prompts.)

Economics (corrected 2026-08-20; billing is per GPU-second, not per hour): dedicated infrastructure is
billed for model load time plus processing plus a configurable idle timeout (60s default), then nothing
after scale-to-zero. At B200 rates ($0.001736/s), an 8-GPU node is about $0.0139/s.

- Batched catalog fill (59 books, ~19k in / ~7k out each): compute is minutes when books run
  concurrently; the dominant unknown is billed load time for ~1TB of weights. Ballpark 10 to 15 billed
  minutes, roughly $8 to $13 per full catalog fill, against $6.42 per-token. Same order of magnitude,
  with a fixed recipe (no quantization confound) as the payoff.
- Single-book trickle (the production request path): each isolated request pays the cold start alone,
  plausibly $3 to $6 against $0.04 per-token. Keep-warm inverts it (roughly $12/hr per warm B200).
  Per-token wins this path decisively.

The one number that settles the batch case is the actual billed cold-start seconds for the V4 Pro
recipe, read off the Modal dashboard after one smoke call. Note `modal_timeout_seconds` defaults to 180
and a cold start will exceed it; the smoke test uses curl with a 900s ceiling instead.

### 3. Direct per-token ZDR hosts

Fireworks, DeepInfra, Together, and Baseten serve DeepSeek models per-token with published no-training /
retention-control postures, and several are the same backends OpenRouter routes to. A direct leg to one
of them would remove the marketplace layer while keeping per-token economics. Not pursued yet: option 1
likely captures most of the benefit with far less new code, and each host's exact ZDR terms and V4 Pro
availability would need the same verification pass.

### 4. DeepSeek first-party API: disqualified

Cheapest per-token rates, but the first-party API's data terms do not offer the ZDR/no-training
guarantee ADR-003 requires, so it fails eligibility regardless of price.

## Recommendation

- Production request path: stay per-token. Verify and adopt option 1 (`zdr` + `quantizations` request
  fields) in `OpenRouterProvider`.
- Offline batched workloads (catalog fills, vendor-comparison and measurement runs, where
  `deepseek-v4-pro` actually lives today): evaluate the Modal endpoint (option 2) with the smoke test
  below; adopt it if the measured billed load time keeps a catalog fill in the ~$10 range.
- Decide on option 3 only if both of the above disappoint.

## Landing prompt for the smoke-test session

```text
Goal: live smoke-test our Modal endpoint for DeepSeek V4 Pro and compare it against
OpenRouter, continuing the provider-options research on branch
claude/deepseek-v4-provider-options-wd2mwy (check it out; it exists on origin).
Read docs/planning/deepseek-v4-provider-options.md on that branch for full context.

Context: We generate stories via generation/providers/openrouter.py under a
workspace ZDR/no-training guardrail (ADR-003 as amended). OpenRouter provider churn
(quantization substitution, transport failures) pushed us to evaluate a dedicated
Modal endpoint (workspace "williaby", env "main", endpoint name "deepseek-v4-pro",
model deepseek-ai/DeepSeek-V4-Pro). A ModalProvider adapter already exists
(generation/providers/modal.py) and speaks OpenAI-compatible chat completions with
Modal-Key/Modal-Secret headers. Modal inference endpoints are ZDR by design and
billed per GPU-second including model load time, so the open question is measured
cost/latency, not privacy. Environment network access was widened to allow
modal.com / *.modal.run / openrouter.ai, and Modal proxy-token env vars were added.

Do the following, in order:

1. Preflight. List env var NAMES only (mask values): confirm which of
   MODAL_BASE_URL, MODAL_MODEL, MODAL_PROXY_KEY, MODAL_PROXY_SECRET,
   OPENROUTER_API_KEY are present. The Modal token pair may have arrived under
   different names (e.g. token_id/token_secret or MODAL_TOKEN_ID/MODAL_TOKEN_SECRET);
   if so, use those values but report the mismatch, since
   core/config.py::Settings expects MODAL_PROXY_KEY/MODAL_PROXY_SECRET.
   Never print secret values. Then verify connectivity: curl -sS -o /dev/null
   -w "%{http_code}" against https://modal.com, https://api.modal.com, and
   https://openrouter.ai/api/v1/models. If Modal domains still 403 at CONNECT,
   stop and report.

2. Modal smoke test. If MODAL_BASE_URL is missing, stop and ask me for the
   endpoint URL from the Modal dashboard. Otherwise POST
   $MODAL_BASE_URL/v1/chat/completions with headers Modal-Key/Modal-Secret and body
   {"model": "<MODAL_MODEL or deepseek-ai/DeepSeek-V4-Pro>",
    "messages":[{"role":"user","content":"Reply with the single word: ok"}],
    "max_tokens": 10}
   Use curl --max-time 900 and time it: the first call may include a multi-minute
   cold start (weights are ~1TB). Record: wall-clock time, HTTP status, and the
   full JSON response body. Immediately repeat the same call twice and record
   warm latency. If auth fails (401/403), report the body; a wk-/ws- proxy token
   is required and an ak-/as- API token will not work.

3. Shape check. Compare the response JSON to what ModalProvider expects:
   choices[0].message.content non-empty, usage.prompt_tokens/completion_tokens
   present (see providers/_base.py dig_content/dig_usage). Note any mismatch
   (e.g. reasoning content, missing usage); that would be an adapter bug we'd
   need to fix before wiring it in.

4. OpenRouter comparison leg. With OPENROUTER_API_KEY, POST
   https://openrouter.ai/api/v1/chat/completions with model
   "deepseek/deepseek-v4-pro" and provider {"zdr": true, "quantizations": ["fp8"]},
   same tiny prompt. Record latency, which backend served it (the response includes
   provider info), and usage. This doubles as a live test of the zdr+quantizations
   provider fields we're considering adding to OpenRouterProvider.

5. Report back in chat: a short table (Modal cold, Modal warm x2, OpenRouter) with
   latency, tokens, and any shape problems; your read on whether the Modal leg is
   usable as-is via MODAL_* config (generation_provider=modal is experimental-only
   per ADR-010; do not wire it into the production cascade); and remind me to read
   the billed seconds for the cold start off the Modal dashboard, which settles the
   cost-per-catalog-fill estimate in docs/planning/deepseek-v4-provider-options.md.
   Keep total spend trivial (three ~10-token completions per provider). Do not
   commit or push anything unless I ask.
```
