---
title: "Coloring Pages and Coloring Books: Revenue and Engagement Concept"
schema_type: planning
status: draft
owner: core-maintainer
purpose: "Parked post-MVP concept: per-story printable coloring pages (free, engagement and
  word-of-mouth) and catalog-only coloring books (digital download and Amazon KDP) built on the
  existing covers pipeline. Records viability, preconditions, and a build sketch so the idea can
  be picked up after launch without re-deriving it."
tags:
  - planning
  - covers
  - commerce
audience: product-owner, engineering
---

# Coloring Pages and Coloring Books (concept, 2026-10-05)

> **Status**: parked concept, not scheduled. Owner-gated decision tracked as
> [UW-M13](./unscheduled-work-register.md#cluster-m-external-and-owner-gated). Nothing here
> authorizes implementation; it records the idea, the analysis, and the preconditions so the work
> can start cleanly once R1/MVP is live.
>
> **Capability-register IDs served** (see [capability-register.md](./capability-register.md)): K6 and K21
> (endings found as a replay motivator and a collectible), K8 (picture support at lower bands), A16
> (cover art reviewed on the approval surface before it reaches a child), and A6 (the admin's recorded
> approval is the only path from generated content to a child). No new capability row is proposed until
> the owner decision in UW-M13 is made.

## TL;DR

Three products hide inside one idea, and they deserve different verdicts:

| Tier | Product | Verdict |
| ---- | ------- | ------- |
| 1 | A free 2-4 page "Color Your Adventure" PDF for every published story | **Build, post-MVP.** Cheap, reuses `covers/`, real engagement and word-of-mouth value. Do not charge for it. |
| 2 | A 24-40 page coloring book for a few flagship *catalog* stories, sold as a web download and on KDP | **Test manually first.** Value is mostly funnel and brand, not margin. One hand-assembled run before any automation. |
| 3 | A generic 100-page AI coloring book, or a 100-page book per family-requested story | **Skip.** Commodity market, poor fit for story length, and personalized content must never go to a public storefront. |

The durable advantage this project has over the TikTok KDP crowd is not image generation, which
everyone has. It is **a story, named characters, and branching endings a child has already
invested in**. Every recommendation below leans on that and away from page count.

## Tier 1: free per-story coloring pages

### Why it is worth doing

- **Engagement off-screen.** A printed page extends the reading session without screen time,
  which is a selling point to the guardians who are the actual buyers.
- **A physical reminder of the app.** It sits on the fridge or goes to school.
- **Word-of-mouth to parents.** A small, unobtrusive "Made with CYO Adventure" line and a QR code
  to the parent landing page turn every printout into a referral, aimed at the adult who sees it.
- **Replay driver.** A closing line on the last page ("This adventure has more endings. How many
  can you find?") points back at alternate-path reading, which is the replay behavior UW-N10's
  value-rate metric already wants to measure. A page for *every* ending is a Tier 2 feature, not
  Tier 1 (see the page-budget rule in the build sketch).

### Why it should be free (part of the base offering)

- Unit cost is small: 2-4 images per story at public image-model rates of a few cents each, plus
  retries, lands well under a dollar per story.
  #ASSUME: financial: per-image pricing for the cover provider is a few cents.
  #VERIFY: re-check current per-image pricing for the cover provider before quoting any number.
- No commerce exists yet (UW-N01 is Phase 8 work), and a separate charge for four pages adds
  payment friction and App Store in-app-purchase handling for almost no revenue.
- Its job is retention and acquisition. Pricing it works against both.

### Constraints it must respect

- **Human approval (ADR-005, ADR-017).** Every image a child sees is reviewed. Coloring pages
  join the existing cover review in the admin queue: 2-4 extra thumbnails per story, approved or
  regenerated together.
- **Automated image moderation (UW-N08, ADR-027 decision 5).** ADR-027 makes an automated image
  classifier the precondition for scaling per-node art past its pilot. Coloring pages are another
  per-story image surface, so the same gate applies before this goes catalog-wide. Line art is
  lower risk than full-color art, but that is an argument for the classifier to pass it easily,
  not for skipping it.
- **Privacy (ADR-018, privacy model).** The PDF and its metadata carry no child identifiers: no
  profile id, no display name in PDF metadata, no per-child tracking parameter on the QR code. The
  QR code goes to a static parent-facing landing page, never a sign-up flow addressed to the child.
  A personalized story's PDF is downloadable by that family only, under the same access rules as
  the story itself.
- **No link-out from the kid surface.** App-store kids-category rules require a parental gate
  before a child can leave the app or reach purchase surfaces, and ADR-016 keeps sharing out of
  the child's hands. The download lives in the guardian console; a kid-surface "print" button, if
  wanted, sits behind the existing parental gate pattern.

## Tier 2: catalog coloring books (web download and KDP)

### What would actually sell

Not "100 pages of generic unicorns", which is the most saturated low-content category on Amazon.
Instead: **the coloring book of a story the child already knows**, for the catalog's flagship
titles and series, with:

- 24-40 single-sided pages, one per key scene and one per ending, in story order;
- short captions from the story text ("Mira reaches the tide pool...") so it reads as a companion
  book, not a stack of clip art;
- a final page: "The adventure has more paths. Find them in the app," with a QR code.

24-40 pages matches the real size of the stories (ADR-027 sizes 3-5 band books at 10-45 nodes);
100 pages from one short story means padding and near-duplicates, which is exactly the review
pattern that sinks AI coloring books on Amazon.

### The economics, honestly

- **KDP at $9.99.** KDP pays roughly 60% of list price minus the print cost. A short black-and-white
  8.5x11 paperback nets on the order of $3 per copy (#ASSUME: financial: KDP print-cost tables
  change; #VERIFY: re-price against the current KDP paperback royalty calculator before listing).
  Most KDP coloring books sell a handful of copies a month without paid Amazon ads, and ads eat
  most of that margin. Treat KDP as **self-funding advertising** that puts the brand in Amazon
  search, not as a revenue line.
- **Web download at $4.99.** Higher margin per sale, but it needs a storefront (Stripe on the web;
  App Store rules govern any purchase made inside the iOS app) and it is a much smaller audience
  than Amazon. Reasonable as a bundle with a subscription later, weak as a standalone.
- **The real cost is review time, not generation.** 30-40 images at a few cents each is trivial.
  A human reviewing 30-40 images per book, plus regenerations, is not. This only works for catalog
  books that are generated once and sold many times, and it gets much cheaper once UW-N08 lands.

### Risks specific to KDP

- **AI disclosure.** KDP requires publishers to disclose AI-generated images and text at upload.
  Comply; it is not shown to buyers.
- **No copyright moat.** US Copyright Office guidance treats purely AI-generated images as
  unprotectable, so anyone can copy the pages. Human-authored story text and the brand/trademark
  are what is defensible. That is another reason to sell the *story's* coloring book rather than
  generic art.
  #ASSUME: legal: the copyright position above is accurate for our use.
  #VERIFY: counsel review via UW-M03 before publishing.
- **Catalog content only, never family requests.** Stories from family requests can contain a
  child's real name, friends' names, or details a guardian supplied (privacy model, ADR-023). They
  must never reach a public storefront, and the terms of service would need to grant publishing
  rights that this project should not ask for. A hard rule: only `catalog`-origin storybook
  versions are eligible for Tier 2.
- **Volume limits and quality enforcement.** KDP caps new titles per day and has acted against
  low-quality AI catalog flooding. A few good titles beats many thin ones.
- **Link and QR rules.** Verify current KDP content guidelines on promotional content, URLs, and QR
  codes in interior pages before the first upload (#VERIFY).

## Tier 3: what to skip, and the better version of it

Skip the generic 100-page book: it competes on price in a race to the bottom with no story
advantage. Skip per-family 100-page books: privacy rules out public sale, and the page count does
not fit the stories.

The better premium version, for much later, is a **personalized printed keepsake** of a family's
own story (text, cover, and coloring pages bound together) through a print-on-demand API rather
than KDP. That is private, differentiated, and priced in the $15-25 range rather than $4.99. It
depends on commerce (Phase 8) and on ADR-018/ADR-023 clearing what personal data may go to a print
vendor, so it is only a note here.

## Build sketch (Tier 1, reused by Tier 2)

The covers pipeline already has most of the substrate: prompt construction with injection guards
(`covers/prompt.py`), provider (`covers/provider.py`), WebP optimization, private R2 storage with
presigned URLs (`covers/storage.py`), an RQ worker, an automated vision-model check of each
generated cover against its prompt (`covers/review.py`, no human involved), and the human approval
step (`POST /storybooks/{storybook_id}/versions/{version}/cover/approve` in `api/covers.py`, shown on
the admin review surface). The coloring pages reuse the human step; the automated check is a separate
pre-filter that would need a line-art variant.

1. **Scene selection (pure).** Page budget: Tier 1 is capped at 4 pages regardless of ending count.
   From the story graph pick the start node, one pivotal choice node, and up to two endings chosen by
   a deterministic rule (most distinct by path, then node id), never "every ending": a story such as
   `the-teddy-bears-picnic` has 11 endings and would blow the cap. Tier 2 raises the cap to the 24-40
   page book and is the only place with one page per ending. Deterministic, so a regeneration picks
   the same scenes.
2. **Prompt (pure).** A `coloring/prompt.py` sibling of `build_cover_prompt`: same guard preamble
   and quote-delimited untrusted story text, plus a line-art clause ("black outlines on white, no
   shading, no gray fill, closed shapes") and band-scaled complexity (3-5: thick lines, few large
   regions; 10-13: finer detail).
3. **Character consistency.** Pass the approved cover image as a reference input so the protagonist
   looks the same on every page. The cover provider's model accepts image inputs
   #ASSUME: external: the cover provider's model accepts image inputs at acceptable cost.
   #VERIFY: confirm reference-image support and pricing on the provider in use before building.
4. **Post-process and gate.** Grayscale, threshold to pure black and white, despeckle. Reject and
   regenerate a page whose ink coverage is outside a band-specific range (mostly-black fills or
   near-empty pages) or that still contains mid-gray. This catches the most common failure,
   models that "shade" a coloring page.
5. **Review.** Pages appear next to the cover on the admin review surface; a human approves them as a
   set through the same approval step as the cover. The automated vision check in `covers/review.py`
   would run first as a pre-filter only and never replaces that approval.
6. **PDF assembly.** Letter and A4 variants, one image per page with generous margins, title and
   caption text set by the PDF library (never rendered by the image model), footer branding, and a
   QR code to a static landing URL. For Tier 2 add KDP trim and bleed settings.
7. **Storage and delivery.** A `coloring_pack` row keyed to `storybook_version`, stored privately in
   R2 and served by presigned URL like covers (note UW-M07: the cover bucket's public exposure must
   be fixed first, not copied).

A full catalog coloring book (Tier 2) is the same pipeline with a larger scene cap and the KDP PDF
profile, run offline for selected catalog titles.

## Preconditions and sequencing

1. MVP live; covers pipeline stable in production.
2. UW-M07 resolved (private cover bucket), so the new artifact does not inherit the exposure.
3. Tier 1 pilot on a handful of catalog stories with human review only; measure download rate and
   whether coloring-pack downloads correlate with replay.
4. UW-N08 (automated image moderation) before Tier 1 goes catalog-wide.
5. Tier 2: one hand-assembled flagship coloring book on KDP to test demand; automate only if it
   sells or measurably drives landing-page traffic (use a distinct QR destination per channel, not
   per child).
6. Commerce (UW-N01, Phase 8) before any web-sold download.

## Open owner decisions

- Is Tier 1 part of the base offering for every story, or only catalog stories at first?
- Confirm the page budget: Tier 1 capped at 4 pages with at most two ending pages, and one page per
  ending reserved for Tier 2 books.
- Branding: how prominent may the footer and QR code be on a child's printout?
- Tier 2 go/no-go after the single-title test, and which flagship titles go first.
- Whether to engage counsel (UW-M03) on AI disclosure, copyright, and KDP terms before the first
  listing or as part of the existing engagement.
