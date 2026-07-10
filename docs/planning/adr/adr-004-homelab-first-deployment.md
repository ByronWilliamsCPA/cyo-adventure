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
for SSO and roles, with Postgres, Redis, and MinIO as services), keeping containers
cloud-portable so Azure Container Apps is a drop-in alternative, because self-hosting
keeps minors' data on hardware we control.

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

**We will deploy to the homelab first, behind Pangolin and Authentik, with Postgres,
Redis, and MinIO as services, because self-hosting keeps minors' data private and
reuses infrastructure we already run well.** Containers stay cloud-portable so Azure
Container Apps is a drop-in alternative.

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

1. **Ingress and auth**: Pangolin (zero-trust) and Authentik (OIDC, guardian and child
   roles).
2. **Stateful services**: Postgres, Redis, MinIO as containers orchestrated via Dockge.
3. **Storage abstraction**: S3 API for story blobs.

### Testing Strategy

- Integration: a placeholder service reachable end to end over the zero-trust path
  (Phase 0).
- Operational: a backup restore drill (Phase 5).

## Validation

### Success Criteria

- [ ] Deployed behind Pangolin with Authentik login.
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
