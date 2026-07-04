---
title: "Modal Generation Leg: ModalProvider Adapter and Live Endpoint Smoke Test (Design)"
schema_type: planning
status: draft
owner: core-maintainer
component: Strategy
source: "docs/planning/adr/adr-010-modal-review-and-gated-generation.md; docs/superpowers/specs/2026-06-23-modal-generation-tiers-design.md; src/cyo_adventure/generation/provider.py; src/cyo_adventure/generation/providers/openrouter.py; Modal Auto Endpoints docs (https://modal.com/docs/guide/endpoints, https://modal.com/blog/introducing-auto-endpoints)"
purpose: "Design for implementing the experimental ModalProvider generation leg (ADR-010 item 2, phased-rollout step 4 of the tiered-backends spec) as an HTTP adapter mirroring OpenRouterProvider, wiring it behind generation_provider=modal without entering the production fallback cascade, and deploying one live Modal Auto Endpoint to run a real end-to-end generation and spend otherwise-unused Modal credits."
tags:
  - planning
  - architecture
  - project
---

> Branch: `feat/modal-generation-leg` (worktree `.worktrees/modal-generation-leg`) |
> Date: 2026-07-04 | Author: Byron Williams (with Claude)
> Implements ADR-010's item 2 (experimental generation leg) and executes step 4 of
> the tiered-backends spec's phased rollout
> (`docs/superpowers/specs/2026-06-23-modal-generation-tiers-design.md#12-phased-rollout`).

## 1. Problem and goal

The project holds ~$30/month of unused Modal credits (noted in the tiered-backends
spec) and an existing, but unimplemented, seam for a Modal generation leg: ADR-010
proposes it, the tiered-backends spec designs it in detail (adapter shape, model
tiers, cost model, phased rollout), and `Settings.review_provider` already reserves
the literal `"modal"` for the sibling moderation-review backend. Nobody has written
the adapter or spent a single credit. This design closes that gap for the
**generation** leg only: implement `ModalProvider`, wire it behind
`generation_provider=modal`, and deploy one live endpoint to prove the whole path
end-to-end with a real story.

**Non-goals** (tracked separately, not touched here):

- The moderation-review Modal backend (ADR-010 item 1; `review_provider="modal"`
  stays deferred).
- Skeleton-fill wiring into the worker/orchestrator (tiered-backends spec section 5;
  a later phased-rollout step). The current orchestrator is brief-driven (Stage A
  structure, Stage B prose), and this design tests the Modal leg against that
  existing pipeline unchanged, which is exactly what ADR-010 asks for: evidence on
  whether decoder-level structure enforcement helps the known Tier-2 structural
  failure mode.
- The ADR-010 promotion gate (20-brief yield harness re-run, cost-per-story
  acceptance against credit-pack pricing). This design produces one measured data
  point, not the full gate.
- A circuit breaker or device-orchestration layer. ADR-010 specifies "same Layer-1
  retry/backoff" as the existing OpenRouter adapter; no new resilience pattern is
  introduced.

## 2. Integration shape

Modal Auto Endpoints (confirmed current via Modal's own docs, not the two-week-old
edge case it first appeared to be) deploy a vLLM-backed model behind a
production OpenAI-compatible Chat Completions API, found via `modal endpoint list`.
This makes `ModalProvider` an HTTP client adapter structurally close to
`OpenRouterProvider`, not a Modal-Python-SDK client (`modal.Cls.lookup(...).remote()`)
as the unrelated `image_detection` repo's device-orchestrator pattern uses for its
own, different, arbitrary-Python-function use case. No `modal` package dependency is
added to the FastAPI app; the Modal CLI is an operator tool run out-of-band, exactly
as the tiered-backends spec states ("Modal endpoints are deployed out-of-band as
config, not maintained Python").

## 3. Components

### 3.1 `generation/providers/modal.py` (new)

`ModalProvider`, cloned in structure from `OpenRouterProvider`
(`src/cyo_adventure/generation/providers/openrouter.py`):

- Same `run_with_retries` Layer-1 retry/backoff (`_base.py`), same transient-vs-leg-fatal
  HTTP status split (429/5xx transient; 400/401/402/403/404 leg-fatal), same
  `strip_code_fences` output normalization.
- **Differences from OpenRouterProvider**: no `reasoning`/`effort` request field (the
  served model is not Anthropic); a longer default per-attempt timeout to tolerate
  cold starts (config knob, not hardcoded); `name` property returns
  `f"modal:{self._model}"` for worker provider-record logging.
- Constructor takes `base_url`, `model`, `proxy_key`, `proxy_secret`,
  `timeout_seconds`, `max_retries`, `backoff_base_seconds`, and an optional
  injected `httpx.AsyncClient` for tests, matching the existing adapters' test
  seam. `proxy_key`/`proxy_secret` are sent as the `Modal-Key`/`Modal-Secret`
  header pair, not a Bearer token: confirmed against Modal's docs (not just
  assumed) during the 2026-07-04 live deployment attempt, when `modal endpoint
  create` rejected the original Bearer-token assumption. Both headers are
  omitted entirely unless both values are set; a half-set pair sends neither,
  never a partial credential.

### 3.2 Settings (`core/config.py`)

- `generation_provider: Literal["mock", "claude", "ollama", "openrouter", "modal"]`
  (adds `"modal"` to the existing literal).
- `modal_base_url: str` (the live endpoint URL from `modal endpoint list`; no
  default, required when `generation_provider="modal"`).
- `modal_model: str` (the served model id, for logging/provider-record purposes;
  distinct from the HF id used at `modal endpoint create` time).
- `modal_proxy_key: str | None` and `modal_proxy_secret: str | None` (the
  Modal-Key/Modal-Secret proxy-token pair, created via `modal workspace
  proxy-tokens create`; must be set together or neither, since a half-set pair
  is a misconfiguration `build_modal_leg` rejects rather than guesses at).
- `modal_timeout_seconds: int` (separate from `llm_timeout_seconds`; cold starts
  need materially more headroom than a warm OpenRouter call).

### 3.3 `build_modal_leg` + `build_provider` branch (`provider.py`)

- `build_modal_leg(settings)` mirrors `build_openrouter_leg`: raises
  `ConfigurationError` naming the missing setting (`MODAL_BASE_URL`), never a value,
  when required config is absent.
- `build_provider` gains a `provider == "modal"` branch returning the **bare**
  `ModalProvider`: no `FallbackProvider` wrapping. This leg never enters the
  production cascade (`openrouter -> ollama`); selecting it is a deliberate,
  explicit, offline-only choice, matching ADR-010's "not on the public path."

## 4. Deployment plan (spends real credits; confirm before each command)

1. **Auth** (interactive, operator-run): `modal token new` opens a browser OAuth
   flow. This is not something a non-interactive session can drive; either it is
   already done, or the user runs it themselves before the next step.
2. **Deploy**: `modal endpoint create --name cyo-standard --model <HF id for
   Gemma 26B-A4B>`. The exact HF identifier and whether Modal's curated catalog
   covers it directly or needs `--custom-hf-repo` is **unverified** as of this
   design; confirmed against Modal's current supported-model list immediately
   before running the command, not guessed here.
3. **Capture the endpoint**: `modal endpoint list` returns the live URL; it goes
   into `.env` as `MODAL_BASE_URL` (never committed).
4. Every command in this section that provisions or runs billed GPU time gets a
   separate, explicit go-ahead at execution time, independent of this design's
   approval: this is real infrastructure and real money, not a reversible local
   edit.

## 5. Live smoke test

With `generation_provider=modal` pointed at the deployed endpoint, run the existing
generation worker against a real brief for the 8-11 reading band (the band
`skeletons/8-11/the-cave-of-echoes.json` already targets, though this test exercises
the freeform brief-driven pipeline, not that skeleton). Record: whether Stage A/B
complete without a leg-fatal error, whether the resulting story clears the existing
gates, and the measured cost (GPU-seconds x $/hr) for one story. This single data
point feeds, but does not by itself satisfy, the ADR-010 promotion gate.

## 6. Testing

Unit tests for `ModalProvider` mirror the existing OpenRouter adapter test suite
(transient failure -> retry, leg-fatal status -> immediate `ProviderError`,
markdown-fence stripping) against an injected `httpx.AsyncClient`, so CI makes no
real network call. `generation_provider` default remains `"mock"`; CI and local dev
are unaffected by this change.

## 7. Security and data policy

`modal_proxy_key` and `modal_proxy_secret` (if present) and the endpoint URL are
secrets: never logged, and `ConfigurationError` messages name the setting, never
its value, mirroring the
existing OpenRouter/Ollama credential handling in `provider.py`. Per ADR-010 and the
tiered-backends spec, self-hosting on Modal means the served model's creator never
receives the prompt, which is the same privacy posture already documented for the
review leg.

## 8. Open items to verify during implementation

- Exact HF model identifier for the Gemma 26B-A4B tier and whether `modal endpoint
  create` needs `--custom-hf-repo` for it.
- RESOLVED: Modal Auto Endpoints require an explicit choice at creation time,
  either `--unauthenticated` or a pre-created proxy token; there is no silent
  default. Discovered when `modal endpoint create` rejected the original
  Bearer-token assumption during the 2026-07-04 live deployment attempt, which
  led to the `proxy_key`/`proxy_secret` (`Modal-Key`/`Modal-Secret` header pair)
  design described in sections 3.1, 3.2, and 7 above.
- Actual per-request cold-start latency, to size `modal_timeout_seconds` from
  measurement rather than the spec's estimate.

## References

- [ADR-010](../../planning/adr/adr-010-modal-review-and-gated-generation.md)
- [Tiered-backends design](2026-06-23-modal-generation-tiers-design.md)
- Provider protocol / factory: `src/cyo_adventure/generation/provider.py`
- Adapter to mirror: `src/cyo_adventure/generation/providers/openrouter.py`
- Modal Auto Endpoints: <https://modal.com/blog/introducing-auto-endpoints>,
  <https://modal.com/docs/guide/endpoints>
