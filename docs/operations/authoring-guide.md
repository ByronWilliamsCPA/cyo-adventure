---
title: "Authoring Guide for Guardians and Admins"
schema_type: common
status: published
owner: core-maintainer
purpose: >-
  A short, non-technical guide to how a story goes from an idea to a child's shelf, what
  each review screen shows, and what to do when a story is rejected.
tags:
  - guide
  - documentation
---

This guide is for guardians and admins, not developers. It explains, in plain language, how a
story request turns into something a child can read, what you will see on each screen along the
way, and what your options are if a story does not pass review. It does not use internal jargon;
a short reference list of the underlying capability IDs is at the bottom for anyone who needs to
cross-check it against the project's planning documents.

## From an idea to a child's shelf

A story can start two ways:

1. **Your child asks for one.** From their library, a child can type a short idea for a story.
   That idea lands in your **Story requests** page (`/guardian/requests`), waiting for your yes
   or no. Your child sees "Waiting for a grown-up to say yes" until you act on it.
2. **You ask directly.** From **Request a story** (`/guardian/intake`) or the top of **Story
   requests**, you describe an idea yourself, pick which child it's for, and choose a tone. A
   request you author this way does not need a separate approval step; it goes straight to being
   written.

Either way, the same checks apply before anything is written:

- **Your consent.** A request only starts consuming your family's story budget once you (a
  guardian) have said yes to it, whether that "yes" is your own request or an **Approve** on your
  child's idea.
- **Your monthly story balance.** A banner near the request form and the Story requests page
  shows "N of M stories left this month." Approving a request uses one; the Approve button also
  shows a reminder such as "This will use 1 of your 3 remaining stories this month" before you
  confirm.

Once approved, the request moves out of your hands and into the writing pipeline:

- **The story gets written.** This step runs automatically once an admin has set it in motion; you
  do not need to do anything. Your **My Requests** list shows a **Generating** status while this
  happens (usually a few minutes).
- **An automated safety check runs first.** Before any human ever sees the story, it must pass a
  set of automated rules (story structure, reading level for the child's age, and content safety
  screening). A story that fails outright never reaches a reviewer; it shows as **Failed** in
  your requests list with a plain-language note ("This story could not be made.") and a **Try
  again** button that refills the form with the same idea so you can resubmit it.
- **A human reviewer checks it.** A story that passes the automated checks is marked "Waiting for
  review" in your requests list, with the reminder: "A grown-up reviewer checks every story before
  kids can read it." An admin reviews it on the **Review queue** (`/admin`) and its detail page
  (`/admin/review/<story>`), described below.
- **The admin approves and publishes, or sends it back.** Approving makes the story visible on the
  shelf of every child it gets assigned to. Sending it back returns it to you or the admin with a
  written reason so it can be improved and resubmitted.
- **You put it on a shelf.** Approval alone does not hand a story to a child. Once your request
  shows **Approved**, use the **Assign** button (on the **Books** page, `/guardian/books`, or the
  **Assign more** button on your requests list) to choose which child profiles can read it. A
  story is only visible to a child once it has both been approved and explicitly assigned to
  their profile.

## What the review screens show

### The Review queue (admin, `/admin`)

Every story waiting on a decision appears here, across every family, so an admin can work through
them in one place. Each row shows whether the story screened clean or has something flagged, so an
admin can prioritize.

### The Review detail screen (admin, `/admin/review/<story>`)

This is the screen an admin uses to actually make the approve/send-back decision. From top to
bottom:

- **A findings summary strip** at the top: a count of automated findings, and colored badges such
  as **Hard block**, **Soft flags**, **Repaired**, and either **Independent review** or **Not
  independently reviewed**. The safety review is deliberately run by a different AI model than the
  one that wrote the story, so "Independent review" tells the admin that separation held.
- **A version comparison**, when this is not the story's first version, so an admin can see exactly
  what changed since the last time it was reviewed.
- **Story overview** (open by default): a quick, skimmable summary of the story's branches and
  themes, so an admin does not have to read every page before deciding whether to dig in.
- **Flagged passages**: the specific passages the automated checks flagged, each with a **Show in
  story** link that jumps straight to that passage further down. If nothing was flagged, this
  section says so plainly: "No flagged passages. This story screened clean."
- **Story-level notes**: findings about the story as a whole rather than one specific passage.
- **The full story**: every passage in reading order, with a **Start** marker on the opening
  passage. Passages the story's own choices can never actually reach are listed separately, under
  **Unreachable passages**, so nothing gets skipped just because a branch is dead.

### Approving a story

Clicking **Approve** opens a confirmation with one important choice: **Who can see this book?**

- **This family only**: the default. Only the requesting family can read and assign it.
- **Catalog (every family)**: shares the book with every family's library. Choosing this shows a
  warning to double-check the story contains no names, photos, or personal details before sharing
  it more broadly.

### Sending a story back

Clicking **Send back for revision** requires a short written reason (this is not optional; the
button stays disabled until a reason is entered). The story returns to "needs revision" so it can
be reworked and resubmitted for another review pass.

## Editing a passage

From the review screen, an admin can click into any passage and edit its **passage text** and the
wording of its existing **choice labels** directly, without changing the story's structure (a
passage's id, where its choices lead, and any underlying conditions cannot be touched this way).

Every edit automatically re-runs the same safety checks the story went through at generation time,
scoped to that one passage, before the edit is saved. If the edit would break a structural or
reading-level rule, the save is rejected with a specific explanation ("This edit did not pass the
validation gate:" followed by the exact rule) and nothing is changed. If the edit introduces a new
safety finding, the save still succeeds, but the finding shows up for the next reviewer to weigh,
the same way an original generation finding would; the automated check never has the final word,
a human reviewer does.

## Ratings, flags, and notifications

- **Ratings**: a child can rate a book they have read, one to five stars. A re-rating simply
  replaces the old one.
- **Flags**: a child can flag a story they're reading using a short, fixed list of reasons (never
  free-text, so a flag can never be used to smuggle inappropriate text past the safety review).
  A flagged story feeds directly into the admin moderation queue for a human to look at.
- **Notifications**: guardians get a notification feed (the bell icon in the guardian console)
  covering four kinds of events: a story is awaiting your consent, a story is ready on the shelf,
  your child flagged something they were reading, or a story generation attempt failed. This feed
  is guardian-only; a child never sees it, since some of these notifications can name the child
  involved.

## When a story is rejected

There are two different "no" outcomes, and they mean different things:

- **The automated checks reject it outright (before any human sees it).** This shows as
  **Failed** in your requests list. Nothing about the story is shown to you (it was never reviewed
  by a person, and showing you the raw draft would defeat the point of the safety gate); use
  **Try again** to resubmit the same idea, which often produces a very different result on the
  next attempt.
- **A human reviewer sends it back.** This means it passed the automated checks but a reviewer
  decided it needs work; you'll see the reviewer's written reason. The story can be revised and
  resubmitted for another review pass, rather than starting over from scratch.

Neither outcome ever results in unreviewed content reaching a child. A story only reaches any
child's shelf after it has passed the automated safety checks **and** been explicitly approved by
a human reviewer **and** been explicitly assigned to that child's profile by a guardian.

## A note on what's still catching up to this guide

One step in the process above ("the story gets written") is triggered by an admin choosing how to
write it (an automated model, or a pre-written story outline filled in by hand) behind the scenes;
there is not yet a console screen for that specific choice, so it is currently handled directly by
whoever operates the system rather than from a page in this guide. If you are a guardian and a
request sits at "Waiting" for longer than expected without moving to "Generating," check with your
admin.

Likewise, pulling a published book back off the shelves in an emergency (the "kill switch")
removes it from every guardian's and child's library listing immediately, and a copy a child's
device already downloaded for offline reading is now also removed the next time that device
connects. The one remaining edge case: if a child is actively reading a book at the exact moment
it gets pulled, that one reading session is not interrupted mid-story; the removal takes effect
the next time they return to their library. Details are in the companion
[operator runbook](runbook.md).

---

### Traceability footer

This guide describes the guardian- and admin-facing behavior corresponding to capability register
entries: G5 (fast review skim aids), G6 (edit with re-review), G7 (consent-gated spend), G8 (kill
switch), G10 (notifications), G13 (predictable cost model), A1 (moderation queue), A5 (incident
trace and pull), A6 (mandatory human approval), and A13 (admin action audit trail). See
`docs/planning/capability-register.md` for the full register.
