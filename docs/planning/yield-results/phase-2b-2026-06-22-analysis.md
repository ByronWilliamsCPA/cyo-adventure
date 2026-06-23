---
title: "Phase 2b yield measurement: 2026-06-22 analysis"
schema_type: planning
status: draft
owner: core-maintainer
purpose: "Record the first live yield measurement, the bugs fixed to get there, and the remaining work to reach the 60% acceptance gate."
tags:
  - planning
  - generation
---

# Phase 2b yield measurement (2026-06-22)

## Result

Live end-to-end yield over the 20-brief sample
([phase-2b-briefs.json](./phase-2b-briefs.json)), primary leg measured in isolation
(`--no-fallback`), on `openrouter:anthropic/claude-haiku-4.5`:

| Run | Pass rate | Tier-1 | Tier-2 |
| --- | --- | --- | --- |
| Initial | 30% (6/20) | 38% (5/13) | 14% (1/7) |
| After self-check + orphan-delete fixes | 70% (14/20) | 85% (11/13) | 43% (3/7) |

The second run is the committed [results JSON](./phase-2b-2026-06-22.json).

**AC #2 (>=60% gate pass over a 20-story sample) is met at 70%.** AC #1 (live providers
wired behind the interface, provider swap is a config change) is also met.

The 30%->70% jump came from two prompt changes: a "verify before you respond" self-check
in the structure prompt (walk the graph and delete/​wire unreachable nodes, reconcile the
ending count, recount depth) and flipping the repair strategy for orphans from "wire it
in" to "delete the spurious node". The lesson: structured-output models satisfy the
validator far better when told to check their own output against the exact rules before
emitting, rather than relying on upstream instruction-tuning alone.

## Bugs found and fixed via live testing (all committed this session)

The pipeline was non-functional against live providers before these; each was invisible
to the mock-based unit tests:

1. **`reasoning` param truncated output.** Enabling Claude reasoning (even `low`) spent
   the whole `max_tokens` on thinking tokens and returned empty content
   (`finish_reason=length`). Fix: `llm_effort` defaults to `off`; the adapter omits the
   `reasoning` param unless explicitly opted in.
2. **`max_tokens` ceilings truncated JSON.** 4096 (Stage A) / 8192 (Stage B, repair)
   truncated larger stories mid-document, surfacing as L1-1 "not valid JSON". Raised to
   16384 / 32000 (a ceiling is free; providers bill tokens generated).
3. **Depth budget under-specified.** Models overshot the L1-7 branch-depth cap. The
   structure prompt now prescribes the SHAPE (at most `max_depth` forward stages,
   reconverging branches, trace-and-recount before finishing). Cut Sonnet depth 15 -> 9.
4. **Repair could not fix global L1-7 breaches.** Branch-depth findings have no
   `node_id`, so the repair prompt's failing-node list was `(none)` and told the model to
   change nothing. Repair now permits graph restructuring when the violation is
   story-wide.
5. **Markdown code fences.** Gemini Flash and Haiku wrap JSON in ```json fences; the
   adapter now strips them (the original probe models did not, so this was missed).

## Model selection

Sonnet (the original primary) is reliable but expensive (~$6-10 for a clean 20-brief
run, because non-truncated full-prose generation is output-token-heavy). Evaluated
cheaper Anthropic/Google primaries (ADR-004 / ADR-003 policy):

- `anthropic/claude-haiku-4.5` ($5/Mtok out, 3x cheaper than Sonnet): clean first-try
  Stage A on the depth-prone brief; chosen for this measurement.
- `google/gemini-2.5-flash` ($2.50/Mtok out, fastest): cheapest, but blocked on L1-7 for
  the test brief.

## Residual failures (polish; the gate is already met)

The 6 remaining `needs_review` briefs are mostly Tier-2 (stateful): Tier-1 is 85% but
Tier-2 is 43%. They still fail on **L1-3** (orphan nodes) and **L1-7** (budget), and a few
on **L1-4** (graph termination), with the repair loop exhausting its 3 attempts. AC #2 is
met, so these are optional quality improvements, not blockers.

Proposed next steps to lift Tier-2 (do them on a cheap primary; Haiku is fast and ~$2/run):

1. **Orphan strategy (L1-3).** Models emit spurious extra nodes nothing points to. The
   repair's orphan pattern says "wire the orphan in"; for spurious nodes, **deleting** them
   is more reliable. Add a structure-prompt final check ("every node id must be a choice
   `target` or the `start_node`; delete any node nothing reaches") and a repair pattern
   that prefers deletion of unreferenced nodes.
2. **Ending-count enforcement (L1-7).** Models miscount endings vs `metadata.ending_count`.
   Add an explicit final reconciliation step.
3. **Tier-2 is much worse (14%).** Stateful stories trip Layer-2 state rules; they likely
   need state-aware structure guidance and may warrant a separate prompt path.
4. **Consider raising `max_repairs`** above 3 only if attempts show progress (most here hit
   the no-progress abort, so more attempts of the same strategy will not help; improve the
   strategy first).
5. Re-measure on Haiku, then a Sonnet confirmation run once Haiku clears 60%.

## Infra / policy notes

- **Ollama** leg: network access provisioned 2026-06-23. The raw `:11434` path TCP-timed-out
  from WSL2; the host is now reached over HTTPS at `https://ollama.svc.williamshome.family`
  (Traefik + Authentik), no explicit port. The adapter reads `OLLAMA_BASE_URL` + `OLLAMA_AUTH`
  (HTTP Basic) and maps the unauthenticated 302 to a leg-fatal error. Server serves `qwen3:30b`.
  Leg yield still to be measured now that the path is open.
- **Provider data policy**: the Anthropic/Google allowlist is worth revisiting as a
  criteria-based policy (no real child data reaches the model; only fictional briefs do).
  A follow-up, not a Phase 2b blocker.
