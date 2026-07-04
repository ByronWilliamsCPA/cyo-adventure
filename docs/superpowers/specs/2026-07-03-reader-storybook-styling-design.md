---
title: "Reader Storybook Styling and Error-State Redesign (Design)"
schema_type: planning
status: draft
owner: core-maintainer
component: Strategy
source: "Brainstorming session 2026-07-03 (Claude for Chrome QA report on the local build); frontend/src/reader/Reader.tsx + ReaderPage.tsx + ReaderRoute.tsx + DownloadNeeded.tsx; frontend/src/api/readerApi.ts + offline/sync.ts; design-system PR #44 components (PassageText, ChoiceButton, StatusBadge, ProgressBar, EmptyState, Dialog, Button) + tokens.css; prior confirmed reader concept in docs/superpowers/specs/2026-06-30-phase-4a-mobile-ui-wireframes-design.md section 4.3."
purpose: "Wire the existing PR #44 design-system components into the reader (the only kid surface that never adopted them) and split the reader's single catch-all error path into a typed phase machine so a missing story, an offline device, and a bad URL each get an honest, styled, exitable screen."
tags:
  - planning
  - architecture
  - project
---

> Date: 2026-07-03 | Author: Byron Williams (with Claude)
> Builds on: [Phase 4a wireframes section 4.3](2026-06-30-phase-4a-mobile-ui-wireframes-design.md),
> PR #44 design system (`frontend/design-system/src/components/`), and a Claude for Chrome QA
> pass on the local internal-web build.

## 1. Problem

A browser-agent QA run of the local build found that the reader, the screen where a child spends
nearly all their time, is completely unstyled: bare `<p>` passage text and bare `<button>` choices
(~21px tall, 13px font), no color, no theming, a stark contrast to the styled Profile Picker and
Library it sits between. Verified in code: no `reader.css` exists and there are **zero** CSS
selectors anywhere for `.reader`, `.reader-choices`, `.reader-ending`, or `.download-needed`.

The same run surfaced three error-handling defects, all traced to one root cause, a single
catch-all in `ReaderPage.load()`:

1. **Missing story shows the wrong message.** Any `fetchStory` failure, including a `404` for a
   story that does not exist, is caught and rendered as `DownloadNeeded` ("Your device cleared this
   story to save space"), which is factually wrong and misdirects a troubleshooting parent.
2. **Dead-end error pages.** `ReaderRoute`'s bad-URL guards render a bare `<p role="alert">` with no
   way back to the library; a child is stuck with only the browser Back button.
3. **Unhandled save rejection.** `persist()` calls `saveProgress` as `void persist(reading)`;
   `saveProgress` correctly re-throws a non-offline HTTP error (e.g. `422`), which then becomes an
   unhandled promise rejection.

The reader engine itself is sound: the QA run verified branching, restart, resume-across-reload,
rating persistence, and back/forward navigation all work. This is a presentation and error-modeling
change, **not** an engine change.

## 2. Scope

**In scope**

- Compose the reader UI from the existing design-system components (section 4).
- Replace `ReaderPage`'s single `Phase` union and catch-all with a typed phase machine that
  distinguishes missing-story from offline from other errors (section 5).
- Give `makeFetchStory` typed failures (`StoryNotFoundError` / `OfflineError`) mirroring the
  pattern `makeSyncApi` already uses (section 5).
- Add an exit ("Back to my books") to every non-reading screen.
- Wrap `persist()` so a non-conflict save error is caught and logged, never unhandled.
- The reader's first responsive breakpoint and a slim persistent top bar (section 4), honoring the
  confirmed concept in the phase-4a wireframes.

**Out of scope (tracked as separate issues)**

- The StrictMode double-save `409` "reading on another device" false-positive (a distinct
  concurrency fix; file separately).
- Real cover illustrations.
- An app-wide responsive pass beyond the reader.
- The seed-script `published_at` bug (already noted for a separate fix).

## 3. Reuse-first finding (why this is small)

PR #44 already delivered every component this screen needs, and the reader imports **none** of
them. The work is composition, not net-new UI:

| Reader element | Existing component | Key props |
| --- | --- | --- |
| Passage body | `PassageText` | `text` (serif, `--leading-relaxed`) |
| Each choice | `ChoiceButton` | `label`, plus native button props (`onClick`, `type`) |
| Online/offline chip | `StatusBadge` | `status: 'connected' \| 'offline' \| 'loading' \| 'error'` |
| Reading progress | `ProgressBar` | `value`, `label`, `showLabel` |
| Missing-story / offline / bad-URL screens | `EmptyState` | `title`, `description`, `actions`, `icon` |
| Ending restart / exit actions | `Button` | `variant`, `size` |
| Conflict overlay (unchanged logic) | existing `ConflictDialog` | left as-is this pass |

Only a thin `reader.css` for layout (the centered reading column and the sticky top bar) is
genuinely new styling.

## 4. Visual design (storybook-immersive, composed from tokens)

- **Layout**: centered column, `max-width: 40rem`, `--space-6` padding, `--color-parchment`
  canvas, matching the Library's column.
- **Persistent top bar** (confirmed in phase-4a 4.3): slim sticky bar carrying `StatusBadge`
  (reflecting online/offline) and `ProgressBar` with a short label. Chrome stays visible because
  offline reading is a core, already-built feature and surfacing connection status constantly was a
  deliberate prior decision over maximizing reading area.
  - `#ASSUME: data-integrity: the progress value is derived from visited-vs-total reachable nodes
    in the reading state.` `#VERIFY: confirm the metric source in the reader engine before wiring
    ProgressBar.value; fall back to hiding the bar's numeric label if no reliable total exists.`
- **Passage**: `PassageText`, serif, `--text-lg` scaling up past the breakpoint, `--leading-relaxed`
  (1.8), `--color-ink`.
- **Choices**: stacked full-width `ChoiceButton`s (the design-system component already meets the
  44px tap target and token styling). False-condition choices remain hidden, not disabled, as today.
- **Ending screen**: serif ending title at `--text-2xl`, the passage body, then a primary
  `Button variant="primary" size="lg"` "Read again" and a secondary "Back to my books".
- **Responsive**: a single `@media (min-width: 40rem)` bump for passage size, the app's first real
  breakpoint; no horizontal scroll at 390px (matches the Library e2e invariant).
- **Motion**: honors the existing `prefers-reduced-motion` handling in the tokens.

## 5. Error-state behavior

`ReaderPage` phase becomes `loading | reading | not-found | offline | error`.

`makeFetchStory` gains typed failures, mirroring `makeSyncApi`:

- HTTP `404` -> throw `StoryNotFoundError`.
- No HTTP response (transport failure) -> throw `OfflineError` (already defined in `offline/sync.ts`).
- Any other HTTP error -> rethrow.

`ReaderPage.load()` replaces its catch-all with:

- `StoryNotFoundError` -> phase `not-found` -> `EmptyState` title "We couldn't find that story",
  description in kid/parent-friendly language, `actions` = "Back to my books".
- `OfflineError` -> phase `offline` -> the existing `DownloadNeeded` copy, now **correct** because
  it only fires when the device is genuinely offline; add a "Back to my books" action.
- other -> phase `error` -> `EmptyState` "Something went wrong" + retry + "Back to my books".

`ReaderRoute` bad/missing-param guards render a styled `EmptyState` (or shared card) with a "Back to
my books" link instead of a bare `<p>`.

`persist()` wraps the non-conflict branch so a rejected save is caught and logged (structured, not
`console.error` noise) without interrupting reading. `#CRITICAL: concurrency: a dropped save must
not silently lose progress.` `#VERIFY: log the failure with enough context (profile, storybook,
revision) to diagnose; the local IndexedDB write in saveProgress still persisted, so the reader
state is not lost, only the server sync for that step.`

"Back to my books" navigates to the profile's library route (`/library/:profileId`).

## 6. Testing

**Unit (Vitest + Testing Library)**

- Each phase (`reading`, `not-found`, `offline`, `error`) renders its expected screen.
- `makeFetchStory` maps `404` -> `StoryNotFoundError` and a no-response error -> `OfflineError`.
- `persist()` swallows a `422` without throwing (no unhandled rejection) and logs it.
- The ending screen renders "Read again" and both exits.

**E2E (Playwright)**

- The two QA-reported bad-URL cases now show a "Back to my books" exit (no dead-end).
- A `404` story id shows the not-found screen, not the offline/download copy.
- Reader column has no horizontal scroll at 390x844.
- `ChoiceButton`s meet the 44px tap target.

## 7. Risks and mitigations

- **Progress metric may not exist cleanly.** Mitigation: the `#VERIFY` above; hide the numeric
  label rather than invent a fake total.
- **`DownloadNeeded` copy currently doubles as the generic failure.** Mitigation: it now maps only
  to true offline; the generic case gets its own `EmptyState`.
- **Component API drift** (e.g. `ProgressBar.value` range). Mitigation: read each component's props
  at implementation time; unit tests assert rendered output, not internal styling.
