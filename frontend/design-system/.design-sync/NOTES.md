# Design Sync Notes: @cyo/design-system

## Setup

- Package: `frontend/design-system/` (standalone Vite library, not a monorepo)
- Build: `npm run build` in `frontend/design-system/`; produces `dist/cyo-design-system.{js,umd.cjs,css}`
- node_modules path: `./node_modules` (relative to package root)
- Entry for converter: `./dist/cyo-design-system.js` (ESM bundle)
- CSS entry: `dist/cyo-design-system.css` (tokens + all component CSS bundled by Vite)
- tsconfig: `./tsconfig.json` sets `noEmit: true`, so no `.d.ts` files in dist; converter cannot auto-discover components via `.d.ts` scan
- FIX: `componentSrcMap` in `design-sync.config.json` seeds the component list explicitly; without it the converter logs `[ZERO_MATCH]` and falls through to tokens-only mode

## First sync: 2026-06-30

- 7 components: Button, ChoiceButton, Dialog, EmptyState, PassageText, ProgressBar, StatusBadge
- All authored previews (user chose "author all 7")
- Target project: 9115f845-b975-460a-af83-cf8e33fff14e ("Design System" on claude.ai/design)
- Branch: feat/design-sync-init (isolated from feat/phase-3-slice-3-backend-closeout)

## Second sync: 2026-07-02

- Added AvatarCircle (8th component), extracted from `frontend/src/profiles/` after C4a-2
  (PR #60) landed it app-side; the app copy switches to the `@ds` import after #60 merges.
- Ships with its avatar catalog (`avatars.ts`): 8 preset ids with emoji glyph placeholders.
  Presets are the permanent model (no photo uploads); generated illustrated art replaces the
  glyphs later (issue #65). The ids are the stable contract.
- Authored preview: WithPresetGlyph, InitialFallback, FullCatalog.
- Branch: feat/design-sync-avatar-circle (isolated from the in-review PR #60 branch).
- Config moved from `design-sync.config.json` to `.design-sync/config.json` (skill's
  canonical location).
- Added `cfg.dtsPropsFor` for ALL 8 components: tsconfig `noEmit: true` means dist ships
  no `.d.ts`, so the converter emitted `[key: string]: unknown` stubs; the hand-written
  bodies mirror the source interfaces.
- Added `cfg.overrides.Button: {"cardMode": "column"}` after a `[GRID_OVERFLOW]` warn
  (Disabled/Sizes/Variants rows render wider than a grid cell).
- Authored `.design-sync/conventions.md`, wired via `readmeHeader`.
- Render check: playwright is NOT in this package's node_modules; install `playwright@1.61`
  into `.ds-sync/` (matches the cached chromium-1228 in ~/.cache/ms-playwright).

## Known render warns

- `[FONT_MISSING]` "Palatino Linotype", "Palatino", "Book Antiqua": accepted by design.
  The serif stack (Georgia/Palatino) is intentionally system fonts; there is no woff2 to
  ship. Recorded at first sync ("Georgia/serif fonts are system fonts").

## Re-sync risks

- `dist/` is gitignored; a fresh clone must run `npm run build` before the converter
- Token CSS is bundled INTO `cyo-design-system.css` by Vite (no separate token file); `cssEntry` covers it
- TypeScript source is the type authority (no emitted `.d.ts`); if component APIs change, rebuild + re-sync
- Georgia/serif fonts are system fonts: no `@font-face` to ship; the design agent gets the font stack via CSS `font-family` in the bundle

## Drift risks (external resource / data integrity)

- #ASSUME: external resource: `projectId` in `design-sync.config.json` points to a
  specific claude.ai/design project that this repo does not control the lifecycle of.
  #VERIFY: before running a re-sync, confirm the project still exists and this branch
  is still the intended target; a deleted or renamed project fails the sync silently
  rather than erroring loudly.
- #ASSUME: data integrity: `componentSrcMap` in `.design-sync/config.json` is a manually
  maintained list of component name to source path; it is not generated from `src/`.
  #VERIFY: when adding, removing, or renaming a component under
  `src/components/`, update `componentSrcMap` in the same change, or the converter
  falls back to `[ZERO_MATCH]` tokens-only mode for the affected component without
  failing the build.
- #ASSUME: data integrity: `dtsPropsFor` in `.design-sync/config.json` hand-duplicates
  every component's props interface because the package emits no `.d.ts` (`noEmit: true`).
  #VERIFY: when a component's props change, update its `dtsPropsFor` entry in the same
  change, or the design agent codes against a stale API. The durable fix is emitting real
  declarations (e.g. vite-plugin-dts) and dropping `dtsPropsFor`.
- `conventions.md` enumerates token names and component props; re-validate its claims
  against the fresh build on every re-sync (the skill's conventions-header step does this).
