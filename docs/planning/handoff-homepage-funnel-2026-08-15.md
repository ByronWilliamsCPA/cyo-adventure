# Session Handoff: homepage sales-funnel redesign (2026-08-15)

Branch: `claude/homepage-redesign-sales-funnel-o5bshc`. Written for the team taking this work over
mid-stream; the paired PR carries the same branch. Treat "What Remains" as a hypothesis and re-verify
against the live branch before acting.

## Goal / Intent

Redesign the root landing page as the product's sales funnel (hero, live demo, how-it-works, safety,
subscription-READY pricing, FAQ) while preserving the two contractual returning-user flows unchanged:
the device-grant-aware Kids door and the Grown-ups door. Subscriptions do not exist yet (no billing
backend; Track 2 Phase 8 per ADR-008), so the pricing section must be structurally ready for the flip
without selling or implying anything today.

The owner's review protocol: three cycles of paired adversarial reviews (one UX, one code quality),
each pair COLD (no access to earlier reports), fixing between cycles. Cycles completed: cycle 1 fully
applied; cycle 2 reviews completed and triaged, fixes PARTIALLY applied (see What Remains); cycle 3
not yet run. The handoff request arrived mid-cycle-2.

## Current State

- Branch `claude/homepage-redesign-sales-funnel-o5bshc`, 3 commits at handoff time (a 4th adds this
  doc), all pushed. Working tree clean.
  - `cfb4bdd` feat(landing): redesign the homepage as the sales funnel
  - `d09025e` fix(landing): apply adversarial UX and code review findings (cycle 1)
  - `7d6a704` fix(landing): first slice of cycle-2 cold-start review fixes
- Gates green at the last commit: `tsc -b`, ESLint (one pre-existing FlagBadge.tsx warning,
  untouched), 31 landing unit tests (2307 repo-wide at last full run), landing e2e 6/6, axe on `/`
  (per-PR tags and A11Y_EXTENDED=1), 320/375/414 overflow checks, visual baseline passing.
- No active errors. No failing tests.
- PR: opened at handoff (same branch); see the PR description for the reviewer-facing summary.

## What Was Done

- Commit 1: full landing rebuild (`frontend/src/landing/*`: LandingPage, landing.css, DemoAdventure,
  demoStory, pricing) plus e2e/spec updates and a regenerated `landing-page-chromium-linux.png`.
- Commit 2 (cycle-1 fixes, both reviews fully applied): production-canary h1 assertion fix
  (`frontend/e2e-prod/landing-login.spec.ts`), COPPA-claim softening, approval-wall expectation
  copy, sticky-topbar CTA, mid-page CTA, doors-first ordering on granted devices, demo endings
  counter, pricing discriminated union, quota disclosure, focus-ring fix on the forest band,
  `scroll-padding-top`, mobile topbar alignment, dead CSS and citation corrections.
- Commit 3 (cycle-2 slice): read-aloud moved to the free Explorer tier (it shipped in Phase 4b;
  advertising it as future-paid was UX finding 2), `formatMonthlyPrice` input guard plus strengthened
  data invariants, demo "Back one choice" action (`DEMO_PARENTS` in `demoStory.ts`), demo scale copy
  spanning the real band range, dead `id` field removed from `DemoNode`, and the h1 moved to a shared
  `LANDING_HEADLINE` constant (`frontend/src/landing/headline.ts`) imported by the unit test, the
  landing spec, the a11y readiness assertion, and the prod smoke test.

## What Remains

Cycle-2 findings triaged and accepted but NOT yet applied, in priority order. UX-n / CQ-n reference
the two cycle-2 reports (full texts in the session transcript; the specs below are self-sufficient).

1. **UX-1 signup dead end (top priority).** Every funnel CTA lands on `/guardian/login`, whose h1 is
   "Guardian sign-in" with no signup affordance; a new parent reads it as "wrong door". GOAL: the
   destination must say an account gets CREATED here. Mechanism (assumed, verify against design
   taste): in `frontend/src/guardian/LoginPage.tsx` retitle the h1 to "Sign in or create your
   account" and add, under the Google button and only when the authorize-device intent is absent, a
   line such as "New family? Continuing with Google creates your account." Then update every
   "Guardian sign-in" heading assertion: `frontend/src/test/App.test.tsx` (2), `frontend/e2e/
   landing.spec.ts`, `frontend/e2e/intake.spec.ts`, `frontend/e2e/a11y.spec.ts:220`,
   `frontend/e2e/guardian-password-reset.spec.ts` (2), `frontend/e2e-prod/landing-login.spec.ts`,
   `frontend/e2e-prod/guardian-profiles.spec.ts` (2). Grep for the string before trusting this list.
2. **UX-3 verification claim.** Trust card 2's body still says "Adult verification and consent are
   built into sign-up" in present tense; KWS is flag-off in production (`core/config.py::
   kws_verification_required` default False; ADR-018). Replace the body with: "Kids never get
   accounts of their own. A grown-up signs in with their own account, and a real person reviews
   every new family before it is switched on. Verified-parent consent (COPPA) is built in and turns
   on with our public launch."
3. **UX-4 device contradiction.** How-it-works footnote says "on any device" while the trust card
   and FAQ say "devices you authorize". New footnote: "Once you approve a book it lands on their
   shelf right away, and it reads offline on any device you have set up."
4. **CQ-1 320px hero overflow.** At <=56rem the hero grid is `grid-template-columns: 1fr`; the art
   row's 300px min-content floors the track and clips the reassure line at 320px. Fix:
   `minmax(0, 1fr)`. ALSO the overflow gate cannot fail: `.landing { overflow-x: clip }` hides
   overflow from `scrollWidth`. Rewrite the landing case in `frontend/e2e/mobile-viewport.spec.ts`
   to assert every `.landing *` descendant's `getBoundingClientRect().right <= clientWidth + 1`.
5. **CQ-2 doors-first top gap.** With a valid grant the doors band starts 0px under the sticky bar
   (`.landing-doors-band` has no top padding). Fix:
   `main > .landing-doors-band:first-child { padding-top: var(--space-8) }` and add a granted-device
   geometry assertion to `frontend/e2e/landing.spec.ts` (band above hero AND band heading below the
   topbar's bottom edge).
6. **CQ-5 `:has()` support.** `html:has(.landing)` no-ops on Firefox 104-120 (Vite's default
   baseline), silently dropping `scroll-padding-top`. Keep `:has()` for `scroll-behavior` only; add
   universal `scroll-margin-top: 5rem` on `#demo`, `#how-it-works`, `#safety`, `#pricing`,
   `#landing-main`, and `.demo-adventure__passage`.
7. **UX-5 phone topbar swap + hero art.** Below 45rem, hide the topbar compact CTA and show
   `.landing__signin` and the wordmark name instead (returning parents lost their only sign-in
   affordance; the hero CTA is one screen away and mid-page CTAs exist). Below 30rem hide
   `.landing-hero__art` entirely (three unlabeled rectangles cost a quarter of screen one). This
   REVERSES part of cycle 1; see Key Decisions.
8. **UX-6 pricing render.** Render a card only for `PRICING_TIERS.filter(t => t.available)`; render
   each unavailable tier as one line under the grid: "A paid Family plan comes later: we will
   announce pricing here before anything changes, and books already on your shelf stay yours." Keep
   the existing footnote sentence about safety never being paywalled. Update the pricing unit and
   e2e tests (the Family ARTICLE disappears; assert the futures line and that the whole section has
   exactly one link). Center the single card (`max-width: ~26rem`).
9. **CQ-3/CQ-4 grant read + RAD.** Derive both `kidsDoorPath`'s initializer and `doorsFirst` from a
   single `const [grantAtMount] = useState(() => hasValidDeviceGrant())`; tag `doorsFirst` with an
   `#ASSUME` timing tag; fix the `#VERIFY` that names a nonexistent "storage-event" unit test by
   ADDING that test: fire a `StorageEvent` after seeding/removing the grant, assert the door HREF
   updates while the section ORDER does not.
10. **UX-8/UX-9 dark-mode states.** FAQ focus ring: `.landing-faq__question:focus-visible
    { outline-color: var(--color-amber-text) }` (amber-deep computes 2.72:1 on the open dark card;
    amber-text 7.53:1 dark / 5.96:1 light, verified). Primary CTA hover:
    `border-color: var(--color-ink)` (amber-deep to amber-hover is 1.01:1 in dark mode, invisible
    under reduced motion).
11. **UX-14/16 + CQ-20 layout polish.** Demo section: retitle h2 to "Try a sample story" (matches
    the hero ghost CTA), add the eyebrow, and give it the asymmetric left-rail frame
    (`minmax(0,0.8fr) minmax(0,1.2fr)` above 56rem). Align the topnav-hide breakpoint to 56rem.
    Compact doors-band variant when funnel-first (UX-7), or explicitly decline it.
12. **Copy dedupe (UX-10/16).** Hero reassure becomes: "Free while in early access. No ads, ever. We
    approve each family by hand, so kids never share the space with strangers." Final-band lede
    becomes: "Create your account in about a minute and meet Pip." Delete the mid-page CTA's note
    line. Footer link "Guardian sign-in" becomes "Sign in" pointing at `/guardian` (update the unit
    test for two same-name links).
13. **UX-12 FAQ additions.** Deletion rights (mirror the policy exactly: profile deletion is in-app,
    family-account deletion is by email; see `frontend/src/legal/PrivacyPolicyPage.tsx:443`) and a
    training-question clause that claims nothing unverified: "Whether a provider may train on inputs
    is governed by that provider's terms; the privacy page names each provider and exactly what it
    receives."
14. **Comment accuracy (CQ-7/8/9/10/21).** landing.css header says three literals, there are four
    (the cover edge highlight); the cover-title citation names lagoon but only plum ships a label
    (moot if UX-15's all-three-labels lands: then lagoon IS the worst case at 10.13:1); the
    ink-muted "3.72:1" figure predates UX-C2 (now 4.57:1 light); `frontend/e2e/landing.spec.ts`'s
    topnav-scoping comment cites a "See how it works" CTA that no longer exists; soften the
    "must always be correct" wording on the door-href comment (cross-tab revoke has a benign
    known race; the server is the boundary).
15. **UX-13 share preview.** Produce a 1200x630 `frontend/public/og-image.png` (screenshot the built
    hero region), point `og:image` at it with correct dimensions, switch `twitter:card` to
    `summary_large_image`.
16. **UX-15 cover labels.** Restore titles on all three hero covers, anchored to the TOP of each
    spine (top labels dodge both the fan overlap and Pip, which is why the bottom-label version was
    removed in cycle 1); keep them hidden below 30rem if the art survives UX-5 there.
17. **Cycle 3.** After the remainder lands and gates pass, run the third cold-start pair (UX +
    code quality, Opus, no access to earlier reports), triage, fix, push. The cycle-2 prompts are a
    good template: constraints block, screenshot paths, "measure the built page" instruction.

## Key Decisions

- **Pricing is a discriminated union on `available`** (`frontend/src/landing/pricing.ts`): an
  available tier must carry price + CTA, an unavailable one cannot; chose this over parallel
  boolean/status/cta fields because a partial Phase 8 flip shipped a contradictory card with every
  test green.
- **Doors order is decided once at mount** and never reshuffles mid-view (href still upgrades live);
  chose over live reordering because a section reshuffle under a reading visitor is hostile CLS.
- **Family card kept in cycle 1, slated for a one-line futures note in cycle 2**: two independent
  cold reviewers converged on the card being a de-conversion element; subscription-readiness now
  lives in the data model plus the render filter, not in a visible unbuyable card.
- **Demo passage uses `:focus`, not `:focus-visible`**, deliberately (script-driven focus after
  mouse clicks must stay visible for AT users); documented in landing.css.
- **Token fallbacks are omitted in landing.css** (header note): tokens.css loads unconditionally
  and a light-only fallback would paint wrong colors in dark mode.
- **Claims discipline**: every safety/limit claim must match something enforced today
  (10-story quota, hand approval, KWS flag-off). Two review cycles each caught one overreach;
  assume cycle 3 will hunt for more.

## Dead Ends / Rejected Approaches

- **Mobile sticky-topbar CTA** (added in cycle 1 for the 6.5-screenful action gap) is slated for
  reversal on phones by cycle-2 evidence: it displaced the only sign-in affordance while mid-page
  CTAs already close the gap. Do not re-add without new evidence.
- **Bottom-anchored labels on all three hero covers** (original build): occluded by the fan overlap
  and the mascot; cycle 1 cut them to one label, cycle 2 wants all three back TOP-anchored. Do not
  re-litigate bottom labels.
- **amber-deep focus rings on non-parchment surfaces**: computed failures on the forest band
  (2.67:1/2.54:1) and the dark FAQ card (2.72:1). Use ink (band) and amber-text (FAQ).
- **`getByRole('link', { name: /get started/i })` unscoped in tests**: the label deliberately
  repeats; scope to a container or use `getAllByRole`.

## User Corrections / Constraints

- Three-cycle cold-review protocol (owner instruction); cycle-2 remainder and cycle 3 outstanding.
- Signed commits (SSH signing is preconfigured in the CCR container), Conventional Commits, no
  em-dash characters anywhere.
- Landing chunk stays static: no data fetching, no Supabase, no kid data hooks.
- Door behavior and accessible names are contractual; KWS-registered `/privacy` and `/support`
  footer links must stay; `frontend/e2e/a11y.spec.ts` scope must not widen in the PR gate (ADR-029).
- Never render a purchase-looking control while no billing exists (`pricing.ts` `#CRITICAL`).

## Files Touched

- `frontend/src/landing/LandingPage.tsx`: the page; door logic byte-compatible with main plus
  `doorsFirst` ordering.
- `frontend/src/landing/landing.css`: all styling; contrast ratios cited per rule (verified by two
  independent recomputations; two comment inaccuracies listed in What Remains 14).
- `frontend/src/landing/DemoAdventure.tsx`, `demoStory.ts`: interactive demo, endings counter,
  Back one choice.
- `frontend/src/landing/pricing.ts`, `headline.ts`: tier data (the Phase 8 flip point) and the
  shared h1 constant.
- `frontend/src/landing/*.test.tsx`, `pricing.test.ts`: 31 tests pinning doors, ordering, pricing
  safety, demo behavior.
- `frontend/e2e/landing.spec.ts`, `a11y.spec.ts`, `mobile-viewport.spec.ts`,
  `e2e-prod/landing-login.spec.ts`: funnel e2e, readiness assertions, overflow gate.
- `frontend/index.html`: funnel meta/OG/JSON-LD copy.
- `frontend/e2e/visual.spec.ts-snapshots/landing-page-chromium-linux.png`: regenerated baseline
  (off-runner; see Gotchas).

## How to Resume

1. `git fetch origin && git checkout claude/homepage-redesign-sales-funnel-o5bshc && git pull`
2. `cd frontend && npm ci`
3. Recreate the Playwright browser shim (container ships Chromium build 1194; Playwright 1.62.1
   expects 1234; do NOT run `playwright install`):

   ```bash
   SHIM=/root/.pw-shim
   mkdir -p "$SHIM/chromium_headless_shell-1234/chrome-headless-shell-linux64" "$SHIM/chromium-1234"
   ln -sfn /opt/pw-browsers/chromium_headless_shell-1194/chrome-linux/headless_shell \
     "$SHIM/chromium_headless_shell-1234/chrome-headless-shell-linux64/chrome-headless-shell"
   ln -sfn /opt/pw-browsers/chromium-1194/chrome-linux "$SHIM/chromium-1234/chrome-linux"
   ln -sfn /opt/pw-browsers/ffmpeg-1011 "$SHIM/ffmpeg-1011"
   touch "$SHIM"/chromium{_headless_shell,}-1234/INSTALLATION_COMPLETE 2>/dev/null || true
   ```

4. Work "What Remains" top-down. Gate loop:
   `npm run typecheck && npm run lint && npx vitest run src/landing` then
   `VITE_SUPABASE_URL=https://example.supabase.co VITE_SUPABASE_ANON_KEY=dummy VITE_API_URL= npm run build`,
   `npm run preview -- --port 4173 --strictPort &`,
   `PLAYWRIGHT_BROWSERS_PATH=/root/.pw-shim npx playwright test landing.spec.ts` plus the a11y and
   mobile-viewport landing cases; regenerate the visual baseline with
   `CI=1 PLAYWRIGHT_BROWSERS_PATH=/root/.pw-shim npx playwright test visual.spec.ts -g landing --update-snapshots`
   whenever anything above the 1280x720 fold changes.
5. Push each verified batch; the PR tracks the branch. Then run cycle 3 (What Remains 17).

## Gotchas

- **Visual baseline provenance**: the committed `landing-page-chromium-linux.png` was regenerated in
  the CCR container, not on the GitHub runner. If the required `frontend-e2e` job fails on sub-pixel
  antialiasing, run the repo's `update-visual-snapshots.yml` workflow rather than hand-tuning.
- **Daily prod canary coupling**: `e2e-prod/landing-login.spec.ts` now asserts the NEW headline
  against LIVE production; between merge and the frontend deploy, the nightly run will fail. Time
  the merge with a deploy or expect one noisy night.
- **`mobile-safari` Playwright project cannot run in the container** (no WebKit binary); CI's
  required gate is the chromium project. Do not chase those local failures.
- **The overflow gate is currently vacuous for the landing page** (see What Remains 4): passing it
  today proves nothing about horizontal overflow there.
- **A first cycle-2 attempt died mid-run on a session usage limit**; its partial outputs were
  discarded and the pair re-ran cold. Only the re-run's findings are reflected here.
- **`docs/template_feedback.md`** (gitignored): no template-level findings this session; nothing
  filed. The authoring-lessons log was not touched: this was frontend work, not a story authoring
  run.

## Next-Session Kickoff Prompt

Resuming work on ByronWilliamsCPA/cyo-adventure (branch
`claude/homepage-redesign-sales-funnel-o5bshc`). Goal: finish the homepage sales-funnel redesign's
review remediations, then run review cycle 3.

First, refresh state before acting (the handoff is a snapshot; treat What Remains as a hypothesis):

    git fetch --all && git status --short && git log --oneline -5

Immediate next action: item 1 of "What Remains" in
`docs/planning/handoff-homepage-funnel-2026-08-15.md` (the guardian login page must say it CREATES
accounts; every funnel CTA lands there and new parents currently bounce off "Guardian sign-in").

Hard constraints: no em-dash characters; signed Conventional Commits; the landing chunk stays
static (no Supabase or data hooks); Kids/Grown-ups door behavior and names are contractual; never
render a purchase-looking control while no billing backend exists; do not widen
`frontend/e2e/a11y.spec.ts`'s per-PR scope (ADR-029).

Full handoff (read on demand): `docs/planning/handoff-homepage-funnel-2026-08-15.md` on the branch.
