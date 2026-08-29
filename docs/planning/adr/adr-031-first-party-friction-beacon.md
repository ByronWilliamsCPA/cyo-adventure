---
title: "ADR-031: Children's-privacy review of the first-party client friction beacon"
schema_type: planning
status: proposed
owner: core-maintainer
purpose: "Discharge the ADR-018 children's-privacy review that task D3 of the
  testing-improvement plan names as a hard precondition before any code: walk every proposed
  beacon event variant to an explicit verdict, decide which surfaces may emit and whether the
  kid surface emits at all, define the session identifier's lifetime, fix where the beacon's
  records live and how their 30-day retention is enforced, and promote the Session Replay
  prohibition from a code comment in observability.ts to a standing decision."
tags:
  - planning
  - architecture
  - decisions
  - privacy
  - compliance
  - observability
---

# ADR-031: Children's-privacy review of the first-party client friction beacon

> **Status**: Proposed (2026-08-28). **Awaiting owner ratification.** This document was
> drafted by an agent as task D3a of the testing-improvement plan, whose D3 entry states
> "Gated on its own ADR ... No code before the ADR is accepted." **It is not a completed
> human privacy review and must not be cited as one.** It becomes Accepted only when the
> owner ratifies it. Until then no beacon client, no ingest route, no table, and no digest
> job may be built, and task D3b is blocked. The ADR is deliberately willing to return a
> narrower feature than the plan proposed: two of the seven proposed event variants are
> dropped here and the remaining five all ship narrowed.
> **Date**: 2026-08-28
> **Relates to**: [ADR-018](./adr-018-childrens-privacy-compliance.md) (the governing
> children's-privacy architecture and the authority this review answers to),
> [ADR-030](./adr-030-engagement-correlation-privacy-review.md) (the adjacent proposal,
> also `proposed` and also awaiting ratification, which worked the same re-identification
> problem for a server-side signal; its rules are carried forward and its divergences are
> named in Decision 2), [ADR-016](./adr-016-recommendation-sharing-social-boundary.md)
> (the no-free-text principle this beacon's closed payload extends to a new channel), and
> [ADR-014](./adr-014-device-authorized-kid-access.md) (the device-grant and child-session
> model that makes a kid-surface request attributable to one child profile).

## TL;DR

The D3 beacon may be built, in a narrower form than proposed, under constraints that are
decisions here rather than implementation preferences.

**The kid surface does not emit. At all, in version 1.** Not a reduced variant set, not a
sampled subset. A kid-surface request authenticates with a child session token whose signed
claim names exactly one child profile (`api/deps.py:738`), so the request is attributable to
one identified child whatever its body says. ADR-030 excluded storybooks carrying
`personalization_subject_profile_id` categorically, on the ground that no aggregate over a
record that is *about* one identified child is publishable at any cohort size. Kid-surface
friction telemetry is about one identified child by construction. The same rule gives the
same answer, and it is a categorical exclusion rather than a threshold.

**The emitting surfaces are the guardian console and the admin console only**, and the server
enforces that by rejecting any principal that is not `guardian` or `admin`. The landing page
does not emit either, because admitting it would require an unauthenticated write route.

**Two of the seven proposed variants are dropped**: offline-sync failure counts (it needs a
profile identifier to be actionable, and the plan's own `#VERIFY` says such a variant is
dropped rather than the rule bent) and dead clicks (its detector requires document-wide DOM
observation and a fetch wrapper, which is the capability the Session Replay prohibition
exists to forbid, at reduced fidelity). The other five ship narrowed. Decision 3 walks each
one.

**The record is not the payload.** The plan's `#ASSUME` is about payload contents, and a
payload proved clean is not a clean record: the envelope carries a bearer token, a client IP,
and a correlation id, and a stored timestamp joins to everything else the server holds at that
instant. This is ADR-030's own rule transposed (a property proved of one part of a record is
not a property of the record), and it produces the two most load-bearing controls here: the
handler resolves a principal for authorization and then **discards it before the insert**, and
`received_at` is **stored truncated to the calendar date**, matching the day-grain posture
`ReadingActivityDay` already establishes (`db/models.py:1745-1747`).

**The beacon does not write to `pipeline_event`, and cannot.** That table is enforced
append-only by trigger `trg_pipeline_event_append_only`
(`supabase/migrations/20260710000000_baseline.sql:524`), which raises on any UPDATE or DELETE.
The plan asks for a 30-day retention window on an append-only table, which is not
implementable. The beacon gets its own table with a `pg_cron` sweep, and **that sweep has no
exemption set at all**, because `UW-C227` records this repository shipping exactly the
sweep-time-versus-decision-time inversion the plan warns about.

**Session Replay stays banned, as a capability rather than as a product name**, because a
first-party reimplementation walks under a vendor-named ban without touching it.

## Context

### Problem

Leg C of the testing-improvement plan's workstream D proposes a first-party client telemetry
beacon: a small module beside `frontend/src/observability.ts` batching a closed enum of events
via `sendBeacon` on `visibilitychange`, posting to `POST /api/v1/client-events`, retained 30
days, and consumed by a weekly digest job in the mould of `moderation-report-health.yml` that
files or updates one tracking issue. The plan gates the whole thing on this ADR and carries
this assumption marker:

> `#ASSUME: security: the leg C payload enum can be kept free of attributable child data (no
> names, no free text, no stable per-profile identifiers) while remaining useful for triage.
> #VERIFY: the ADR review must walk every enum variant against the privacy model in
> docs/planning/ and against observability.ts's existing scrubbing rules before implementation
> starts; if any variant needs an identifier to be actionable, that variant is dropped rather
> than the rule bent.`

The marker is correct about what it names. It is incomplete in one respect that decides most
of this document: **it is an assumption about the payload, and what gets stored is a record.**
A payload can satisfy every clause of that marker while the record it lands in is attributable
to one child, because the attribution arrives in the envelope rather than the body. Three
structural properties of this system make that concrete.

1. **A kid-surface request names one child profile in a signed claim.** `api/deps.py`'s child
   principal is constructed with `profile_ids=frozenset({claims.profile_id})` (line 738), the
   singleton taken from the session token. A `device` principal carries `family_id` with
   `profile_ids` force-cleared (line 831), and a `guardian` principal carries a resolved
   `User.id`. There is no authenticated request shape on this API that does not identify at
   least a family. An anonymous body posted over an identified connection is an identified
   record unless the handler deliberately throws the identity away, and nothing makes a
   handler do that by default.
2. **The request path observes the client before the handler sees the body.**
   `CorrelationMiddleware` stamps a correlation id on every request and propagates it into
   every log line, and `RateLimitMiddleware` keys per client IP
   (`middleware/security.py:366` onward). Both are correct and neither is being changed here;
   the point is that they exist upstream of the beacon and so the beacon's anonymity claim
   cannot be made by inspecting its schema alone.
3. **The population is tiny and the timeline is dense.** The production roster is four adult
   accounts, two of them holding admin. A family may hold one child. A stored timestamp at
   full precision joins a beacon row to `pipeline_event.occurred_at`, to `completion.found_at`,
   to `reading_activity_day`, and to the edge access log for the same instant. In this
   population a timestamp is close to an identifier.

Two further hazards the plan itself names are real and open in this repository, and are
answered in Decisions 7 and 8 rather than left to the implementer: retention evaluated at
sweep time rather than decision time (`UW-C227`), and the shared redaction censor missing
several credential shapes.

There is also a plain implementability defect in the plan's server leg. It says the beacon
writes "through the existing append-only `events/` pipeline with a 30-day retention window."
Those two clauses contradict each other. `pipeline_event` is enforced append-only by a
database trigger that raises on any UPDATE or DELETE, so no retention sweep can touch it; its
`event_type`, `entity_type`, and `actor_role` columns each carry a closed CHECK constraint that
a new client event type would have to widen by migration; a further constraint,
`(actor_role = 'system') = (actor_id IS NULL)`, forces every row to either carry a user id or
declare itself a system transition, with no third option for an anonymous browser; and
`events/writer.py::record_event` requires an `Actor` and joins the caller's unit of work, which
a fire-and-forget beacon has no business doing. `UW-D28` already records the same collision for
`security_event`: "the `security_event` table has no retention or purge mechanism at all,
which is an ADR-018 gap the append-only trigger makes harder to close, not easier." Decision 7
resolves it for this data class.

### Constraints

- **ADR-018 is the authority, and consent does not stretch.** A child cannot consent, and a
  guardian's consent is scoped to the product functions disclosed to them. Telemetry recording
  how a child struggles with an interface is behavioural data about a child collected for an
  engineering purpose, which is a new processing activity rather than an extension of an
  existing one. The Rule's necessity limit bars conditioning a child's participation on
  collecting more than is reasonably necessary, and no child's reading experience improves
  because a beacon fired.
- **This repository is public, and the digest publishes into it.** The plan's consumption leg
  files or updates a tracking issue. An issue on this repository is world-readable and is not
  retractable. Whatever the digest says is a publication, so the beacon has two boundaries to
  close and not one: browser to server, and server to issue.
- **No measurement is available.** Nothing in this system currently measures client-side
  friction, so every number below is derived rather than calibrated, and is labelled as such.
- **The existing observability posture is deliberate and is being extended, not replaced.**
  `frontend/src/observability.ts` adds no `BrowserTracing` and no `Replay` integration, sets
  `tracesSampleRate`, `replaysSessionSampleRate`, and `replaysOnErrorSampleRate` all to 0 and
  `sendDefaultPii: false`, and runs a `beforeSend` scrubber that reduces `event.user` to a bare
  anonymous id and strips request bodies, cookies, and headers. Its module docstring states the
  reasoning: "This is a kids' reading app: Session Replay records DOM mutations and interaction
  video of whoever is using the page, which is exactly the kind of telemetry a
  children's-privacy-conscious app must not collect." That reasoning is carried forward into
  Decision 9 as a stated prohibition, because a posture that lives only in a comment is a
  posture the next module does not inherit.
- **ADR-030 is adjacent, not settled.** It is `proposed` and awaiting the same owner's
  ratification (`UW-A57`). It is treated here as the nearest precedent whose reasoning should
  not be contradicted, not as policy already in force.

### Significance

The asymmetry runs the same direction ADR-030 found. A beacon that collects less than it could
costs engineering visibility into an adult console, which the project has done entirely without
until now. A beacon that collects a child's interaction difficulty, or that stores an
attributable record, or that publishes an hour-grain hotspot into a public issue, discloses
something about identifiable children and cannot be undone: the issue is public from the
moment it is filed and the rows are joined the moment they are stored. When one side of the
error is reduced visibility and the other is irreversible disclosure about children, the review
takes the reduced visibility.

## Decision

### 1. Which surfaces emit, and the kid surface does not

**Emitting surfaces**: the guardian console (`/guardian/*`) and the admin console
(`/admin/*`). Nothing else.

**Non-emitting surfaces, each for its own reason**:

- **The kid surface (`/kids`, `/library/:profileId`, `/read/:profileId/:storybookId/:version`)
  emits nothing.** This is a categorical exclusion, evaluated before any other rule, not a
  threshold and not a reduced variant set. Four reasons, of which the first is sufficient on
  its own:
  1. **The request identifies one child.** A kid-surface session authenticates as a `child`
     principal whose `profile_ids` is the singleton from a signed claim (`api/deps.py:738`).
     A record created by that request is about one identified child at the moment it arrives,
     before anything in the payload is considered. ADR-030 reached the identical situation
     from the other side and excluded it categorically: "No aggregate over a book that is about
     one identified child is publishable at any cohort size, and no counting argument reaches
     this case." The subject here is reached by the session rather than by a column, and the
     rule is the same rule.
  2. **The route itself is the disclosure.** The reader route carries `:profileId` and
     `:storybookId`. Even a route *class* emitted from the reader says a specific child was
     reading at a specific time, and a route *path* would say which book.
  3. **The signal is a frustration observation about a child.** A rage-click hotspot on one
     control, from one session, in a product where a family may hold one child, is close to an
     observation about one identified child even with no identifier in the payload. This is
     the same argument ADR-030 made in refusing to publish `kid_flag.node_id`: a pointer to
     the passage at which a child recorded that something upset them is a statement about that
     child, and coarsening it does not change what it is about.
  4. **Consent does not cover it.** See Constraints.

  **What changes if the kid surface ever emits.** It becomes a new processing activity under
  ADR-018 D6, requiring an entry in `records-of-processing-activities.md` and a direct-notice
  review under 312.4(b)/(c) before any code, plus its own answer to every question in this
  document re-derived for a subject who cannot consent. It is an amendment to this ADR and a
  fresh ADR-018 review, not a configuration change. The only condition that could reasonably
  motivate it is a materially larger user base (Decision 10), and even then the categorical
  argument in point 1 survives population growth: a child session names a child regardless of
  how many children there are.

- **The landing page (`/`) does not emit**, because it is pre-login and admitting it would
  require an unauthenticated write route. An unauthenticated append path on a public origin is
  an abuse surface and an anti-automation obligation, and the value at stake is the landing
  page's own Web Vitals, which are recoverable from the D1 Lighthouse job without any beacon.

**The surface restriction is enforced server-side.** The ingest handler resolves the principal
and rejects any role other than `guardian` or `admin` with 403. A client that never mounts the
module on the kid shell is the first layer; it is not the control. A client-side-only surface
restriction is not a restriction, for the same reason a client-side-only kill switch is not a
kill switch (Decision 6).

**Note on the difference from Sentry, so this is not read as a reversal.** `initSentry()` is
called globally from `main.tsx` and does receive errors thrown on the kid surface today. That
posture is not reopened here and this ADR does not amend it. The two are different: a Sentry
error event is an exception report to a third party under a scrubbing `beforeSend` with no
replay and no tracing, whereas this beacon is a first-party behavioural record stored in our
own database beside our own identity tables. The beacon module therefore mounts per shell
(`GuardianShell`, `AdminShell`) and **must not** be initialised from `main.tsx`, where it would
run on every route including the reader. That is a binding implementation constraint for D3b,
recorded because `main.tsx` is the obvious place to put it and is the wrong one.

### 2. Re-identification: three vectors, and what carries over from ADR-030

The plan's `#ASSUME` names one vector. Two others decide more of this design than it does.

**V1: payload contents.** Named by the plan. Closed by Decision 3's closed enum and by
Decision 8's server-side rejection of anything outside it.

**V2: the envelope, not the payload.** An authenticated POST carries a bearer token that names
a user, a family, or a child profile; it arrives with a client IP that `RateLimitMiddleware`
already keys on; and `CorrelationMiddleware` has stamped it with a correlation id that reaches
the log line the handler writes. None of this is in the payload and all of it is in the record
unless the handler deliberately discards it. Bindings:

- **The handler resolves a principal for authorization and discards it before the insert.** The
  stored row carries no `user_id`, no `family_id`, no `profile_id`, no `created_by`, no IP, no
  User-Agent, and **no correlation id**.
- **The handler logs no request body and no principal**, and its structured log line for an
  accepted batch carries the batch size and nothing else.
- Discarding the correlation id has a real cost: a beacon row cannot be traced back to the
  request that produced it, so a malformed batch is diagnosed from the 422 at the client and
  never from the row. That cost is the point and is accepted.

**V3: the join to the server's own timeline.** A perfectly anonymous row still carries the
instant it arrived, and the server holds `pipeline_event.occurred_at`, `completion.found_at`,
`reading_activity_day`, `security_event`, and an edge access log covering the same instant. In
a four-adult roster a full-precision timestamp attributes. Bindings:

- **`received_on` is a DATE, not a timestamp.** The server stamps the calendar date at insert
  and stores nothing finer. This follows `ReadingActivityDay`'s docstring
  (`db/models.py:1745-1747`), which records that no timestamp finer than a day ever reaches
  the server for reading activity; the beacon inherits that posture rather than inventing a
  looser one for a lower-value signal.
- **The client sends no timestamp of its own**, in any form: no event time, no monotonic
  offset, no ordering index, no batch start time. Only the count of events per variant per
  batch (Decision 3) survives, and within a batch the events are unordered.
- Two consequences, stated so they are not discovered later as bugs. An INP p75 by hour cannot
  be computed, and the rage-click hotspot "at one hour" the plan's own hazard example uses is
  not expressible. Both are intended: that example is the disclosure, not the feature.
- A third consequence, from a trap this repository has already paid for: a `DATE` stamped with
  a server default is transaction-start-derived, and rows committed together are unorderable.
  **The beacon table carries no ordering guarantee and the digest must not depend on one.**

**What carries over from ADR-030, and where this ADR diverges.** Two ADRs on the same product
giving different answers to the same question is a defect, so each of its four mechanisms is
addressed explicitly:

| ADR-030 mechanism | Applies here | Reasoning |
| --- | --- | --- |
| Categorical exclusion of records *about* one identified subject | **Yes, and it is the strongest control in this document** | Decision 1. ADR-030 reached the subject through `personalization_subject_profile_id`; this ADR reaches it through the child session claim. Same rule, same verdict |
| A minimum floor binding **every emitted signal**, not merely the row | **Yes, adapted, at the publish boundary** | Decision 5. ADR-030's revision found that a row clearing the gate can still carry a cell built from one contributor; the same shape here is a weekly digest clearing a floor overall while one testid's hotspot rests on one session |
| Counting the floor over **distinct families** | **No. Diverges, deliberately** | The beacon carries no family key by construction, and acquiring one would be exactly the identifier Decision 4 forbids. The strongest unit available is the distinct session id, which is **weaker** than a family: two sessions can be one adult. Decision 5 states the compensating controls and the condition that voids the compensation |
| No total spanning more than one entity, so suppression is not defeated by subtraction | **Yes, unchanged** | Decision 5. The digest publishes no total spanning more than one testid or route class, and no exact denominator |

### 3. Every proposed variant, walked, with a verdict

Seven variants were proposed. **Two are dropped and five ship narrowed. None ships as
proposed.** Each is walked as: what it carries, what it discloses alone, what it discloses
joined to anything else the system emits, and the verdict.

#### 3.1 Largest Contentful Paint, bucketed. Verdict: **ships narrowed**

- **Carries**: one of three bucket labels, plus the route class, per page load.
- **Alone**: how slowly the adult console painted. Nothing about a person. At full millisecond
  precision a timing value is a device and network fingerprinting surface; bucketing removes
  that, which is why the bucketing is a requirement rather than a convenience.
- **Joined**: a bucket plus a route class plus a calendar date, with no session-stable id and
  no principal on the row, does not narrow to a person on the adult surfaces.
- **Narrowing, binding on D3b**: the buckets are the standard Web Vitals thresholds, fixed here
  so D3b does not re-decide them: `good` at or below 2500 ms, `needs_improvement` at or below
  4000 ms, `poor` above 4000 ms. **A raw millisecond value never leaves the browser**, is never
  transmitted alongside the bucket, and is never stored. The route class is one of a closed set
  (`guardian_root`, `guardian_requests`, `guardian_books`, `guardian_profiles`, `admin_root`,
  `admin_review`, `admin_moderation`, `admin_users`, `other`), never a route path, so no
  `:profileId` or `:storybookId` can ride along in it.

#### 3.2 Interaction to Next Paint, bucketed. Verdict: **ships narrowed**

- **Carries**: one of three bucket labels per page load, plus the route class.
- **Alone**: how long the app took to respond to a human interaction. INP differs from LCP in
  that it is triggered by a person's action, so it is worth stating plainly that what is
  measured is the application's response latency and not any property of the person: the metric
  is the same whoever clicked.
- **Joined**: as 3.1.
- **Narrowing, binding on D3b**: buckets are `good` at or below 200 ms, `needs_improvement` at
  or below 500 ms, `poor` above 500 ms. No raw value, ever. **The digest thresholds on the
  share of `poor` observations, not on a p75.** The plan's consumption leg asks for "an INP p75
  regression"; a p75 cannot be computed from three buckets, and admitting raw values so a p75
  could be computed would reintroduce the timing surface the bucketing exists to remove. This
  is a change to the plan's D3 consumption spec, decided here rather than left as a
  contradiction for D3b to resolve in whichever direction is convenient.

#### 3.3 Cumulative Layout Shift, bucketed. Verdict: **ships narrowed**

- **Carries**: one of three bucket labels per page load, plus the route class.
- **Alone and joined**: as 3.1. CLS is page-derived and carries no interaction at all.
- **Narrowing, binding on D3b**: buckets are `good` at or below 0.1, `needs_improvement` at or
  below 0.25, `poor` above 0.25. No raw score.

#### 3.4 Error-boundary hit as a component-stack hash. Verdict: **ships narrowed**

- **Carries**: a truncated hash of the React component stack, plus the route class and a count.
- **Alone**: which component subtree threw. The honest statement about the hash is that **it is
  not a de-identification measure and nothing in this design depends on it being one.** The
  input space is this repository's own component tree, which is public, so anyone can enumerate
  every stack from source and build the reverse mapping in minutes. The hash is a **bounded
  grouping key**: it lets the digest say "a new error-boundary signature appeared" and count
  recurrences without transporting a stack string.
- **Joined**: the component tree is public, so joining the hash to source recovers the
  component names, which is intended and discloses nothing about a person. The risk is not the
  hash, it is what a stack string could contain: a `displayName` or a React `key` composed at
  runtime can interpolate a book title or a child's display name, and an error *message*
  routinely does.
- **Narrowing, binding on D3b**:
  1. **The raw stack never leaves the browser.** Hashing in the browser rather than on the
     server is the actual control: an unexpected interpolated value in a stack is never
     transmitted, so it cannot be stored or logged even by accident. This is why a truncation
     or a prefix would not do.
  2. **The hash is SHA-256, truncated to 16 hex characters.** SHA-256 rather than MD5 or SHA-1
     per the project's FIPS posture, even though this use is not security-critical, so the
     codebase carries no weak-digest call site to explain away.
  3. **The error message, the error name, and every stack frame text are not emitted, in any
     form, hashed or otherwise.** Diagnosis is Sentry's job and that channel already exists
     with its own scrubbing; this beacon's job is counting.

#### 3.5 Offline-sync failure counts. Verdict: **DROPPED**

- **Carries**: a count of failed reading-state sync writes.
- **What it is actually about**: `frontend/src/offline/sync.ts` is the *reading-state* sync
  queue. Its writes are one child's reading progress. A sync-failure count is therefore a count
  of failed writes of a child's progress, and it fires from the reader, which is the kid
  surface. Under Decision 1 the kid surface does not emit, so this variant has no emitter left.
- **Joined, and why it fails the plan's own test even if an emitter existed**: the server
  already knows which child's `reading_state` writes did not arrive, because their absence is
  observable; a beacon count at day grain joined to the writes that did arrive narrows toward a
  profile without ever naming one. More decisively, the operational question this signal exists
  to answer is "whose writes are failing, and against which book", and that question **cannot
  be answered without a profile identifier**. The plan's own `#VERIFY` is explicit: "if any
  variant needs an identifier to be actionable, that variant is dropped rather than the rule
  bent." It is dropped.
- **The alternative, named so this does not return as a proposal.** Sync failure is already
  observable server-side without any client telemetry: the replay endpoint sees the retry rate
  and the conflict rate directly, and `sync.ts` already distinguishes `OfflineError` (no HTTP
  response) from a real HTTP failure, the latter reaching Sentry today. If a durable measure is
  wanted, the instrument is a server-side metric on the replay path, which needs no beacon, no
  child-device emission, and no new data class. That is a different piece of work with its own
  review, and this ADR does not authorise it.

#### 3.6 Rage clicks, identified by role plus testid. Verdict: **ships narrowed**

- **Definition, fixed here**: three or more `click` events on the same element within 1000 ms.
- **Carries**: the element's `data-testid`, its ARIA role, the route class, and a count.
- **Alone**: "a control was clicked four times in a second." On the adult surfaces this is a
  usability observation about a control.
- **Joined**: this is where the small population bites, and it bites on adults rather than
  children. The admin roster is two accounts. A hotspot attributed to the admin console in a
  given week is an observation about one of two identified adults. The mitigations are
  Decision 5's publish boundary: the digest carries no role class, no time grain finer than the
  week, and no figure resting on fewer than 5 distinct sessions.
- **Narrowing, binding on D3b**:
  1. **No `aria-label`, no `innerText`, no `textContent`, no coordinates, no element id, no
     class list.** `aria-label` is called out specifically because the accessibility work has
     been adding accessible names across these consoles and those names routinely interpolate
     data ("Open Ella's shelf"). An accessible name is exactly the field an implementer would
     reach for as "just an identifier" and it is the one field in the set most likely to carry
     a child's name.
  2. **The testid value space must be enumerable from public source, and that is enforced in
     two places.** First, a lint or `ast-grep` check that every `data-testid` in `frontend/src`
     is a string literal, never a template literal and never an expression, so no testid can be
     composed from runtime data. Second, server-side validation rejecting any testid not
     matching `^[a-z0-9-]{1,64}$`, as a second layer rather than the primary one. The first
     control is the real one; the regex alone would accept a slugified title.
  3. **The ARIA role is one of a closed set** taken from the roles this codebase actually uses,
     not an arbitrary string.

#### 3.7 Dead clicks. Verdict: **DROPPED**

- **Definition proposed**: a click with no DOM or network consequence.
- **Carries**: the same role plus testid as 3.6. **The payload is not the problem.**
- **Why it is dropped: the detector, not the data.** Detecting "no DOM consequence" requires a
  `MutationObserver` over the document subtree, and detecting "no network consequence" requires
  wrapping `fetch` and `XMLHttpRequest`. Those are the two capabilities Decision 9's Session
  Replay prohibition exists to forbid, at reduced fidelity: an in-page observer over document
  content, and an interceptor sitting on every request in the app including its bodies. A
  prohibition that a first-party reimplementation walks under is not a prohibition, and the
  first module to test that would be this one. The signal is also the weakest of the seven: a
  dead click on an adult console is most often a click on a non-interactive label.
- **The path back, stated so this is a narrowing and not a dead end.** A detector that observes
  only the clicked element's own subtree and the router's location, with no document-wide
  observer and no fetch or XHR wrapper, would not engage the prohibition and could be argued on
  its merits. That is an amendment to this ADR with the detector specified in it. **D3b does
  not get to invent one.**

#### Verdict summary

| Variant | Verdict |
| --- | --- |
| LCP, bucketed | ships narrowed |
| INP, bucketed | ships narrowed |
| CLS, bucketed | ships narrowed |
| Error-boundary component-stack hash | ships narrowed |
| Offline-sync failure counts | **dropped** |
| Rage clicks (role plus testid) | ships narrowed |
| Dead clicks | **dropped** |

### 4. The session id: lifetime, resets, reach, and the queue that does not exist

**Definition.** One `crypto.randomUUID()` value, minted at module initialisation and held in a
**module-scope variable only**.

**Explicitly forbidden storage**: `localStorage`, `sessionStorage`, IndexedDB, a cookie, a URL
parameter, a header, and any other durable location. The id exists in memory and nowhere else.

**Explicitly forbidden reuse, each named because each is reachable and plausible**:

- **`frontend/src/offline/deviceId.ts::getOrCreateDeviceId()`.** This is the single most likely
  mistake D3b can make. It is a `localStorage`-backed identifier that, by its own docstring,
  "outlives any one login session"; it already exists for fire-and-forget reporting from a load
  path; and it sits in the tree the beacon module will be written next to. Using it, or copying
  its pattern, converts "non-persistent random session id" into a permanent cross-session
  device identifier, silently, with no schema change to notice.
- The device-grant `jti` (`core/device_grant.py`, `DeviceGrant.jti`), the Supabase `sub`,
  `User.id`, `family_id`, and any child `profile_id`.
- Any value derived from any of the above, including hashed, truncated, or positional forms.

**Lifetime, precisely: one JavaScript realm.** The id lives exactly as long as the document's
script context.

- **A reload resets it.** New document, new realm, new module evaluation, new id.
- **A tab duplication resets it.** A duplicated tab is a fresh document load with a fresh realm.
- **A new tab resets it**, including one opened from a link in an existing tab.
- **A back-forward-cache restore does not reset it**, because bfcache preserves the realm. This
  is stated rather than glossed: within one bfcache-preserved history sequence the id spans
  more than one navigation. That is inside a single tab's continuous use by one person, which
  is the intended reach.
- **`visibilitychange` does not reset it.** It is the flush trigger, not a boundary. Backgrounding
  and returning to a tab keeps the same session.

**What an adversary can stitch within one lifetime**: every event from one document load in one
tab, which is one adult's console session: a set of route-class visits, a Web Vitals bucket per
load, error-boundary signatures, and rage-click targets, all at calendar-date grain and all
unordered. It is bounded by the realm and it reaches no second session, no second tab, and no
second day beyond a session spanning midnight.

**The offline case, and the decision that removes it.** This app has real offline support, so a
beacon queued offline and flushed later is a case the plan's "non-persistent" claim has to
survive. It does not survive it, so the queue is removed instead:

- **The beacon never queues and never persists.** A batch that cannot be sent is **discarded**.
  If `navigator.sendBeacon` returns `false`, or the browser is offline at flush time, the batch
  is dropped and nothing is written anywhere.
- **The beacon module must not touch `frontend/src/offline/` at all**: not `db.ts`, not the
  IndexedDB stores, and not `sync.ts`'s write queue.
- **Why.** Persisting a batch gives the session id a durable home on disk, which falsifies
  "non-persistent" by construction; a batch flushed in a later realm carries an id minted in an
  earlier one, so the lifetime claim above stops being true; and emission time and arrival time
  diverge, which makes the retention clock in Decision 7 ambiguous exactly when it matters.
- **The cost.** Samples from a device that goes offline mid-session are lost. The signal is
  statistical and the adult consoles are the least offline part of this product, so the cost is
  some lost samples against a durable client-side identifier. That trade is not close.
- **Therefore: a queued event cannot outlive its session id, because there is no queue.** The
  question the plan raises is answered by removing its premise rather than by managing it.

**Local rate limiting** (the plan's own requirement) is per realm: at most 1 flush per 10
seconds and at most 50 events per batch, with overflow **dropped rather than buffered**, for
the same reason a failed batch is dropped rather than queued.

### 5. Two allowlists, and the floor that binds published figures

ADR-030's revision found that a closure argument made on one side of a data path does not reach
the other, and closed both. This beacon has two boundaries and needs the same treatment.

**Allowlist A: browser to server (the emit allowlist).** A batch may contain these fields and no
others. Anything not listed is denied, including fields a later change would find natural.

| Field | Form |
| --- | --- |
| `session_id` | one `crypto.randomUUID()` value per realm (Decision 4) |
| `surface` | `guardian` or `admin` |
| `route_class` | one value from the closed set in 3.1, never a route path |
| `vital` entries | `{metric: lcp\|inp\|cls, bucket: good\|needs_improvement\|poor}` |
| `error_signature` entries | `{hash: 16 hex chars, count: bounded int}` |
| `rage_click` entries | `{testid: ^[a-z0-9-]{1,64}$, role: closed set, count: bounded int}` |

**Allowlist B: server to the weekly digest issue (the publish allowlist).** A digest issue may
contain these and no others.

| Field | Form |
| --- | --- |
| ISO week | the week the digest covers, never a finer grain |
| `route_class` | as above |
| `error_signature` hash | the 16-hex grouping key, with a count |
| `testid` | with a count, for a rage-click hotspot |
| `vital` poor-share | per metric per route class, rounded to the nearest 0.05 |

**Denied from Allowlist B specifically, each with its reason:**

- **The `surface` value.** A published figure never says whether it came from the guardian
  console or the admin console. With two admin accounts, naming the admin surface on a
  published figure identifies a population of two. The distinction stays queryable on the
  deployment host and is not published.
- **The `session_id`, in any form**, including hashed, truncated, or as a positional index.
- **Any exact denominator or raw count of sessions.** A count of 1 beside a share recovers the
  observation. The poor-share carries a stated rounding for the same reason ADR-030 rounds its
  rates: full precision reconstructs the denominator the suppression withheld.
- **Any total spanning more than one testid or route class**, and any corpus-wide summary line
  or count of how many signatures were considered, included, or suppressed. This is what makes
  suppression sufficient on its own: a suppressed figure is recoverable by subtraction only if
  some published figure includes it, and none does.
- **Anything else. The list is closed.** A new published field is an amendment to this ADR.

**The floor: 5 distinct session ids per published figure.** No figure appears in a digest issue
unless its own contributing population reaches 5 distinct session ids. Below that it is
suppressed as a single explicit marker covering the whole 0-to-4 range, never as a zero, never
as a null, and never as an omitted line, so a marker and an absence of the problem remain
indistinguishable in the published artifact. The floor binds **each figure separately**: a
digest week clearing 5 sessions overall can still carry a testid hotspot resting on one, which
is the exact defect ADR-030's revision found at the row-versus-cell level and is the reason the
floor is stated per figure rather than per digest.

**Why 5, and why the unit is weaker than ADR-030's.** The number is 5 to match ADR-030, so the
two documents do not give different answers to the same question. The unit is different and
weaker, and pretending otherwise would be the defect: ADR-030 counts distinct families because
its records reach a family key; this beacon deliberately carries none, so the strongest unit
available is the distinct session, and two sessions can be one adult on two days. Three things
compensate, and they are the reason the weaker unit is accepted rather than an argument that it
is equivalent: the subjects are adults using an internal console rather than children; no
published figure names a person, a role, a surface, or a time finer than a week; and no
published figure spans more than one entity, so nothing is recoverable by subtraction. **The
compensation voids** if any of those three changes, and Decision 10 says so.

### 6. The kill switch: two flags, the server authoritative, both default off

Following the exemplar this repository already uses for safety properties enforced at settings
construction rather than by operator discipline (`core/config.py:1211-1212`, and
`_reject_start_override_against_production_kws` at `core/config.py:2125`).

- **Client flag**: `VITE_CLIENT_BEACON_ENABLED`, absent or anything other than `"1"` meaning
  off. **Default off.** When off the module **registers no listeners at all**: no
  `visibilitychange` handler, no click listener, no Web Vitals observer, no error-boundary
  hook. It is not a mode that collects and withholds, because a withholding path that only runs
  when the flag is off is a path nobody exercises.
- **Server flag**: `client_events_ingest_enabled: bool = Field(default=False,
  validation_alias="CLIENT_EVENTS_INGEST_ENABLED")`. **Default off.**
- **The server is authoritative and gates ingest, not merely emission.** With the server flag
  off, `POST /api/v1/client-events` rejects with **503** and writes nothing, whatever any client
  believes. This is the answer to "a client-side-only kill switch is not a kill switch": a
  browser with a stale bundle, a modified build, or a hand-crafted request reaches the same
  refusal as a correctly configured one.
- **503 rather than 404, and rather than a silent 200.** Not a silent 200, because a fake
  success makes an enabled client indistinguishable from a disabled server, which is the shape
  of failure this project has already paid for where a fail-safe verdict laundered an outage.
  Not 404, because in this deployment a 404 is ambiguous with an unrouted host, a service-worker
  navigation fallback, and a tier mid-redeploy, all of which have produced false diagnoses here
  before. The **router is mounted unconditionally** so the OpenAPI contract is identical across
  tiers and the committed generated client cannot drift by tier; the flag gates the handler, not
  the mount.
- **The operator's oracle is the startup log line**, which names the effective ingest state, not
  a probe of the route.
- **Turning the flag off does not delete existing rows**, and, critically, **the retention sweep
  in Decision 7 is not gated by the flag.** A sweep conditional on the feature being enabled
  would stop deleting the moment someone turned the feature off, which is the exact inverse of
  what turning it off means, and this repository has already shipped a conditional guard that
  exited successfully having done nothing.

### 7. Retention: where the clock starts, what enforces it, and why there is no exemption set

- **The window is 30 days**, as the plan specifies.
- **The clock starts at server ingest**, on the `received_on` DATE the server stamps at insert.
  Not the client's clock, which is drift- and caller-controlled, and not an event time, because
  Decision 4 removed the queue so ingest and occurrence are within seconds of each other and
  Decision 2 removed sub-day precision from the record entirely.
- **Because the stamp is a date, "30 days" is precisely: the sweep deletes every row whose
  `received_on` is earlier than `current_date - 30`.** That is 30 to 31 calendar days of
  retention depending on the hour of arrival, and it is stated so nobody reports the extra day
  as a defect.
- **What enforces it**: a `pg_cron` job following the established pattern of
  `20260718000000_add_report_retention_purge.sql`, including the idempotent unschedule-then-
  schedule form and the graceful `RAISE NOTICE` degradation on any Postgres without the
  extension, so local, test, and CI environments are unaffected. The sweep runs unconditionally,
  independent of the kill switch (Decision 6).
- **The rows do not live in `pipeline_event`, and cannot.** See Problem. `pipeline_event` is
  trigger-enforced append-only; retention and that trigger are mutually exclusive, so the plan's
  "append-only pipeline with a 30-day retention window" is not implementable as written. The
  beacon gets its own table, `client_friction_event`, whose append-only property comes from the
  **absence of any update or delete code path in the ORM plus the least-privilege role's
  grants**, not from a trigger. That is a deliberate and stated weakening of the append-only
  guarantee relative to `pipeline_event`, taken because for this data class retention is the
  stronger privacy control and the two cannot both be had. `UW-D28` records the same collision
  reaching the opposite outcome for `security_event`, where the audit value justifies the
  trigger; naming both here is what keeps this from looking like an oversight.
- **The sweep has no exemption set at all.** Every row past the window is deleted
  unconditionally. `UW-C227` records this repository shipping exactly the inversion the plan
  warns about: the `generation_job.report` retention exemption "is evaluated when the nightly
  sweep runs, not when a human decides, so it does not protect a slow review." The cheapest
  immunity to that entire class of defect is to have nothing to evaluate, and no beacon row is
  ever evidence in a review, a moderation decision, or an audit, so no legitimate exemption
  exists to give up.
- **The form any future exemption must take, bound here so the inversion cannot recur.** If an
  exemption is ever proposed, the exempt determination must be **materialised onto the row at
  the moment the decision is taken**, as a nullable `retention_hold_set_at` column written by
  that decision, and the sweep must read only that column. A predicate joined at sweep time
  against a mutable status elsewhere is forbidden, because that is precisely `UW-C227`. Adding
  an exemption is an amendment to this ADR.
- **The digest issue is a permanent derived holding and is not covered by the 30 days.** A
  weekly digest issue on a public repository outlives the rows it summarises, forever. Saying
  "we keep beacon data for 30 days" while a permanent public issue restates it would be false,
  so it is stated the other way: **the published digest is permanent by design**, and that is
  acceptable only because Allowlist B plus the 5-session floor make its contents an aggregate
  over adult console operators with no person, role, surface, or sub-week time in it. If either
  of those weakens, the permanence of the artifact is the reason it matters.

### 8. Redaction: the payload is closed, and the shared censor is not relied on

**Decision: the beacon path relies on the shared redaction censor for nothing, and must never be
described as protected by it.** That censor is known to miss several credential shapes, and a
control with known gaps is not a foundation for a new data path.

The posture instead is that nothing arrives that would need censoring:

- **Every value in Allowlist A is a member of a closed enum, a bounded integer, or a slug
  matching `^[a-z0-9-]{1,64}$`.** The test that makes this checkable in one sentence:
  **there is no string field in the beacon payload whose value space is not enumerable from
  this repository's own source.** Adding a free-text field falsifies that sentence visibly,
  which is the point of stating it as a property rather than as a list of prohibitions.
- **Server-side validation rejects the whole batch, with 422, on any field outside the closed
  shape.** No partial acceptance, no silent field dropping, no truncation. A batch is a unit and
  a malformed one is refused whole, so a client that starts sending something new fails loudly
  on its first attempt rather than having the new field quietly discarded for a release.
- **The server never logs the request body**, in whole or in part, at any level, and never on
  the rejection path either. A 422 log line carries the failing field name and nothing else.
- **The test asserts against the allowlist, not against a list of forbidden names**, so a field
  added later fails by default rather than passing by omission. This is ADR-030's own discipline
  and the reason for it is the same: a deny-list is a list of the mistakes already made.

### 9. Session Replay is prohibited, as a capability rather than as a product name

`observability.ts` today carries this posture as a code comment. A comment does not bind a new
module, so it is stated here as a standing decision.

**No code in `frontend/src` may record, buffer, or transmit any of the following, whether via a
vendor SDK or a first-party implementation:** DOM content or DOM mutation records; input values
or keystrokes; pointer, scroll, or gesture traces; canvas, video, or screen captures; or any
time-ordered reconstruction of a page's visual state.

- **The prohibition is on the capability, not on a vendor.** Naming products would be trivially
  routed around by a first-party reimplementation, and this very ADR found one: the dead-click
  detector in 3.7 is a partial replay at reduced fidelity, and it is dropped for that reason. A
  ban expressed as "no `@sentry/replay`" would not have reached it.
- **Named packages, non-exhaustively, so the check is mechanical**: `@sentry/replay`, `rrweb`
  and its forks, LogRocket, FullStory, Hotjar, Microsoft Clarity, and any equivalent. Their
  absence from `frontend/package.json` and the lockfile is checkable and should be checked.
- **`BrowserTracing` and non-zero `tracesSampleRate` fall under the same prohibition, for a
  different reason**: a performance trace carries request URLs, and this app's routes contain
  `:profileId` and `:storybookId`. The beacon must not become the thing that reintroduces
  per-request tracing under a different name.
- **The reasoning, carried forward from `observability.ts` verbatim in substance**: this is a
  kids' reading app, Session Replay records DOM mutations and interaction video of whoever is
  using the page, and on the kid surface that person is a child. It stays off unconditionally
  rather than gated behind a sample rate, because a sample rate is a number someone can raise.
- **The existing configuration is the code expression of this decision, not an independent
  choice**: no `Replay` or `BrowserTracing` integration added, `tracesSampleRate: 0`,
  `replaysSessionSampleRate: 0`, `replaysOnErrorSampleRate: 0`, `sendDefaultPii: false`, and
  `beforeSend: scrubEvent`. `observability.test.ts` already pins part of that and should pin the
  sample rates and the empty integration set explicitly.

### 10. What would make this ADR wrong

Each of these voids part of the analysis above and requires a fresh review rather than an
adjustment:

- **The user base grows materially** (the ADR-008 public App Store launch being the concrete
  case). This cuts both ways and the direction matters: aggregates over adults become genuinely
  non-attributable and the Decision 5 floor may be doing no work, while the categorical
  kid-surface exclusion in Decision 1 **survives growth unchanged**, because a child session
  names a child regardless of how many children exist. Growth is the only condition that could
  reasonably motivate revisiting the kid surface, and even then it is an ADR-018 review and an
  amendment here, never a configuration change.
- **ADR-030 is ratified with amendments, or rejected.** This ADR borrows its floor of 5, its
  categorical-exclusion rule, and its two-allowlist discipline. If the owner rules differently
  there, the two documents must be reconciled rather than left to diverge.
- **Any of Decision 5's three compensations for the weaker session unit changes**: the subjects
  stop being adults on an internal console, a published figure gains a person, role, surface, or
  sub-week time, or a published figure starts spanning more than one entity. The 5-session floor
  is accepted only in combination with all three.
- **The digest's publication target changes**, in either direction. A move to a private surface
  relaxes Allowlist B's argument; any move that widens readership tightens it.
- **Any beacon field gains a value space not enumerable from this repository's source**, which
  is the single sentence Decision 8 is built on.
- **`frontend/src/offline/` grows a general-purpose client event queue** for unrelated reasons.
  Decision 4's "the beacon does not queue" would then read as a local exception rather than a
  design property, and the pull to reuse the queue would be strong. It would still be forbidden,
  and the reason would need restating at that time.
- **The admin roster grows** past a size where 5 distinct sessions is meaningfully more than one
  person, which would let Allowlist B publish the surface class it currently withholds.
- **The signal proves uninformative.** Pre-committed here, mirroring ADR-030's Decision 10: if
  after a full quarter of adult-surface emission the digest has filed nothing actionable, the
  correct response is to **retire the beacon**, not to widen it to the kid surface. An empty
  digest is evidence about the value of the signal, not evidence that the constraints are too
  tight.

## Consequences

### Positive

- The plan's `#VERIFY` is discharged in writing, variant by variant, with two drops and five
  narrowings rather than a blanket approval. Neither drop is a matter of taste: the sync-failure
  count is dropped by the plan's own stated rule about identifiers, and the dead click is
  dropped by the Session Replay prohibition reaching its own detector.
- Two re-identification vectors the plan's `#ASSUME` did not name are closed: the request
  envelope (a token, an IP, and a correlation id that make an anonymous body an identified
  record) and the join to the server's own timeline (a stored instant in a four-adult roster).
  Both produce controls a naive implementation would omit, because discarding a resolved
  principal and storing a DATE instead of a timestamp are both things you have to decide to do.
- A plain implementability defect is caught before any code: the plan asks for a retention
  window on a trigger-enforced append-only table, and those are mutually exclusive.
- The Session Replay prohibition is promoted from a comment to a decision and generalised from
  a product name to a capability, which is what let it reach the dead-click detector.
- Both boundaries are closed by default. Allowlist A closes browser to server and Allowlist B
  closes server to a public issue; ADR-030's revision established that a closure argument on one
  side of a path does not reach the other, and this design has two sides for the same reason.
- The retention hazard is closed by removing its precondition rather than by implementing the
  exemption correctly, which is a stronger position than `UW-C227`'s subject is in.

### Trade-offs

- **The kid surface, where a reading app's real friction lives, is unobservable by this
  instrument.** That is the largest cost in this document and it is deliberate. Kid-surface
  quality signal has to come from the e2e suites, the accessibility gates, and the usersim
  personas, none of which observe a real child.
- **No p75, no percentile of any kind, no hour-grain analysis.** Buckets plus day grain give
  poor-share and nothing sharper. The plan's own INP p75 threshold is replaced by a poor-share
  threshold.
- **Samples are lost whenever a device cannot send**, because there is no queue and no retry.
- **A beacon row cannot be traced to its request**, because the correlation id is discarded, so
  malformed batches are diagnosed at the client.
- **The floor's unit is weaker than ADR-030's**, and is accepted only on three compensations
  that can each individually stop being true.
- **The `client_friction_event` table's append-only property is weaker than
  `pipeline_event`'s**, resting on code discipline and grants rather than on a trigger, because
  retention required it.
- **Allowlist B is closed by default**, so every field a future digest wants is an amendment to
  this ADR rather than a code change. That friction is the point and it will be felt as
  friction.

### Technical debt

- **The digest issue is a permanent public artifact summarising data that is otherwise deleted
  in 30 days.** It is accepted on Allowlist B plus the floor, and it is the part of this design
  with no expiry.
- **The testid-literal lint check in 3.6 does not exist yet** and is a prerequisite of the
  rage-click variant, not a follow-up to it. Shipping the variant without it leaves the payload's
  closure resting on a regex that a slugified title would satisfy.
- **`security_event` still has no retention mechanism** (`UW-D28`), and this ADR's resolution of
  the same append-only-versus-retention collision for a new table does not close it. The two
  reach opposite answers for defensible reasons; nothing here should be read as having decided
  the `security_event` case.
- **This ADR is `proposed` and D3b is blocked on ratification.** Building any part of the beacon
  before then is exactly what the plan's "No code before the ADR is accepted" forbids.

## Follow-on work

- **`UW-A58`** (Cluster A, `decision`): owner ratification of this ADR, and with it the four
  rulings that are the owner's rather than an agent's: the kid surface emitting nothing in
  version 1, the two dropped variants, the 5-distinct-session publish floor on a weaker unit
  than ADR-030's, and the standing Session Replay capability prohibition. Until ratified, task
  D3b is blocked and no beacon client, ingest route, table, or digest job may be built.
- **`UW-C431`** (Cluster C, new): a plan document specified a retention window on a table
  enforced append-only by a database trigger. Append-only-by-trigger and retention are mutually
  exclusive, and nothing in the review chain flags a plan that asks for both. The general sweep
  is the other durable tables in this schema against their stated retention obligations,
  `security_event` (`UW-D28`) included.
- **`UW-C432`** (Cluster C, new): a privacy assumption stated about a payload was read as a
  property of the record. The envelope (a bearer token that names a subject, a client IP, a
  correlation id) and the stored timestamp both carry attribution that no payload allowlist
  reaches. This is ADR-030's row-versus-cell finding generalised to payload-versus-record; the
  row carries the sweep of this repository's other "the payload contains no PII" claims against
  what their records actually store.
- **`UW-A50`** (Cluster A, existing, ADR-018 D6): unchanged in scope by this ADR while the kid
  surface does not emit, since the beacon collects nothing about a child. It gains one dependent
  obligation: a new processing-activity entry in `records-of-processing-activities.md` covering
  adult-console friction telemetry, which must land **before the ingest flag is first turned
  on**, not after.

## Note on the documentation nav

This ADR is deliberately **not** added to `mkdocs.yml`'s nav, for the reason
[ADR-030](./adr-030-engagement-correlation-privacy-review.md) records: that nav's ADR list stops
at ADR-011 and includes no later ADR, so the directory is navigated through
[`adr/README.md`](./README.md) instead. A single nav entry for ADR-031 would invent a convention
holding for one document. The `README.md` index table is the surface that does need a row for
this ADR.
