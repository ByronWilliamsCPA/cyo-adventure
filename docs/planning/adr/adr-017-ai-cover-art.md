---
title: "ADR-017: AI cover art per storybook version"
schema_type: planning
status: accepted
owner: core-maintainer
purpose: "Retroactively record the shipped AI cover-art subsystem as a design decision:
  admin-triggered Gemini image generation per storybook version, WebP optimization,
  Cloudflare R2 storage, kid-visible covers with a deterministic fallback tile, and the
  human-gate posture for generated imagery."
tags:
  - planning
  - architecture
  - decisions
  - generation
---

# ADR-017: AI cover art per storybook version

> **Status**: Accepted (2026-07-16)
> **Date**: 2026-07-16
> **Relates to**: [ADR-005](./adr-005-mandatory-human-approval.md) (the human gate that
> covers imagery), [ADR-004](./adr-004-homelab-first-deployment.md) /
> [ADR-009](./adr-009-supabase-platform.md) (storage topology this adds a vendor to)
> **Source**: traceability review 2026-07-16 (finding U-2) and owner ruling the same day;
> this ADR documents a subsystem that shipped ahead of any design record

## TL;DR

Each storybook version can carry an AI-generated cover: an admin triggers generation from
the review surface, a Gemini image model produces the art from injection-hardened,
metadata-derived prompts, the image is optimized to WebP and stored in Cloudflare R2, and
the kid library shows it with a deterministic letter-tile fallback when absent. Covers are
reviewed by the admin on the same surface that approves the story, so generated imagery
sits behind the same human gate as generated prose. Per-passage illustrations remain out
of scope.

## Context

The vision listed per-passage illustrations as out of scope and said nothing about
covers; the capability register initially recorded "cover art absent from foundational
docs" (K8). Meanwhile a complete production subsystem shipped: `covers/` (prompt
construction, provider, WebP optimization, R2 storage, RQ worker, error taxonomy),
`api/covers.py` (admin-only enqueue and status polling), `cover_image_url`/`cover_status`
on `StorybookVersion`, a generate control on the admin review page, and cover display
with fallback on the kid shelf. The owner ruled 2026-07-16 that cover art is wanted
("it will add a lot to the user experience") and must become a registered design element.

## Decision

1. **Scope**: one cover per storybook version, admin-triggered (register A16); kid
   surfaces display it with the deterministic letter-tile fallback (K8, K9). Per-passage
   or in-story illustrations remain out of scope; revisiting them requires a new ADR.
2. **Generation**: Gemini image model (the "nano banana" leg, via google-genai) behind
   the covers provider seam. Prompts derive only from story metadata and are
   injection-hardened; no child PII reaches the image provider (same posture as the
   text-generation PII guard, S10).
3. **Storage and delivery**: WebP-optimized images in Cloudflare R2 (S3-compatible).
   This adds R2 as a named vendor alongside the ADR-004/009 storage topology; if story
   blobs ever externalize (Supabase Storage per ADR-009), consolidating cover storage
   there is the natural review point.
4. **Safety posture**: generated imagery is human-gated, not classifier-gated. The admin
   sees the cover on the review surface and approval covers the whole artifact (prose
   plus cover). If cover generation ever becomes guardian- or child-triggerable, or if
   volume outgrows per-item human review, an automated image-moderation pass becomes a
   precondition and this ADR must be amended.
5. **Failure behavior**: cover generation is best-effort and never blocks the publish
   path; a missing or failed cover falls back to the letter tile.

## Consequences

- ✅ K8 moves from "absent from foundational docs" to a decided, bounded capability;
  the shelf gets real covers, which carries much of the kid-facing delight.
- ⚠️ Google (Gemini image endpoint) and Cloudflare (R2) are data-handling
  counterparties for generated imagery and metadata-derived prompts; both belong in the
  privacy model's provider review scope alongside the Stage-0 classifiers.
- ⚠️ Retroactive documentation: this ADR records the subsystem as built; any behavioral
  claims found to diverge from code should be corrected here, not assumed.

## Validation

- [ ] A published story with a failed or absent cover still publishes and renders the
      fallback tile.
- [ ] No cover prompt contains child PII (covered by the same egress guard tests as
      text generation).
- [ ] The admin review surface displays the cover before approval.

## Related

- [Capability register](../capability-register.md): K8, K9, A16.
- [Privacy model](../privacy-model.md): provider counterparty scope.
- [Traceability review 2026-07-16](../traceability-review-2026-07-16.md): finding U-2.
