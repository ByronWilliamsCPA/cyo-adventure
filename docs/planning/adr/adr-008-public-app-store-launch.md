---
title: "ADR-008: Public App Store launch with tiered subscription monetization"
schema_type: planning
status: proposed
owner: core-maintainer
purpose: "Record the decision to take CYO Adventure public via the Apple App Store with a
  tiered family subscription, and the auth, hosting, and compliance pivots that requires."
tags:
  - planning
  - architecture
  - decisions
  - monetization
---

# ADR-008: Public App Store launch with tiered subscription monetization

> **Status**: Proposed
> **Date**: 2026-07-02
> **Amends**: [ADR-002](./adr-002-client-pwa.md) (distribution), [ADR-004](./adr-004-homelab-first-deployment.md) (hosting for the public tier)
> **Amended by**: [ADR-009](./adr-009-supabase-platform.md) (2026-07-02): Supabase
> replaces the Authentik broker and the Azure-hosted service set for the public tier;
> the distribution, monetization, and compliance decisions below stand

## TL;DR

Take the app public through the Apple App Store as a Capacitor-wrapped iOS app with a
tiered family subscription (free curated library, paid family plan, metered custom-story
generation credits), authenticating guardians only, through Authentik as the single OIDC
broker with Sign in with Apple and Google as federated sources, on hosted infrastructure;
children remain in-app profiles with backend-issued scoped sessions, never IdP identities.

> **Amendment note (2026-07-02)**: the auth-broker and hosting choices in this ADR were
> superseded the same day by [ADR-009](./adr-009-supabase-platform.md): Supabase Auth
> replaces the Authentik broker, and the Supabase platform plus one container host
> replaces the Azure-hosted service set. The sections below are retained unedited as the
> decision record; parts marked "superseded" must be implemented from ADR-009. The
> distribution, guardian-only identity model, monetization, and compliance decisions
> stand as written.

## Context

### Problem

The v1 scope (family-only, homelab, no monetization; ratified decision 4 in
`docs/phase0-decisions.md`) deliberately excluded public distribution. The owner has now
decided to offer the app publicly to earn revenue. That decision forces four linked
pivots that are expensive to reverse and must be recorded together:

1. **Distribution**: the App Store rejects thin web wrappers (Guideline 4.2) and the
   current client is a PWA with no native shell.
2. **Authentication**: `api/deps.py` is a dev-only stub; there is no signup, no
   multi-tenant provisioning, and Guideline 4.8 requires Sign in with Apple whenever any
   third-party login (Google) is offered.
3. **Monetization**: digital content consumed in-app must use Apple In-App Purchase
   (Guideline 3.1.1); Kids Category apps must put purchases behind a parental gate.
4. **Compliance and hosting**: a child-directed public app triggers Kids Category rules
   (Guidelines 1.3, 5.1.4), COPPA and GDPR-K, in-app account deletion (Guideline
   5.1.1(v)) with Sign in with Apple token revocation, and the homelab cannot serve
   public traffic with the required availability.

### Constraints

- **Technical**: the `Principal` auth seam, family/guardian/child authorization model,
  publish state machine, and moderation pipeline already exist and must be reused, not
  rebuilt. The generated OpenAPI client contract and offline-first reader must survive
  the packaging change.
- **Business**: the safety pipeline (validation gate, moderation, mandatory guardian
  approval per [ADR-005](./adr-005-mandatory-human-approval.md)) is the product's core
  differentiator and its App Store review defense; nothing in this pivot may weaken it.
- **Regulatory**: children must not become identifiable accounts in any third-party
  identity provider; child-linked data classification and deletion-readiness in
  `docs/planning/privacy-model.md` become externally enforceable obligations (COPPA,
  GDPR-K), not just house rules.

### Significance

This is the largest scope change since Phase 0: it converts a single-tenant family tool
into a multi-tenant commercial product. The choices below (broker topology, who gets an
IdP identity, IAP model, hosting split) each lock in integration work that would be
costly to unwind.

## Decision

**We will launch publicly on the Apple App Store as a Capacitor shell around the
existing PWA, sell a tiered family subscription through Apple In-App Purchase, keep
Authentik as the sole OIDC issuer brokering Sign in with Apple and Google for guardians
only, and run the public tier on hosted infrastructure.**

*(As amended by ADR-009: read "Authentik as the sole OIDC issuer" as "Supabase Auth as
the sole token issuer" and "hosted infrastructure" as "the Supabase platform plus one
container host". The rest of the statement is current.)*

The decision decomposes into five parts:

1. **Distribution: Capacitor iOS shell.** The React PWA is wrapped in a Capacitor shell
   with native affordances (Keychain token storage, `ASWebAuthenticationSession` login,
   offline-first launch, iPad layouts). The web PWA remains the browser channel and the
   basis for a later Android build. This amends ADR-002's "no app-store friction"
   rationale: the format and client stay the same; only packaging is added.
2. **Auth: Authentik as broker, guardians only.** *(Broker choice superseded by
   ADR-009: Supabase Auth is the issuer. The guardian-only identity model, the
   `sub`-not-email keying, and the child-session design in this part stand.)*
   Authentik remains the single OIDC
   issuer; Sign in with Apple and Google are federated sources configured in Authentik.
   The backend validates only Authentik-issued JWTs (issuer, audience, signature,
   expiry, via cached JWKS) and keys users on the Authentik `sub` claim
   (`User.authn_subject`), never on email (Apple private relay makes email unstable).
   Children never get IdP identities: a child session is a guardian-authorized profile
   selection for which the backend mints its own short-lived, single-profile scoped
   token. `require_principal` accepts both token types and produces the same
   `Principal`.
3. **Monetization: tiered subscription via Apple IAP.** Free tier (curated starter
   library, zero marginal cost), family subscription (full catalog, multiple child
   profiles, offline downloads, read-aloud when Phase 4b lands), and metered
   custom-story generation credits (caps LLM spend exposure; generation cost on the
   Haiku-primary roster is cents per story). Purchases sit behind the parental gate.
   Enroll in the Small Business Program (15% commission). No ads, ever, in the kid
   experience.
4. **Hosting: public tier on hosted infrastructure.** *(Topology superseded by
   ADR-009: the public tier runs on Supabase plus a single container host; Azure
   Container Apps remains only a candidate for that host. The homelab-stays-dev/family
   split stands.)* The public deployment runs on
   cloud infrastructure (Azure Container Apps is the pre-planned portable target per
   ADR-004), including a production-grade Authentik. The homelab remains the
   development and family-staging environment. This supersedes ADR-004's homelab-first
   posture for the public tier only.
5. **Compliance: Kids Category posture.** Verifiable parental consent at signup, a
   published privacy policy, privacy nutrition labels derived from the existing
   child-linked data classification, in-app account deletion with Apple token
   revocation, no third-party ad or analytics SDKs transmitting identifiable data from
   the kid context, and a parental gate in front of settings, purchases, generation,
   and external links. Children never trigger generation and never see raw model
   output; review notes will document the pre-moderated pipeline explicitly.

### Rationale

Each part picks the option that reuses what exists. Capacitor preserves the React
codebase and generated client; Authentik-as-broker means one issuer, one JWKS, and zero
Apple-specific code in the backend while satisfying Guideline 4.8; guardian-only IdP
identities keep child PII out of third-party systems entirely, which is both the
strongest COPPA posture and the cheapest one; the subscription model matches the buyer
(a parent paying for an ongoing supply of safe stories) and the metered credit add-on
converts the pipeline's marginal cost into margin; the hosting split keeps minors'
family-tier data private while giving the public tier real availability.

## Options Considered

### Option 1: Capacitor shell + Authentik broker + IAP subscription ✓

**Pros**:

- ✅ Reuses the entire existing frontend, auth seam, and authorization model.
- ✅ One OIDC issuer; Apple and Google are configuration, not code.
- ✅ Strongest child-privacy posture (no child IdP identities).

**Cons**:

- ❌ Operating Authentik publicly makes login a self-managed availability concern.
- ❌ Apple commission (15% under Small Business Program) on all in-app revenue.

### Option 2: Native rewrite (Swift/React Native) + managed IdP (Auth0/Clerk/Cognito)

**Pros**:

- ✅ Best-feeling native client; IdP availability outsourced.

**Cons**:

- ❌ Rewrites a working, tested offline reader and player; months of duplicated effort.
- ❌ Per-user IdP pricing; migration away from Authentik the owner already operates.

### Option 3: Stay web-only (PWA) with Stripe subscriptions

**Pros**:

- ✅ No Apple commission, no review process, no shell work.

**Cons**:

- ❌ Forfeits App Store discovery, the primary acquisition channel for parents.
- ❌ iOS PWA installation friction and storage eviction undermine the offline promise.

## Consequences

### Positive

- ✅ Revenue path with tiered pricing and controlled marginal cost.
- ✅ Auth becomes real (the dev stub is retired), benefiting the family tier too.
- ✅ The safety pipeline becomes a marketable differentiator, not just an internal rule.

### Trade-offs

- ⚠️ Kids Category and COPPA obligations become externally enforceable. Mitigation: a
  dedicated compliance phase with a sign-off checklist before submission.
- ⚠️ Public LLM generation is a cost-abuse surface. Mitigation: metered credits,
  per-family quotas, global cost caps, rate limiting.
- ⚠️ App Store review is a rejection risk (4.2 wrappers, kids' AI content). Mitigation:
  native affordances in the shell, parental gate, TestFlight beta, detailed review
  notes on the pre-moderated pipeline.

### Technical Debt

- The Sign in with Apple client secret is a signed JWT valid at most 6 months; key
  rotation must be operationalized (calendar + runbook) or logins silently break.
- Apple returns name and email exactly once at first authorization; Authentik source
  mapping must capture them at that moment.
- Account deletion must call Apple's token-revocation endpoint; deletion is not
  complete without it.

## Implementation

### Components Affected

1. **`api/deps.py`**: `_extract_subject` becomes real JWT validation (cached JWKS);
   the import-time environment guard is removed; a second branch accepts backend-minted
   child-session tokens.
2. **`core/config.py`**: `oidc_issuer`, `oidc_audience`, `oidc_jwks_url`, entitlement
   and quota settings, with non-local fail-fast validators (existing pattern).
3. **Onboarding**: JIT guardian provisioning (first login creates Family + guardian
   User) plus verifiable parental consent capture.
4. **Entitlements**: subscription state and generation-credit ledger in Postgres,
   enforced in the library and generation APIs; App Store Server Notifications (or
   RevenueCat) drive state transitions.
5. **Publishing state machine**: a curated public-catalog state on top of the existing
   family-scoped `published` state; admin curation reuses the approval spine.
6. **Frontend**: OIDC Authorization Code + PKCE, tokens out of `localStorage`
   (memory + silent refresh on web, Keychain in the shell), profile picker, parental
   gate, paywall and restore-purchases screens.
7. **Infra**: hosted Postgres/Redis/object storage/Authentik; live moderation
   classifiers mandatory; rate limiting; Sentry; backups and restore drill.

### Testing Strategy

- Auth negative tests: expired, wrong-issuer, wrong-audience, algorithm-confusion
  tokens; cross-tenant IDOR extended to stranger families.
- Child-session tests: child token cannot reach guardian, purchase, or generation
  endpoints; offline reading works for the token's full lifetime.
- Sandbox IAP tests: purchase, renewal, expiry, refund, restore; entitlement
  transitions verified server-side.
- Deletion test: full family erasure including Apple token revocation, verified
  against the child-linked data classification.

## Validation

### Success Criteria

- [ ] A stranger can install from the App Store, sign up with Apple or Google, and see
      only their own family's data.
- [ ] App Store approval obtained (first or second submission).
- [ ] Sandbox subscription lifecycle drives entitlements correctly end to end.
- [ ] Account deletion erases all family data and revokes Apple tokens.

### Review Schedule

- Initial: Phase 6 exit (auth live behind a flag).
- Pre-submission: Phase 7 compliance checklist sign-off.
- Ongoing: quarterly against App Store guideline changes.

## Related

- [ADR-002](./adr-002-client-pwa.md): the PWA this shell wraps (amended, not replaced).
- [ADR-004](./adr-004-homelab-first-deployment.md): superseded for the public tier;
  still governs dev and the family tier.
- [ADR-005](./adr-005-mandatory-human-approval.md): the approval guarantee this launch
  markets and must preserve.
- [Privacy model](../privacy-model.md): data classification that becomes the privacy
  nutrition label and deletion contract.
- [PROJECT-PLAN.md](../PROJECT-PLAN.md): Track 2 (Phases 6 through 9) implements this
  decision.
