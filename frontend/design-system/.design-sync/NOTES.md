# Design Sync Notes — @cyo/design-system

## Setup

- Package: `frontend/design-system/` (standalone Vite library, not a monorepo)
- Build: `npm run build` in `frontend/design-system/` — produces `dist/cyo-design-system.{js,umd.cjs,css}`
- node_modules path: `./node_modules` (relative to package root)
- Entry for converter: `./dist/cyo-design-system.js` (ESM bundle)
- CSS entry: `dist/cyo-design-system.css` (tokens + all component CSS bundled by Vite)
- tsconfig: `./tsconfig.json` — `noEmit: true`, so no `.d.ts` files in dist; converter cannot auto-discover components via `.d.ts` scan
- FIX: `componentSrcMap` in `design-sync.config.json` seeds the component list explicitly; without it the converter logs `[ZERO_MATCH]` and falls through to tokens-only mode

## First sync — 2026-06-30

- 7 components: Button, ChoiceButton, Dialog, EmptyState, PassageText, ProgressBar, StatusBadge
- All authored previews (user chose "author all 7")
- Target project: 9115f845-b975-460a-af83-cf8e33fff14e ("Design System" on claude.ai/design)
- Branch: feat/design-sync-init (isolated from feat/phase-3-slice-3-backend-closeout)

## Re-sync risks

- `dist/` is gitignored — a fresh clone must run `npm run build` before the converter
- Token CSS is bundled INTO `cyo-design-system.css` by Vite (no separate token file); `cssEntry` covers it
- TypeScript source is the type authority (no emitted `.d.ts`); if component APIs change, rebuild + re-sync
- Georgia/serif fonts are system fonts — no `@font-face` to ship; the design agent gets the font stack via CSS `font-family` in the bundle
