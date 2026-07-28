---
title: "Spec: Backend-unreachable interstitial for guardian auth"
schema_type: planning
status: draft
owner: core-maintainer
purpose: "Give the principal-unresolved auth-failure branch a dedicated retry interstitial so a transient backend outage degrades gracefully instead of trapping guardians in a silent login loop."
tags:
  - planning
  - frontend
  - auth
  - resilience
component: Development-Tools
source: "Prod/staging login-loop incident 2026-07-23 (docker-host power outage); root-cause in AuthContext.syncPrincipal catch"
---

# Spec: Backend-unreachable interstitial for guardian auth

> **Tracking issue:** [#452](https://github.com/ByronWilliamsCPA/cyo-adventure/issues/452).
>
> **Line anchors verified against `main` at `e2720c7` (2026-07-28).** Source locations are
> given as code spans with line ranges rather than links: no other document under `docs/`
> links outside `docs_dir`, and MkDocs runs with `strict: true`, so a relative
> `../../frontend/...` link fails the docs build.

## 1. Problem

When a guardian completes Google (or password) sign-in, `AuthContext.syncPrincipal`
establishes a Supabase session, then resolves the backend principal via
`POST /v1/onboarding` and `GET /v1/me`
(`frontend/src/auth/AuthContext.tsx:163-199`).

Every failure of that resolution funnels into one catch block
(`frontend/src/auth/AuthContext.tsx:200-219`): it calls `safeRemoveToken()`, sets
`status='signed-out'` and `authError='principal-unresolved'`. `ProtectedRoute` then
falls through to its default and redirects to the login page
(`frontend/src/auth/ProtectedRoute.tsx:66-68`), where a re-fired
`onAuthStateChange`/`getSession` re-runs the same failing resolution. Result: an
**infinite login loop**.

The `awaiting-approval` and `needs-consent` statuses each have a dedicated
interstitial route that breaks this loop
(`frontend/src/auth/ProtectedRoute.tsx:59-64`, `frontend/src/routes.ts:16-23`).
`principal-unresolved` is the **only** non-signed-in branch with no such interstitial,
so it degrades to the looping default. `ProtectedRoute` already carries the reasoning
in its own comments (lines 55-58): interstitial statuses are routed to their page
"rather than looping them through login". This spec adds the missing fourth branch of
an established pattern, not a new one.

**Incident that surfaced it (2026-07-23):** a homelab docker-host power outage took
the backend offline for both prod and staging. Google/Supabase auth (cloud) kept
working and the PWA served its cached shell, so guardians hit exactly this branch:
`POST /v1/onboarding` timed out (`ERR_CONNECTION_TIMED_OUT`), and the app looped
them back to login with no explanation. See memory
`cyo-host-down-login-loop-pattern`.

The bug is not the outage; it is that a **transient, recoverable** infrastructure
failure is handled identically to a **terminal, non-recoverable** auth rejection.

## 2. Goal and non-goals

**Goal.** Distinguish transient backend-unreachability from genuine auth rejection.
On transient failure, route the guardian to a dedicated interstitial that:
explains the situation in plain language, preserves the Supabase session, and
offers retry (manual, plus gentle bounded auto-retry) so recovery needs no
re-login. On terminal failure, keep today's fail-closed behavior unchanged.

**Non-goals.**

- Does **not** prevent or shorten backend outages (that is infra: see
  `cyo-host-down-login-loop-pattern`).
- No change to the kid surface, offline reading/sync, or the admin console.
- No new backend endpoint, and no new context method: retry re-runs the existing
  `refreshStatus()` path (see 3.4).
- Does not alter `awaiting-approval` / `needs-consent` handling.

## 3. Design

### 3.1 Split the catch by error class (the crux)

Introduce a classifier in the `syncPrincipal` catch that maps the caught error to
`'transient'` or `'terminal'`:

| Class | Trigger (from the axios/JS error) | Handling |
| --- | --- | --- |
| **transient** | No HTTP response (network error, `err.code === 'ERR_NETWORK'`), timeout (`ECONNABORTED`), or a 5xx / 502 / 503 / 504 response | New `status='backend-unreachable'`; **keep** the token; offer retry |
| **terminal** | 401 / 403 (rejected or expired JWT, "unknown subject"), the explicit unrecognized-role `throw` at `frontend/src/auth/AuthContext.tsx:183`, any other 4xx, or an **unclassifiable** error | Current behavior: `safeRemoveToken()`, `status='signed-out'`, `authError='principal-unresolved'` |

```text
// #CRITICAL: security: classification must FAIL CLOSED. Only an explicit
// network/timeout/5xx signal is 'transient'. Anything ambiguous (no recognizable
// shape, unexpected error type) is 'terminal' -> signed-out + token removed. A
// rejected/expired JWT (401/403) must NEVER be treated as transient, or we would
// keep a dead session alive behind a retry button.
// #VERIFY: AuthContext.test.tsx cases: 401 -> terminal; unknown Error -> terminal;
// axios network error -> transient; 503 -> transient.
```

This preserves the existing `#CRITICAL security` invariant documented at
`frontend/src/auth/AuthContext.tsx:201-208`: a session the backend actually rejects
still fails closed.

### 3.2 New auth status, not a reused authError

`ProtectedRoute` and the interstitial pages route off `status`
(`frontend/src/auth/authContext.ts:15-16` union). To match the existing interstitial
pattern, add a status member:

```ts
export type AuthStatus =
  | 'loading'
  | 'signed-out'
  | 'awaiting-approval'
  | 'needs-consent'
  | 'signed-in'
  | 'backend-unreachable'   // NEW: transient principal-resolution failure, retry-friendly
```

The shipped declaration is a single-line union; widening it to one member per line is
part of this change so the new member can carry its own doc comment, matching how the
other members are documented in the block above it (`authContext.ts:1-14`).

`AuthError` stays `'principal-unresolved'` for the terminal path (LoginPage still
shows its inline banner for that case, and the `busy = submitting && !authError`
derivation documented at `frontend/src/auth/AuthContext.tsx:306-312` is unaffected
because the transient path sets a status, not an authError).

### 3.3 Preserve the session so retry can succeed

On the transient branch, do **not** call `safeRemoveToken()`. Keeping the Supabase
access token means a retry re-invokes `syncPrincipal` against the live session and
can transition straight to `signed-in` once the backend answers, no re-login.

### 3.4 Reuse the shipped `refreshStatus()`; do not add a new method

**No context-API change is needed.** `AuthContextValue` already exposes
`refreshStatus: () => Promise<void>` (`frontend/src/auth/authContext.ts:76-85`), whose
implementation (`frontend/src/auth/AuthContext.tsx:420-423`) is exactly the retry
mechanism this spec wants:

```ts
refreshStatus: async () => {
  const { data } = await supabase.auth.getSession()
  await syncPrincipal(data.session)
},
```

It re-reads the current Supabase session and re-runs `syncPrincipal`'s
onboarding-then-`/me` resolution. It was added in P-6d for
`GuardianAwaitingApprovalPage`'s "Check again" button and background poll, and it is
the same tail `recordConsent` runs after submitting consent
(`frontend/src/auth/AuthContext.tsx:402-410`).

An earlier draft of this spec proposed adding `retry: () => Promise<void>`. That is
now redundant: it would be a byte-for-byte duplicate of `refreshStatus`. The
interstitial calls `refreshStatus()` directly.

Note that `syncPrincipal` catches internally, so `refreshStatus()` resolves rather
than rejecting when resolution fails; the outcome is observed as a `status`
transition, not a thrown error. The interstitial's own `catch` is therefore a
belt-and-braces guard for a `getSession()` failure only, exactly as on
`GuardianAwaitingApprovalPage` (`frontend/src/auth/GuardianAwaitingApprovalPage.tsx:46-60`).

### 3.5 New route and interstitial page

- `frontend/src/routes.ts`: `export const GUARDIAN_UNAVAILABLE_PATH = '/guardian/unavailable'`
  (verified free on `main`: no existing `GUARDIAN_UNAVAILABLE` or `backend-unreachable`
  identifier anywhere under `frontend/src/`).
- `frontend/src/router.tsx`: register it alongside the awaiting-approval / consent
  routes (`frontend/src/router.tsx:132-141`) rendering a new
  `GuardianBackendUnavailablePage` via the existing `suspended(...)` helper, inside the
  guardian `AuthProvider` subtree but **outside** `ProtectedRoute`, for the same reason
  the sibling interstitials sit there (documented at `router.tsx:126-131`: these
  statuses never reach `'signed-in'`, so a route under `ProtectedRoute` would bounce).
- `frontend/src/auth/GuardianBackendUnavailablePage.tsx`: mirror the self-guarding shape
  of `GuardianAwaitingApprovalPage.tsx` and `GuardianConsentPage.tsx`:
  - If `status === 'signed-in'` -> `<Navigate to={GUARDIAN_CONSOLE_PATH} replace />`.
  - If `status === 'signed-out'` -> `<Navigate to={GUARDIAN_LOGIN_PATH} replace />`.
  - Only render its own UI while `status === 'backend-unreachable'`.
  - UI: plain-language message ("We can't reach CYO Adventure right now. This is
    usually temporary."), a **Try again** button wired to `refreshStatus()` and
    `disabled` while a check is in flight, and a **Back to sign-in** escape that signs
    the Supabase session out.
  - Carry over the same `#ASSUME: security` note the sibling pages document
    (`GuardianAwaitingApprovalPage.tsx:35-40`): the route sits outside `ProtectedRoute`,
    so a direct-URL visitor in any status can land here, which is why the status guards
    above are required rather than defensive extras.

Concretely, the recheck loop is the shipped pattern copied verbatim in shape
(`GuardianAwaitingApprovalPage.tsx:21`, `:44`, `:51-71`): a module-level
`AUTO_RECHECK_INTERVAL_MS`, a `checking` boolean, a `useCallback` wrapper that
brackets `refreshStatus()` with `setChecking(true/false)`, and a `useEffect` whose
`setInterval` is gated **inside** the effect on `status !== 'backend-unreachable'`
(hooks must run unconditionally, before the status-gated early returns). The one
deliberate divergence is the attempt cap in Decision A.

### 3.6 Wire the two routers

- `frontend/src/auth/ProtectedRoute.tsx`: add a branch alongside the existing
  interstitial redirects at lines 59-64, before the signed-in check at line 66:

  ```tsx
  if (status === 'backend-unreachable') {
    return <Navigate to={GUARDIAN_UNAVAILABLE_PATH} replace />
  }
  ```

- `frontend/src/guardian/LoginPage.tsx`: add a mirror branch next to its existing
  interstitial redirects (`frontend/src/guardian/LoginPage.tsx:376-381`) so a guardian
  who lands on `/guardian/login` while `backend-unreachable` is forwarded to the
  interstitial instead of re-triggering the loop.

## 4. Decisions (recommended defaults)

| # | Decision | Recommended default | Rationale |
| --- | --- | --- | --- |
| A | Auto-retry vs manual only | **Both**: manual button + auto-retry on a `20_000` ms interval matching the shipped `AUTO_RECHECK_INTERVAL_MS`, capped at 15 attempts (~5 min), after which the timer stops and the manual button stays live | Power-outage recovery should be hands-off for the common short outage; the cap is the one divergence from the awaiting-approval page, because each poll here targets a host that is *down*, so every attempt costs a full request timeout rather than a cheap short-circuit |
| B | Dedicated route vs inline-only | **Dedicated route** (`GUARDIAN_UNAVAILABLE_PATH`), consistent with awaiting-approval / needs-consent; the login page keeps its existing inline banner for the terminal `principal-unresolved` case | Status-driven routing is the established pattern; inline-only would not break the loop for a mid-navigation guardian |
| C | Preserve session on transient | **Yes**, do not remove the token | Enables retry-without-relogin; a transient failure has not invalidated the session |
| D | New `AuthStatus` vs new `AuthError` value | **New status** `backend-unreachable` | `ProtectedRoute` keys off status; reusing an authError would not give a clean routable state |
| E | New `retry()` vs existing `refreshStatus()` | **Reuse `refreshStatus()`** | It already does exactly this (3.4); a new method would duplicate it |

These are reversible defaults; flag any you want changed and the spec updates before
implementation.

## 5. RAD assumption tags to carry into implementation

- `#CRITICAL security`: error classification must fail closed (3.1). A 401/403 or
  any ambiguous error is terminal, never transient. `#VERIFY`: unit tests per 3.1.
- `#EDGE external-resources`: backend availability is the modeled failure; the
  interstitial is the defensive UI for it.
- `#ASSUME timing`: auto-retry interval and attempt cap (Decision A) bound the poll;
  `#VERIFY`: test that auto-retry stops at the cap and does not fire after unmount
  (the interval is cleared by the effect's teardown, and `syncPrincipal`'s existing
  `cancelledRef`/`isStale` guard already blocks resolved-after-unmount state writes).

## 6. Files to change (implementation checklist)

- [ ] `frontend/src/auth/authContext.ts` - extend `AuthStatus` (3.2); document the new member.
- [ ] `frontend/src/auth/AuthContext.tsx` - add `classifyPrincipalError`; split the
      catch (3.1); keep token on transient (3.3). **No new context method** (3.4).
- [ ] `frontend/src/routes.ts` - add `GUARDIAN_UNAVAILABLE_PATH`.
- [ ] `frontend/src/router.tsx` - register the interstitial route (3.5).
- [ ] `frontend/src/auth/GuardianBackendUnavailablePage.tsx` - new component (3.5).
- [ ] `frontend/src/auth/ProtectedRoute.tsx` - add the `backend-unreachable` branch (3.6).
- [ ] `frontend/src/guardian/LoginPage.tsx` - add the mirror redirect (3.6).
- [ ] Tests (Section 7).

## 7. Test plan

Vitest + Testing Library. The frontend coverage gate is **per-file 70%**
(`frontend/vite.config.ts:210-216` sets `lines/branches/functions/statements: 70` with
`perFile: true`), and only `npm run test:coverage` enforces it; `npm run test:run`
does not. The new page therefore needs its own test file.

- `AuthContext.test.tsx`: network error -> `status='backend-unreachable'`, token
  retained; 503 -> transient; 401 -> `signed-out` + `authError='principal-unresolved'`,
  token removed; unknown/unclassifiable error -> terminal (fail closed);
  `refreshStatus()` from `backend-unreachable` reaches `signed-in` when the mock recovers.
- `ProtectedRoute.test.tsx`: `backend-unreachable` -> redirects to
  `GUARDIAN_UNAVAILABLE_PATH`, not login. Extend the existing interstitial redirect
  tests, which follow a copyable shape: "redirects to the awaiting-approval
  interstitial, not login" (`frontend/src/auth/ProtectedRoute.test.tsx:51-71`) and
  "redirects to the consent interstitial, not login" (`:73-91`).
- `GuardianBackendUnavailablePage.test.tsx`: renders the message while
  `backend-unreachable`; the button calls `refreshStatus()` and is disabled while
  checking; redirects to console on `signed-in` and to login on `signed-out`;
  auto-retry fires on a fake timer and stops at the cap.
- `LoginPage`: `backend-unreachable` forwards to the interstitial.

## 8. Acceptance criteria

1. A guardian whose `/v1/onboarding` times out lands on `/guardian/unavailable`
   with a plain-language message, not a login loop.
2. Once the backend recovers, a manual retry (or an auto-retry tick) completes sign-in
   with no re-login.
3. A genuine 401/403 or unrecognized role still fails closed to `signed-out` with
   the token removed and the existing login banner (behavior unchanged).
4. Auto-retry is bounded and does not fire after the page unmounts.
5. All frontend gates green: `npm run lint && npm run typecheck && npm run test:coverage`.

## 9. Capability-register note

The capability register has no dedicated "authenticate / sign-in" row; guardian
authentication is foundational to the entire G- and A-series (it gates G1 account
access and every guardian/admin console capability). This work is therefore a
**cross-cutting resilience hardening of that foundation**, not a new capability. If
the owner wants it tracked with a stable ID, the register would need a new
foundational auth-resilience line; flagged here rather than citing an ID that does
not exist.
