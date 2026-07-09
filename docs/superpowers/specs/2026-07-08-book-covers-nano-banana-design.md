---
title: "Book Covers via Nano Banana (Design)"
schema_type: planning
status: draft
owner: core-maintainer
component: Strategy
source: "Brainstorming session 2026-07-08; image-generation repo nano banana convention (google-genai); CYO storybook content model + RQ worker + library BookCard surface."
purpose: "Generate story-derived front-cover book images via nano banana (Gemini image generation), stored as small WebP in Supabase and rendered in the kid library BookCard tile with an HTML title overlay."
tags:
  - planning
  - project
---

## Problem

CYO Adventure has no book covers. In the kid library, every story tile
(`frontend/src/library/BookCard.tsx`) renders a placeholder: the uppercased
first letter of the title in a cover-shaped box. Stories carry rich content
(title, themes, age band, safety flags, prose) that could drive a distinctive
illustrated cover, but nothing consumes that content for imagery today. There
is no cover field on any model and no object storage wired.

This spec designs a feature where an admin generates an illustrated front cover
for a published story from its own contents, using nano banana (Google Gemini
image generation), and the library renders it in place of the letter tile.

## Ratified decisions

From the brainstorming session (2026-07-08):

| Decision | Choice | Rationale |
| --- | --- | --- |
| Storage backend | Supabase Storage (`covers` bucket, public URL) | Supabase already in the stack for auth + Postgres; a public bucket gives durable storage + CDN with minimal new infra. |
| Generation trigger | Admin button only | Explicit generation from the approval/admin console; no auto-trigger at publish. |
| Model tier | Pro (`gemini-3-pro-image-preview`) | Higher illustration fidelity. (Note: Pro's text-rendering edge is unused because covers are textless; Pro is chosen for artwork quality.) |
| Title rendering | Textless art + HTML title overlay | Avoids garbled AI text, keeps the title accessible/localizable/screen-readable, image stays reusable. |
| Cover attachment | Per `StorybookVersion` | Cover is derived from a specific immutable version's blob; a new published version gets a new cover. |
| Aspect ratio | Portrait 2:3, tile CSS changed to portrait | A real book-cover shape rather than a landscape banner. |
| Generation execution | Async on the existing RQ/Redis worker | Pro generation takes 10-30s and the SDK call has no retry; do not hold an HTTP request open on an external API. |
| Storage budget | Small WebP in Supabase (target <= ~250KB); optional full-res PNG local backup | Supabase bucket is capped at **500MB total**. A web-sized WebP keeps ~2,000-3,000 covers within budget; the large source is downscaled before upload. |

## Architecture

```text
Admin console (frontend)
  │  POST /api/v1/admin/storybooks/{id}/versions/{v}/cover   (enqueue)
  │  GET  .../cover                                          (poll status)
  ▼
FastAPI admin route (api/covers.py)
  │  enqueue on the "generation" RQ queue
  ▼
RQ worker  (covers/worker entrypoint: run_cover_job_sync)
  │  covers/service.py orchestrates:
  │    1. load StorybookVersion.blob (+ join Concept.brief for protagonist)
  │    2. covers/prompt.py   -> descriptive prompt string
  │    3. covers/provider.py -> nano banana Pro (google-genai) -> source PNG bytes
  │    4. covers/optimize.py -> downscale + WebP encode -> small bytes (<=~250KB)
  │         (optional: write full-res source PNG to local backup dir)
  │    5. covers/storage.py  -> upload WebP to Supabase "covers" bucket -> public URL
  │    6. write StorybookVersion.cover_image_url + cover_status
  ▼
Postgres  (StorybookVersion.cover_image_url, cover_status)
  │
  ▼  surfaced via Storybook.current_published_version
Library API (api/library.py)  -> LibraryItem.cover_url
  ▼
BookCard.tsx  -> <img src={cover_url}> with HTML title overlay
                 (falls back to first-letter tile when null)
```

## Components

Each component has one purpose, a defined interface, and can be tested in
isolation.

### `covers/prompt.py` - prompt construction

**Purpose:** turn a story version's content into one descriptive nano banana
prompt. No I/O, no network; pure function over already-loaded data.

**Interface:** `build_cover_prompt(blob: dict, brief: ConceptBrief | None) -> str`

**Inputs, in priority order:**

- `blob["title"]` and `blob["metadata"]["themes"]` - what the story is about.
- `blob["metadata"]["age_band"]` - drives art maturity/style register.
- `blob["metadata"]["content_flags"]` + per-node `safety_scope` - **cap** the
  scariness/peril of the art to the story's own safety ceiling.
- `blob["start_node"]` body + ending-node bodies/titles - plot arc / setting.
- `brief.protagonist` (name/age/role) and `brief.premise`, when the concept
  join succeeds - character identity. The blob has no character roster;
  `story_requests/anchoring.py::anchor_context_from_blob` already walks the
  blob and recovers the protagonist from the concept, so reuse that pattern.

**House-style scaffold** (fixed prefix/suffix for library-wide visual
consistency): children's-storybook illustration, warm and whimsical, portrait
framing, **no text or lettering anywhere in the image**, age-appropriate, safe.
The scaffold enforces consistency; the story-specific slots give each cover its
identity.

### `covers/provider.py` - nano banana call

**Purpose:** call Gemini image generation and return raw image bytes. Mirrors
the convention in `/home/byron/dev/python-libs/packages/gemini-image` but is
self-contained so CYO does not depend on that monorepo.

**Interface:** `generate_cover_image(prompt: str, settings: Settings) -> bytes`

**Behavior:**

- Uses the official `google-genai` SDK (added as a direct dependency), not raw
  HTTP.
- `client = genai.Client(api_key=settings.gemini_api_key)`.
- `client.models.generate_content(model="gemini-3-pro-image-preview",
  contents=[prompt], config=types.GenerateContentConfig(
  response_modalities=["IMAGE", "TEXT"],
  image_config=types.ImageConfig(aspect_ratio="2:3", image_size="1K")))`.
  Source is `1K` (not `2K`): the final asset is downscaled to a web-sized
  WebP anyway, so a `1K` source is ample and cuts generation cost and
  post-processing work.
- Extract bytes from `response.candidates[0].content.parts[*].inline_data.data`.
- A safety refusal (empty candidates / `content is None`) raises a typed
  `CoverGenerationError` carrying `prompt_feedback`. No retry/backoff (matches
  the reference implementation; the caller decides retry policy).

### `covers/optimize.py` - size reduction

**Purpose:** turn the large source image into a small, web-sized asset that
respects the 500MB Supabase budget. Pure function; no network.

**Interface:** `optimize_cover(source_bytes: bytes, *, max_width: int = 800,
quality: int = 80, max_bytes: int = 256_000) -> bytes`

**Behavior:**

- Uses Pillow (`pillow`, added as a direct dependency).
- Downscale to `max_width` (portrait, preserving 2:3), encode WebP at
  `quality`.
- If the result still exceeds `max_bytes`, step the quality down (e.g. 80 ->
  70 -> 60) until under the ceiling or a floor is hit; the ceiling is a target,
  not a hard failure (log if the floor is reached).
- Returns the WebP bytes; `service.py` then uploads them. At ~200KB/cover, a
  500MB bucket holds ~2,500 covers.

**Optional local full-res backup:** when a `covers_backup_dir` setting is
configured, `covers/service.py` also writes the original source PNG there
before optimization, keyed `{storybook_id}/{version}.png`. Best-effort only:
per the deployment notes, container volumes are wiped on redeploy unless a
persistent volume is mounted, so the backup is a convenience, never the system
of record. A backup-write failure is logged and does not fail the job.

### `covers/storage.py` - Supabase upload

**Purpose:** persist image bytes and return a public URL.

**Interface:** `upload_cover(image_bytes: bytes, key: str, settings: Settings)
-> str` where `key` is deterministic, e.g. `{storybook_id}/{version}.webp`.

**Behavior:**

- Uploads the optimized WebP to the Supabase Storage `covers` bucket (public)
  using a storage-scoped/service key (new setting; distinct from the auth JWKS
  path), with `content-type: image/webp`.
- Upsert semantics so a regenerate overwrites the same key (no orphaned
  objects, so the 500MB budget is not leaked on re-rolls).
- Returns the bucket's public object URL.

### `covers/service.py` - orchestration

**Purpose:** the end-to-end job body, wired for injection so it is testable
without Redis.

**Interface:** `async def generate_cover(storybook_id: str, version: int,
session: AsyncSession, settings: Settings) -> None`

**Steps:** set `cover_status="generating"` -> load blob + concept brief ->
build prompt -> generate source bytes -> (optional local backup write) ->
optimize to WebP -> upload -> write `cover_image_url` + `cover_status="ready"`
in its own transaction. On any failure set `cover_status="failed"` and log;
never raise out of the worker.

### Worker entrypoint

`run_cover_job_sync(storybook_id, version)` - the sync wrapper RQ calls (mirrors
`generation/worker.py::run_generation_job_sync`). Opens its own `AsyncSession`
with its own transaction boundary. Enqueued on the existing `"generation"`
queue via `generation/queue.py`.

### API route - `api/covers.py`

- `POST /api/v1/admin/storybooks/{id}/versions/{v}/cover` - admin-guarded
  (reuse the existing admin auth dependency used by `api/approval.py`),
  enqueues the job, sets `cover_status="generating"`, returns 202 + status.
- `GET /api/v1/admin/storybooks/{id}/versions/{v}/cover` - returns
  `{cover_status, cover_url}` for the console to poll.

### Data model - one migration

Add to `StorybookVersion` (`src/cyo_adventure/db/models.py`):

- `cover_image_url: Mapped[str | None] = mapped_column(String(1024))`
- `cover_status: Mapped[str] = mapped_column(String(16), default="none")`
  with a CHECK constraint `ck_storybook_version_cover_status` over
  `{none, generating, ready, failed}` (follows the existing `ck_*_status`
  pattern).

Mirrors the `ChildProfile.avatar` String-URL precedent. One Alembic revision.

### Config - `core/config.py`

New `Settings` fields:

- `gemini_api_key: str | None`
- Supabase Storage settings: bucket name (`covers`) + a storage-scoped/service
  key + the Supabase URL (URL may already be present for auth; reuse if so).
- `covers_backup_dir: str | None` - when set, full-res source PNGs are written
  there as a best-effort local backup (default unset = no backup).
- Optional tunables for the WebP target (`cover_max_width`, `cover_quality`,
  `cover_max_bytes`) with the defaults from `optimize.py`.

New dependencies: `google-genai` (nano banana SDK) and `pillow` (WebP
optimization).

If `gemini_api_key` or the storage key is unset, the enqueue endpoint returns a
clear 503/misconfiguration error rather than enqueuing a job that will fail.

### Frontend surface

Two-place rule (the UI reads a hand-typed adapter, not the generated client):

1. Backend: add `cover_url: str | None = None` to the `LibraryItem` Pydantic
   schema (`api/schemas.py`) and populate it in `api/library.py::_library_item`
   from the current published version's `cover_image_url`. Merge the cover into
   the single-story blob response in `get_storybook_version`.
2. Regenerate the client (`npm run generate-client`) for type parity.
3. Hand-add `cover_url` to the `LibraryItemView` interface in
   `frontend/src/library/libraryApi.ts` - this is the type `BookCard` actually
   imports and renders.
4. `BookCard.tsx`: render `<img src={cover_url} alt="">` (decorative;
   `aria-hidden` on the image, title conveyed by the existing `<h3>`) inside
   `.book-card__tile`, with the title as an HTML overlay. Fall back to today's
   first-letter tile when `cover_url` is null.
5. `library.css`: change `.book-card__tile` `aspect-ratio` from `3 / 2` to
   `2 / 3`; add the title-overlay styles and `object-fit: cover` on the image.
6. Admin console: a **Generate cover** button on the story detail view that
   POSTs the enqueue endpoint and polls the GET endpoint, showing
   generating/ready/failed and a retry on failure.

## Data flow

1. Admin opens a published story in the console and clicks **Generate cover**.
2. `POST .../cover` validates config + admin auth, sets `cover_status`
   to `generating`, enqueues `run_cover_job_sync` on the `"generation"` queue,
   returns 202.
3. The worker runs `covers/service.py::generate_cover`: loads the version blob,
   joins back through `GenerationJob.concept_id -> Concept.brief` for the
   protagonist, builds the prompt, calls nano banana Pro, optimizes the result
   to a small WebP (optionally backing up the source PNG locally), uploads the
   WebP to Supabase, and writes `cover_image_url` + `cover_status="ready"`.
4. The console polls `GET .../cover` until `ready` (or `failed`) and shows the
   result.
5. On the next library fetch, `LibraryItem.cover_url` is populated for that
   story and `BookCard` renders the image with the title overlaid.

## Error handling and safety

- **Safety refusal / generation failure:** the job sets `cover_status="failed"`
  and logs `prompt_feedback`; the worker never raises. The admin can re-click
  Generate. The library falls back to the letter tile, so a missing/failed
  cover degrades gracefully.
- **Content-flag caps in the prompt** keep requests within the kids-safe
  envelope, minimizing refusals.
- **Missing credentials:** the enqueue endpoint fails fast with a clear
  configuration error instead of enqueuing a doomed job.
- **Upload failure:** treated the same as generation failure (`failed` status).
- **Regenerate:** deterministic storage key + upsert means a re-roll overwrites
  the previous image at the same URL (no orphaned objects). Note: because the
  URL is stable across regenerations, CDN/browser caching may serve a stale
  image; append a cache-busting query derived from the job's completion time
  (e.g. `?v=<unix-ts>`) to `cover_image_url` when writing it.

## Testing

- `covers/prompt.py`: unit tests over representative blobs - asserts title,
  themes, age band, and content-flag caps appear; asserts protagonist is
  included when the brief is present and gracefully omitted when the join
  fails; asserts the "no text in image" instruction is always present.
- `covers/provider.py`: unit test with the `google-genai` client mocked -
  asserts model id, aspect ratio, `response_modalities`, correct byte
  extraction, and that a refused/empty response raises `CoverGenerationError`.
- `covers/optimize.py`: unit test - asserts output is valid WebP, portrait
  dimensions <= `max_width`, and size under `max_bytes` (including the
  quality-step-down path for a large synthetic input).
- `covers/storage.py`: unit test with the Supabase client mocked - asserts key
  format (`.webp`), `image/webp` content type, upsert, and returned public URL.
- `covers/service.py`: integration-style test with provider + storage mocked
  and a real (testcontainers) session - asserts `generating -> ready` writes
  the URL, and that a provider error yields `failed` without raising.
- API route: tests for admin-auth enforcement, 202 on enqueue, 503 when
  credentials are unset, and status polling.
- Library: `_library_item` populates `cover_url` from the current published
  version; null when no cover exists.
- Frontend: `BookCard` renders `<img>` when `cover_url` is set and the letter
  tile when null; `libraryApi` adapter maps the new field.

## Out of scope (YAGNI for v1)

- Automatic generation at publish (admin-only was chosen).
- Reference-image character consistency across a series (nano banana supports
  passing prior covers as references; noted as a future extension, not built).
- A reader title-screen splash (the reader has no pre-story screen today;
  adding one is separate UI work).
- Migrating story blobs off inline JSONB / activating the reserved MinIO
  `blob_ref` path.
