---
title: "ADR-004: Homelab-first deployment, Azure as the scale-out alternative"
schema_type: planning
status: accepted
owner: core-maintainer
purpose: "Record the decision to deploy to the homelab first with cloud-portable containers."
tags:
  - planning
  - architecture
  - decisions
---

# ADR-004: Homelab-first deployment, Azure as the scale-out alternative

> **Status**: Accepted (2026-07-10; deployed and live behind Pangolin at
> `cyo.williamshome.family` since the R1 rollout on 2026-07-05, with nightly Postgres
> backups running on docker-host; guardian auth on this deployment runs on Supabase per
> [ADR-009](./adr-009-supabase-platform.md) rather than Authentik as originally decided
> here; the MinIO object-storage leg and a formal restore drill remain outstanding under
> Phase 5 hardening)
> **Date**: 2026-06-20
> **Amended by**: ADR-008 (public-tier hosting), ADR-009 (Supabase platform); ADR-004 still governs the dev and family/homelab tier

## TL;DR

Deploy to the homelab first (containers behind Pangolin zero-trust ingress, Authentik
for internal homelab-service SSO, with Postgres, Redis, and MinIO as services), keeping
containers cloud-portable so Azure Container Apps is a drop-in alternative, because
self-hosting keeps minors' data on hardware we control. App-level guardian and child
authentication runs on Supabase Auth (OIDC) per [ADR-009](./adr-009-supabase-platform.md),
not Authentik.

## Context

### Problem

The data is the children's reading activity, which argues for a strong privacy posture.
We already run a zero-trust homelab (Pangolin, Authentik, Docker, Dockge) and could
instead deploy to Azure.

### Constraints

- **Technical**: homelab uptime and backups become our responsibility.
- **Business**: avoiding third-party telemetry on children is a core requirement; the
  existing stack already provides ingress and auth, so the marginal infrastructure is
  small.

### Significance

Provider-specific services would create lock-in. Using plain containers and the S3 API
keeps a move to Azure cheap if we ever outgrow the homelab.

## Decision

**We will deploy to the homelab first, behind Pangolin (with Authentik for internal
homelab-service SSO), with Postgres, Redis, and MinIO as services, because self-hosting
keeps minors' data private and reuses infrastructure we already run well.** App-level
guardian and child authentication is Supabase Auth (OIDC) per
[ADR-009](./adr-009-supabase-platform.md), not Authentik. Containers stay cloud-portable
so Azure Container Apps is a drop-in alternative.

### Rationale

Self-hosting keeps minors' data on controlled hardware, the right privacy posture, and
avoids third-party telemetry on children. The existing stack already provides ingress
and auth. Cloud portability via plain containers means we can move to Azure for
always-on uptime and managed backups if the need arises.

## Options Considered

### Option 1: Homelab-first, cloud-portable ✓

**Pros**:
- ✅ Data stays private; reuses infrastructure we run well; portable.

**Cons**:
- ❌ Homelab uptime and backups are on us.

### Option 2: Azure Container Apps first

**Pros**:
- ✅ Managed uptime and backups; always-on.

**Cons**:
- ❌ Puts minors' data on third-party infrastructure; weaker privacy posture for v1.

## Consequences

### Positive

- ✅ Data stays private; existing ingress and auth are reused; the design stays
  portable.

### Trade-offs

- ⚠️ Uptime and backups are self-managed. Mitigation: nightly Postgres dump and MinIO
  snapshot, with a restore drill in Phase 5.
- ⚠️ The "no minors' data on third-party infrastructure" stance is amended for the
  **public tier** by [ADR-008](./adr-008-public-app-store-launch.md) and
  [ADR-009](./adr-009-supabase-platform.md): the public tier runs on Supabase-managed
  Postgres, a US processor. ADR-004 continues to govern the dev and family/homelab tier.
- ⚠️ **Scope clarification (2026-07-28).** This ADR's "avoid third-party telemetry on
  children" stance is about **where minors' data is stored and what observes their
  behavior**: hosting, telemetry, analytics, and ad SDKs. It is not, and never was, a
  vendor-selection rule for the outbound generation call. That call carries no registered
  child identifier by construction ([ADR-003](./adr-003-frontier-llm-generation.md)'s
  2026-07-28 amendment and the `generation/pii.py` hard fail), so ADR-003 cites this ADR
  for its privacy *posture*, not as a source of provider restrictions. Reading it as the
  latter is what produced the Anthropic/Google-only production rule that the ADR-003
  amendment retires.

### Technical Debt

- No provider-specific services in the core. Object storage goes through the S3 API so
  MinIO and Azure Blob are interchangeable.
- The R1 internal-web deploy (`services/cyo-adventure/` in the separate
  `ByronWilliamsCPA/homelab-infra` repo) uses nginx as the ingress point, reverse-proxying
  `/api` to the backend container internally, rather than Pangolin forwarding to it
  directly. This is a distinct rung from the Pangolin-and-Authentik ingress described
  above, not yet reconciled into a single documented topology.

## Implementation

### Components Affected

1. **Ingress and auth**: Pangolin (zero-trust ingress) and Authentik (internal
   homelab-service SSO only); app-level guardian and child authentication is Supabase
   Auth (OIDC) per [ADR-009](./adr-009-supabase-platform.md).
2. **Stateful services**: Postgres, Redis, MinIO as containers orchestrated via Dockge.
3. **Storage abstraction**: S3 API for story blobs.

### Testing Strategy

- Integration: a placeholder service reachable end to end over the zero-trust path
  (Phase 0).
- Operational: a backup restore drill (Phase 5).

## Validation

### Success Criteria

- [x] Deployed behind Pangolin with Supabase Auth login for guardians/children (live
  since 2026-07-05; Authentik remains internal homelab-service SSO only).
- [ ] A restore from backup succeeds in a drill.

### Review Schedule

- Initial: Phase 0 hosting milestone (PL-12).
- Ongoing: if uptime needs exceed homelab capacity.

## Related

- [ADR-003](./adr-003-frontier-llm-generation.md): the external generator call this
  posture constrains.
- [ADR-008](./adr-008-public-app-store-launch.md): public-tier hosting that amends this
  posture for the commercial tier.
- [ADR-009](./adr-009-supabase-platform.md): the Supabase managed platform adopted for
  the public tier's auth, database, and storage.
- [Tech Spec: Infrastructure](../tech-spec.md#infrastructure)

## Amendment (2026-08-22): the deployment target is moving off the homelab, to Vultr

### What this amendment records, and what it does not decide

The deployment target is moving off the homelab this ADR's Decision describes, to Vultr
cloud hosting. This amendment **records a decision already being acted on elsewhere in
this change set; it does not make that decision here.** The visible, already-shipped
consequence is the retirement of the local Ollama generation leg: a self-hosted model has
no home once the homelab that served it goes away, so retiring that leg ahead of the move
is a direct, immediate consequence of the move rather than an independent choice. See
ADR-003's [2026-08-18 amendment][adr003-amend] and ADR-010's
[2026-08-22 amendment][adr010-amend] for what replaced it.

[adr003-amend]: ./adr-003-frontier-llm-generation.md#amendment-2026-08-18-the-ollama-leg-is-retired-and-modal-takes-leg-3
[adr010-amend]: ./adr-010-modal-review-and-gated-generation.md#amendment-2026-08-22-modal-is-cascade-leg-3-not-primary

### What is NOT recorded here

No instance sizing, region, timeline, or cost figures for the Vultr move are recorded
anywhere in this repository as of this amendment. Every reference this amendment could
find (`docs/architecture/deployment.md`, `docs/planning/roadmap.md`,
`core/pricing.py`, and the retirement migration
`supabase/migrations/20260818120000_retire_ollama_provider.sql`) states only that the
Ollama leg's retirement is "ahead of the homelab-to-Vultr move", with no further detail
given anywhere. That detail is not yet recorded, and this amendment does not invent it.

### Outstanding work

**The full migration decision record, the Vultr counterpart to this ADR's homelab
decision, is still outstanding.** Until it exists:

- The Pangolin/Authentik ingress, the R1 nginx topology
  (`services/cyo-adventure/` in the separate `ByronWilliamsCPA/homelab-infra` repo), and
  the docker-host backup regime this ADR's Decision and Consequences describe remain the
  last fully-recorded deployment topology.
- This ADR's `Status` line ("Accepted...deployed and live behind Pangolin...") is
  deliberately left unchanged by this amendment, because the move has not completed as of
  this writing; a future amendment, or a dedicated ADR once the migration record exists,
  should update it when Vultr hosting is actually live.
- No `UW-*` register entry currently tracks writing that migration record; this amendment
  flags the gap rather than assigning it an ID it cannot verify.

### Related

- [ADR-003](./adr-003-frontier-llm-generation.md#amendment-2026-08-18-the-ollama-leg-is-retired-and-modal-takes-leg-3):
  the Ollama-retirement consequence of this move.
- [ADR-010](./adr-010-modal-review-and-gated-generation.md#amendment-2026-08-22-modal-is-cascade-leg-3-not-primary):
  the leg that replaced it.
