# Session Handoff: homepage sales-funnel redesign (2026-08-15)

Branch: `claude/pr-717-review-e01svz`. Originally written mid-stream, when cycle 2 was partly
applied and cycle 3 unrun; UPDATED on completion of the full three-cycle protocol, so it now records
what was done rather than what was left. Still verify against the live branch before acting on any
specific claim.

## Goal / Intent

Redesign the root landing page as the product's sales funnel (hero, live demo, how-it-works, safety,
subscription-READY pricing, FAQ) while preserving the two contractual returning-user flows unchanged:
the device-grant-aware Kids door and the Grown-ups door. Subscriptions do not exist yet (no billing
backend; Track 2 Phase 8 per ADR-008), so the pricing section must be structurally ready for the flip
without selling or implying anything today.

The owner's review protocol: three cycles of paired adversarial reviews (one UX, one code quality),
each pair COLD (no access to earlier reports), fixing between cycles. All three cycles are complete
and applied.

What the protocol was worth, since that is the question a future reader will have: each cycle found
defects the previous one could not. Cycle 1 caught claim overreach and a focus-ring contrast
failure. Cycle 2 caught a conversion dead end and an overflow gate that could not fail. Cycle 3,
the only cycle to simulate large text scale, caught two WCAG blockers on the contractual entry
points plus a grant-resurrection race, and it found three defects that turned out to live in shared
code rather than on this page at all. The pattern to keep: reviewers who MEASURE the built artifact
rather than reading the source find a different class of defect than reviewers who read.

## Current State

**The three-cycle review protocol is COMPLETE.** All three paired cold-start review cycles have
run (one UX reviewer + one code-quality reviewer per cycle, each pair with no access to earlier
reports), and every accepted finding has been applied. There is no outstanding remediation list.

Branch: `claude/pr-717-review-e01svz` (successor to `claude/homepage-redesign-sales-funnel-o5bshc`;
see the note under "What Was Done"). Working tree clean.

Gates at the final commit: `tsc -b`, ESLint (one pre-existing `FlagBadge.tsx` warning, untouched),
`prettier --check`, 2318 frontend unit tests across 174 files, 59 Playwright cases across
`landing`/`mobile-viewport`/`a11y`/`keyboard-nav`, 18 visual baselines, the coverage-matrix
drift-guard, the RAD citation gate, the lessons-log and work-linkage checks, and a clean
`npm run build`.

## What Was Done

- **Original build and cycles 1-2** (commits `cfb4bdd`, `d09025e`, `7d6a704`, `03937463`): the full
  landing rebuild plus the first cycle's fixes and the first slice of cycle 2. Recorded in the
  original version of this document.
- **Branch move.** The work now lives on `claude/pr-717-review-e01svz`, which carries those four
  commits unchanged plus the remediation below. PR #717 was closed in favour of its successor
  rather than continuing on a branch whose review history predated the remaining work.
- **CI repair.** The `Frontend (Node 22)` job was failing at `format:check` on `demoStory.ts`, and
  the coverage-matrix drift-guard behind it had not been reached: the two new landing test files
  were never registered. Both fixed, and `main` merged in.
- **Cycle-2 remainder (items 1-16 of the original list), all applied.** The signup dead end, the
  present-tense KWS consent claim, the device contradiction, the 320px hero clip and the overflow
  gate that could not fail, the `:has()` dependency, the doors-band gap, the unbuyable pricing card,
  the doubled device-grant read and its missing storage-event test, the phone topbar, the
  dark-mode contrast states, the cover labels, the copy dedupe, the FAQ additions, the share image,
  and the comment-accuracy sweep.
- **Cycle 3, run cold and fully applied.** Two blockers, seven should-fixes and seventeen polish
  items. Highlights:
  - **WCAG 1.4.4 / 2.4.7 at large text scale**, the cycle's most valuable finding and one no
    previous cycle or CI gate could see. `minmax(15rem, 1fr)` grids overflowed by 153px at 200%
    text scale, and the non-wrapping topbar pushed the theme toggle off-screen while leaving it
    focusable. A 200% text-scale e2e case now guards both.
  - **`overflow-x: clip` narrowed from `.landing` to `.landing-hero__art`.** On the wrapper it hid
    real overflow from `documentElement.scrollWidth`, which is precisely why the page-level gate
    stayed green through both blockers.
  - **A cross-tab revoke could resurrect the revoked grant** from the IndexedDB mirror, because the
    hydrate effect re-armed on the downgrade it had just caused. The hydrate is now deferred to
    first interest in the Kids door, which also stops an anonymous marketing visit from creating
    the reader's database at all.
  - **Pip rendered faceless in dark mode** (1.12:1), **`body` had no background** so short pages
    painted browser-default white, and the design system's primary-button hover border was
    invisible in dark mode (1.01:1) app-wide. All three were found via the landing page and fixed
    at their real source.
  - **Five tests that could not fail** were rewritten, and the two mechanisms most relied on
    (the element-overflow gate and the durable-downgrade test) were verified by reintroducing the
    bugs and confirming the tests fail.

## What Remains

Nothing from the review protocol. The list that stood here is fully applied; see "What Was Done".

Two items were considered and **declined**, each documented at the point in the code where a future
reader will ask:

- **A compact doors-band variant when the band renders funnel-first (UX-7).** Two visual treatments
  of a contractual entry point is ongoing upkeep (geometry, focus order, touch targets) for a
  cosmetic gain, and on an unknown device the band sits below the fold. Revisit only with evidence
  that it diverts new visitors.
- **Replacing the landing page's `.landing-cta` and card treatments with the design system's
  `.cyo-btn` / `.cyo-card` primitives.** Cycle 3 counted 11 duplicated `.landing-cta` rules against
  13 `.cyo-btn` rules already loaded on the page, so the observation is correct and the cleanup is
  real. It is declined *here* only because it is a broad visual-equivalence refactor landing at the
  end of a large PR, where the risk of silent visual drift outweighs the tidiness. It wants its own
  change with its own visual-baseline review.

One finding was **narrowed** rather than fully applied: the stale `ink-muted only clears 3.72:1`
contrast figure appears in `guardian.css`, `kid.css`, and `library.css` as well as `landing.css`.
Recomputed it is 4.57:1 light / 5.38:1 dark, so ink-muted now passes AA and the justification those
comments give no longer holds. Only the two rules this PR already touches were corrected; the rest
are a separate sweep.

## Key Decisions

- **Pricing is a discriminated union on `available`** (`frontend/src/landing/pricing.ts`): an
  available tier must carry price + CTA, an unavailable one cannot; chose this over parallel
  boolean/status/cta fields because a partial Phase 8 flip shipped a contradictory card with every
  test green.
- **Doors order is decided once at mount** and never reshuffles mid-view (href still upgrades live);
  chose over live reordering because a section reshuffle under a reading visitor is hostile CLS.
- **The unbuyable Family card was removed**: two independent cold reviewers converged on it as a
  de-conversion element. Subscription-readiness lives in the data model plus a render filter over
  `available`, not in a visible card, so the Phase 8 flip is still a data change in `pricing.ts`.
- **Demo passage uses `:focus`, not `:focus-visible`**, deliberately (script-driven focus after
  mouse clicks must stay visible for AT users); documented in landing.css.
- **Token fallbacks are omitted in landing.css** (header note): tokens.css loads unconditionally
  and a light-only fallback would paint wrong colors in dark mode.
- **Claims discipline**: every safety/limit claim must match something enforced today
  (10-story quota, hand approval, KWS flag-off). Every cycle caught at least one overreach, the
  last being a trust card that promised reading-time tracking the guardian console does not have.
  `LandingPage.test.tsx`'s "claims discipline" block now pins the corrected ones; assume the next
  copy change needs the same scrutiny.

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

## How to Verify

1. `git fetch origin && git checkout claude/pr-717-review-e01svz && git pull`
2. `cd frontend && npm ci`
3. Recreate the Playwright browser shim (the container ships Chromium build 1194; Playwright 1.62.1
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

4. Gate loop:
   `npm run typecheck && npm run lint && npm run format:check && npm run test:run`, then
   `VITE_SUPABASE_URL=https://example.supabase.co VITE_SUPABASE_ANON_KEY=dummy VITE_API_URL= npm run build`
   and
   `PLAYWRIGHT_BROWSERS_PATH=/root/.pw-shim npx playwright test landing.spec.ts mobile-viewport.spec.ts a11y.spec.ts keyboard-nav.spec.ts --project=chromium`.
   From the repo root: `python3 scripts/check_coverage_matrix.py`.
5. Regenerate the visual baseline with
   `CI=1 PLAYWRIGHT_BROWSERS_PATH=/root/.pw-shim npx playwright test visual.spec.ts -g landing --update-snapshots`
   whenever anything above the 1280x720 fold changes, and regenerate `frontend/public/og-image.png`
   whenever the hero's copy or art changes (build, serve, screenshot the hero at 1200x630 in the
   light palette with the topbar hidden).

## Gotchas

- **Visual baseline provenance**: the committed `landing-page-chromium-linux.png` was regenerated in
  the CCR container, not on the GitHub runner. If the required `frontend-e2e` job fails on sub-pixel
  antialiasing, run the repo's `update-visual-snapshots.yml` workflow rather than hand-tuning.
- **Daily prod canary coupling**: `e2e-prod/landing-login.spec.ts` asserts the NEW headline AND the
  new login heading ("Sign in or create your account") against LIVE production; between merge and
  the frontend deploy, the nightly run will fail. Time the merge with a deploy or expect one noisy
  night. `e2e-prod/guardian-profiles.spec.ts` carries the same heading assertion in three places.
- **`mobile-safari` Playwright project cannot run in the container** (no WebKit binary); CI's
  required gate is the chromium project. Do not chase those local failures.
- **The overflow gate WAS vacuous for the landing page and is not any more.** `.landing`'s
  `overflow-x: clip` kept clipped content out of `documentElement.scrollWidth`, so the assertion
  could not fail there. The clip is now scoped to `.landing-hero__art`, and
  `mobile-viewport.spec.ts` additionally measures every `.landing` descendant's right edge. Both
  mechanisms were verified by reintroducing the bug: the gate fails and names the clipped elements.
  Keep that habit for any new gate on this page.
- **A first cycle-2 attempt died mid-run on a session usage limit**; its partial outputs were
  discarded and the pair re-ran cold. Only the re-run's findings are reflected here.
- **`body` now carries the app background** (`src/index.css`). That is a global change made from
  this page's diff, because the funnel's destination painted browser-default white. If a surface
  ever wants a different ground it must set it explicitly rather than relying on the old
  transparent default.
- **The design system's primary-button hover border changed** (`Button.css`): amber-hover was
  invisible against amber-deep in dark mode (1.01:1) and is now ink. This affects every button in
  the app, by design; no visual baseline captures a hover state, so nothing needed regenerating.
- **`docs/template_feedback.md`** (gitignored): no template-level findings this session; nothing
  filed. The authoring-lessons log was not touched: this was frontend work, not a story authoring
  run.

## Next-Session Kickoff Prompt

The homepage sales-funnel redesign is COMPLETE through all three review cycles; there is no
remediation backlog. Pick this up only for one of:

- **The two declined items** above (the compact doors-band variant, and the design-system primitive
  refactor), if either is scheduled. The refactor in particular wants its own change and its own
  visual-baseline review.
- **The `ink-muted` comment sweep** in `guardian.css`, `kid.css`, and `library.css`: the cited
  3.72:1 figure is stale everywhere it appears, and the conclusion it supports is now false.
- **Phase 8 billing** (ADR-008), where `frontend/src/landing/pricing.ts` is the flip point: give the
  Family tier `available: true`, a price, and a CTA, and its card renders with no layout work.

Hard constraints, unchanged: no em-dash characters; signed Conventional Commits; the landing chunk
stays static (no Supabase or data hooks); Kids/Grown-ups door behavior and accessible names are
contractual; never render a purchase-looking control while no billing backend exists; do not widen
`frontend/e2e/a11y.spec.ts`'s per-PR scope (ADR-029).
