---
purpose: Full frontend test review (health, coverage robustness, user-fidelity, a11y/e2e)
component: frontend
source: session review 2026-07-27, isolated worktree test/frontend-review
---

# Frontend Test Review, 2026-07-27

Scope: `frontend/` React app. Run in an isolated worktree (`test/frontend-review`)
to avoid collisions with concurrent sessions. Assessed three things: do the tests
pass, is coverage robust, and do the tests assert what a USER expects (not just
what was built), including a11y and Playwright e2e.

## 1. Test health (all green after one fix)

| Check | Result |
| --- | --- |
| `npm run typecheck` (tsc -b) | PASS (exit 0) |
| `npm run lint` (eslint, incl. all e2e tiers) | PASS (exit 0) |
| `npm run test:coverage` (Vitest, 125 files) | PASS, thresholds met |
| `npm run test:e2e` (mocked Playwright chromium, incl. a11y.spec.ts) | 185 pass / 1 flake, **fixed** |

The one e2e failure (`authoring-queue.spec.ts:52`) was a **latent strict-mode
flake**, not an app bug (zero code changed on the branch; passed 3/3 in isolation).
`getByText(request title)` also matched the open dialog heading whose full text
("Build authoring plan: <title>") lives in the DOM while CSS-truncated. Under
parallel load the React state flush that removes the row + unmounts the dialog
lagged the mocked POST that `expect.poll` awaits, so both elements briefly
coexisted. CI `retries: 1` masked it. Fixed by scoping the assertion to the row
testid (unambiguous, and the true user-observable outcome). Verified 12/12 under
4x parallel-repeat stress. Committed `54be69b`.

Not run here (environment-gated, correctly local-only per project setup):
`e2e-real/` (needs seeded local backend), `e2e-staging/`, `e2e-prod/`,
`visual.spec.ts` (Linux-CI pixel baselines; deliberately ignored off-CI), and
the design-system workspace (separate vitest + Codecov flag).

## 2. Coverage robustness

Vitest overall: **Statements 95.93% | Branches 88.62% | Functions 94.97% | Lines 97.87%**,
well above the enforced `perFile: true` 70% floor. Weakest module is
`src/api/readerApi.ts` (76% branches); `LandingPage.tsx` at 70% branches.

Caveat that drove the rest of this review: line coverage measures execution, not
assertion quality. High coverage here is real, but a handful of tests execute the
line and then assert an implementation detail rather than a user outcome (below).

## 3. User-fidelity verdict by surface

Overall the suite is unusually faithful to user-observable behavior: e2e specs
capture and assert real request bodies, the player Go-Back is proven by replay
(not reversal) with fixtures a naive "undo" would fail, offline conflict is driven
through real fake-IndexedDB, and auth fails closed (malformed `is_admin` stays
false, `/me` rejection clears the bearer AND any child session).

| Surface | Verdict |
| --- | --- |
| Kid / Reader / Player / Offline | Strong. Behavioral + adversarial. Minor CSS-class coupling. |
| Guardian / Auth | Strong. COPPA consent + shared-device boundary tested end-to-end. |
| Admin (behavior) | Strong. Real payload round-trips, fail-closed permission states. |
| Hooks / client / infra | Strong. Real interceptor logic, secret-leak assertions. |
| **Accessibility** | **Floor only.** Real gaps (see below). Highest-value area. |

## 4. Prioritized findings

The finding text below is the pre-fix baseline, recorded as it stood at the
start of this review. Where a finding was closed later in this same PR, a
`Status:` line says so directly under it; the original wording is left intact
rather than rewritten, so the audit trail of what was wrong and what fixed it
survives the merge.

### P1 - Accessibility is a happy-path smoke, not a WCAG 2.1 AA floor

The a11y suite (axe + touch-targets) is well-built where it runs, but:

- **No keyboard-navigation coverage anywhere**: no Tab/focus-order (2.4.3), no
  dialog focus-trap or Escape-to-close (2.1.2) assertions on any of the many
  dialogs (review approve/send-back/edit, assign-children, profile form).
  `review-edit.spec.ts:13` claims to drive "through the focus trap" but only clicks.
  Status: closed in this PR (commit 87600b1). `frontend/e2e/keyboard-nav.spec.ts`
  asserts focus-in, both-direction Tab-trap wrap, and Escape-restores-trigger on
  three representative `cyo-dialog` modals, plus keyboard reachability of the
  Send Back and Edit passage textareas. Writing it surfaced a real WCAG 2.1.1
  defect: the shared Dialog focus-trap selector omitted `textarea`, locking
  keyboard-only admins out of both flows. Fixed in the same commit.
- **Admin pages scanned with EMPTY fixtures** (`a11y.spec.ts:138-145,231-306`):
  severity pills, content-flag badges, valence badges, the exact colored status
  indicators where contrast/name-role-value issues hide, are never rendered under axe.
  Status: closed in this PR (commit 87600b1). Populated-fixture scans now cover
  the admin thresholds, dashboard, provider-allowlist, and review-queue surfaces.
- **`/admin/review/:id` excluded from axe entirely** (`a11y.spec.ts:15-17`), the
  richest admin page (flagged-passage cards, jump buttons, alerts, inline 422 errors).
  Status: closed in this PR (commit 87600b1). The exclusion rested on the page
  having no fixed heading to assert on, which an axe scan does not need; it is
  now scanned against a seeded review surface in both its flagged-passage and
  approve-failure-alert states.
- **Touch-target check is height-only** (`admin-touch-targets.spec.ts:77-78`);
  WCAG 2.5.5 is 44x44. Also admin-scoped; kid reader choice buttons unverified.
  Status: closed in this PR (commit 87600b1). The admin sweep now asserts width
  as well, and `frontend/e2e/kid-touch-targets.spec.ts` measures every visible
  kid-reader choice button on both axes at a phone viewport.
- **Only resting render scanned**; no open menus, error toasts, loading, 422 panels.
  Status: partially closed in this PR (commit 87600b1). Populated rows and the
  review detail's approve-failure alert are now scanned; open menus, toasts, and
  loading states still are not. This one stays open.

### P2 - Half-built two-device conflict resolution (product decision needed)

`resolveConflict(..., 'continue_from_this_device')` is unit-tested
(`sync.test.ts:287-307`) but no component ever calls it or renders a choosing UI;
every test asserts `conflict-dialog` is ABSENT. Reader only does silent
newest-write-wins (`ReaderPage.tsx:321-327`). Either remove the dead branch + its
test, or build+test the "ask the user" dialog. Right now the test implies a user
flow that does not exist.

### P3 - Small, high-value untested units

Status: closed in this PR (commit 65087ce). All four now have tests; see the
per-item notes below.

- `src/env.ts flagEnabled` has NO test, yet exists specifically to dodge the
  `Boolean("false") === true` trap. 3-line table test, high regression value.
  Closed by `frontend/src/env.test.ts`.
- `src/reader/useReaderFontScale.ts`: no direct test that bumping text size
  actually enlarges the passage / persists across mounts (the child-observable payoff).
  Closed by `frontend/src/reader/useReaderFontScale.test.ts`, including the
  per-profile scoping of the storage key.
- Condition evaluator: add a metamorphic property (double-negation / De Morgan)
  to the fast-check layer, which today only asserts the return is boolean.
  Closed by three fast-check properties in `frontend/src/player/evaluator.test.ts`.
- `useApi` 403 interceptor pass-through boundary (only 500 is asserted).
  Closed in `frontend/src/hooks/useApi.test.ts`.

### P4 - Minor implementation-coupling nits (low urgency)

Status: partially closed in this PR (commit 65087ce). `ReaderChrome.test.tsx`
and `LibraryPage.test.tsx` now assert observable behavior instead of class
names. The rest were kept deliberately: they have no jsdom-observable
alternative (jsdom applies no stylesheets, so a class is the only evidence the
styling hook fired), and each is now annotated in place with that reasoning.

CSS-class assertions used as proxies for observable state, each sitting beside a
genuine assertion so not urgent: `Reader.test.tsx:367-388` (celebrate class),
`ReaderChrome.test.tsx:81,97`, `KidShell.test.tsx:87,117-133` (data-attrs for
theme/reduce-motion, no visible-effect assertion), `BudgetBanner.test.tsx:26,36`,
various `toHaveClass('toast--*')`. Prefer role/label/`toHaveFocus()` over class tokens.

## 5. Recommendation

Status: acted on in this PR (commits 87600b1, 65087ce). The recommendation below
is kept as written, as the reasoning that motivated the work; what it recommends
was then done rather than deferred. What remains open after that pass is P2 (a
product decision, not a test gap) and the non-resting a11y states (open menus,
toasts, loading) noted under P1.

Test health and coverage are in excellent shape; the flake is fixed. The one area
that does not yet meet "tests what a user would expect" is **accessibility for
keyboard and assistive-tech users** (P1). Recommend a focused a11y hardening pass
(keyboard/focus-trap assertions on dialogs, populated + error-state axe scans,
`/admin/review/:id` scan, 44x44 width on touch targets) as the highest-value next
step, then the P3 quick wins.
