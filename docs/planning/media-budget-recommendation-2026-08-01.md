---
title: "Media Budget Recommendation: Offline-First Media Sizing (v1)"
schema_type: planning
status: draft
owner: core-maintainer
purpose: "Best-practice research and per-band media budget recommendation commissioned by owner
  decision D13 (kid-appeal design review): image formats and sizes for in-story illustration,
  audio strategy, per-book and per-device offline budgets, and iOS PWA storage mitigations."
tags:
  - planning
  - frontend
  - covers
  - offline
audience: product-owner, engineering
---

# Media Budget Recommendation (2026-08-01)

> **Status**: Recommendation for owner approval | commissioned under decision D13 in
> [design-review-kid-appeal-2026-08-01.md](design-review-kid-appeal-2026-08-01.md) section 8 (Q6).
> Evidence classes are labeled: measured (repo code, vendor price sheets, published engine
> behavior), vendor docs, and heuristic (extrapolations and market norms).

## 1. The binding constraint is the device, not the cloud (measured)

Cloudflare R2, where covers already live, charges zero egress; storage is $0.015/GB-month with a
perpetual 10GB free tier ([R2 pricing](https://developers.cloudflare.com/r2/pricing)). A thousand
fully illustrated books at 10MB each fit in the free tier. Cloud cost is a non-factor. The real
constraints are:

1. **Device storage with all-or-nothing eviction.** Browsers evict an origin's storage entirely
   (IndexedDB and Cache Storage together, never partially) under LRU pressure. A full family
   tablet does not lose one book; it loses the whole offline library at once.
2. **Download time on family wifi.** A 10MB book is roughly 4-8 seconds on mediocre wifi; that is
   the UX ceiling for "tap to save for offline."

## 2. Browser storage reality (vendor docs)

- **iOS/Safari**: per-origin quota up to ~60% of total disk for Safari and for **Home Screen web
  apps**; the 7-day ITP storage wipe applies to Safari-tab usage but **installed home-screen web
  apps are effectively exempt** (WebKit: they "have their own counter" and data deletion there
  would be "a serious bug"). Sources:
  [WebKit storage policy](https://webkit.org/blog/14403/updates-to-storage-policy/),
  [WebKit ITP post](https://webkit.org/blog/10218/full-third-party-cookie-blocking-and-more/).
- **Chrome/Android**: per-origin up to 60% of disk; `navigator.storage.persist()` auto-decided by
  engagement heuristics ([web.dev](https://web.dev/storage-for-the-web/)).
- **Firefox**: best-effort min(10% of disk, 10GiB); prompt-based persistent mode.
- ADR-002's stance ("call `persist()` but do not trust it; IndexedDB is a cache, Postgres is
  canonical") is correct and stays.

**Practical safe budget (heuristic)**: family tablets are frequently old 32GB iPads with 2-8GB
free. Self-impose a default offline cap of ~250MB with a hard self-cap of 500MB, gated by
`navigator.storage.estimate()` before each download, evicting by our own per-profile LRU rather
than letting the browser's all-or-nothing eviction decide.

## 3. Images (vendor docs + measured comparisons)

- **Format**: keep WebP (~95-96% support). For illustrated art specifically, AVIF's advantage
  narrows to ~10-15% smaller at ~5x encode cost (measured comparisons:
  [SpeedVitals](https://speedvitals.com/blog/webp-vs-avif),
  [BulkImagePro](https://bulkimagepro.com/compare/next-gen-image-formats)). JPEG XL is
  Safari-only; not usable. **Keeping the existing WebP pipeline is the recommendation.**
- **Resolution**: 1536px wide is the sweet spot for full-width art on 10" tablets (2x of an
  ~800-CSS-px layout; Apple/KDP 2048px targets are print-retail-derived and oversized for
  screen-only). Store **one reader rendition (1536px) plus an optional ~300px thumbnail** for
  grids; do not cache multiple DPR variants offline.
- **Size targets (heuristic, extrapolated from the repo's own 800px/256KB cover pipeline)**:
  children's-book art at 1536px WebP q70-75 lands ~100-200KB; target **150KB, ceiling 200KB** per
  illustration; spot art at 1200px can target 120KB.
- **Loading**: offline, decode is the cost, not network; render the current node's image and
  prefetch-decode 2-4 adjacent nodes. Online, fetch ahead along outgoing edges instead of eagerly
  downloading whole books.

## 4. Audio (measured arithmetic + codec reality)

- **Codec gotcha**: Ogg Opus does not play on iOS Safari; use **AAC-LC in .m4a** (universal;
  48-64kbps mono is fine for narration). Sources:
  [Apple dev forums](https://developer.apple.com/forums/thread/722399),
  [Opus support matrix](https://www.testmuai.com/learning-hub/opus-audio-codec-browser-support/).
- **UI sound effects**: 10-20 short SFX at 10-30KB each is under 0.5MB total; **bundle app-wide
  once** in the service-worker precache, as every comparable product does. Mute control required
  per owner decision D7.
- **Ambient loops (if added)**: a shared app-wide mood library (~2-3MB total), not per-book.
- **Recorded narration (if ever)**: 3-8MB per young-band book at 48-64kbps AAC mono; it dominates
  any budget it enters. Browser TTS (already shipped) costs zero bytes and stays the default;
  recorded narration is an explicit per-book opt-in add-on download with its own size tag, never
  bundled.

## 5. Market anchors (heuristic)

Kindle illustrated picture books cluster at 4-8MB (delivery-fee-shaped market norm); single-title
multimedia storybook apps run 100-400MB (e.g., a 32-page narrated/animated title at 151.8MB),
which is the ceiling NOT to emulate. Static-illustration kids' ebooks at 4-10MB per book is the
industry lane.

## 6. Recommendation table

Assumes story JSON 0.1-0.4MB gzipped and the existing 256KB cover. "Scene" = contiguous nodes
sharing a setting (the graph's chapter/anchor structure already provides this).

| Band | Illustration basis | Spec | Est. images/book | Per-book media budget | Audio |
|---|---|---|---|---|---|
| 3-5 (10-45 nodes) | per node (the image is the page) | WebP 1536px, ≤150KB target / 200KB ceiling | 10-45 | **≤8MB** | app SFX + TTS; narration opt-in (+3-8MB) |
| 5-8 (29-86 nodes) | per scene (~1 per 2-3 nodes) | same | 12-35 | **≤6MB** | same |
| 8-11 (60-240 nodes) | per chapter/anchor scene (spot art) | WebP 1200px, ≤120KB | 8-20 | **≤3.5MB** | SFX only |
| 10-13 | cover + chapter headers | 1200px, ≤120KB | 4-10 | **≤2MB** | SFX only |
| 13-16 / 16+ | cover only (1-3 mood pieces at most) | cover spec as today | 1-4 | **≤1MB** | SFX only |

A 240-node 8-11 book must NOT get per-node art (it would be ~36MB); the per-scene basis is what
keeps the budget flat as node counts grow.

**Per-device offline library budget**: target ~40 books within ~250MB (mixed-band average ~4MB per
book); hard self-cap 500MB enforced client-side with `storage.estimate()` and our own
oldest-unpinned eviction.

**iOS mitigations (extends ADR-002)**:

1. Gate the offline-library promise behind **Add to Home Screen**: installed web apps get the
   large quota, favorable `persist()` heuristics, and exemption from the 7-day wipe; in-tab Safari
   usage is treated as ephemeral cache only.
2. Call `navigator.storage.persist()` on install; keep server-authoritative reading state so a
   wipe costs re-download, never progress (already the architecture).
3. Show "last verified offline" per book and re-verify silently when online, since iOS has
   historically lost IndexedDB on OS updates.

## 7. Owner decision points

1. Adopt the per-band budget table above (it operationalizes D7's "balance storage against
   reasonable offline download sizes").
2. Confirm image pipeline stays WebP (defer AVIF until it earns its encode cost).
3. Confirm audio v1 = app-bundled UI SFX only (mute per D7), with ambient/narration deferred to
   explicit follow-up decisions.
4. Approve the 250MB default / 500MB hard self-cap for the offline library and the
   Add-to-Home-Screen gating of the offline promise on iOS.
