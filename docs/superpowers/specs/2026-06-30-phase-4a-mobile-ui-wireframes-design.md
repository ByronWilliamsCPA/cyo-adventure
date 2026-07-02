---
title: "Phase 4a Mobile UI: Initial Concept Wireframes (Design)"
schema_type: planning
status: draft
owner: core-maintainer
component: Strategy
source: "docs/planning/completion-plan.md Phase 4a (C4a-1..C4a-6), PR #44 design-system components + tokens.css (branch feat/design-sync-init), frontend/src/reader/Reader.tsx + ReaderPage.tsx, ADR-005 mandatory human approval, brainstorming session 2026-06-30 (visual companion wireframes)"
purpose: "Concept-level wireframes and the confirmed direction for the five key mobile-UI pages needed to close the first usable release: Profile Picker, Library, Reader restyle, Guardian Console, and Concept Intake + Assign. Feeds the C4a-1..C4a-6 implementation plan."
tags:
  - planning
  - architecture
  - project
---

> Date: 2026-06-30 | Author: Byron Williams (with Claude)
> Builds on: [Completion plan Phase 4a](../../planning/completion-plan.md#phase-4a-library-profiles-and-the-guardian-app-shell-closes-the-first-release),
> [PR #44 design system](https://github.com/ByronWilliamsCPA/cyo-adventure/pull/44),
> [ADR-005 mandatory human approval](../../planning/adr/adr-005-mandatory-human-approval.md).

## 1. Problem and scope

`App.tsx` is still a small, single hard-coded page (about 50 lines) with no router installed;
Phase 4a (C4a-1 through C4a-6) is the largest remaining build before the first usable release and
has no UI concept work behind it yet beyond the reader engine itself. PR #44 (merged) delivered seven
on-brand primitives (`Button`, `ChoiceButton`, `Dialog`, `EmptyState`, `PassageText`,
`ProgressBar`, `StatusBadge`) and a "storybook palette" token set, but nothing yet says which
pages exist or how those components compose into them.

This spec identifies the five key mobile-UI pages and captures a confirmed concept direction for
each, at wireframe fidelity, so C4a-1..C4a-6 implementation has something concrete to build
against instead of discovering structure mid-code. **This is a UX/structure spec, not an
implementation plan**: routing, state management, and API wiring for these pages are separate
follow-on work (see Section 7).

## 2. App structure: two distinct experiences

The kid-facing and guardian-facing surfaces are **two distinct experiences**, not one app with a
shared shell and mode-switch. No shared login/profile-switch flow connects them at the UI level:

- **Kid surface**: Profile Picker &rarr; Library &rarr; Reader. A child never authenticates as a
  guardian or sees guardian-only screens.
- **Parent surface**: Guardian Console (queue + review/approve) &rarr; Concept Intake + Assign.
  A guardian's session is the OIDC/Authentik-backed one described in the roadmap's Phase 5.

This decision drives routing: expect two separate route trees (or genuinely separate apps/entry
points) rather than one router with role-gated branches.

## 3. Design tokens in play

All wireframes below use the actual "storybook palette" from PR #44's `tokens.css`
(branch `feat/design-sync-init`), not placeholder colors, so the direction is traceable to what
implementation will actually use:

| Token group | Values |
|---|---|
| Backgrounds | `--color-parchment` `#f8f3e8` (warm cream), darker variants for chrome/nav bars |
| Text | `--color-ink` `#2c1a0e`, secondary `#5a3e28`, muted `#8c6f56` |
| Primary accent | `--color-amber` `#c17b2a` / hover `#a3631f`; buttons, choices, progress fill |
| Secondary | `--color-forest` `#2d5a3d` (success/approve/connected), `--color-sky` `#4a7fb5` (info) |
| Semantic | error `#9b2c2c`, warning `#92600a`, success `#276749` |
| Type | Serif (`Georgia`/`Palatino`) for story passages, sans (`Segoe UI`/system) for UI chrome |
| Shape | Generous radii (4-20px, full pill for buttons/badges), warm-toned soft shadows |

## 4. The five pages

### 4.1 Profile Picker (kid surface, entry point)

**Confirmed concept**: 2-column avatar grid (not a carousel or full-width rows), where each
avatar is a **custom child photo** (not just an initial) inside a bordered circle, with a name
label and a small colored **status pill** beneath it showing the currently-in-progress book title
(or a "new story ready!" state when a guardian has just approved something). A dashed-outline
"Add Child" tile completes the grid. A child with no photo yet falls back to a dashed
placeholder circle rather than blocking the flow.

**Why this shape**: the grid reads as a familiar "device lock screen" pattern and scales to more
children by adding rows; the status pill reuses the same visual language as PR #44's
`StatusBadge` component, so "new story ready" can share styling with other status states later.

**RESOLVED 2026-07-02**: child avatars are preset-only, permanently; there is no photo upload
and no custom image path, so this screen never stores images of children. A curated set of
generated illustrated avatars will replace the interim emoji glyphs (tracked in issue #65);
the avatar ids in the catalog are the stable contract, so the art swap requires no data
migration. A child with no avatar selected falls back to a dashed initial circle, exactly as
wireframed.

### 4.2 Library / Bookshelf (kid surface, home screen)

**Confirmed concept**: a "Continue Reading" hero card for the most recently active book (cover,
chapter count, and a **full-width progress bar**), followed by a "More to Explore" shelf grid
below it for everything else assigned to that child. Every book in the shelf grid also carries
its own thin progress bar; a book with no progress shows an empty track plus a "Not started"
label rather than a bar that reads as broken.

**Why this shape**: fastest path back into an in-progress story (the common case), while the
shelf below still surfaces the rest of the library without a second screen. Needs a shared empty
state ("No books yet &middot; ask a grown-up to add one!") for a child with nothing assigned.

### 4.3 Reader (kid surface, restyle of existing engine)

`Reader.tsx`/`ReaderPage.tsx` already implement the reading flow correctly: offline-first
caching, state-gated choice visibility, 409 conflict resolution (`ConflictDialog`), and an
ending screen with restart. **This page is a visual restyle onto PR #44's real components, not a
new structure.**

**Confirmed concept**: a **persistent sticky top bar** carrying a `StatusBadge` (online/offline)
and a `ProgressBar` with a "Ch. X/Y" label, always visible during reading, not a minimal/
immersive layout with no chrome. The passage body renders via `PassageText` (serif, generous line
height); choices render as stacked full-width `ChoiceButton`s. The existing ending screen and
`ConflictDialog` get the same token treatment (serif ending title, pill-style restart button,
`Dialog` component for the conflict overlay) without changing their logic.

**Why persistent chrome**: offline reading is a core already-built feature, so surfacing
connection status constantly (rather than only contextually) was preferred over maximizing
reading real estate.

### 4.4 Guardian Console: review queue + approve/send-back detail (parent surface)

Two connected screens, both backed by C3-4's review-surface API and C3-3's approve/send-back
endpoints.

**Queue (landing view): confirmed concept**: one flat scroll grouped into
severity-ordered sections: **Flagged (review carefully)** first, then **Ready to
review**, then **Still processing**, using a `flag-badge`-style pill per row (flagged
count / "Clean" / "Generating&hellip;"). Nothing needs a tap-through to find what needs attention
most; it is already sorted to the top.

**Review detail: confirmed concept**: the **flags-first summary** is the landing view for
a given story: every flagged passage surfaces immediately as its own card (moderation
category + quoted excerpt), with a "Read full story &rarr;" link. Tapping that link (or a
specific flagged card) **drills into the full story text with flagged passages highlighted
inline**, auto-scrolled to that passage, with the moderation note directly beneath the
highlighted text. **Approve** and **Send Back** stay pinned in a bottom action bar on both the
summary and the drilled-in full-text view, so reading in depth is never a dead end for the
decision.

**Deliberately excluded, not an oversight**: a card-swipe "approve right / reject left" pattern
was considered and dropped before wireframing. ADR-005 requires a recorded human approval as the
sole gate before a child ever sees a story; a swipe gesture makes accidental approval too easy
for something safety-critical, so it was never presented as an option to choose between.

### 4.5 Concept Intake + Assign (parent surface)

Combines C4a-5 (concept intake + job status) and C4a-6 (assign-to-profile), which the completion
plan lists as separate workstreams; this page keeps them as **separate actions loosely coupled by
a shared recipient field**, not fully merged.

**Confirmed concept**: a single form (not a multi-step wizard) with **"Who's it for?"** as the
first field: a child-selector chip row that sets the age-band/reading-level constraint for
generation and pre-selects the default assignee once approved. Below it, "What's it about?" (free
text) and a tone chip row (Gentle / Adventurous / Silly), then "Request Story." Below the form, a
persistent **"My Requests"** status list shows every request the guardian has made, each with a
status pill (Generating / Approved / Failed) and who it was written for. An approved request
keeps a separate **"Assign more &rarr;"** action, which opens a child multi-select to widen an
already-approved story to additional children without re-requesting it.

**Why this shape**: picking a recipient upfront (like a wizard) would conflate "who am I
imagining this for" with "who ultimately gets it"; the separate "Assign more" action
preserves the ability to broaden an approved story to siblings later, while still giving the
generation pipeline a concrete age-band target from the start.

## 5. Cross-page notes

- **Empty states**: Library and the Guardian queue both need an explicit empty state (`EmptyState`
  from PR #44); this spec only wireframed Library's ("No books yet").
- **Status pill reuse**: the Profile Picker's book-status pill, the Guardian queue's flag badges,
  and the Intake status list all converge on the same pill/badge visual language
  (`StatusBadge`-style), which should be a single shared component rather than three
  near-duplicates once implementation starts.
- **Fidelity**: all wireframes are structural (spacing, hierarchy, real token colors) and
  intentionally not pixel-final; expect a polish pass once real components replace these mockups.

## 6. Open questions carried forward

| Question | Why it matters | Owner |
|---|---|---|
| Child profile photos: local-only or synced? Is a photo ever required? | RESOLVED 2026-07-02: preset-only avatars, no photos ever; generated illustrated set replaces emoji glyphs (issue #65). See Section 4.1. | Closed |
| Does "Assign more" need per-child unassign too, or only additive assignment? | Not explored in this pass; only additive assignment was wireframed (Section 4.5). | Follow-up brainstorm at C4a-6 |
| Kid surface and parent surface: fully separate deployments/routes, or same app with two disjoint route trees? | Confirmed as two distinct experiences (Section 2) but the deployment-level split (subdomain vs. route prefix) wasn't decided. | Follow-up at C4a-1 |

## 7. Next steps

This spec identifies pages and concept direction; it does not plan routing, state management, or
API integration. The natural next step is a **brainstorming + writing-plans pass on C4a-1 (app
shell + routing)** first, since every other page in this spec depends on it existing, followed by
per-page implementation plans that reference the corresponding section above.
