---
title: "Capability Register (Top-Down Expectation Map)"
schema_type: planning
status: active
owner: core-maintainer
purpose: "Enumerate every persona capability derived from the top-line project goal, with stable IDs,
  so scope can be checked off and tested against expectations rather than against what happens to exist."
tags:
  - planning
  - scope
  - testing
component: Strategy
source: "Fresh-look capability review session, 2026-07-16"
---

# Capability Register

> **Status**: Active | **Version**: 1.10 | **Created**: 2026-07-16 | **Updated**: 2026-08-08
> (v1.4: note corrections and ruling queue from the full traceability review, see
> [traceability-review-2026-07-16.md](./traceability-review-2026-07-16.md);
> v1.5: owner rulings applied: K18 and A16 minted, back button ratified, ADR-007
> admin-first sequencing, repair re-gate and band fail-closed fixes ordered, G2 build
> confirmed; v1.6: A12 note extended to name the admin child-PIN set/reset authority
> explicitly, with an ADR-014 cross-reference, per the 2026-07-16 review condition;
> v1.7: comprehensive plan-audit correction (2026-07-20) - the 2026-07-17 delivery
> update below was never propagated into the per-row Docs column: K6, K15, G9 flipped
> ❌->✅, K12/G10/S9 flipped ❌->🟡 (each shipped in PR #270 per its own banner note,
> just not synced into the table), with file-level evidence added to each row's note;
> see the 2026-07-20 plan-audit summary in roadmap.md for the full cross-doc reconciliation;
> v1.8 (2026-07-25): **G18** and **K20** minted for guardian opt-in story personalization
> ([ADR-023](./adr/adr-023-story-personalization-slots.md), status Proposed), with scope notes
> added to G4, G17, K19, S10, S11, and S12; see the ruling entry under "Unregistered scope" for
> why two new IDs rather than cross-references alone;
> v1.9 (2026-08-01): **K21, K22, K23, and G19** minted for gamification, the weekly
> reading-days ring, day-grain active reading time, and guardian gamification controls,
> from owner decisions D6/D12/D16/D17 in
> [design-review-kid-appeal-2026-08-01.md](./design-review-kid-appeal-2026-08-01.md)
> section 8; **row wording awaits owner final sign-off**. Same-day delivery notes added to
> K12 and K19 (kid loop closure shipped: honest request status, picker pill, reflect-back
> surfaced), G9 and S10 (K23 extensions). Rendered-stop flow, the choice grammar, tone,
> and POV rulings change presentation and content contracts under existing IDs (K1, K2,
> K5, K11, K13) rather than minting new ones; ADR-026 and ADR-011 section 10 are their
> decision records. K8's illustration pilot (plan wave 4) and K23/K22 delivery will flip
> statuses when shipped;
> v1.10 (2026-08-08): **K24** minted for the reader-facing persistent character (build once,
> carry across every participating book), the runtime half of
> [ADR-028](./adr/adr-028-persistent-reader-characters.md)'s K3 extension, delivered on branch
> `feat/persistent-characters-runtime`. Partial: the runtime and CH-* proof exist but no catalog
> book has shipped participating yet, tracked as the pathfinder pilot under
> [UW-A46](./unscheduled-work-register.md))

> **Delivery update (2026-07-17, M4b-d execution on branch
> claude/app-capabilities-review-wm6gt3)**: the following capabilities moved to DELIVERED
> (code, tests, and E2E where noted; commits 5fd1de7 through 6f729d5): K5 (Go Back pinned),
> K6 (tracker UI), K7 (read-aloud), K12 (complete incl. generation status), K15 (flag end
> to end: kid button, admin queue, guardian alert), K17 (shelf chips), G2 (controls UI and
> brief wiring), G3 (envelope backend, write path, and form UI), G5 (structure summaries),
> G6 (prose editor with gate and moderation re-run; admin surface, guardian UI awaits a
> guardian review surface), G7 (complete: consent debits quota on ALL spend paths incl.
> the legacy intake gate), G9 (Reading page), G10/S9 (notification feed and bell), G13
> (interim balance), G17/A15 (dual-guardian consent flow with the ENFORCED ring-2 guard,
> superseding the holds-by-omission note below), and the S8 flow now includes the budget
> stage. PR #267 (A12/A13, connection substrate) merged to main; PR #268 (A8 UI) in
> flight. Remaining for M4-full: G15 device/storage view (needs a design decision), G8
> offline revocation (Phase 5), and the owner-side items (secrets, redeploy, live
> checklist).

> **Delivery-state review (2026-07-16, open PRs and working docs)**: the Docs column below
> measures *foundational-doc* coverage, but a review of
> [story-lifecycle-redesign.md](./story-lifecycle-redesign.md) (owner-ratified 2026-07-06,
> workstreams A-G merged 2026-07-10) and open PRs #267/#268 found several items further
> along in working docs and code than foundational coverage suggested. Affected rows carry
> delivery notes; treat the Notes column as the current truth.

## Purpose and method

This register was produced by a deliberate fresh-look exercise: start from the top-line goal only
(an online and offline app where kids read choose-your-own-adventure books and use AI to generate
new stories based on their interests), derive what a child, guardian, and application admin would
expect the app to do, and only then compare against the foundational documents (project vision,
tech spec, ADRs 001-014, privacy model, authorization matrix). It deliberately ignores code,
sprints, and milestones.

Each capability has a stable ID: **K** (kid), **G** (guardian), **A** (admin), **S** (system,
cross-cutting). IDs are permanent; never renumber. New capabilities append at the end of their
section. This register is the checkoff sheet for scope and the basis for acceptance testing:
every item should eventually map to one or more tests, and every spec or feature should trace
back to at least one ID.

The **Docs** column records coverage in the foundational documents as of 2026-07-16:

- ✅ covered (the docs spec this, often more deeply than the expectation)
- 🟡 partial (mechanism or fragment exists; the user-facing capability is not fully specced)
- ❌ missing (absent from the foundational docs)

## Ratified decisions (2026-07-16)

These rulings from the project owner resolve the open tensions the fresh-look surfaced. They are
binding on the register below. Decisions 1-3 are recorded in
[ADR-015](./adr/adr-015-story-request-initiation-and-gating.md); all five are folded into the
vision doc (v1.2):

1. **Initiation is universal.** A child, a guardian, or an admin may initiate a story request
   (K11, G4, A10). The original guardian-only intake was scope inherited from the one-family era.
2. **The guardian is the cost gate.** A story request consumes generation budget only with
   guardian consent; guardians control spend (G7, G13).
3. **The admin is the AI gate.** The admin remains the party who gates the AI output before it
   can reach a child (A6), consistent with ADR-005 as amended 2026-06-30.
4. **The kid feedback loop exists.** Children get a simple flag/reaction signal that a grown-up
   actually sees (K15, feeding G10 and A1).
5. **Guardian visibility and notifications exist.** Engagement visibility (G9) and a
   digest-plus-alerts notification surface (G10, S9) are in scope.
6. **The social boundary is three rings, not a flat exclusion** (ruled 2026-07-16, recorded
   in [ADR-016](./adr/adr-016-recommendation-sharing-social-boundary.md)): recommendations
   flow within a family (ring 1) and between guardian-approved connected families, the
   cousins case (ring 2, structured data only, dual-guardian consent, no
   receive-from-everyone option); globally only the system recommends, from anonymized
   aggregate scores (ring 3, future); never kid to kid beyond ring 2, and no messaging,
   discovery, or contact outside active parental approval (K17, G17, A15, S11, S12).

The resulting canonical request flow (S8):

```text
initiate (K11 | G4 | A10)
   -> guardian cost gate (G7; may be pre-authorized per child via G3)
   -> staged generation (existing pipeline)
   -> deterministic validation + independent moderation (S4, S7)
   -> admin safety gate: approve and publish (A6)
   -> child's shelf (K9), with honest status shown to the requester throughout (K12, G10)
```

## K: Kid capabilities

| ID | Capability | Docs | Notes |
|----|------------|------|-------|
| K1 | Read with age-appropriate presentation: legible type, UI complexity, and reading level matched to the child's band | ✅ | Bands/reading levels specced (ADR-011); per-band presentation/UX shipped PR #389 (2026-07-24): `KidShell.tsx` stamps `data-age-band`, `band-tokens.css` maps every `AgeBand` to typography/motion tiers, consumed live by `PassageText.css`/`reader.css`. Residual (corrected 2026-08-01 per the kid-appeal design review section 6 item 2): not just `--band-tap-min`; the entire motion and gap tier of `band-tokens.css` (`--band-motion-*`, `--band-gap`) has zero consumers, so the 8-11/10-13 "adventurer" tier renders identically to the teen tier, and the file's header cites a `frontend/src/kid/ageBand.ts` that does not exist. Consume or delete (design review recommendation 11) |
| K2 | Choices are obvious, tappable, impossible to get mechanically wrong; locked (state-gated) choices are hidden, never shown-and-disabled | ✅ | Tech spec runtime semantics |
| K3 | Choices are consequential: paths genuinely differ, endings vary, the story remembers state (items, flags, counters) | ✅ | Storybook format, Tier 2 state, ADR-011 clocks; WS-5 (delivered 2026-07-20) adds the catalog-time mechanism to grow structural + state variation, the M1-M5 mutation operators re-proven by the unchanged gate plus the WS-5 acceptance floors, promoted via bundle + human PR (ADR-020); WS-8 (the catalog flywheel, delivered 2026-07-21, D1-D8) closes the demand loop end to end: the enum-only saturation trigger drives a bounded candidate strategy, human-gated draft-PR promotion, and a scheduled S1-S6 cadence runner behind six reviewed-PR-only caps, so K3 holds up for heavy readers in saturated cells with no standing authoring budget. **Extended (2026-08-06)** by [ADR-028](./adr/adr-028-persistent-reader-characters.md): state a reader carries between books, not only within one, via a seeded `VarState` character and the CH-* validator proof over its declared envelope |
| K4 | Resume exactly where they left off, on any device, with no understanding of sync required | ✅ | Revision-based sync, version pinning |
| K5 | Restart and re-read freely; replay is first-class, including a single-step "Go back" undo | ✅ | RULED 2026-07-16: the back button stays; tech spec Runtime Semantics amended (replay-based undo, no backward state mutation); shipped in the Reader |
| K6 | Endings tracker as a replay motivator ("found 3 of 7 endings") | ✅ | Tracker UI shipped 2026-07-17 in PR #270: `frontend/src/reader/EndingsProgress.tsx` ("found N of M"), wired into `Reader.tsx`, tested; `completion` rows are the write path |
| K7 | Read-aloud / narration for pre-readers and emerging readers | ✅ | Shipped 2026-07-17 in PR #270: Web Speech API read-aloud (`frontend/src/reader/useReadAloud.ts`), per-profile `tts_enabled` toggle wired into `Reader.tsx` and `ProfileFormDialog.tsx` |
| K8 | Picture support at lower bands: covers at minimum; per-passage illustrations as an explicit decision | 🟡 | Cover art ratified and recorded in [ADR-017](./adr/adr-017-ai-cover-art.md) (shipped: Gemini generation, R2 storage, kid-visible with fallback tile); per-passage art stays out of scope; pre-reader picture support beyond covers still open |
| K9 | Visual library shelf with covers: what's new, in progress, finished | ✅ | `LibraryPage.tsx` ships a real "Continue Reading" hero plus a "More to Explore" grid, and `BookCard.tsx` shows "Finished!"/progress-bar/"Not started" states, all tested; the "what's new" leg closed 2026-07-28: `LibraryItem.published_at` reuses the existing `StorybookVersion.published_at` stamped by the publishing state machine (`api/schemas.py:171`, wired through `api/library.py`'s `_library_item`/`list_library`), and `BookCard.tsx:75-97` renders a "New" badge (`bookCardUtils.ts:23` `isRecentlyPublished`, a 7-day window) independent of progress state; tested in `test_library_api_unit.py` and `BookCard.test.tsx`/`bookCardUtils.test.ts` |
| K10 | Offline is invisible: identical experience offline; never a connectivity error; at most "this book isn't downloaded yet" | ✅ | Specced in `docs/design/offline-conflict-ux.md`; `OfflineError` (`offline/sync.ts`) routes through `ReaderPage.tsx`'s distinct `'offline'` phase to `DownloadNeeded.tsx`, `LibraryPage.tsx` shows a cached-shelf banner, `BookCard.tsx` shows a "Needs internet to open" tile instead of a dead link. Tested in `ReaderPage.test.tsx` |
| K11 | Express interests and initiate a story request in kid terms (picking interests, typing a wish) | ✅ | Verified 2026-07-29 shipped end to end on a real child principal (not guardian-on-behalf): `POST /story-requests` accepts a child token (`api/story_requests.py:313-363`, `Principal.can_access_profile`), stamps `initiator_role="child"`, proven by `tests/integration/test_story_requests_api.py::test_child_creates_own_profile_request`; kid-terms UI (idea box, series continuation, own-status list) in `frontend/src/library/RequestStory.tsx`; series continuation e2e in `frontend/e2e/story-requests-kid.spec.ts`. ADR-015 is the foundational record. Was 🟡 only because the register lagged the code |
| K12 | Kid-friendly waiting and error states: "your story is being written", sync conflicts, and failures presented in kid terms | ✅ | Shipped 2026-07-17 in PR #270 (per its own delivery banner, "K12 complete incl. generation status"): kid-language request statuses, plain-language conflict dialog, mascot error/empty states, honest save-retry banner, and the kid-facing generation-in-progress state. **Extended 2026-08-01** (plan W0.4/W1.4, closing persona-audit findings 1A/2B): request status is now honest end to end via `story_request.resulting_storybook_id` (the title-substring guess is deleted; an ordinary one-off request flips to "it's on your shelf" when the linked book is assigned), and the profile picker gained the "new story!" pill over the boolean-only bulk `GET /v1/profiles/story-status` endpoint (7-day assignment window matching the shelf's NEW badge) |
| K13 | Age-band content guarantee: themes, scariness, and ending intensity land within the band (e.g. no death endings in young bands) | ✅ | ADR-011 per-band allowances, content flags, moderation by band. **H1 gap closed 2026-07-28** (security-hardening-plan-2026-07.md): `assign_storybook` (`api/assignments.py`) now rejects assigning a storybook whose band exceeds the target profile's band; the read gate in `api/library.py` (`list_library`, `get_storybook_version`) adds a band comparison as defense in depth; and guardian confirmation at approve/authored-create time (`story_requests/service.py`) can no longer set an age band above the requesting profile's band. All three layers, generation-time, assignment-time, and delivery-time, now agree |
| K14 | Safe room: no ads, no purchases, no external links, no contact with strangers, no dark patterns in the kid context | ✅ | Permanent exclusions in vision; parental gate in ADR-008 |
| K15 | Feedback signal: "I didn't like this / this scared me", routed to a grown-up who actually sees it | ✅ | Shipped 2026-07-17 in PR #270: `KidFlag` model, kid-facing `POST /flags`, admin list/resolve (`src/cyo_adventure/api/flags.py`); feeds G10 alerts and the A1 queue as designed |
| K16 | Pick "me" from a picker: name and avatar, no password or email; sibling shelves and progress never collide | ✅ | Profile picker, per-profile PIN, ADR-014 device grants, IDOR suite |
| K17 | Give and receive structured book recommendations within the family and across guardian-connected families (cousins); a recommendation is a book pointer plus rating, never a message | ✅ | ADR-016 records the policy; PR #267 shipped the connection substrate, and PR #270 (2026-07-17) shipped the kid-facing recommendation chips ("made for you by / cousin X loved this") over `/v1/recommendations`, gated by G17's enforced consent guard; K18 ratings are the payload substrate |
| K18 | Rate a finished book (1-5 stars): the enjoyment signal that feeds S12 aggregate scoring and K17 recommendation payloads | ✅ | RULED 2026-07-16: owner's variant of thumbs up/down for aggregate ratings; shipped (kid widget, `Rating` table, `api/ratings.py`); debt item U6 (cannot clear a rating) folds here; distinct from K15, which remains the safety-flag signal. **Referenced (2026-08-06)** by [ADR-028](./adr/adr-028-persistent-reader-characters.md) as the pilot's measurement basis: the pathfinder decision criteria compare a character-carrying skeleton's K18 ratings against a matched non-carrying skeleton in the same cell |
| K19 | Request interpretation and expectation-setting: when a child submits a free-form story idea, the app reflects it back in kid terms before generation, what it understood and will build into the story versus what it set aside and why (outside the age band, not safe, or not part of this kind of story), so the child knows what to expect from their wish | ✅ | DELIVERED 2026-07-20 (WS-7 D1-D8): the interpretation core (`story_requests/interpretation.py`), the persisted `story_request.interpretation` column, the submission-time general layer, the contract-grounded refined layer (interpret-and-bind + worker wiring), the CANNOT_CARRY rejection surface, and the D8 API contract (`RequestInterpretationView` on the story-request view) are built, tested, and merged. Added 2026-07-18 (owner directive). Design record: [story-flexibility-plan.md](./story-flexibility-plan.md) WS-7 and [ws7-request-interpretation-design.md](./ws7-request-interpretation-design.md). Gated by K13 (never echo unsafe input back); complements K11 (express a request) and K12 (kid-friendly states). The guardian-console view is the G-side companion surface. **Copy dependency added 2026-07-25**: this capability's kid-facing Route A line ("Heroes in our stories always have made-up names") becomes false for a family that enables **G18**, so ADR-023 makes rewording it a precondition on that feature's flag, not a follow-up; the wording also has to stay consistent with PR #415's A11 hero-name copy. **Status checked 2026-07-26: this dependency is still OPEN, and note the collision of two different "A11"s.** The register's own A11 (corpus quality tooling, above) is a separate item; the one named here is PR #415's plan item A11, a reader-UX change to `RequestStory.tsx`. That change is unstarted, gated behind a naive-user comprehension session, and PR #415 has touched zero frontend files, so the Route A hero-name copy is unchanged on both sides. Both halves of the dependency therefore remain to be done together, and neither G18 nor plan-A11 may ship its wording without the other. **Kid-UI delivery closed 2026-08-01** (plan W1.4, resolving the persona audit's 2A finding that the kid surface showed none of the reflect-back): the request card now renders "We heard you: {interpretation.kid_summary}" on pending and approved requests, so the register status and the shipped surface finally agree |
| K20 | Read a story that uses my own details: my name, and a small closed set of other things my grown-up has turned on (a pet, a brother or sister, what I call my grandma), appearing in the story itself; plus my own switch to turn that off and back on for my books | ❌ | Proposed 2026-07-25 in [ADR-023](./adr/adr-023-story-personalization-slots.md) (status Proposed, not yet Accepted). The kid-facing half of G18. Distinct from K16 (picking "me" from a picker is identity *in the app*; this is identity *in the story*) and from K11/K19 (what a child may *ask for* is unchanged: Route A's self-naming block stays fully in force, and this capability is reached only through a guardian setting, never by asking). The child's switch narrows within the guardian's envelope and can never widen it. **Not offered at the 3-5 band**: a control a pre-reader cannot exercise is not a safeguard, so for the youngest band this is guardian-controlled with no child-side surface (ADR-023 section 9) |
| K21 | Collect and be celebrated: an endings gallery (found endings as cards, unfound as silhouettes), finished-shelf states, and story-themed badges earned from real reading (distinct endings, distinct books, replay depth); rewards are made of story, never points or currency; family-visible within ring 1, never ranked against siblings, never crossing ring 2 | 🟡 | **Minted 2026-08-01** from owner decisions D6/D12 ([design-review-kid-appeal-2026-08-01.md](./design-review-kid-appeal-2026-08-01.md) section 8; design authority [gamification-recommendation-2026-08-01.md](./gamification-recommendation-2026-08-01.md) sections 1-2). Row wording awaits owner sign-off. **Delivered 2026-08-01** end to end: backend projection (`progress/` package, `GET /v1/me/progress`, badges 1-8/10/11) and kid UI (`EndingsGallery.tsx`, `BadgeCase.tsx`, `BookCard` ribbons, `BadgeUnlockToast` with badges_enabled suppression). Residuals: badges 9 and 12 (dependencies landed same day, trailing work), curated badge art (placeholder styling). Bounded by K14: no loss states, no leaderboards, no purchasable anything |
| K22 | A weekly reading-days ring: "you read on N days this week" toward a per-band default goal, celebrating a filled week and doing nothing at all on an unfilled one; no consecutive-day streak, no resets, no reminders; goal capped at 6 so one free day is always guaranteed; off by default at 3-5; teen bands set their own goal within a guardian cap | 🟡 | **Minted 2026-08-01** from owner decisions D6/D16/D17 (per-band defaults table P-A, approved). Row wording awaits owner sign-off. Design authority: gamification recommendation section 2.3 (the no-loss-state rationale and the calendar-day versus reading-days evidence). **Delivered same day**: `WeeklyRing.tsx` in the kid shell, server-resolved P-A defaults (`api/progress.py::_resolve_ring_settings`, cap-6 triple-backstopped), once-per-week celebration, fail-closed on fetch errors, guardian toggles. Residual: teen self-set goal within the guardian cap (guardian-only in v1, #ASSUME-tagged both sides). Guardian per-profile controls are G19 |
| K23 | My reading days are counted honestly and privately: active reading time captured at day grain only (nothing finer ever leaves the device), surfacing to the child as days and milestones, never minutes; guardian sees minutes per day as a literacy signal (G9); first-party only, 12-month day-grain retention default, and never used to make the app harder to put down | 🟡 | **Minted 2026-08-01** from owner decisions D12 (total active reading time added) and the plan defaults (retention). Row wording awaits owner sign-off. **Substrate delivered 2026-08-01**: reading_activity_day table (CASCADE, RLS, deletion-drill), idempotent clamped flush endpoint with server-side enforcement of the guardian pause toggle, 90s-idle visibility-gated client accumulator with offline day buckets. Residuals: 12-month retention/rollover job unbuilt (documented in the model), counsel-bundle entry pending (UW-M03). Extends S10's data classification (new child-linked behavioral category; counsel-bundle retention entry per UW-M03) and is bound by K14's no-dark-patterns exclusion, which the trust copy makes testable: "nothing in the app punishes a missed day" |
| K24 | Build a character once, in kid terms (a look and archetype, or trained strengths in a gamebook), and have that same character remembered and carried into every other participating book, instead of starting from nothing each time | 🟡 | **Minted 2026-08-08** for the persistent-characters runtime (branch `feat/persistent-characters-runtime`), which delivers the reader-facing half of [ADR-028](./adr/adr-028-persistent-reader-characters.md)'s K3 extension (the validator-side authorization) end to end: character creation and picker UI (`frontend/src/characters/CharacterCreator.tsx`, `CharacterPicker.tsx`), server-derived binding with the seed snapshotted once at read start (`api/reading.py::_bind_active_character`, never a client-supplied `character_id`), progression written back idempotently on satisfying endings (`characters/progression.py`, keyed on the `character_book_completion` primary key), and the bound character surfaced in the reader (`Reader.tsx`). Partial because no catalog book has shipped participating yet: the CH-* proof and the runtime both exist, but until a book is promoted with a declared `accepts_character` envelope and published, no reader can exercise this. The pathfinder pilot (one participating skeleton, K18 rating comparison against a matched non-carrying skeleton as the GO/NO-GO basis) is [UW-A46](./unscheduled-work-register.md)'s remaining open item |

## G: Guardian capabilities

| ID | Capability | Docs | Notes |
|----|------------|------|-------|
| G1 | One account, multiple child profiles; each profile's age band and reading level actually changes what the child sees | ✅ | `child_profile` caps enforced in library filtering |
| G2 | Per-child content controls: allowed and banned themes, content flags, family-specific exclusions (phobias, no-magic, no-weapons) | ✅ | **Corrected 2026-08-09**: fully delivered, not schema-deep only. `frontend/src/guardian/ProfileFormDialog.tsx` has a working add/remove banned-themes chip UI; `frontend/src/guardian/IntakePage.tsx` reads the profile's real `banned_themes` (no longer a hardcoded empty list); `story_requests/brief.py:122` sets `content_nogo = list(profile.banned_themes or [])`, wiring the guardian's choice into generation. `allowed_content_flags` remains inert per `UW-E07`, which is a separate, still-open gap from this one |
| G3 | Per-child permissions and limits: whether the child may initiate story requests (including pre-authorized auto-allow), screen-time norms if any | ✅ | Pre-authorization envelope shipped 2026-07-17 in PR #270 (`request_auto_approve`, `monthly_request_envelope` on `child_profile`; form UI in `ProfileFormDialog.tsx`/`ProfilesPage.tsx`); screen-time norms are explicitly out of scope by the same note, not a remaining gap, so flipped to done 2026-07-29 |
| G4 | Initiate story requests themselves, including personalized stories ("one about our camping trip for Maya") | ✅ | Concept-brief intake; PII rules keep real names out of prompts. Note the tension this row's own example carries: it names a real child, while the mechanism deliberately cannot. **G18** (proposed 2026-07-25, ADR-023) resolves it at a different layer, by substituting at render time on the family's own devices rather than at generation time, so G4's guarantee here is unchanged |
| G5 | Fast review of a generated story without reading every path: summary, themes, flagged passages, branch structure | ✅ | Structure summaries shipped 2026-07-17 in PR #270 (per its delivery banner: "G5 structure summaries"); approval itself is on the admin surface (A6) |
| G6 | Edit or reject a generated story (prose tweaks, veto) with re-review on edit | 🟡 | Edit half CLOSED: `PATCH /storybooks/{id}/versions/{v}/nodes/{node_id}` (`api/node_edit.py`) already authorized guardians and re-runs the gate/moderation on edit; the guardian now also has a UI path to it, `GuardianReviewDetailPage.tsx` at `/guardian/review/:storybookId`, backed by a new read-only `_load_review_target` helper in `api/approval.py` that admits a guardian for the GET review surface of their own family's story only (family-scoped via `authorize_family`), leaving every mutating admin handler (submit/approve/send-back/archive) untouched and admin-only. Reject/veto half remains open: `approval.py`'s `_load_admin_story` still hard-requires `is_admin` in every mutating check, so guardians have **no API path at all** to reject or veto a generated story. Whether guardians should get a veto, or admin is deliberately the sole safety gate per ADR-005, is an open product/ADR decision, not yet an engineering ticket |
| G7 | Cost gate: a story request spends generation budget only with guardian consent; per-child auto-allow is a guardian setting | ✅ | Consent step shipped (guardian request approval precedes any concept/GenerationJob, WS-B); budget/credit debiting completed 2026-07-17 in PR #270 (per its delivery banner: "G7 complete: consent debits quota on ALL spend paths incl. the legacy intake gate"); pre-auth envelopes are G3 |
| G8 | Kill switch: pull any published book off a child's shelf immediately, including offline copies at next connection | ✅ | Delivered at two granularities. Per-child (the row's own "a child's shelf"): guardian unassign, `DELETE /v1/storybooks/{id}/assignments/{profile_id}` with a per-child Remove control in `AssignChildrenDialog.tsx` (2026-07-27); removes only that child's access and preserves reading progress (resurrects on reassignment). Book-wide (all children at once): admin `archived` state. Offline-copy revocation delivered 2026-07-17 (client-side reconcile-on-fetch/reconnect against the authoritative `/v1/library` response, no backend change needed; `frontend/src/offline/revocation.ts`) |
| G9 | Engagement visibility: what each child is reading, how much, endings found, re-reads; literacy signals, not surveillance | ✅ | Shipped 2026-07-17 in PR #270: `GET /families/me/reading-summary` (`src/cyo_adventure/api/reading_history.py`), guardian-facing `frontend/src/guardian/ReadingPage.tsx`. Open extension (proposed 2026-07-25, [reader-path-engagement-design.md](./reader-path-engagement-design.md) decision 4): whether a guardian sees their own child's **stop points**. "Started three times, furthest point chapter 3" is real reading-support value for a struggling reader and is the closest this capability comes to its own surveillance edge; the recommendation is book-granular support framing, never a choice-by-choice replay. Note the underlying data already arrives and is discarded: the offline client sends the full accumulated `path` on every save and the server overwrites it. **Extended 2026-08-01**: the reading summary gains minutes-per-day and days-per-week from K23's day-grain reading-time substrate (plan W3.3, in flight); the per-profile control surface for that data is G19 |
| G10 | Notifications that matter: child flagged content, a story awaiting action, a story ready; digest by default, alert on safety | ✅ | Shipped 2026-07-17 in PR #270: `GET /notifications` projects `pipeline_event` into a guardian feed (`src/cyo_adventure/api/notifications.py`, `notifications/service.py`), rendered by `frontend/src/guardian/NotificationBell.tsx`. "Alert on safety" is a real, code-enforced delivery tier, not just a polling convention - `notifications/models.py`'s `severity` field fires an immediate toast only for `'alert'`-kind items (`NotificationBell.tsx:94-97`), `'info'` items sit passively (the "digest by default" half this row also asks for). The push-channel gap this row previously carried is closed: `GET /v1/notifications/stream` is an authenticated Server-Sent Events endpoint (`api/notifications.py`, 25 unit tests incl. auth, role enforcement, event framing, and session-lifecycle cleanup), consumed by `frontend/src/guardian/notificationsStream.ts` and wired into `NotificationBell.tsx`'s existing poll effect (15 frontend tests). The poll (now a fallback, not the sole path) is never removed. **Closed 2026-08-09**: the literal "digest by default" mechanism (a scheduled batch, not just passive info-severity items) is now also real; see S9 |
| G11 | Plain-language trust surface: what data is collected, where the AI text came from, who reviewed it, no training on child inputs, COPPA/GDPR-K posture | ✅ | Shipped 2026-07-28: `frontend/src/guardian/PrivacyPage.tsx` at `/guardian/privacy`, reached from a footer link in `GuardianShell.tsx`. Covers all five clauses of this row: what is collected and what is deliberately not, that the prose is AI-written, the two-gate automatic-then-human review (ADR-005), and no-retention/no-training routing (ADR-003's 2026-07-28 amendment). Every claim is anchored to enforcing code in the component's own docstring, and the page is scoped to the plain-language explanation only: the statutory privacy notice with retention periods and formal rights stays an ADR-018 D4 Phase-7 deliverable, and the page says so rather than standing in for it. Deliberately omits ADR-023 name-level personalization, which is Proposed and not built |
| G12 | Data export and full account/family deletion | 🟡 | Deletion-readiness and Apple revocation specced; user-facing export absent |
| G13 | Predictable cost model: quotas, "3 stories left this month", no surprise bills a child can trigger | ✅ | `GET /families/me/budget` + `enforce_family_quota` (`story_requests/service.py:247`) blocks generation before job creation, at both the guardian-consent and admin-authored paths, plus a per-child envelope gate; `BudgetBanner.tsx` renders the "N of M stories left" copy this row asks for; 5 integration tests. Marked done for the R1 interim scope this row describes; ADR-008's full credits/IAP model for the public tier remains separate Phase 8 scope, not counted against this row |
| G14 | Standard adult auth; multi-guardian households (two parents, a grandparent) | ✅ | `User.family_id` already supports multiple guardians per family; `POST /admin/users` (merged, WS-J) covers the admin-mediated path, live and tested (`test_pending_invite_binds_on_first_login_by_email`). Closed 2026-07-28: `POST /me/family/invite-guardian` (`api/me.py::invite_guardian`) adds the guardian-initiated self-service "invite my co-parent" path, hard-scoped server-side to the caller's own `family_id` (the request body carries no `family_id` or `role` field at all), sharing the same duplicate-email guard as the admin path via `create_pending_invite`. The two invite kinds are deliberately NOT the same row state: an admin-created invite is `status='pending'` and binds to `'active'` on first sign-in (an admin vetted it), while a guardian-created one is `status='pending_guardian_invite'` and binds to `'awaiting_approval'`, so an admin still approves before the invitee joins; without that split a guardian could pre-claim any email address and capture its owner into their family. `frontend/src/guardian/InviteCoParentSection.tsx` on the guardian console home; 14 backend integration tests plus 8 frontend tests |
| G15 | Device management: authorize and revoke devices, see which books are downloaded where, storage use | 🟡 | Device list/revoke half shipped 2026-07-28: `frontend/src/guardian/DevicesPage.tsx` (reached from `GuardianShell`'s "Devices" nav item, guardian-only like Books/Profiles/Connections) calls the existing `GET`/`DELETE /v1/device-grants` endpoints (`api/device_grants.py`), which were already family-scoped and tested (`test_list_returns_only_own_family_active_grants`, `test_revoke_other_family_grant_is_404`) but had no UI caller; `deviceGrantApi.ts.list()` was dead code until now. `ConsolePage.tsx`'s own "this device" localStorage control is unchanged and is cross-referenced by id so a guardian can tell which row is the device they are on. **Closed 2026-08-09**: download/storage visibility now exists end to end. New `device_download` table (Tier 1 family_scoped RLS) + `api/offline_downloads.py` (`PUT`/`DELETE`/`GET /v1/device-downloads`); `frontend/src/offline/deviceId.ts` mints a persistent client-side device id (deliberately separate from `device_grant.jti`, since a guardian's own browser downloads books too and holds no device grant); `ReaderPage.tsx` reports every read via a new `reportDownload` prop, wired from `ReaderRoute.tsx`; `DevicesPage.tsx` renders the result grouped by device below the device list. One honest scope limit, documented in `DeviceDownload`'s docstring and the section's UI copy: this is a best-effort snapshot, not a strict inventory. The report path (creating/refreshing a row) is fully live; the removal path (the `DELETE` endpoint) is implemented and tested but is NOT wired into the client's automatic eviction paths (`offline/downloadBudget.ts`'s space-pressure eviction, `offline/revocation.ts`'s server-directed removal), both of which are deliberately network-free modules by existing architecture. A device that evicts a book that way leaves a stale row until it is manually reconciled; nothing purges on a timer |
| G16 | Browse the curated catalog and assign books to their own children | ✅ | WS-E catalog visibility + assignment gate |
| G17 | Approve, decline, and revoke family connections for their own family, in each direction (share out and receive in); connections activate nothing without this consent | ✅ | ADR-016 requires dual-guardian consent; shipped 2026-07-17 in PR #270: paired consent columns (`db/models.py` `FamilyConnection`), `POST`/`DELETE /family-connections/{id}/consent`, and an enforced guard at the read path (`api/recommendations.py::_is_dual_consented()` requires both `consented_by_viewer_user_id` and `consented_by_sharer_user_id` before a connection is treated as active), superseding the prior holds-by-omission state Scope note (2026-07-25): this consent covers **recommendations** crossing ring 2, which is what ADR-016 and the substrate were built for. It is deliberately NOT read as consent to a child's real details appearing in story content in the connected household; **G18** adds a separate signed disclosure consent for that. |
| G18 | Opt a child's real details into their stories, per child and per slot, scoped by ring: within our own family (ring 1) or additionally with a specific connected family (ring 2, behind its own signed disclosure consent); and revoke either at any time | ❌ | Proposed 2026-07-25 in [ADR-023](./adr/adr-023-story-personalization-slots.md) (status Proposed, not yet Accepted; OD-1 and OD-5 gate the ring-2 half). Everything defaults **off**. Extends G4 ("personalized stories") with a mechanism G4's own note could not offer: substitution happens client-side at render time, so the S10 invariant ("no child PII to providers") is preserved rather than traded away. The ring-2 consent is layered **on top of** G17's connection consent, never merged into it: G17 consents to recommendations crossing the boundary, G18 consents to a child's real details appearing in story content read in another household. Revocation is prospective (effective on the connected household's next connection), not a retroactive claw-back |
| G19 | Gamification controls: per-profile toggles for the weekly ring (on/off and goal, within the cap), badges (hide without losing earned awards), and a pause switch for reading-time capture; defaults per the approved P-A table (ring off at 3-5); plus the guardian-side reading-time view (minutes per day, days per week) folded into the existing G9 reading summary | 🟡 | **Minted 2026-08-01** from owner decisions D12/D16/D17. Row wording awaits owner sign-off. Design authority: gamification recommendation section 4 (controls and defaults table). Distinct from G3 (request permissions and limits; its note explicitly scoped screen-time norms out, and the ring is a reading goal, not a screen-time cap) and from G2 (content controls). **Partially delivered 2026-08-01** (flip ❌ to 🟡): per-profile toggles shipped in `ProfileFormDialog.tsx` backed by the child_profile gamification columns; the reading-summary API carries minutes_last_7_days and days_read_this_week. Residual: the guardian ReadingPage UI does not yet render the time fields (API-only) |

## A: Admin capabilities

| ID | Capability | Docs | Notes |
|----|------------|------|-------|
| A1 | Moderation queue: flagged, uncertain, and reader/guardian-reported items, each showing why; decisions feed back into automated rules | ✅ | `needs_review` routing and global queue ✅; feedback-into-rules shipped as the WS-F propose-and-ratify suggestion dashboard over `pipeline_event`; kid/guardian reports (K15) shipped 2026-07-17 and feed this queue (`GET /admin/flags`) |
| A2 | Sample audits: random re-review of anything published without direct human review (becomes real if any auto-publish tier ever exists) | ❌ | Moot while A6 gates everything; register it so it survives any future gating change |
| A3 | Global policy levers: age-band definitions, theme taxonomy, classifier thresholds, banned-content lists | 🟡 | Per-band moderation thresholds are DB-backed, admin-editable with an audit trail (WS-A); band definitions and taxonomy remain code-level |
| A4 | Policy re-evaluation: re-screen the already-published catalog when policy or thresholds change | ✅ | First cut delivered 2026-07-17 (Phase 5/M5): admin-only `POST /api/v1/admin/rescreen` (`moderation/rescreen.py`, `api/rescreen.py`) re-runs the deterministic policy/band gate plus Stage-0 classifiers over an already-published book, and writes a `moderation_completed` pipeline event; a flagged book is never auto-unpublished (ADR-005), only surfaced for an admin to act on by hand. That hand action now has two forms, not one: `archive` (terminal, `archived` is absorbing) and, since `RS-C1`, `recall` (`POST /api/v1/storybooks/{id}/recall`, `publishing/service.py::recall`), which returns the book to `in_review` with a closed-vocabulary `reason_code` and writes a `storybook_recalled` event. Recall is what makes this row's premise workable: re-screening under moved thresholds previously left an admin choosing between killing a book and leaving an invalidated verdict live. It extends ADR-005 rather than relaxing it, since a recalled book must clear the human gate again before any child sees it, and assignment rows survive, so re-approval restores it to exactly the shelves it left. The UI-only gap closed: `ReviewDetailPage.tsx`'s actionbar carries a single-story Re-screen button (published-only, confirm dialog, loading/success/error states, outcome and reasons shown inline) via `frontend/src/admin/rescreenApi.ts`. Full public-catalog re-screen (Phase 9) stays out of scope by design |
| A5 | Incident path: trace how content reached a child (prompt, model, gate version), pull it everywhere including offline, notify affected guardians | 🟡 | Provenance trace and pull-everywhere (offline copies, `frontend/src/offline/revocation.ts`) delivered 2026-07-17. Guardian notification for the OWNING family only, delivered 2026-07-29 (commit 3916e99): `EventType.STORYBOOK_ARCHIVED` (`events/models.py`) fires from the sole published->archived hop (`publishing/service.py::archive`), and `notifications/registry.py::_compose_storybook_archived` composes it as a G10/S9 alert-severity notice; no frontend change needed, `NotificationBell.tsx` already renders any alert-severity item generically. **Cross-family recipients remain open**, so the row stays partial: `notifications/service.py::_resolve_storybook` resolves the recipient family from `Storybook.family_id` and `list_guardian_notifications` drops any item whose `ctx.family_id` is not the caller's, while `api/assignments.py` lets a guardian assign another family's `visibility='catalog'` book (the cross-family allow at its visibility gate) and catalog books are owned by the `CATALOG_FAMILY_ID` sentinel (`db/models.py`). Archiving a catalog book sitting on many families' shelves therefore notifies nobody, which A5's own text ("notify affected guardians") promises. Closing this needs recipient resolution to follow assignments rather than ownership |
| A6 | AI safety gate: the admin's recorded approval is the only path from generated content to a child (approve-and-publish) | ✅ | ADR-005 as amended; state machine with no bypass; ratified 2026-07-16 (decision 3) |
| A7 | Pipeline observability: success/failure rates, queue depth and latency, rejection reasons by stage, cost per story, per-provider quality | 🟡 | `pipeline_event` captures every transition and the WS-F dashboard aggregates moderation outcomes; cost/latency/yield operational views still ❌ |
| A8 | Pipeline levers: switch or disable providers, tune prompts/templates, set rate limits and cost caps, kill a runaway job | 🟡 | Config-pinned swap + fallback cascade ✅; per-request provider/model against a server-side allowlist shipped (WS-C), with allowlist + authoring-queue admin UI in PR #268; kill-job and caps surfaces still ❌ |
| A9 | Curated/seed catalog management so a new child never sees an empty shelf | 🟡 | Catalog visibility + "curated starter library" (ADR-008); management surface thin |
| A10 | Admin-initiated story generation (seeding the catalog, testing the pipeline) | ✅ | Shipped (WS-B): `POST /story-requests/authored`, admin catalog-targeted with no family; ADR-015 names it foundationally |
| A11 | Structural quality tools across the corpus: broken graphs, reading-level drift, repetitive or template-y output | 🟡 | Per-story validator is world-class. **Corpus-level repetition tooling delivered 2026-07-26** (PR #415, plan items A8/A21 plus the WS-0 gate): `scripts/run_diversity_eval.py --check` is the regression gate over the committed panel; `scripts/check_incell_clones.py --check` is the A8 in-cell duplicate audit over the real catalog, blocking against the `tau_cell` floor and carrying a self-pruning allowlist that must shrink to zero (one entry, A9); `validator/theme_leak.py` is the A21 residual retired-theme scan, wired into both the per-skeleton acceptance runner and `tests/unit/test_skeleton_contracts.py` as a catalog-wide drift guard; and `tests/unit/test_validator_rules_catalog.py` holds the rule catalog itself in lockstep with the code. **Author-feedback tooling added 2026-07-25** from the Wyrmreach three-book run (PR #416): the [authoring lessons log](./authoring-lessons-log.md) is delivered (append-only per-run lessons with a proposed change per row, validated by `scripts/check_lessons_log.py`, mandated as a core directive in `CLAUDE.md`), while reader-outcome quality tooling is designed but unbuilt ([reader-path-engagement-design.md](./reader-path-engagement-design.md): stop-rate per node, unreached endings, choice take rates, and a `skeleton_slug` join that separates a weak fill from a weak skeleton); ten further gaps are catalogued with fixes in [story-quality-lessons-2026-07.md](./story-quality-lessons-2026-07.md), of which one is blocking: no hand-authored skeleton can pass the `skeleton-promotion` CI gate, because `check_promotion_bundle.py` requires a lineage sidecar unconditionally and none exists in `skeletons/`. **Corpus-level *reading-level* drift tooling is still ❌**: RL-13 is per-story and advisory, and nothing tracks its distribution across the catalog or over time, so this row stays 🟡 rather than ✅. **Broken graphs** are covered per-story (L1/L2) and, across a series chain, by SR-1..SR-9 at publish |
| A12 | Account support ops: lockouts, deletion requests, abuse handling (an adult misusing generation) | 🟡 | PR #267 (open) delivers user/family lifecycle management: invites, edit, deactivate with auth-boundary enforcement and self-lockout guard; deletion-request and abuse workflows still ❌. Per the 2026-07-16 review condition: PR #267 also grants the admin console authority to set and reset a child profile's picker PIN (`PATCH /admin/profiles/{profile_id}`, `api/admin_profiles.py`), named here explicitly as an A12 admin-support capability rather than left implicit in the CRUD description; cross-reference [ADR-014](./adr/adr-014-device-authorized-kid-access.md), which defines the picker PIN as a convenience lock behind an already-authenticated guardian/admin bearer, not a security boundary in its own right |
| A13 | Admin action audit trail: admins touching child-related data leave a trail | ✅ | Approver stamps and `acting_role` audit stamps ✅; the view/report half this row previously marked missing is also shipped: `AuditPage.tsx` is a complete, wired, admin-only filterable audit log (event kind, storybook/profile id, date range, paginated) over `GET /api/v1/admin/audit`, routed at `/admin/audit` and linked from `AdminShell.tsx`'s nav. The page's own docstring cites this row by ID |
| A14 | Compliance and platform ops: retention enforcement, compliance reporting, backups and tested restore | 🟡 | ADR-007 retention, backups live, restore drill planned; compliance reporting ❌ |
| A15 | Administer family connections: broker, list, and remove connection records on request; admin action never substitutes for guardian consent | ✅ | Console shipped and merged in PR #267 (folded into #270 per roadmap.md M4d: "Delivered 2026-07-17"); this row said "open" only because it lagged the merge. ADR-016 subordinates it to G17 consent. Flipped to done 2026-07-29; empties Phase 4d down to the UW-A20 verification row |
| A16 | Generate and manage AI cover art per storybook version, reviewed on the approval surface before it reaches a child | ✅ | RULED 2026-07-16, recorded in [ADR-017](./adr/adr-017-ai-cover-art.md); shipped (covers/ module, admin trigger, R2 storage, best-effort with fallback). **H2 human-approval gate closed 2026-07-28** (security-hardening-plan-2026-07.md, PR #469): `generate_cover` stops at `cover_status = "pending_review"` instead of writing `ready` directly; admin-only `covers.service.approve_cover` (`POST /storybooks/{id}/versions/{version}/cover/approve`) is the sole path to `ready`, stamping `cover_approved_by`/`cover_approved_at`; `api/library.py`'s existing `cover_status == "ready"` read filter excludes any pending cover with no change needed, and the migration demotes pre-gate `ready` rows with a NULL approver back to `pending_review`. **Review UI closed 2026-07-29** (PR #471): `ReviewDetailPage.tsx` renders the pending cover and an "Approve cover" action wired through `coverApi.approve`; `api/covers.py::_cover_url` was widened to presign `pending_review` covers for that admin-only surface (`api/library.py` and `api/recommendations.py` compute their own child-facing URLs and stay untouched), and the server-side `is_admin` re-check is covered by `tests/integration/test_cover_api.py::test_approve_cover_non_admin_forbidden`. A still-missing automated image-safety classifier is treated as out of scope for this row, mirroring how A6 stands for story text. **`UW-M07` closed 2026-07-30**: the R2 bucket's public custom domain was disconnected in Cloudflare (outside this repository) and re-verified this session (`dig cyo-bucket.williamshome.family` fails to resolve, against a working general-egress sanity check), so an unapproved cover's bytes are no longer fetchable without credentials and the H2 gate now governs actual reachability, not only the API read paths. Flipped to done 2026-07-30 |

## S: System capabilities (cross-cutting)

| ID | Capability | Docs | Notes |
|----|------------|------|-------|
| S1 | Offline as a first-class mode: reading, choices, progress, and flags all work offline and reconcile later | ✅ | ADR-002, sync rules, offline queue with idempotent replay |
| S2 | Multi-device conflict resolution that never silently loses a child's progress | ✅ | Revision-based 409 model; kid-facing presentation tracked as K12 |
| S3 | Story representation that supports the format: branching graph, state, conditions, multiple ending types | ✅ | ADR-001, ADR-006, ADR-011; deeper than the expectation |
| S4 | Deterministic pre-publication validation that a story is playable (no dead ends, orphans, traps, unsatisfiable paths) | ✅ | Two-layer gate incl. state-space walk; RULED 2026-07-16: repair output must re-run the gate and the band policy must fail closed on an unconfigured band (fixes implemented on this branch) |
| S5 | Age-banding as the system-wide spine: reading level, theme intensity, safety thresholds keyed off one per-child band | ✅ | ADR-011 |
| S6 | Human-legible provenance per story: who or what created it, checks passed, approver, when | ✅ | Per-version model/provider/prompt/approver stamps |
| S7 | Independent safety pipeline: moderation independent of the generator; no path to a child bypasses the automated gates plus the human gate | ✅ | ADR-005, ADR-010, prompt-injection defenses |
| S8 | End-to-end request flow: initiate (K/G/A) -> guardian cost gate -> generation -> validation/moderation -> admin gate -> shelf, with honest async status | ✅ | Flow shipped end to end (WS-A..G: request -> guardian approve -> admin authoring plan -> pipeline -> admin release); ADR-015 is the foundational record. Both sub-gaps this row previously cited are already closed elsewhere: budget-at-consent is the same `enforce_family_quota` call G13 covers, kid-facing status is K12 (already ✅), confirmed live in `RequestStory.tsx`'s `STATUS_COPY`. No independent code of its own beyond what G7/G13/K12/G10/S9 already cover |
| S9 | Notification/event delivery infrastructure underlying K12, G10, and admin alerts | ✅ | Shipped 2026-07-17 in PR #270: `notifications/service.py` projects the append-only `pipeline_event` log into the K12/G10 feeds. Push transport shipped: `GET /v1/notifications/stream` (authenticated SSE via FastAPI's native `StreamingResponse`, deliberately not a WebSocket, which `middleware/security.py` disclaims support for) reuses this same `list_guardian_notifications` query rather than duplicating it, and `NotificationBell.tsx` prefers it over the poll, falling back on connection failure. **Closed 2026-08-09**: the server-scheduled digest job (a periodic batched summary, distinct from both the poll and the SSE push, neither of which is scheduled infra) is now built: `notifications/digest.py::run_notification_digest` writes one `NOTIFICATION_DIGEST_READY` event per family with pending info-severity notifications since their last digest, run daily by `.github/workflows/notification-digest.yml` via `scripts/run_notification_digest.py`. Proven by `tests/integration/test_notification_digest.py` (real cross-family Postgres, including cursor idempotency) and `tests/unit/test_run_notification_digest.py`. In-app delivery only: no email/push provider is introduced, so a guardian who is not polling and whose SSE stream never connects is still not reached externally |
| S10 | Privacy architecture: no child PII to providers, data minimization, deletion-readiness, no third-party trackers in the kid context | ✅ | Privacy model, PII guard, ADR-007/008/009. **Materially extended, not merely touched, by G18/K20** (ADR-023, proposed 2026-07-25): the "no PII to providers" invariant is preserved by construction, but the feature adds a new child-linked data category (per-child slot values), a new client-held payload at rest on devices, and a new cross-family flow, all of which the classification, retention schedule, and deletion drill must cover. **Extended again 2026-08-01 by K23** (reading_activity_day): a second new child-linked behavioral category, deliberately day-grain-only, cascade-purged with the profile, deletion-drill-covered, with a 12-month day-grain retention default entered into the UW-M03 counsel bundle |
| S11 | Social boundary enforcement: no messaging or free text between users, no user/family discovery, no kid contact outside active parental approval; cross-family flows exist only through ring-2 connections | ✅ | ADR-016 + vision v1.3; enforcement is structural (no such surfaces exist) plus the ADR-016 validation criteria. **G18 adds a second kind of ring-2 flow** (personalization values, alongside recommendations) and is the first one whose enforcement is a runtime authorization predicate rather than the absence of a surface; ADR-023's implementation plan section 8.4 is where that predicate lives, and it is the highest-consequence authz surface the boundary now depends on |
| S12 | System recommendations from anonymized aggregate book scores (ring 3): no identity in or inferable from a global recommendation; minimum-population threshold before aggregates surface | 🟡 | Named as permitted future scope in ADR-016; recommendation scoring itself still has no design. The **aggregate substrate and its privacy contract** are now designed (2026-07-25): [reader-path-engagement-design.md](./reader-path-engagement-design.md) specifies a de-identified `node_engagement` rollup carrying no child or device id, aggregate-by-construction endpoints that accept no profile parameter, a proposed 5-trail minimum-population floor with the population returned alongside every rate, and rollup-then-purge of the child-linked raw trails at 30 days on the ADR-007 precedent. This is the same threshold discipline S12 requires, built once for engagement and reusable for ring-3 scoring. **Forward-binding constraint added the same day (ADR-023)**: any story reachable through a ring-3 surface must render fully generic regardless of every G18 toggle. Story *content* satisfies this for free (the stored blob is always generic); the values *payload* path does not, and whoever builds S12 must land that as a test rather than assume it |

## Known doc debt this register supersedes or exposes

All three items below were resolved in the 2026-07-16 alignment pass; kept for the record:

- ~~The vision doc still says "no story reaches a child until a parent approves it"~~:
  resolved in vision v1.2 (TL;DR, success metrics, and MVP capability 5 now name the global
  safety admin per ADR-005 as amended); the guardian's residual controls are G5/G6/G7/G8,
  not approval.
- ~~The vision doc's one-family target-user framing predates the public pivot~~: resolved in
  vision v1.2 (scope note generalizes to the three roles; the founding family is kept as
  reference personas).
- ~~The "children cannot request stories" narrowing was never a recorded decision~~: resolved
  by [ADR-015](./adr/adr-015-story-request-initiation-and-gating.md), which reverses it
  explicitly and refines ADR-008's "children never trigger generation" phrasing to the
  enforceable invariant (no spend or provider egress without adult consent).

## Unregistered scope: rulings

Per maintenance rule 3, work serving no register ID gets a conscious call. Found in the
2026-07-16 open-PR review; both now ruled:

- **Cross-family recommendation connections** (PR #267): RULED 2026-07-16 (decision 6).
  Registered as K17/G17/A15/S11/S12 and recorded in
  [ADR-016](./adr/adr-016-recommendation-sharing-social-boundary.md). The PR's substrate
  stands; the binding constraint is that no connection activates child-facing visibility
  until the dual-guardian consent flow (G17) exists.
- **Provider allowlist admin UI** (PR #268): serves A8 and is cited there; no separate
  ruling needed.

Added by the full traceability review (2026-07-16, see
[traceability-review-2026-07-16.md](./traceability-review-2026-07-16.md) section 2);
RULED by the owner later the same day:

- **Star ratings**: RULED, registered as **K18** (the owner's variant of thumbs up/down,
  feeding aggregate ratings/S12). Debt item U6 folds under K18.
- **AI cover-art subsystem**: RULED, wanted as a register item; K8 updated, **A16**
  minted, recorded in [ADR-017](./adr/adr-017-ai-cover-art.md).
- **Reader "Go back" button**: RULED, the app should have one; tech spec Runtime
  Semantics amended, K5 updated.
- **ADR-007 raw output**: RULED, admin reviews first, then the parent (a dual-role adult
  is covered by the admin capability); the job-detail endpoint is tightened to
  admin-only `report` access and ADR-007 amended. The parent may ultimately receive
  unedited LLM output when the admin approves without changes; accepted, since it has
  passed the automated gates and admin review by then.
- **Repair re-gate and band fail-closed**: RULED, both fixes ordered and implemented on
  this branch (S4 note updated).
- **G2 content controls**: RULED, will be built; scheduling open.
- **Admin child-PIN set/reset** (PR #267): still open, recommend naming in A12 with an
  ADR-014 cross-reference at PR review time.
Added 2026-07-25 by the ADR-023 authorship pass:

- **Guardian opt-in story personalization** (render-time substitution of a child's real details
  into story content, ring-scoped): **registered as K20 and G18**, with scope notes on G4, G17,
  K19, S10, S11, and S12. Recorded in
  [ADR-023](./adr/adr-023-story-personalization-slots.md) (status Proposed).

  *Why two new IDs and not cross-references alone*, since that was the live question. Three
  existing rows are adjacent and none of them covers it. G4 already promises "personalized
  stories" and its example even names a child, but its whole mechanism is generation-time with
  real names kept out of prompts; this feature is a different layer reaching a different outcome,
  so folding it into G4 would make one row mean two incompatible things. S10 and S11 are
  *extended* by it (new data category, new cross-family flow) but are cross-cutting system
  guarantees, not the capability itself; a feature cannot be checked off against "privacy
  architecture". K16 is identity in the app, not in the story. So without a new ID, the single
  most user-visible thing this feature does would trace to nothing, which is exactly the failure
  maintenance rule 3 exists to catch.

  *Why two and not more.* Two personas genuinely gain a capability: a guardian who can opt in and
  scope it (G18), and a child who sees their own details and holds a switch over them (K20). The
  admin side does **not** need one: an admin reviewing marker-bearing prose is a presentation
  detail of A6's existing approval gate, not a new authority. Nor does the system side: the
  sentinel and render architecture is an *implementation of* S10's invariant, not a new
  cross-cutting guarantee, so S10/S11/S12 get extended notes instead of new IDs. Both new rows sit
  at ❌ and stay there until ADR-023 is Accepted and the work lands.

- **Planned items lacking a design element** (not schedulable until one exists): Android
  release, web direct-billing channel, education/teacher persona, i18n catalog. Still
  open as a batch.

## Maintenance rules

1. IDs are stable forever. Append, never renumber; mark dead items "Retired" with a reason.
2. When a capability lands, flip Docs status and link the spec/ADR and the tests that cover it.
3. Any new feature proposal must cite the ID(s) it serves; a proposal serving no ID is either
   scope creep or a missing register entry, and that call gets made consciously.

## Related documents

- [Project Vision](./project-vision.md) (update pending per doc debt above)
- [Tech Spec](./tech-spec.md)
- [ADR index](./adr/README.md)
- [Authorization Matrix](./authorization-matrix.md)
- [Privacy Model](./privacy-model.md)
