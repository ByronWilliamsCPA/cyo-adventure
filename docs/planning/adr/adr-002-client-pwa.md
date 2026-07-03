---
title: "ADR-002: Client is a Progressive Web App"
schema_type: planning
status: accepted
owner: core-maintainer
purpose: "Record the decision to build the reader and parent tools as a Progressive Web App."
tags:
  - planning
  - architecture
  - decisions
---

# ADR-002: Client is a Progressive Web App

> **Status**: Accepted (2026-07-03; distribution premise amended by ADR-008)
> **Date**: 2026-06-20
> **Amended by**: ADR-008 (distribution: adds a Capacitor App Store shell; the web PWA remains the browser channel)

## TL;DR

Build the reader and the parent tools as a PWA (React 19, TypeScript, Vite, service
worker, IndexedDB), because reading is the core interaction and a PWA serves it fully:
installable, offline-capable, and updated by a deploy with no app-store review.

## Context

### Problem

Kids will read on mixed devices (iPads, phones, a laptop). We want easy updates and,
ideally, offline reading. The choices are native iOS/Android, a cross-platform
framework (React Native, Flutter), or a PWA.

### Constraints

- **Technical**: offline play is a first-class requirement; iOS PWAs have storage and
  install quirks to test for.
- **Business**: a private family app gets no payoff from app-store distribution, and
  app-store review is a real recurring cost.

### Significance

The client is a large build surface, but the JSON format (ADR-001) is client-agnostic,
so this decision is reversible: a native app can be added later without touching the
pipeline.

## Decision

**We will build the reader and parent tools as a PWA because it fully serves the core
reading interaction while eliminating app-store friction.** A service worker provides
offline caching and IndexedDB holds downloaded stories and progress.

### Rationale

Reading is installable to a home screen, offline-capable, and updated by a deploy with
no review queue. App-store review buys nothing for a private family app. The
client-agnostic format keeps a future native app open for any of the kids.

## Options Considered

### Option 1: PWA ✓

**Pros**:
- ✅ One codebase; offline reading; instant updates; no store friction.

**Cons**:
- ❌ Slightly less native polish; iOS PWA storage-eviction and install nuances.

### Option 2: Native iOS/Android

**Pros**:
- ✅ Best polish, native TTS.

**Cons**:
- ❌ Two codebases, app-store friction, slow updates. Overkill for a reading app.

### Option 3: React Native / Flutter

One codebase with a near-native feel, but a heavier toolchain and store friction
remains. More than a reading app needs at v1.

## Consequences

### Positive

- ✅ One codebase, offline reading, zero install friction, fast iteration.

### Trade-offs

- ⚠️ iOS PWAs can evict site data under storage pressure. Mitigation: treat IndexedDB
  strictly as a cache, never the source of truth; the canonical reading progress is the
  Postgres `reading_state` row. Call `navigator.storage.persist()` but do not trust it
  on iOS.

### Technical Debt

- Offline sync: budget service-worker and IndexedDB work into Phase 1; sync progress to
  the server on every choice while online, queue writes when offline, and reconcile on
  reconnect using the revision-based concurrency model (a stale `state_revision`
  returns 409).

## Implementation

### Components Affected

1. **PWA shell**: React 19 / Vite, service worker via vite-plugin-pwa (Workbox).
2. **Offline cache**: IndexedDB (`idb`) for stories and queued progress writes.
3. **Sync client**: revision-based reconciliation against the backend reading store.

### Testing Strategy

- E2E (Playwright): a full playthrough including offline mode, save/resume, and
  multi-device 409 reconciliation.
- Unit: the offline write queue and replay idempotency.

## Validation

### Success Criteria

- [ ] A downloaded story plays start to finish with the network disabled.
- [ ] A two-device conflict resolves without silent loss.

### Review Schedule

- Initial: Phase 1 acceptance.
- Ongoing: on iOS Safari major releases.

## Related

- [ADR-001](./adr-001-story-format-json-storybook.md): the client-agnostic format that
  keeps a native app open.
- [ADR-008](./adr-008-public-app-store-launch.md): adds a Capacitor App Store shell as a
  distribution channel; the web PWA remains the browser channel.
- [Tech Spec: Multi-device sync rules](../tech-spec.md#multi-device-sync-rules)
