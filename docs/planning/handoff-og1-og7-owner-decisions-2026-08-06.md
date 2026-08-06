---
purpose: Scope the two owner decisions (OG1, OG7) that are blocking the story-structure-improvement
  program from starting, so the owner can rule on both without re-reading the full 24-item plan
component: docs/planning/story-structure-improvement-plan.md, docs/planning/unscheduled-work-register.md,
  docs/planning/capability-register.md
source: R1-completion review session, 2026-08-06
---

# Handoff: OG1 and OG7 owner decisions

Written 2026-08-06. This is item 4 of a four-item R1-completion handoff set; see the sibling
handoffs for the CVE gate/live defects (item 1), the R1 live E2E sign-off (item 2), and ADR-018
counsel engagement (item 3). Unlike the other three, this item has **no engineering task attached
to it directly**, it is two rulings that unblock engineering work described elsewhere
(`story-structure-improvement-plan.md`, briefed in full in `story-structure-implementation-briefs.md`).
Nothing here should be implemented before the owner rules.

## 1. Why these two, and why together

Both gates sit in `story-structure-improvement-plan.md` section 8 (owner decision gates). They're
handed off together because they're the two items currently stopping the story-diversity/"retire the
old-structure stories" program from starting at all, for two different reasons:

- **OG1** decides whether the 23 already-authored, single-voice stories go live now, accepting a
  named cost.
- **OG7** decides where the plan's core remedy for that cost (Stage 2, beat variants) actually lives
  in the roadmap's phase vocabulary, and today it's mis-registered in a way that contradicts the
  plan's own priority.

Ruling on OG1 without OG7 ships the old-structure inventory with no clear commitment to when it gets
replaced. Ruling on OG7 without OG1 fixes the roadmap's bookkeeping while the catalog stays empty.
They're a pair.

## 2. OG1: publish the 23 already-authored books, as-is, now?

**The decision**: whether to promote the 23 stories currently sitting at `in_review` (imported
2026-07-21 per issue #347, never published, `import_catalog.py` doesn't publish by design) to
`visibility='catalog'`, and in what order.

**What's really being decided, stated plainly**: these 23 stories were authored before any of the
differentiation machinery (variation axes, beat variants, cover-style variation) existed or was
wired through. Publishing them now means, **as the plan's own default proposal for OG1 states**,
"this ships the single-voice, no-diversity-machinery inventory as-is", the exact thing the second
half of the original question ("retire the current stories built on the old structure") is about.
The plan's position is that a reachable catalog beats an empty one, and that the SQ-13 variant
rollout (see the sibling program) is the intended remedy, not a substitute for shipping now.

**The concrete alternative**: re-author the inventory through the parity-fixed skill path (SQ-04)
first, at much higher cost, before publishing anything. The plan does not recommend this, but it
should be a conscious rejection, not a default.

**Default proposal, if no other preference**: promote all 23 that pass the existing `#529`
re-moderation sweep, kid bands first. The owner may hold back specific look-alike pairs (the plan
names `the-sunken-temple`/`the-harrowstone-keep` as the one pair currently on an allowlist for being
structurally near-identical, pending the A9 restructure).

**What this decision unblocks directly**: `SQ-01` (the promotion runbook itself, a process task,
not an authoring one) and, per `story-structure-improvement-plan.md` section 11.1, whether **`SQ-01`
counts as an `R1` release-rung item rather than ordinary `content`-workstream cadence**. That's a
real stake: `M5.1`'s own exit definition is "every family-tier register row at delivered status,"
and a library with zero reachable catalog books arguably fails that bar regardless of how the
Content workstream is scheduled elsewhere. If the owner agrees SQ-01 is an R1 usability gap, it
should be tracked and expedited as such, not left in the `content` bucket the roadmap has already
defined as release-rung-independent.

**Three inherited open questions from issue #347 that ride along with this decision** (per the SQ-01
implementation brief), decide these as part of the same runbook, not separately:

- Whether a review-stage billing bug (a nominally-mock provider making real OpenRouter calls) is
  confirmed fixed before trusting a fresh moderation-sweep run's verdicts.
- What should hard-block import versus stay advisory (e.g., does a large Flesch-Kincaid delta
  block?).
- Whether each moderation stage's fail-safe direction has been audited so a `verdict_parse_failed`
  can't silently PASS content that should have been flagged.

## 3. OG7: where does the beat-variant program (the actual "retire old structure" work) live?

**The decision**: whether to accept the plan's proposed remapping of the register's phase
vocabulary for the SQ-01..SQ-24 program, and specifically to resolve one internal contradiction the
plan admits it introduced.

**The contradiction, stated exactly**: `UW-G12` (the register row that SQ-11, the alternate-beats ADR,
unblocks) is currently registered as `post-launch` / `blocked`. But `story-structure-improvement-plan.md`
section 1.1 calls the SQ-11 → OG3 → SQ-12 → SQ-13 → SQ-14 chain the plan's **value-critical chain**,
the actual mechanism that makes a retold story feel distinct instead of a reskinned template, and
schedules SQ-11 to start "immediately after PR review," in week one. A row that says "post-launch,
blocked" while its own governing plan calls it the near-term decisive bet is not a stale label like
some of the plan's other register cross-references; the plan calls this one out explicitly as a
live contradiction that predates it and needs an owner ruling to resolve, not an engineering fix.

**What the plan proposes** (section 11.1's table, not a demand): once SQ-11 unblocks `UW-G12`, its
disposition should flip from `post-launch`/`blocked` to `content`, the same token already used for
the rest of the diversity workstream, consistent with the roadmap's own framing that this workstream
"does not block a release rung." The plan is explicit that `content` here means "decisive in impact,
not gating in timing," and separately proposes `SQ-01` alone (see OG1 above) as the one exception
that should carry the `R1` token instead.

**Secondary items OG7 also covers, lower stakes**: the plan proposes `content` tokens for most of
Stages 0, 1, 3, and 4 (SQ-02 through SQ-10, SQ-15, SQ-17, SQ-20, SQ-21, SQ-23), keeps SQ-16/SQ-18 on
their already-settled `4b`, and leaves SQ-19, SQ-22, SQ-24 with no new token (they're decision rows
or already-settled elsewhere). These stretch the `content` token from prose authoring to backend
selection/measurement code in a few places, flagged in the plan as a "mild" inference the owner can
reject if `content` is meant to mean authoring specifically, but none of them carry the SQ-11/UW-G12
contradiction's urgency.

**What this decision unblocks**: whether the register and the roadmap's phase-linkage tables (which
`scripts/check_work_linkage.py` validates) can stop flagging this program as inconsistent, and
whether the implementation team can point at a settled phase home when scheduling Stage 2 work
instead of working against a register row that says the opposite of the plan they're following.

## 4. What NOT to decide here

Section 8 of the plan has five other owner gates (OG2 through OG6) that are genuinely downstream of
engineering work starting (e.g., OG2's theme-overlap cap value needs a month of serving data to
calibrate; OG3 is SQ-11's ADR acceptance, which doesn't exist as a document yet). Don't try to rule
on those now, they're sequenced later in the plan for a reason, and ruling early would be a
guess, not a decision informed by the evidence the plan gathers between now and then.

## 5. Definition of done

- OG1: a recorded decision (publish list, order, any held-back pairs) plus the #347 sub-questions
  resolved; `UW-G14` flipped to `done` with a Ref once the promotion runs.
- OG7: a recorded ruling on the section 11.1 mapping table, at minimum resolving the `UW-G12`
  contradiction; the register row(s) updated to match (this is the plan author's stated follow-up,
  not something this handoff does on its own authority).
- Both decisions recorded in `story-structure-improvement-plan.md` section 8's table (update the
  "Default proposal" column to "Decided: ..." per the convention the ADR-018 handoff's D1/D3 rows
  already use) or in a dedicated decision log, whichever the owner prefers to keep as the durable
  record.
