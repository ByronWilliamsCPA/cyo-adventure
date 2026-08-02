---
title: "ADR-027: In-story illustration (3-5 pilot)"
schema_type: planning
status: accepted
owner: core-maintainer
purpose: "Amend ADR-017's per-passage-illustration exclusion to authorize art scope by band
  (per-node at 3-5, per-scene at 5-8), define the schema-minor node fields it rides on, and
  bound the pilot to the seven 3-5 skeletons with per-item human review, naming automated
  image moderation as the gate that must land before the pilot expands."
tags:
  - planning
  - architecture
  - decisions
  - covers
  - storybook
---

# ADR-027: In-story illustration (3-5 pilot)

> **Status**: Accepted (2026-08-01), on owner direction recorded in
> [design-review-kid-appeal-2026-08-01.md](../design-review-kid-appeal-2026-08-01.md) section 8
> (decisions D13, D20) and adopted by
> [kid-appeal-implementation-plan.md](../kid-appeal-implementation-plan.md) W4.1.
> **Authority**: [media-budget-recommendation-2026-08-01.md](../media-budget-recommendation-2026-08-01.md)
> section 6 (per-band budget table) and section 7 (owner decision points), ratified as D20.
> **Amends**: [ADR-017](./adr-017-ai-cover-art.md) decision 1 ("per-passage or in-story
> illustrations remain out of scope; revisiting them requires a new ADR") and engages ADR-017
> decision 4's own amendment clause (the automated-moderation precondition).
> **Cross-sign**: [ADR-025](./adr-025-additive-storybook-schema-versioning.md) (the schema minor
> this rides on), both player engines and the conformance corpus once the fields become
> runtime-visible, `covers/` (the reused pipeline substrate).
> **Scope**: this ADR is a design record only. No pipeline, schema, or reader code ships with it;
> implementation is separately scheduled work.

## TL;DR

ADR-017 scoped AI art to one cover per storybook version and named per-passage illustration as
out of scope, to be revisited only by a new ADR. This is that ADR. It authorizes per-node
illustration at the 3-5 band and per-scene illustration at 5-8 (the latter for a later pilot,
not this one), reusing the covers pipeline (prompt construction, R2 storage, WebP optimization)
rather than building a new one. Two optional node fields, `image_url` and `image_alt`, carry the
art through an ADR-025 schema minor. Per-node art at 3-5 multiplies image volume from one per
book to one per page, exactly the "volume outgrows per-item human review" condition ADR-017
names as the trigger for automated image moderation; this ADR does not build that classifier. The
pilot instead stays bounded (the seven 3-5 skeletons only) and keeps per-item human review, and
names automated moderation as the precondition for any expansion past the pilot.

## Context

ADR-017 shipped one AI-generated cover per storybook version, human-gated on the same admin
review surface that approves the story's prose, and explicitly excluded per-passage art:
"Per-passage or in-story illustrations remain out of scope; revisiting them requires a new ADR."
That ADR also named its own amendment trigger in decision 4: "If cover generation ever becomes
guardian- or child-triggerable, or if volume outgrows per-item human review, an automated
image-moderation pass becomes a precondition and this ADR must be amended."

The kid-appeal design review (D13) commissioned a best-practice media sizing recommendation,
delivered as media-budget-recommendation-2026-08-01.md and adopted whole by the owner as D20:
WebP stays the format, 1536px is the reader-rendition resolution, and the per-band table sets a
per-node basis at 3-5 (the image is the page), a per-scene basis at 5-8 (roughly one illustration
per 2-3 nodes, so a growing node count does not blow the budget linearly), and spot art or
cover-only for every band above that. The recommendation frames the per-device offline budget
(W4.3, a sibling item in this same wave) as the hard constraint; per-book size is the softer,
band-graded constraint this ADR operationalizes for illustration specifically.

Node count at 3-5 runs 10-45 per skeleton (ADR-011's scale table). Per-node art there means 10-45
generated images per book instead of ADR-017's one cover per book: an order-of-magnitude increase
in generated-image volume per approval pass. ADR-017's own volume-outgrows-review trigger is not
hypothetical here; it is the exact shape of what per-node art produces. This ADR resolves that by
scoping the pilot narrowly (seven skeletons, not the whole 3-5 cell) rather than by building the
classifier now: the classifier is real engineering work with its own accuracy/latency tradeoffs,
and committing to it ahead of any illustrated content existing to review would be speculative.
Keeping the pilot small enough for continued per-item human review, while naming the gate
explicitly, lets the pilot ship without that dependency and forces the conversation before scale.

## Decision

1. **Scope amendment to ADR-017 decision 1.** Per-passage illustration is no longer categorically
   out of scope. It is authorized by band:
   - **3-5**: per-node art (media recommendation: "the image is the page"). This is the pilot.
   - **5-8**: per-scene art (roughly one illustration per 2-3 contiguous nodes sharing a setting,
     using the graph's existing chapter/anchor structure to define a scene). Authorized in scope
     by this ADR but **not** part of this pilot; it follows once the 3-5 pilot's review load,
     budget adherence, and moderation posture are validated.
   - **8-11 and up**: unchanged from ADR-017. Cover art only; this ADR does not extend art scope
     there. Any future spot-art-per-chapter proposal (the media recommendation's 8-11/10-13 rows)
     needs its own decision when it is actually proposed.
2. **Pilot bound.** The seven 3-5 skeletons named in the implementation plan (W4.1), and no others,
   receive per-node art under this ADR. Expanding per-node art to the rest of the 3-5 cell, or
   starting the 5-8 per-scene pilot, is a separate go/no-go decision gated on decision 5 below, not
   an automatic follow-on.
3. **Prompt construction reuses ADR-017's posture, extended with node text.** ADR-017's cover
   prompts derive only from story metadata (title, theme, band, tone) and are injection-hardened
   against content embedded in that metadata; no child PII reaches the image provider. In-story
   illustration prompts derive from that same story metadata **plus the specific node's body
   text**, because a per-node image has to depict that page, not a generic scene. The node text
   fed to the prompt builder passes through the same injection-hardening treatment as the metadata
   fields (a node's prose is generated content already screened by the validator and moderation
   pipeline, but the prompt builder must not trust it as instructions to the image provider any
   more than ADR-017 trusts story metadata). The same no-child-PII rule applies without exception:
   generated prose at every band is written in second person per D8/D14 and carries no real child
   name (personalization values are resolved separately, at read time, never at generation time),
   so node text reaching the image provider is categorically the same class of content ADR-017
   already clears through this posture, not a new PII surface.
4. **Schema.** Two new **optional** fields on the node model, added via the next ADR-025 minor:
   - `image_url: str | None` (default `None`) - the R2-hosted, presigned-served illustration for
     this node, mirroring `StorybookVersion.cover_image_url`'s pattern at node grain.
   - `image_alt: str | None` (default `None`) - accessible alt text, required to be non-empty
     whenever `image_url` is set (a schema-minor field-level rule, not a new cross-field
     invariant on existing fields, so it stays within ADR-025's additive-only ceiling). Absent
     entirely = today's semantics (no image), satisfying ADR-025's additive-minor requirement
     that omission reproduces current behavior byte-for-byte.
   These are **runtime-visible** fields (ADR-025 decision 4): they change what a reader sees. No
   production content may set them until both `player/engine.py` and
   `frontend/src/player/engine.ts` (or the presentation layer that reads node fields) render them,
   and `schema/conformance/` gains cases covering an illustrated node, a node with `image_url` set
   and no `image_alt` (rejected at validation, not at render), and a node with neither field
   (unchanged rendering). The minor's changelog entry must say so explicitly, per ADR-025's own
   requirement for a runtime-visible addition.
5. **Moderation posture: per-item review for the pilot, automated moderation named as the scale
   gate.** ADR-017 decision 4's trigger ("volume outgrows per-item human review") is engaged by
   per-node art at 3-5: a 10-45-node book turns one review artifact (a cover) into 10-45. This ADR
   rules that the **pilot** (seven skeletons, decision 2) stays within what per-item human review
   can absorb: the admin review surface that already gates prose and cover approval gates every
   generated illustration too, one image at a time, before any pilot book publishes. This is a
   bounded-volume argument, not a claim that per-item review scales past the pilot. Before art
   generation expands beyond the seven pilot skeletons (more 3-5 books, or the 5-8 per-scene
   pilot), an automated image-moderation pass (classifier gate ahead of the human review, the same
   two-layer shape the text pipeline already uses: `validator/` then `moderation/`) becomes a
   precondition, exactly as ADR-017 anticipated. Building that classifier is out of scope for this
   ADR; it is the named blocker on the pilot's own expansion, tracked as follow-on work when the
   pilot's results justify scaling.
6. **Pipeline reuse.** No new image-generation subsystem. The pilot reuses ADR-017's shipped
   substrate: the covers provider seam (`covers/provider.py`, Gemini image model via
   `google-genai`), prompt construction (`covers/prompt.py`, extended per decision 3), WebP
   optimization (`covers/optimize.py`, re-profiled per decision 7), and R2 storage with presigned
   delivery (`covers/storage.py`, `generate_presigned_cover_url`-equivalent for node images). The
   RQ worker pattern (`covers/worker.py`) generalizes to a per-node job instead of a per-version
   job; the admin review surface gains a per-node approval affordance alongside the existing
   per-version cover approval, both still inside the single human gate before publish.
7. **Budgets (media recommendation section 6, D20).** Per illustration: WebP, 1536px reader
   rendition, 150KB target / 200KB ceiling. Per 3-5 book: 8MB ceiling across all node images (10-45
   images at the per-image target keeps a 45-node book inside budget; the ceiling, not the target,
   is the enforced number). These are illustration-specific budgets, distinct from and additive to
   the offline per-device library cap W4.3 enforces client-side; a book that fails its own 8MB
   illustration budget does not publish with images (falls back to no art for the over-budget
   nodes, mirroring ADR-017's "best-effort, never blocks publish" failure posture) rather than
   blowing past the per-book ceiling.
8. **Failure behavior mirrors ADR-017 decision 5.** Illustration generation is best-effort per
   node and never blocks publish. A node with a failed or ungenerated image renders with no image
   (text-only, today's behavior), never a broken-image state or a placeholder that looks like
   content.

## Alternatives Considered

### Alternative 1: leave ADR-017 decision 1 standing (cover art only, at every band)

Decline the amendment; keep per-passage illustration categorically out of scope.

Rejected on the band that needs it most. At 3-5 the reader is largely pre-literate and is being
read to, so a text-only page with a single cover thumbnail is not a picture book, it is a
transcript. The media recommendation's own framing at this band is "the image is the page". The
cost of saying no is concentrated entirely on the youngest readers.

### Alternative 2: per-node art at every band, not just 3-5

Authorize per-node illustration across the catalog in one decision.

Rejected on both moderation load and reader value. The load argument is decisive: per-node art
converts one review artifact per book into 10-45, and ADR-017 decision 4 names exactly that
("volume outgrows per-item human review") as the trigger requiring automated image moderation
first. Doing it catalogue-wide would demand the classifier this ADR explicitly does not build. The
value argument is independent: an 8-11 or 13-16 reader reads prose, and heavy per-page art there
would work against the text rather than carry it. Hence per-node at 3-5, per-scene at 5-8, and
unchanged above.

### Alternative 3: build the automated image-moderation classifier first, then pilot

Treat the classifier as a hard precondition for any in-story art at all.

Rejected as sequencing, not as principle: the classifier is still required, just not yet. A
seven-skeleton pilot is a volume per-item human review demonstrably absorbs (it is the same gate
that already approves every cover and every passage of prose), so gating the pilot on the
classifier would build a scale mechanism before knowing whether the thing being scaled is worth
scaling. Decision 5 keeps the precondition binding at the point it actually starts to matter: any
expansion past the pilot.

### Alternative 4: a separate in-story-illustration pipeline

Build a new generation/storage/serving path tuned for node-grain images rather than extending
`covers/`.

Rejected as duplication with a safety cost. The covers pipeline already carries the parts that are
hard to get right and dangerous to get wrong twice: injection-hardened prompt construction, the
no-child-PII rule, WebP optimization, R2 storage with presigned delivery, and the RQ worker
pattern. A second pipeline would be a second place for the PII and injection rules to drift out of
agreement. The genuine delta (per-node instead of per-version job grain, and node body text in the
prompt) is small enough to be an extension, which decisions 3 and 6 make explicit.

## Consequences

- K8 ("picture support at lower bands... per-passage illustrations as an explicit decision" in
  the capability register) moves from "pre-reader picture support beyond covers still open" to a
  bounded, decided pilot, tracked at its existing register row (no roadmap table change needed:
  K8 is already mapped via the "K5/K8 test pins" phase-4b row, so nothing here creates an
  unmapped register item).
- The admin review workload grows per pilot book from 1 image review to 10-45; this is accepted
  as bounded (seven books total) and is the explicit input to the go/no-go call on decision 5.
- A schema minor lands (decision 4) whose fields are inert until both engines and the conformance
  corpus implement them, per ADR-025's own rule; deploy order is code-then-content, same as every
  other ADR-025 minor.
- The 5-8 per-scene pilot and any 8-11+ art proposal remain named-but-not-started: this ADR
  authorizes their eventual scope so a future pilot does not need its own ADR-017 amendment, but
  neither ships until its own planning item is picked up.
- Cloudflare R2 storage volume grows materially (illustrated 3-5 books at up to 8MB each versus
  a 256KB cover), still inside R2's free-egress, cheap-storage economics per the media
  recommendation section 1; no cost decision is needed at pilot scale.

## Validation

- [ ] Every pilot book's illustrated nodes pass through the admin review surface individually
      before the book publishes; no generated image reaches a child unreviewed.
- [ ] No illustration prompt contains child PII (same egress-guard test shape as ADR-017's cover
      prompts and the text-generation pipeline).
- [ ] A pilot book's total node-image payload is at or under 8MB; any node whose image would
      exceed the per-image ceiling publishes without that image rather than over budget.
- [ ] `image_url`/`image_alt` are absent from every non-pilot book's blob (additive-minor,
      opt-in-by-content, not a retroactive rewrite).
- [ ] Before any book beyond the seven pilot skeletons generates per-node or per-scene art, an
      automated image-moderation pass exists ahead of human review (this ADR's decision 5 gate).

## Related

- [ADR-017](./adr-017-ai-cover-art.md): the cover-art subsystem this ADR amends and reuses.
- [ADR-025](./adr-025-additive-storybook-schema-versioning.md): the schema-versioning mechanism
  `image_url`/`image_alt` rides on.
- [Media budget recommendation](../media-budget-recommendation-2026-08-01.md): sections 3
  (images), 6 (recommendation table), 7 (owner decision points, D20).
- [Design review](../design-review-kid-appeal-2026-08-01.md): section 8, D13/D20.
- [Kid-appeal implementation plan](../kid-appeal-implementation-plan.md): W4.1.
- [Capability register](../capability-register.md): K8.
