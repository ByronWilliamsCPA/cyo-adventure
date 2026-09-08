---
schema_type: common
title: "AI-Assisted Cover Review: Catching Baked-In Text and Incoherent Art Before Human Approval"
status: draft
owner: core-maintainer
purpose: "Add a vision-model review-and-regenerate loop inside covers/service.py::generate_cover so a cover with baked-in text or incoherent art gets one bounded automatic retry before landing in pending_review, with the reviewer's verdict surfaced on the admin approval surface."
tags:
  - generation
  - safety
  - guardrails
  - specifications
---

## Problem

Some AI-generated covers ship with simple, avoidable defects: garbled or
nonsensical text baked into the artwork, or art that does not depict what the
story is actually about. `covers/prompt.py` already tells the generator not to
render any text at all (`build_cover_prompt`, the "Do NOT include any text,
letters, words, titles, numbers, or logos anywhere in the image" clause), so
visible text in a cover is a clean violation of the generator's own
instructions, not an ambiguous judgment call.

Nothing checks for this today. `covers/service.py::generate_cover` goes
straight from the provider's raw image bytes to `optimize()` and `upload()`,
and the function's own `#CRITICAL: security` marker (lines 206-217) documents
this gap explicitly: "An automated image-safety classifier (the moderation/
analogue of the story-text gate) does NOT exist in this codebase yet and is
deliberately out of scope for this change... human approval via approve_cover
is the sole gate right now, not a second independent layer the way text has
validator+moderation+approval." The only correction path is an admin noticing
a bad cover by eye during `approve_cover` and re-triggering generation by
hand.

The story-text pipeline already has a directly analogous pattern:
`moderation/fidelity_review.py::run_semantic_fidelity_check` makes one
independent LLM call to judge whether generated prose matches its intended
beats, returns a `pass`/`flag` verdict, and fails open (an unparseable or
missing response is treated as "pass," since it is advisory, not a hard
gate). This design applies that same shape to cover art, with a vision-capable
model in place of a text-only one.

## Goal

Between the provider returning raw image bytes and the cover being optimized
and uploaded, run an independent vision-model check against what
`covers/prompt.py` actually asked for: no baked-in text, and art that
plausibly depicts the given protagonist/scene. A failing check triggers one
bounded regeneration attempt. Whatever image survives the loop (a clean pass,
or the last attempt after the retry cap) is the one that gets optimized,
uploaded, and set to `pending_review`, now carrying the reviewer's verdict and
notes for the admin who approves it.

## Non-goals

- **Not a hard gate.** No verdict here blocks `approve_cover`. Human approval
  stays the sole authority over what a child ever sees; this only improves
  what a human is asked to approve.
- **Not a new admin review queue.** The existing polling admin surface
  (`GET /api/v1/storybooks/{id}/versions/{version}/cover`) gains three
  response fields; no new route, table view, or dashboard.
- **Not general image-safety re-classification.** Nudity/violence/other
  content-safety concerns stay the responsibility of the generator's own
  refusal behavior (`covers/provider.py` raising `CoverGenerationError`) and
  the safety clauses already baked into `build_cover_prompt`. This reviewer's
  scope is narrowly "did the art follow its own textless/protagonist
  instructions," not a second safety classifier.
- **Not retroactive.** Only future `generate_cover()` runs get reviewed.
  Covers already sitting in `pending_review` or `ready` are unaffected;
  backfilling verdicts onto existing rows is a smaller, separate follow-up if
  wanted later.

## Design

### 1. `covers/review.py`: the reviewer module

A new cover-domain-owned module, alongside `prompt.py`/`optimize.py`, that
imports the shared review infrastructure from `moderation/review_provider.py`
(`ReviewProvider`, `PiiGuardedProvider`, `completion_text`): a one-way
dependency, no cycle, the same import `moderation/fidelity_review.py` already
makes.

`review_cover(image_bytes, generation_prompt, review_provider)` takes the
*exact* prompt string `build_cover_prompt` already produced for the
generator (not a separately re-extracted title/protagonist tuple; the
service function already has this value in hand as `prompt`, before the
retry loop even starts), embeds it in the reviewer's own system+user prompt
as "here is what the artist was asked to draw," sends it alongside the
image, and parses a JSON verdict shaped identically to
`fidelity_review.py`'s:

```json
{"verdict": "pass" | "flag", "notes": "<short>"}
```

System prompt instructs the reviewer to flag on either of two conditions:
(1) any visible text, letters, numbers, or logos anywhere in the image
(directly checkable against the generation prompt's own "no text" clause),
or (2) art that does not plausibly match the scene/subject the generation
prompt described (garbled subject, wrong species or setting, unrelated
imagery). Either condition is enough to flag; the `notes` field says which.
Judging (2) against the actual prompt text, rather than a bare protagonist
name, is what makes the check meaningful: a name alone ("Aria") gives a
vision model nothing to verify an image against, while the prompt's
scene/character description does.

Like `run_semantic_fidelity_check`, an unparseable, empty, or missing
response returns `None` (treated as pass) rather than raising; this module
never itself decides to fail a cover generation.

### 2. Extending review infrastructure for image input

`ReviewProvider.complete()` stays text-only; every existing text reviewer and
every existing mock keeps working unchanged. Rather than widening that
signature, add a second method to the OpenRouter-backed provider class only:

```python
async def complete_with_image(
    self, *, system: str, prompt: str, image_bytes: bytes,
    image_mime: str, max_tokens: int,
) -> Completion: ...
```

OpenRouter's chat-completions endpoint accepts multimodal content arrays on
the same API surface `ReviewProvider` already calls, so this is an additive
method on the existing class, not a new provider integration. The `mock`
backend used in tests gains a matching method returning a configurable
canned verdict.

The existing reviewer-independence check
(`review_provider.py:284-285`, "verifies reviewer model differs from
generator model") extends to cover review: assert the configured cover-review
model differs from `gemini-3-pro-image` (the generation model). This is
trivially true today since they're different vendors entirely, but keeping
the check live catches a future misconfiguration rather than assuming it away.

A new setting, `cover_review_model`, names the OpenRouter vision-capable
model slug. **Open question, not resolved by this design**: which slug to
pin. Recommend picking this the same way the existing `review_provider`
model was chosen (an OpenRouter auto-routed vision-capable model, not a
hardcoded vendor-specific id) and confirming the choice during
implementation planning rather than blocking this spec on it.

### 3. Retry loop in `covers/service.py::generate_cover`

The insertion point is exactly where the existing `#CRITICAL: security`
marker (lines 206-217) says it should be: between the provider call and
`optimize()`/`upload()`. Today:

```python
source = await asyncio.to_thread(generate, prompt, settings)
_maybe_backup(source, storybook_id, version, settings)
optimized = await asyncio.to_thread(optimize, source, ...)
```

Becomes a bounded loop around generation + review, with optimize/upload
happening once, after the loop, on whichever image it ends with:

```python
verdict: str | None = None
notes: str | None = None
for attempt in range(1, MAX_COVER_REVIEW_ATTEMPTS + 1):
    source = await asyncio.to_thread(generate, prompt, settings)
    verdict, notes = await review_cover(source, prompt, review_provider)
    if verdict != "flag":
        break
_maybe_backup(source, storybook_id, version, settings)
optimized = await asyncio.to_thread(optimize, source, ...)
```

`MAX_COVER_REVIEW_ATTEMPTS = 2` (one regeneration after an initial flag) is
the proposed default, the same "bounded, not unlimited" shape as
moderation's own repair loop
(`moderation/pipeline.py` lines 714-873). Whatever the loop ends with, a
clean pass or the last attempt after the cap is exhausted, is uploaded.
The row is always set to `pending_review` at the end (never blocked), per the
non-goals above; a cap-exhausted cover reaches the admin flagged rather than
being withheld.

Reviewing raw bytes *before* `optimize()`/`upload()` run means a rejected
attempt never touches R2 storage or its 500MB/10GB free-tier budget
(`[[book-covers-feature-design]]`); only the surviving image gets optimized
and uploaded, exactly once.

`_pii_context_for_family` / `assert_prompt_pii_safe` already guard `prompt`
once, before the loop starts (lines 246-254). Because the reviewer's text
input is that same already-guarded string, not a freshly assembled one, no
second PII-guard call is needed for the review leg: one guard covers both
destinations the prompt now reaches (the image generator and the reviewer).

### 4. New columns (Supabase CLI migration)

Three nullable columns on `StorybookVersion`, added via a new file under
`supabase/migrations/` (the current migration mechanism per ADR-012, not
Alembic: the July 2026 cover-feature memory's "one Alembic migration" note
predates that cutover and should not be copied):

- `cover_review_verdict` (`text`, nullable: `'pass'` / `'flag'` / `NULL` for
  a cover generated before this feature shipped)
- `cover_review_notes` (`text`, nullable)
- `cover_review_attempts` (`integer`, `NOT NULL DEFAULT 0`)

Stamped once at the end of the retry loop in `generate_cover`, alongside the
existing `cover_status = "pending_review"` commit.

### 5. Admin surface

`CoverStatusView` (`api/covers.py:30-42`) gains the three fields above,
returned by the existing `GET .../cover` endpoint, with no new endpoint. A small,
additive change to the existing admin cover panel displays verdict and notes
as plain text next to the presigned preview image that panel already shows.
No new queue, route, or dashboard component.

### 6. Error handling (fail-open, consistent with `fidelity_review.py`)

- An OpenRouter timeout, non-2xx response, or unparseable body during
  `review_cover` returns `None` (treated as pass) for that attempt; the loop
  proceeds with that image rather than retrying or failing the whole
  generation. An OpenRouter outage degrades cover review to "off," never to
  "cover generation broken."
- `generate_cover`'s existing outer `try/except Exception` (which already
  catches provider failures and rolls the row to `cover_status = "failed"`)
  wraps the whole loop unchanged; a hard failure in image generation itself
  still behaves exactly as it does today.
- The reviewer-independence check logs a warning rather than raising if it
  ever fails, matching the existing text-reviewer pattern
  (`review_provider.py:310-319`, a `reviewer_not_independent` advisory
  finding, not a block).

## Testing

- Unit tests for `covers/review.py`: mock provider returning `pass`, `flag`
  with notes, and an unparseable/empty response (asserting fail-open to
  `None`).
- Unit test for the independence check against a misconfigured
  same-model setup.
- Extend `tests/integration/test_cover_service.py`:
  - Reviewer flags attempt 1, passes attempt 2 (mock `generate` returns
    distinct bytes per call): assert the final row holds attempt 2's image,
    `cover_review_verdict = "pass"`, `cover_review_attempts = 2`.
  - Reviewer flags every attempt: assert the row still reaches
    `pending_review` (not `failed`) after `MAX_COVER_REVIEW_ATTEMPTS`, with
    `cover_review_verdict = "flag"` and non-null `cover_review_notes`.
  - Reviewer call raises/returns garbage on attempt 1: assert that attempt is
    treated as pass (loop does not retry) and generation completes normally.
  - A pre-existing row with `cover_status = "ready"` and null review columns
    (representing a cover generated before this feature shipped) is
    unaffected by any read path: confirms the nullable columns are truly
    backward-compatible.

## Known limitations / open questions

- `cover_review_model` (the OpenRouter vision-capable model slug) is not
  pinned by this design; needs an explicit decision during implementation
  planning.
- `MAX_COVER_REVIEW_ATTEMPTS = 2` is a starting default, not a measured
  figure; revisit after seeing real flag rates in the review notes.
- **Cost**: worst case this roughly doubles per-cover cost (up to 2 image
  generations + 2 review calls). No hard budget cap is built into this first
  cut; flagged with an `#ASSUME: external-resources` marker in the
  implementation for follow-up if OpenRouter spend on this jumps
  unexpectedly.
- This design does not attempt to correct a flagged cover automatically
  beyond a plain re-generation (e.g., no prompt-repair feedback loop that
  tells the generator what specifically was wrong). If the flat retry proves
  low-yield in practice, feeding the reviewer's `notes` back into a
  corrective second prompt is a natural follow-up, deliberately deferred here
  to keep this first cut simple.
