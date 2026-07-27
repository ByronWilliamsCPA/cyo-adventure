---
purpose: What remains in slice S5 of the story-diversity work (the naive-user session, then A11, A13b, A18, B4), why the session gates three of the four items, and what A12 needs before it can be scheduled at all
component: frontend/src/library/RequestStory.tsx, frontend/src/reader/Reader.tsx, frontend/src/player/machine.ts, .claude/skills/naive-ux-check/
source: PR #415 session 2026-07-26
---

# Handoff: S5 reader UX, what remains

Written 2026-07-26. **S5 is entirely unstarted**: PR #415 has changed **zero
files under `frontend/`**, verified against `origin/main`, not assumed. That is
by design rather than neglect, and this doc records why, so a future session does
not "get ahead" by building the three items the plan deliberately gates.

Read alongside `story-diversity-plan-v2.md` (rows A11, A12, A13a, A13b, A18, B4
and the section-6.1 child-reader review) and
[ADR-024](./adr/adr-024-bounded-backtracking-path-replay.md).

---

## 1. The gate: a naive-user session with real children

The plan is explicit, and the wording is deliberate: **"Run those before building
A11, A13b or A18, not after."**

The section-6.1 child-reader review *reasoned* about what a child would find
confusing. Three of its judgements are empirical questions that one session with
a real child settles better than any amount of further analysis:

- **Does a 3-hop rewind read as "the app took my turn"?** (A13b's core risk)
- **Is the lower back-chevron confusable with the one that exits the book?** (A18)
- **Does a hero-name field with a shuffle land as a toy or as a restriction?** (A11)

If the answer to the first is yes, A13b changes shape or should not be built at
all. Building it first risks building the wrong thing carefully.

### How to run it

The repo ships `.claude/skills/naive-ux-check/` for exactly this: 17 staged
comprehension prompts across three personas (K0-K4, G0-G7, A0-A3), logged to a
dated findings report.

**The skill cannot drive a browser.** There is no Claude-for-Chrome tool
available to an agent session, so the skill hands you a prompt to paste into the
extension by hand. This is the one part of S5 that only the owner can do. The
default target is the local dev frontend pointed at staging via `.env.staging`
(see the committed `.env.staging.example`).

The owner's children are the current test readers, and the development stage
(one household) is what makes this available at all. It is, in the plan's words,
"the one form of evidence this plan has been unable to gather, and it is
currently available."

---

## 2. The four build items

### B4 - not gated, do this one first

`frontend/src/player/machine.ts`, the `reset` action
(`reset: assign(({ context }) => safeStart(context.story))`, verified still
present at handoff). It resets to the start node with **declared initials**, so
"Read again" in a continuation read fabricates `has_lantern=true` and `vigor=5`
that the reader never earned, and discards the carried state.

This is a real bug, independent of anything the naive-user session could find,
and it is the only S5 item safe to build today. Effort **S**.

Note the adjacency to B1 (delivered, `save_slots` validation on the reading-state
write path): both are about state the reader did not earn. Keep the same posture.

### A11 - reshape the request page. Effort M. Gated

`frontend/src/library/RequestStory.tsx` (359 lines) is one prompt and a
500-character box today. Per the child-reader review:

- **Drop** the fixed-structure statement from the kid surface. No child under
  about eleven has that model; keep it on guardian intake.
- **Drop** "some themes are off for this family". It is unnameable on the kid
  surface, so it is a pre-emptive accusation with nothing to act on, and the
  existing blocked-status copy already handles the real event kindly.
- **Reshape** the naming rule from a prohibition into a mechanism: a "Who's the
  hero?" field pre-filled with a made-up name plus a shuffle control, which sets
  the expectation without ever saying "you cannot be the hero".

**Copy constraint, load-bearing:** the wording is **superseded by ADR-023**,
merged in PR #418. **Adopt ADR-023 section 4 Ask 1's wording; do not draft
alternatives.** The earlier suggestion to reuse `interpretation.py`'s "Heroes in
our stories always have made-up names" is **withdrawn**: that sentence becomes
false for a family that enables **G18**, and so does the affirmative PII line the
plan previously proposed. The load-bearing change is "starts with", which is
unconditionally true because generation always uses a placeholder.

**This is the open half of K19's copy dependency** recorded in
`capability-register.md`: G18 and this item must ship their wording together,
and neither may ship it alone. Beware the name collision while reading that
register - its own `A11` is a different item (corpus quality tooling).

### A13b - "Try a different way." Effort M. Gated

Add a second, **separately labelled** affordance **at the ending screen only**.
It walks up to **3 hops** back to the last node where the reader had a real pick,
and **falls back to one step when there is none**.

**A13a is explicitly a decision to change nothing**: the in-story Go back stays
one step, always available. `Reader.tsx:210` states its purpose - "Kids mis-tap
constantly; Go back undoes just the last choice" - and binding a multi-hop rewind
to that button would move a mis-tapping child further than they meant to go. Do
not "simplify" the two into one control.

The 3-hop bound is the owner's settled decision. ADR-024 is the governing record
for backtracking semantics; read it before touching replay.

### A18 - differentiate the two back-chevrons. Effort S. Gated

`frontend/src/reader/Reader.tsx` (438 lines) renders Go back as a ghost button
with a chevron **visually identical** to the top-bar "Leave" chevron - and one of
those exits the book. A13b makes the lower one more consequential, so these two
should land together.

Give the story-level control a circular-arrow glyph, and make the ending-screen
affordance **primary weight rather than ghost**, since there it is a headline
action.

---

## 3. A12 is deferred, not pending. Do not schedule it as work

`replayRecordedPath` fails closed when `path[0] !== start_node`, which disables
Go back in exactly the state-carrying series books where a reader has most to
lose. It looks like a small bug. It is not.

Replaying a continuation read needs its origin's initial variables, and **nothing
retains them**: `startContinuation` seeds `var_state` from a carried map but the
resulting `ReadingState` does not keep it, `ReadingState` has no column for it
(`db/models.py:725`), and `Completion` stores only
`(child_profile_id, storybook_id, version, ending_id, found_at)`, so the
predecessor's exit state cannot be re-derived either. The seed reaches the client
only transiently through router `location.state`, which `series.ts` itself
documents as untrusted and attacker-shapeable.

Enabling it therefore needs new durable state, hence a schema change, an API
change and an OpenAPI regeneration - **and that state would be a replay origin,
a state-restoration input of exactly the class B1 describes.** Built naively it
becomes a second `save_slots`, letting a forged origin replay into a state the
reader never earned, in precisely the books where that pays best.

**ADR-024 Decision 6 records it as not authorized** and states the
fail-closed-validation requirement any future decision must meet. A12 needs an
owner decision before any implementation time, and that decision should cite
ADR-024.

---

## 4. Suggested order

1. **Owner runs the naive-user session** via `.claude/skills/naive-ux-check/`,
   targeting at minimum the three questions in section 1
2. **B4** - independent of the findings; can be done in parallel or first
3. **A18**, then **A11** and **A13b**, shaped by what the session actually found
4. Re-check the K19 / G18 copy dependency in `capability-register.md` once A11's
   wording lands, and close it there

No backend contract should change, so no OpenAPI regeneration is expected. If one
does, regenerate the client (`cd frontend && npm run generate-client`) and commit
the diff: the `contract` CI job fails on drift.
