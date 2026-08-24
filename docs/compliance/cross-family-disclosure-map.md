---
title: "Cross-Family Disclosure Map"
schema_type: planning
status: draft
owner: core-maintainer
purpose: "One record of every surface on which data about a child reaches an actor outside that child's family, naming for each surface the actor's capacity, the authorization gate that admits it, the fields that cross, and the COPPA question it raises; the adult-originated counterpart to the child-origin dataflow matrix."
tags:
  - compliance
  - privacy
  - security
component: Development-Tools
source: "Direct review of src/cyo_adventure/api/ (all routers), src/cyo_adventure/api/deps.py, src/cyo_adventure/api/personalization.py, src/cyo_adventure/db/models.py, re-verified line by line at commit 56728e96 (2026-08-11) after an initial compilation at d0613a87 (v0.70.0, 2026-08-09), extending docs/compliance/child-origin-dataflow-matrix.md (v2.0) to the adult-originated surfaces that document's scope excludes, and reading against docs/planning/adr/adr-016-recommendation-sharing-social-boundary.md, adr-018-childrens-privacy-compliance.md, adr-022 (RLS tiering), adr-023 (personalization)"
---

> **Status**: Draft | **Version**: 1.2 | **Compiled**: 2026-08-09 | **Updated**: 2026-08-11
> **Code reviewed at**: commit `56728e96` on `main`, the commit this branch is rebased onto.
> v1.0 was compiled against `d0613a87` (`chore(release): v0.70.0 (#660)`); every citation below
> was re-derived against `56728e96` for v1.2, so no pointer in this document resolves against the
> older commit only.
> **Scope**: every FastAPI route in `src/cyo_adventure/api/` whose authorization allows a
> caller to receive data about a child who is not in the caller's own family.
>
> **Revision history**
>
> - **v1.2, 2026-08-11**: re-derived every crossing from the `is_admin` authorization capability
>   rather than from route names. That corrected Section 5, six of whose seven negative claims were
>   false (see the note there), and added eight surfaces as Sections 3.11 to 3.18, including two
>   credential-minting surfaces more severe than anything v1.1 listed. Re-pinned all citations,
>   correcting fifteen line shifts and two that pointed at the wrong construct. Marked Section 2.1's
>   legal consequences **OPEN** and restored CFD-1 to Critical, per Section 7 item 1.
> - **v1.1, 2026-08-09**: recorded the owner ruling on CFD-1 in Section 2.1.
> - **v1.0, 2026-08-09**: initial compilation.

## 0. Important disclaimer

This is an engineering-derived record, not legal advice. It states what the code does and names the
legal question each behaviour raises; it does not answer those questions. Every classification below
marked **OPEN** is a question for counsel, not a conclusion this document reaches.

## 1. Why this document exists separately

[`child-origin-dataflow-matrix.md`](child-origin-dataflow-matrix.md) traces ten events **a child
triggers**. That scoping is deliberate and correct for its purpose, and it means exactly one event
**that a child triggers** carries data across a family boundary (Event 9, ring-2 recommendations).
Every other cross-family path in this application is **adult-originated**: an admin opens a review
queue, a guardian consents to a family connection, an admin creates a profile in another family.
Several of those paths read the same records a child's own events write, so the "one of ten" count
is a statement about who triggers a crossing, not about how many crossings exist. Those paths carry
child data across the same boundary, and no existing document enumerates them.

**Why this document is still needed after the 2026-08-10 VPC ruling.** As originally written, this
section argued that the disclosure question was upstream of the consent-method question: under
16 CFR 312.5(b)(2) the **email-plus** method is available only to an operator that makes no
disclosure of children's personal information to third parties, so whether Section 3 constitutes
third-party disclosure appeared to determine which verifiable parental consent methods were
available to this product at all.

That framing is superseded. ADR-018's owner ruling of 2026-08-10 makes **KWS card or debit
verification the sole VPC method**, and records that "the § 312.2 'disclose' analysis leaves the VPC
critical path... 312.5(b)(2)(ii) carries no no-disclosure condition, so a card-only route does not
turn on whether a child's free-text story wish reaching a third-party classifier is disclosure."
The email-plus argument in Section 2.1 is retained as decision history, not as a live constraint.

The enumeration below survives that ruling because four consumers of it do not depend on the
consent-method question at all:

1. the **312.4(c)(1) direct notice**, which must name the categories of recipient, whatever
   verification method admitted the parent;
2. the **records of processing activities** and the processor and GDPR track, which ADR-018
   explicitly keeps live for its own reasons;
3. the **counsel engagement brief**, to which Sections 2.1 and 7 are named inputs; and
4. **data minimization review**, which needs to know what actually crosses regardless of how it
   is characterized.

So the disclosure question is no longer upstream of consent; it remains upstream of notice,
minimization, and the vendor track.

## 2. The boundary, and the two capacities that cross it

A "family boundary crossing" here means: an authenticated actor receives a field describing a
`ChildProfile` whose `family_id` differs from the actor's own `family_id`.

Two mechanisms produce a crossing, and they are legally different:

**The admin capability.** `Principal.is_admin` is an orthogonal boolean, not a role. `deps.py:142`
declares it; the invariants at `deps.py:157-171` force `Role.ADMIN` to imply `is_admin=True` while
leaving `Role.GUARDIAN` free to carry it. One adult can therefore be a guardian of their own family
**and** an admin over every other family at the same time. `deps.py:184-202` (`acting_role`) is the
only place that distinguishes the two capacities: a dual-role adult acting outside their own family
is stamped `admin`. It is used mostly for the audit stamp, and **almost every** admin surface
authorizes on the bare `is_admin` boolean instead. There is exactly one exception, and it is
instructive: `library.py:606` gates on `acting_role(book.family_id) != Role.ADMIN`, and the comment
there explains that a bare `is_admin` test would have fired "for exactly one population, the
dual-role adult acting on their OWN family, silently exempting the very people this gate protects."
That is the whole argument for CFD-7 in one line, written by the code.

**Two enforcement layers, not one.** The bypasses enumerated in Section 3 are application-layer:
a router wraps an ownership check in `if not principal.is_admin:`. Neither `authorize_profile`
(`deps.py:919-931`) nor `authorize_family` (`deps.py:941-952`) contains an admin bypass of its own,
so every crossing below is a deliberate, greppable choice at a call site rather than a property of
the helpers. Underneath that sits a second, database-layer bypass: `require_principal` calls
`apply_family_rls_context(session, family_id=..., is_admin=principal.is_admin)`
(`deps.py:698-700`), setting the Postgres GUCs that back the ADR-022 Tier-1 policies, whose
predicate is satisfied by the `app.is_admin` disjunct alone. None of the routes audited here rely
on RLS to stop an admin, so this substrate changes no conclusion below. It matters because it is
what makes a *newly written* query cross-family by default: at the application layer a missing
check is a bug, and at the data layer it is the configured behaviour.

**Consented family connections.** `FamilyConnection` rows are created by an admin
(`POST /api/v1/admin/family-connections`) and become active only when both guardians
consent (ADR-016's dual-guardian rule, `_is_dual_consented` at `recommendations.py:250-253`). These are
consumer-to-consumer crossings: no operator capacity is involved.

### 2.1 The capacity question, and the owner's ruling

Every classification in Section 3 turns on one question:

> **Is the admin capability held only by the operator's own personnel, or can it be delegated to a
> guardian who is a customer rather than staff?**

**Owner ruling, 2026-08-09: the admin capability is internal only. An admin is the operator's own
personnel and is never a third party.** The capability is not, and will not be, delegated to a
guardian acting as a customer.

**The ruling is a statement of operational fact, not a legal conclusion.** It settles who staffs
the admin role. It does not, by itself, settle how the law characterizes a role staffed that way,
and Section 7 item 1 records the specific reason it may not: the operator here is a sole individual
who is simultaneously a customer of the product. Each consequence below therefore follows *if* the
operator-personnel characterization holds on the facts, and each is marked **OPEN** for counsel
under the Section 0 disclaimer rather than asserted by this document.

Consequences, which would apply to every surface in Section 3:

- **OPEN**: whether Section 3 is **not third-party disclosure**, on the theory that it is the
  operator processing data it collected, covered by the operator's own processing plus "support for
  the internal operations of the website or online service" (16 CFR 312.2) where an
  internal-operations characterization is needed at all.
- **OPEN**: whether the amended Rule's **separate consent for non-integral third-party disclosure**
  obligation therefore does not attach on account of the admin surfaces.
- **OPEN**: whether the direct notice under 312.4(c)(1) need not name an admin recipient category,
  on the theory that there is no external recipient here to name. Note that this is the consequence
  with the nearest deadline, because the direct notice is user-facing text that ships.
- **OPEN**: whether Section 3 places no constraint of its own on which consent methods are
  available. Superseded in practical effect by ADR-018's 2026-08-10 ruling (see Section 1): the
  consent method is now KWS card or debit regardless of how this question resolves.

**What the ruling does not do (retained as decision history).** The analysis below was written
before ADR-018's 2026-08-10 ruling put KWS card or debit verification on the critical path and took
email-plus off it. It is preserved rather than deleted because the two grounds it identifies are
real disclosures that still matter for notice, minimization, and the processor track; only their
bearing on *consent method* lapsed.

The reasoning as it stood: the ruling does not make email-plus available, because email-plus under
312.5(b)(2) is conditioned on the operator making no disclosure of children's personal information
to third parties **at all**, and two independent grounds already foreclose it, neither of which
involves the admin capability:

1. **Third-party processors.** A child's free-text story wish reaches external classifiers and
   model providers. The child-origin dataflow matrix establishes at least one confirmed adverse
   case: the Google Perspective request sets no `doNotStore` field, so the content is usable for
   the vendor's own model building, which defeats the internal-operations characterization for that
   vendor specifically (matrix sections at lines 186-207 and 828-833; code fix tracked as issue
   **#659**). A second, **unverified in this pass**, is that the Anthropic direct leg may sit
   outside the OpenRouter zero-data-retention guardrail; that claim carries no citation here and is
   tracked as CFD-8 rather than relied on.
2. **Consumer-to-consumer ring-2 flows.** Section 4 discloses a child's real `display_name` to
   another household. Another family is a third party regardless of how the admin capability is
   staffed.

So the ruling **simplifies** the analysis and removes an open architectural question. It did not
change the consent-method conclusion at the time; ADR-018 subsequently changed it on other grounds.

**What still needs to happen, and why it is now smaller.** The ruling is a statement about how the
product is operated. The code does not yet enforce it: `Principal.is_admin` can be set on any
guardian's `User` row, and `POST /api/v1/admin/users` (`admin_users.py:264`) is a live route for
creating adults. The code's own comments already assume the ruling (`approval.py:108` calls the
admin "the backend safety-review operator"), so what remains is to make an asserted operational
fact into an enforced invariant, which is ordinary work rather than an open question. Until it is
enforced, the ruling is a policy that a future configuration change could silently falsify, and it
would falsify a compliance premise rather than merely a design intent. See Section 6, item CFD-1.

## 3. Operator-capacity crossings (the admin capability)

Eighteen surfaces, in two groups.

**Sections 3.1 to 3.10** were derived by walking the routes that name themselves admin routes, and
are ordered among themselves by sensitivity of the field set rather than by route path.

**Sections 3.11 to 3.18** were derived differently, and the difference is the point. v1.2 re-walked
the crossings from the authorization capability instead: `is_admin` appears 124 times across 29 of
the 36 routers, and nine of those are bypasses that skip an ownership or family check.

> **Inventory note, 2026-08-14.** The denominator has since moved: the app wires **37** distinct
> routers, not 36. `api/consent.py` (ADR-018 D1, the browser-facing KWS verification start) landed
> after this walk. The finding above is left exactly as derived rather than renumbered, because
> re-spelling a denominator would imply the new router was walked when it was not. It does not need
> to be for the conclusion to hold: `consent.py` contains **zero** `is_admin` references, so it is
> neither one of the 29 nor one of the nine bypasses. Re-verified 2026-08-14 that
> `grep -c is_admin src/cyo_adventure/api/*.py` still totals 124 matching lines across 29 files, so
> the numerator and the reference count are both unchanged. Note that those 29 files include
> `deps.py`, `review_surface.py`, and `schemas.py`, which define no router: "29 of the 36 routers"
> is 29 *files under `api/`*, three of which are support modules. Eight of the
resulting surfaces appear in no `/admin/` route name at all. They are ordinary endpoints, several of
which a guardian's own app calls in normal use, that widen for an admin caller in one inline
condition. That is why the first pass missed them, and why Section 5's negative claims were wrong
(see the note there).

**Read the two groups as one ranked list only with care.** The appended group is ordered internally,
but the single most severe surface in this document is **Section 3.11**, not Section 3.1: it hands
the caller a credential rather than a projection. The numbering is append-only so that citations to
3.1 through 3.10 from other documents keep resolving; the ranking is stated here instead.

### 3.1 `GET /api/v1/admin/story-requests` (highest sensitivity: free text)

`story_requests.py:827-868`. Global across every family; `family_id` is an optional **filter**, not
a scope (`story_requests.py:863-864`).

| Field | Source | Notes |
| --- | --- | --- |
| `request_text` | `StoryRequest.request_text` | **Free text.** When `initiator_role == "child"` this is the child's own typed story wish, the child-origin matrix's Event 6. Suppressed only for `status == "blocked"` rows (`_to_view`, story_requests.py:240+). |
| `profile_id` | `StoryRequest.profile_id` | Persistent identifier for a specific child. |
| `age_band` | `StoryRequest.age_band` | Age range of a specific child. |
| `interpretation` | `StoryRequest.interpretation` | Derived from the child's text: the interpretation projection specified in [WS-7](../planning/ws7-request-interpretation-design.md), serving capability `K19`. |
| `initiator_role` | `StoryRequest.initiator_role` | Reveals *that a child* authored the text. |
| `proposed_series_title` | `StoryRequest.proposed_series_title` | Free text; suppressed for blocked rows. |
| `moderation_flags` | `StoryRequest.moderation_flags` | Admins get **every** well-formed flag, unfiltered by the age-band threshold (`surface_all=True`, story_requests.py:867). |

This is the most sensitive cross-family surface in the application: free text authored by a child,
attached to that child's persistent identifier and age band, readable by an adult in a different
family. It is also the surface the admin console's request queue actually reads, so it is exercised
in normal operation rather than being a theoretical capability.

Note the deliberate separation the code already maintains: the guardian-facing
`GET /api/v1/story-requests` is **family-scoped for every caller including admins**
(`story_requests.py:791-797`), so holding the admin capability never silently widens a dual-role
adult's everyday list. The global scope is an explicit, separate route. That is the right pattern,
and CFD-10 in Section 6 recommends generalizing it: most of the crossings below widen an
otherwise family-scoped route inline instead, which is what made them hard to enumerate.

### 3.2 `GET /api/v1/admin/audit` (second free-text channel, and the least bounded)

`audit.py:244`. Global over `pipeline_event`, filterable by `profile_id`, `actor_id`,
`storybook_id`, `kind`, and time.

The projection includes **`payload=row.payload`** verbatim (`audit.py:335`): the raw stored event
dictionary, with no field allowlist and no redaction. Per the child-origin matrix's cross-cutting
section, `pipeline_event` receives Events 4, 5, and 6, and Event 6 is the child's free-text story
wish.

This route is therefore a **second, unbounded egress path for child free text** that does not appear
in any prior document, because it is adult-originated and thus outside the child-origin matrix's
scope. Its risk profile is worse than 3.1 in one specific way: 3.1 projects a fixed, reviewed field
list, so adding a column to `StoryRequest` does not silently widen it. `payload` is a
`dict[str, object]` pass-through, so **any future event writer that adds a field to a payload widens this
surface with no code change here and no review signal**.

`GET /api/v1/admin/audit` is nonetheless the surface that answers "who did what to child-linked
data" (capability `A13` in the [capability register](../planning/capability-register.md)) and is
itself a compliance control. The recommendation in Section 6 is a
payload field allowlist, not removal.

### 3.3 `GET /api/v1/admin/profiles` (broadest identity surface)

`admin_profiles.py:170`, projected by `_view` at `admin_profiles.py:141-167`.

Returns, for **every child in every family**: `id`, `family_id`, `display_name` (the child's real
first name in the common case), `age_band`, `reading_level_cap`, `avatar`, `tts_enabled`,
`reduce_motion`, `has_pin`, `status`, `created_at`.

`display_name` is the single field the codebase treats as most sensitive elsewhere: it renders
directly into a child's own story prose and carries a denylist gate at every write point
(`profiles.py:233-270`). This route is where it crosses the family boundary in bulk.

`reading_level_cap` and `tts_enabled`/`reduce_motion` warrant separate mention: a reading level
materially below the age band, combined with text-to-speech and reduced motion, is a reasonable
proxy for a **disability or learning difference**. Under GDPR that is special-category data (Art.
9); under COPPA it is ordinary personal information but is exactly the kind of inference a
data-minimization review should catch. Nothing in the admin console's stated purpose requires
accessibility settings to be cross-family readable.

### 3.4 `POST` and `PATCH /api/v1/admin/profiles` (cross-family write)

`admin_profiles.py:223` and `admin_profiles.py:313`. Same field set, written rather than read, into
an arbitrary family.

**Correcting a prior note:** an earlier working note recorded that `create_admin_profile` skips the
consent check. It does not. `_require_family_consent` (`admin_profiles.py:68-138`) queries the
**target** family for any non-child `User` with `consent_accepted_at IS NOT NULL` and raises
`BusinessLogicError(rule="vpc_required")` otherwise; it is called at `admin_profiles.py:251`,
ordered deliberately after the family 404 so a caller naming a nonexistent family learns that rather
than being told about a vacuously absent consent record. Both admin write points also run
`validate_display_name` (`admin_profiles.py:252`, `admin_profiles.py:296`).

The gate reads any non-`child` role, not only `guardian`, which is correct: an adult holding the
admin base role can still be the parent of their own family, and a guardian-only gate would lock
such a family out while adding no protection.

**The gate has a second leg, added after this document's first compilation** (PR #681, ADR-018 D1),
and it changes what the first leg means. When `settings.kws_verification_required` is on, a recorded
consent is no longer sufficient: `has_usable_verification` must also return true for one of the
adults who actually consented, or the write is refused with
`BusinessLogicError(rule="vpc_verification_required")` (`admin_profiles.py:131-138`). The scoping is
the load-bearing detail. The verification set is intersected with the consented set rather than
taken over the family's adults generally, so a verification by an adult who never consented does not
satisfy it. **The flag defaults to off**, so on a default deployment this route still admits a
cross-family child-profile write on a recorded consent alone, with no verification behind it. That
is a configuration state, not a code gap, and it is the state that governs today.

### 3.5 Review surface, approval transitions, and node edit (full story text)

- `GET` review surface: `approval.py::_load_review_target`
  (`approval.py:206-248`) plus
  `review_surface.py`
- Transitions: submit / approve / send-back / archive via `_load_admin_story`
  (`approval.py:96-130`), admin-only, globally scoped,
  `SELECT ... FOR UPDATE`
- `node_edit.py` cross-family edit, gated at
  `node_edit.py:164` and
  `node_edit.py:178`

These carry the **full text of an unpublished story generated from another family's child's
request**. The comment at `approval.py:105-109` states the design plainly: `authorize_family` is
intentionally not called because admin authority is cross-family, this being the backend
safety-review function. That review is the ADR-005 mandatory human approval gate, so the crossing is
not incidental; it is the product's central safety control.

**Protective architectural finding, load-bearing for the whole analysis.** Personalized story prose
does **not** contain real child names at rest. Personalization values are resolved by a separate
route, `GET /api/v1/storybooks/{storybook_id}/personalization-values` (`personalization.py:1359`),
which returns a `values` map plus a `sentinel_pattern` (`personalization.py:185`) for the **client**
to substitute at read time. The stored storybook version therefore holds sentinels, and a
cross-family reviewer reading the review surface sees placeholders, not `ChildProfile.display_name`.

This is a genuine privacy-by-design property and should be recorded as such rather than left as an
implementation accident. It means the operator's mandatory human review runs on content that is
de-identified with respect to the personalization channel. Note what this pass actually established:
the citations above are on the **read** path, showing that resolution happens client-side against a
sentinel pattern. That the **stored** version therefore holds only sentinels is an inference from
the absence of a server-side substitution step, not something a citation here demonstrates
positively. CFD-5 in Section 6 is the recommendation to pin it with a test, so a future change that
bakes values into stored prose fails loudly instead of quietly falsifying this paragraph.

The residual free-text risk on this surface is different and unpinned: a child's `request_text`
(3.1) can itself name the child, and generated prose derived from it can echo that name. The PII
egress guard in 3.6 addresses the LLM leg of that risk but not the human-review leg.

### 3.6 `POST /api/v1/admin/rescreen` and `POST /api/v1/admin/remoderate/{id}/{version}`

`rescreen.py:121`, `remoderate.py:873` (the route) into `remoderate.py:523` (the work).

Cross-family content re-review.

`remoderate.py`, along with `node_edit.py`, loads **the subject family's** child display names
rather than the caller's. `rescreen.py` does **not**, and an earlier revision of this document
said it did. The difference is structural rather than an omission: the names exist to be redacted
out of the review and repair PROMPTS, and a re-screen sweep builds neither. It runs the
deterministic gate and the Stage-0 classifiers only, so it has no prompt to guard and loads no
names; `grep -n ChildProfile src/cyo_adventure/api/rescreen.py src/cyo_adventure/moderation/rescreen.py`
returns nothing. Read the rest of this section as being about `remoderate.py` and `node_edit.py`.

Note that `_family_child_names` is not one shared helper: it is three independent module-private
definitions of the same shape, duplicated deliberately rather than imported
(`remoderate.py:394-398` explains why, citing this codebase's avoidance of cross-module underscore
imports). Three copies of a PII guard is three places a fix has to land, which is worth knowing
before relying on any one of them.

- `node_edit.py:295-312` (docstring is explicit:
  "the story's family, not necessarily the caller's, for the admin cross-family case")
- `remoderate.py:389-437`, the query at `remoderate.py:436`, called at `remoderate.py:626`
- `story_requests.py:112-125`

**Scope, as of 2026-08-24**: `remoderate.py` admits `in_review` storybooks as well as `published`
ones (`REMODERATABLE_STATUSES`). The cross-family read described here therefore now reaches books
that are NOT published and that no guardian has approved. That does not change the disclosure
shape, the same family-scoped names are read into the same in-process guard, but it does widen the
population, and a reader who assumed "re-moderation implies a published book" would be wrong. The
sibling `rescreen.py` remains published-only.

`generation.py:227` runs the same PII egress guard but does **not** belong on that list: the
endpoint is guardian-only (`if not ctx.principal.is_guardian: raise`, `generation.py:216-217`),
it queries `ChildProfile.display_name` inline rather than through the shared helper, and it scopes
that query to `ctx.principal.family_id`, the caller's own family. It is noted here only because an
earlier revision of this document grouped it with the cross-family callers, and a reader checking
that claim should find the correction rather than the claim.

This is a **PII egress guard**: the names are loaded so they can be redacted before the prompt
reaches an LLM provider. It is protective, and it is the right design. It is recorded here because
it is nonetheless a real read of another family's children's real names into the admin's request
process, and a data-flow map that omitted it would be incomplete. The names are not returned to the
caller.

### 3.7 `GET /api/v1/admin/flags`

`flags.py:184-213`, projected by `_to_view` at `flags.py:53-71`.

Every unresolved kid flag across every family: `family_id`, `profile_id`, `storybook_id`, `version`,
`node_id`, `reason`, `created_at`, `resolved_by`, `resolved_at`, `resolution`.

`reason` is a closed `Literal` enum, not free text, matching the child-origin matrix's Event 5
characterization. So this surface crosses **persistent identifiers and a coded reason, with no name
and no free text**: the lowest-sensitivity of the child-linked admin surfaces, and a good model for
what the others could be reduced to.

`POST /api/v1/admin/flags/{flag_id}/resolve` (`flags.py:236`) shares the same admin gate with no
`family_id` check, so the same capability carries a **write** on another family's flag row
(`resolved_by`, `resolved_at`, `resolution`). No child field crosses outward on the write, but the
resolution of a child's safety flag is decided cross-family, which is the ADR-005 operator role
working as designed.

### 3.8 `GET /api/v1/admin/family-connections`

`family_connections.py:80`, returning `FamilyConnectionView` (`schemas.py:2901-2909`): `family_id`,
`family_name`, `connected_family_id`, `connected_family_name`.

Family-level identifiers only. `family_name` is adult-supplied and commonly a surname, so it is
personal information about the household, but it is not child-originated and no child field crosses
here.

### 3.9 `GET /api/v1/admin/moderation/dashboard` and `/suggestions`

`moderation_dashboard.py:59`, `moderation_dashboard.py:119`. Aggregate threshold statistics, both
admin-gated at `moderation_dashboard.py:47-56`.

Field by field, `ModerationDashboardView` carries two lists and nothing else:

| Field | Contents | Child-linked? |
| --- | --- | --- |
| `insights[]` (`CategoryInsightView`) | `age_band`, `category`, `advisory_findings`, `flag_findings`, `decided_versions`, `released_versions`, `override_rate`, `last_seen` | No. Every value is a count, a rate, or a corpus-wide band label. No `profile_id`, no `family_id`, no name, no free text. |
| `recent_changes[]` (`ThresholdChangeView`) | `occurred_at`, `event_type`, `entity_id`, `payload` | No, but structurally by allowlist rather than by projection. See below. |

`GET /admin/moderation/suggestions` is narrower still: `SuggestionListView` carries the two policy
constants plus per-suggestion `age_band`, `category`, current and suggested verdicts and scores, and
the same three counts. Nothing per-child.

**The one thing worth recording is `recent_changes[].payload`**, which is `PipelineEvent.payload`
passed straight through with no field allowlist, the same `dict[str, object]` shape that makes
Section 3.2's audit surface the least bounded one in this document. Here it is bounded, but only by
an `event_type` filter narrowing the query to `THRESHOLD_CHANGED` and `NOISE_FLOOR_CHANGED`
(`moderation_dashboard.py:78-91`), both of which are written by admin threshold changes rather than
by anything a child touches. The code says so itself: the comment at `moderation_dashboard.py:70-76`
names that filter as "the only boundary keeping non-admin-authored payloads out of the response" and
requires revisiting payload exposure before any new `event_type` is added. That is the correct
control, and it means the safety of this surface rests on a query predicate that a future feature
could widen in one line, not on the response model.

A separate re-check is owed **if** the dashboard later gains per-version drill-down, which would
change the projection rather than merely the confidence in it.

### 3.10 `GET`, `POST`, `PATCH /api/v1/admin/users`

`admin_users.py:213`, `admin_users.py:264`, `admin_users.py:370`. Adult accounts across families.
Adult data, outside COPPA's child scope, but it is the route through which the admin capability
itself is granted, which makes it the control point for Section 2.1.

### 3.11 `POST /api/v1/child-sessions` (the most severe surface in this document)

`child_sessions.py:60`. Admitted by the role gate at `child_sessions.py:95-100`, which names
`is_admin` alongside `is_guardian` and `Role.DEVICE`; the ownership check is then skipped at
`child_sessions.py:114` (`if not ctx.principal.is_admin and ctx.principal.role is not Role.DEVICE:`
guarding `authorize_profile`). The comment above it states the design: "an admin is global and skips
the ownership check by design".

**What crosses is not a field, it is a credential.** The response (`ChildSessionView`) carries a
signed, short-lived session `token` scoped to the named `profile_id`. An admin naming any child in
any family receives a bearer token that authenticates **as that child** for its lifetime: reading
state, choice submission, and every other child-scoped route accept it through `require_principal`'s
child-session branch. The endpoint will also JIT-provision the child's `User` row if none exists.

Every other crossing in this document is a projection: the operator sees some fields. This one is an
impersonation capability, and the distinction matters legally as well as technically, because
"access for internal operations" and "the ability to act as the data subject" are not the same
claim. It is recorded as CFD-11.

This surface is genuinely necessary for the guardian and device flows it primarily serves; the
finding is not that it exists but that its admin leg was undocumented and is unbounded.

### 3.12 `POST /api/v1/device-grants` (durable credential mint, chains into 3.11)

`device_grants.py:50`, with the admin branch resolved in `_resolve_target_family` at
`device_grants.py:178` (`if not ctx.principal.is_admin: raise ...`, so everything past that raise is
the admin path: accept an arbitrary caller-supplied `family_id` and return it).

Mints a durable `DeviceGrant` token (`DeviceGrantView.token`) for an **admin-named family**. The
grant authenticates a `Role.DEVICE` principal for that family, which `child_sessions.py`'s device
branch then accepts as an input to 3.11.

The two compose: an admin can mint a durable credential for a family they were never a guardian of,
and that credential mints child-session tokens within it. Neither step requires a
`FamilyConnection`, a consent record, or an audit-stamped review action. Recorded as CFD-11
alongside 3.11, because a recommendation that addressed only one of the two would leave the chain
intact.

### 3.13 `GET /api/v1/storybooks/{storybook_id}/versions/{version}` (full story blob, including drafts)

`library.py:528`. Three separate widenings, at `library.py:565`, `library.py:571`, and
`library.py:606`.

Section 3.5 covers the *review* path into story text (the review surface, approval transitions, node
edit). This is a different route to the same content, and a plainer one:

| Line | Gate skipped for an admin | Consequence |
| --- | --- | --- |
| `library.py:565` | `authorize_family(principal, book.family_id)`, for a non-catalog book | Any family's book, not just catalog-visible ones. |
| `library.py:571` | published / current-version / `approved_by is not None` | An **unpublished, unapproved draft** version is readable. |
| `library.py:606` | the `StorybookAssignment` plus age-band check | A book assigned to no profile the caller controls is readable. |

What crosses is `version_row.blob`: the full story text, node graph, and choices. Distinct from 3.5
in that there is no `SELECT ... FOR UPDATE`, no state transition, and no audit-stamped review
action; it is a plain content `GET`. An admin does not have to enter the review workflow to reach
arbitrary-family story content.

Note that `library.py:606` is the one authorization site in the codebase that gates on `acting_role`
rather than on raw `is_admin`, deliberately, so that a dual-role adult is held to the assignment
gate inside their own family. That is the correct pattern and the basis for CFD-7.

### 3.14 `GET /api/v1/reading-history/{profile_id}`

`reading_history.py:251`, widened at `reading_history.py:281` (`if not principal.is_admin:` guarding
`authorize_profile(principal, parsed)`). The comment there cites the capability register's "admin
any" spec, so this is intended behaviour, not an oversight.

Crossing, for a `profile_id` in any family the admin names: the `ending_id`s that child has found,
`Completion.found_at` timestamps, `ReadingState` (`node_id`, accumulated `choices`, version), and
the joined `Storybook` and `StorybookVersion` titles.

This is a strict superset of Section 3.7's sensitivity class. Section 3.7 crosses a persistent
identifier plus a coded enum; this crosses a persistent identifier plus a behavioural record of what
one specific child read, when, and which choices they made. A reading history is a profile of a
child's interests over time, which is why it sits above the two narrow surfaces below it.

### 3.15 `GET /api/v1/recommendations/{profile_id}`, the admin-capacity leg

`recommendations.py:256`, widened at `recommendations.py:284` (`if not principal.is_admin:` guarding
`authorize_profile`).

Section 4.1 analyzes this file for its ring-2 consumer-to-consumer flow, which is gated on a
dual-consented `FamilyConnection`. **This is a separate and more direct crossing in the same file**,
and it is not gated on any connection at all. An admin names an arbitrary `profile_id`; the handler
derives `family_id` from that profile row and then serves the ring-1 recommendation set for that
family as though the caller were a guardian of it. Ring-1 `recommender_name` is a **sibling's**
`display_name`, so a real child's first name crosses, sourced from a family the caller holds no
connection with.

The ADR-016 three-ring boundary that Section 4 is built around is a consent construct. It does not
bind the operator capacity, and this route is where that is most visible.

### 3.16 `GET /api/v1/storybooks/{storybook_id}/content-summary`

`assignments.py:211`, widened at `assignments.py:188` (`if not ctx.principal.is_admin and
book.visibility != Visibility.CATALOG.value:` guarding `authorize_family`).

Crossing: the story's flagged-content gating summary, total flagged count, and story-level validator
note aggregate, for any family's non-catalog book.

**No child field crosses here**: no `display_name`, no `profile_id`, no child identifier. This is
book-level content-moderation metadata. It is recorded because Section 5 previously asserted that
`assignments.py` does not cross at all, which is false; the rest of that file holds up, since
`assign_storybook` and `unassign_storybook` use a bare `authorize_profile` with no admin exemption
and `list_assignments` scopes to the caller's own `family_id`.

### 3.17 Cover-art admin surface

`covers.py:46`, `covers.py:175`, `covers.py:209`: `_require_admin` on `request_cover`,
`cover_status`, and `approve_cover`.

An admin requests, polls, and approves AI-generated cover art for any family's storybook version,
including `pending_review` covers withheld from every child's library card. Crossing: a presigned
image URL and approval provenance. Book-level, not child PII.

The mechanism is worth stating precisely, because Section 5 previously described this file as
keying on `family_id` or `authorize_profile`. It does neither. There is no family-scoping construct
in the file at all, so there is nothing here for `is_admin` to bypass; the route is simply global by
construction. A negative claim that names the wrong mechanism is worse than no claim, because it
tells the next reader the check exists.

### 3.18 `POST /api/v1/admin/generation-jobs/{job_id}/force-fail`

`generation.py:514`, gated at `generation.py:546`. Admin-only, with no `family_id` or
`authorize_family` check, force-failing any family's stuck `GenerationJob`.

A write capability on the generation pipeline (`GenerationJob.status`, `.error`), not a read of
child-identifying fields. Recorded for completeness and for the contrast: `get_generation_job`
immediately above it (`generation.py:430`, the `authorize_family` call at `generation.py:469`) calls `authorize_family` **unconditionally**, with no
admin exemption, and uses `is_admin` only to gate report visibility within the caller's own family
(`generation.py:501`). Two adjacent handlers in one file, one scoped and one global, is the pattern
CFD-10 is about.

## 4. Consumer-to-consumer crossings (family to family, no operator capacity)

These are the crossings the child-origin matrix classifies as carrying "their own, separate consent
bar rather than riding on D1". All three are gated on a dual-consented `FamilyConnection`; the
first two carry child data across the boundary, and the third (Section 4.3) exposes only the
connection's own existence and the adult counterparty.

### 4.1 Ring-2 recommendations

`recommendations.py:365-380`. For a `ring == "connection"` item, `recommender_name` is set to
`rater.display_name`: **the other family's child's real name**, paired with a book title and a star
rating.

This is the child-origin matrix's Event 9, already classified there as a consumer-to-consumer
disclosure under 312.5(a) with prospective-only revocation. Nothing in this pass changes that
classification; it is repeated here so this document is complete on its own terms.

### 4.2 Ring-2 personalization (ADR-023)

`personalization.py:1104-1169` (`_ring2_values`), reached through
`GET /api/v1/storybooks/{storybook_id}/personalization-values`.

A sharer-family child's `display_name` and up to eleven further slot values are rendered into a
viewer child's story in a **connected** family. This is the most personal cross-family flow in the
product, and it is also, by a wide margin, the best-governed one. The predicates, all of which must
hold:

1. an active `FamilyConnection` with both guardians consented;
2. `subject.real_name_ring2_enabled` for the name slot specifically
   (`personalization.py:1133`);
3. a live `ChildProfilePersonalizationConsent` for that subject and that connection;
4. the specific `slot_type` present in `consent.covered_slot_types`
   (`personalization.py:1128-1142`);
5. the slot not in `_RING2_EXCLUDED_SLOT_TYPES`;
6. `_is_live(profile)`: neither deactivated nor Article-18 processing-restricted
   (`personalization.py:921-933`);
7. for a sibling slot, the named sibling must additionally be in the sharer's own family, be live,
   have `real_name_ring2_enabled`, and have its own live consent covering the name slot
   (`personalization.py:1040-1101`).

The consent record carries `consent_policy_version`, and the code returns it **alongside** the
values rather than re-querying, explicitly to close a TOCTOU window where a consent revoked between
two reads could be misreported as needing no consent (`personalization.py:1114-1123`). Per-slot
failures omit that slot individually rather than failing the payload, and the universal empty
payload (`_empty_values_view`, personalization.py:163-188) is byte-identical across every predicate
failure so nothing about the existence of a book, subject, connection, or consent is observable.

**This is the architecture the rest of the consent work should be measured against.** It is already
a per-recipient, per-field, versioned, revocable consent ledger with a non-observable denial path.
The COPPA VPC design under discussion needs the same shape at the account level, and this is in-repo
prior art rather than a greenfield design.

### 4.3 `GET /api/v1/family-connections/mine`

`family_connections.py:413`, returning `FamilyConnectionMineItem` (`schemas.py:2933-2949`):
`counterpart_family_id`, `counterpart_family_name`, `direction`, `my_consent`, `active`.

Family-level only. Deliberately narrower than the admin view (the docstring at
`schemas.py:2927-2930` says so: "the caller's own family's side of each directional connection it
touches, never the full admin view"). No child field crosses at connection-management time; a
guardian consenting to a connection is consenting before knowing which children are on the other
side.

## 5. Surfaces verified as NOT crossing the boundary

Recorded so a future reader does not have to re-derive the negative. Each row names the specific
construct that does the scoping, because a negative claim is only as good as its mechanism.

> **Correction, v1.2.** v1.1 closed this section with a single row asserting that seven files
> (`offline_downloads.py`, `reading_history.py`, `assignments.py`, `library.py`, `child_sessions.py`,
> `device_grants.py`, `covers.py`) key their reads on the caller's `family_id` or an
> `authorize_profile` check. **Six of the seven were false.** They are now Sections 3.13, 3.14,
> 3.16, and 3.17, plus the two credential-minting surfaces at 3.11 and 3.12. Only
> `offline_downloads.py` survives, and it is listed on its own below with the evidence spelled out.
>
> This was not drift. The code has not changed on those paths since v1.0 was compiled; the row was
> wrong when written. The cause is worth recording because it is a reusable failure mode: v1.0
> enumerated crossings by reading route names, and `is_admin` is an orthogonal boolean rather than a
> role, so a route reads as family-scoped and still admits a global operator through one inline
> condition. Deriving the list from the authorization capability instead surfaced 124 `is_admin`
> references across 29 of the 36 routers (denominator as at v1.2; it is 37 today, see the inventory
> note in Section 3's preamble, and the added router carries no `is_admin` so this holds), of which
> nine are ownership-check bypasses. **A negative
> claim about authorization has to be derived from the authorization, not from the route name.**
> That is also why the rows below now cite a construct each rather than sharing one summary line.

| Surface | Scoping evidence |
| --- | --- |
| `GET /api/v1/story-requests` | Family-scoped for **every** caller including admins (`story_requests.py:791-797`); a child token is further narrowed to its own `profile_ids`. |
| `GET /api/v1/notifications` | Guardian-only and family-scoped; **explicitly rejects an admin-only adult** because `Principal.family_id` has no guardian meaning for one (`notifications.py:180-200`). |
| `GET /api/v1/families/me/budget` | `ctx.principal.family_id`, guardian-or-admin, own family only (`story_requests.py:905-943`). |
| `GET /api/v1/me` export | Own family only; this is the 312.6 parental review mechanism, and it correctly includes tombstoned personalization rows and per-slot ring flags (`me.py:112-268`). |
| `GET /api/v1/profiles` | `_view` at `profiles.py:97-112`, own family. |
| Ring-1 personalization | `_ring1_values` scopes every candidate to `_family_profile_ids(session, subject.family_id)` (`personalization.py:950`, helper at `personalization.py:256-271`); the same set gates the write path (`put_personalization`, `personalization.py:535`), and a sibling reference is re-checked for liveness at render (`personalization.py:1022`). |
| `api/offline_downloads.py` (all three routes) | The only one of the seven files in the v1.1 row that holds. `report_device_download` calls `authorize_profile` with **no** `is_admin` bypass (`offline_downloads.py:73`); `remove_device_download` filters `DeviceDownload.family_id == ctx.principal.family_id` (`offline_downloads.py:175`); `list_device_downloads` admits an admin-only caller at its role gate (`offline_downloads.py:204`) but then queries `DeviceDownload.family_id == ctx.principal.family_id` (`offline_downloads.py:209`), the caller's own id rather than a parameter, so an admin sees only their own family. |
| `POST`, `DELETE /api/v1/assignments` | `assign_storybook` (`assignments.py:251`) and `unassign_storybook` (`assignments.py:378`) call a bare `authorize_profile` with no admin exemption; `list_assignments` (`assignments.py:352`) scopes to `ctx.principal.family_id`. Only the content-summary read in the same file crosses (Section 3.16). |
| `GET /api/v1/generation-jobs/{job_id}` | `authorize_family(ctx.principal, concept.family_id)` runs **unconditionally**, with no admin exemption (`generation.py:469`); `is_admin` appears in this handler only to gate report visibility within the caller's own family (`generation.py:501`). |
| `GET /api/v1/device-grants`, `DELETE /api/v1/device-grants/{id}` | Admin admitted at the role gate (`device_grants.py:221`, `device_grants.py:274`) but the queries scope to the caller's own `family_id`. The mint route in the same file is the crossing (Section 3.12). |
| `GET /api/v1/families/me/reading-summary` | Guardian-or-admin role gate at `reading_history.py:489`, own family only. The per-profile history read in the same file is the crossing (Section 3.14). |

## 6. Findings and recommended work

> **On the `CFD-*` identifiers.** These are local to this document. They are not a registered ID
> namespace: `docs/planning/plan-manifest.toml` declares `uw`, `debt`, `al`, `cap`, and `sq`, and
> `scripts/check_work_linkage.py` only walks `docs/planning/`, so nothing validates a `CFD-*` ID or
> notices when one is dropped. They exist to make the rows in this table citable from a review
> conversation, not to schedule work. Anything here that needs a phase home should be raised as a
> `UW-*` row, and anything that needs a compliance-assurance home should be raised as an `O-*` row
> in the security assurance register, with the `CFD-*` ID cited as the source.

| ID | Finding | Recommendation | Priority |
| --- | --- | --- | --- |
| **CFD-1** | **The owner ruled on 2026-08-09 that the admin capability is internal only, so an admin is operator personnel rather than a third party. The ruling is recorded, not closed** (Section 2.1, Section 7 item 1): it states who staffs the role, and the question of whether an operator-personnel characterization survives when the operator is a sole individual who is also a customer of the product is unanswered. Independently, the code does not enforce the ruling at all: `Principal.is_admin` can be set on any guardian's `User` row, so a configuration change could silently falsify what the ruling treats as a premise. | Record the ruling in an ADR and put the residual legal question to counsel, so Section 2.1 stops carrying an unreviewed classification. Separately, enforce the ruling with a settings-backed allowlist of admin-eligible subjects, checked at `POST /api/v1/admin/users` and at any capability grant, with a test asserting a non-allowlisted subject cannot be granted `is_admin`. | **Critical** (both the legal question and the enforcement are open; the 2026-08-09 ruling narrowed neither) |
| **CFD-2** | `GET /api/v1/admin/audit` projects `payload` as an unfiltered `dict[str, object]` (`audit.py:335`) over an event log that receives child free text. Any future payload field widens the surface with no review signal. | Replace the pass-through with a per-`event_type` field allowlist; unknown keys drop rather than pass. Add a test that a novel payload key does not reach the wire. | **High** |
| **CFD-3** | `GET /api/v1/admin/story-requests` returns child-authored free text plus `profile_id` and `age_band` across families. | Confirm the admin console actually renders `request_text` for triage; if a redacted or interpretation-only view suffices for the queue, project that and fetch full text only on explicit drill-down, so bulk listing is not bulk free-text egress. | **High** |
| **CFD-4** | `GET /api/v1/admin/profiles` returns `reading_level_cap`, `tts_enabled`, `reduce_motion` cross-family; jointly a disability proxy. The same listing also returns every child's `display_name` in bulk across all families (Section 3.3), which is a direct identifier and not merely a proxy. | Drop accessibility and reading-level fields from the admin list projection unless a named admin workflow needs them. `display_name` is not proposed for removal, since an admin cannot triage a profile they cannot name; instead, treat bulk enumeration as the thing to bound, by paginating and audit-logging the listing rather than by widening what each row carries. | **Medium** |
| **CFD-5** | Sentinel-based personalization keeps real names out of stored prose, so cross-family human review runs on de-identified content. This is load-bearing for Section 3.5 but is not pinned by a test. | Add a test asserting no stored `StorybookVersion` content matches a resolved personalization value, and that the review surface returns sentinels. | **Medium** |
| **CFD-6** | The ring-2 personalization consent model (per-recipient, per-slot, versioned, revocable, non-observable denial) is exactly the shape the account-level VPC consent ledger needs. Section 4.2 of this document describes it, but nothing in the VPC design track points at it, so the VPC work is at risk of designing a second consent ledger from scratch. | Cite `_ring2_values` and `ChildProfilePersonalizationConsent` from the VPC design in ADR-018 as the in-repo reference implementation, linking to Section 4.2 here. | **Medium** |
| **CFD-7** | `acting_role` (`deps.py:184-202`) distinguishes acting-as-guardian from acting-as-admin, but only one authorization site in the codebase uses it as a gate (`library.py:606`); everywhere else authorization reads the bare `is_admin` boolean. The comment at that one site records why it matters: a raw `is_admin` test exempts the dual-role adult acting inside their **own** family, which is the population the gate exists to hold. So the two concepts already differ in behaviour, and the difference is currently load-bearing in exactly one place. | Route cross-family authorization through `acting_role` wherever the distinction is meaningful, so "acting as admin" is one concept rather than two that can drift, and so the `library.py:606` reasoning does not have to be rediscovered per route. Fold this into the CFD-10 named dependency rather than doing it as a separate sweep. | **Medium** (raised from Low: the dual-role-adult exemption is a real behavioural difference, not a naming preference) |
| **CFD-8** | Section 2.1 records a claim that the Anthropic direct provider leg may sit outside the OpenRouter zero-data-retention guardrail. This document did not verify it, and no citation supports it here; it is retained as decision history because it was part of the reasoning presented to the owner, not because it has been checked. | Verify the retention posture of each configured provider leg against its contract, and record the result in the provider allowlist documentation. Until then, do not rely on the claim in either direction. | **Medium** |
| **CFD-9** | `GET /api/v1/admin/moderation/dashboard` returns `recent_changes[].payload` as an unfiltered `PipelineEvent.payload`, bounded from child-authored content only by the query's `event_type` filter (`moderation_dashboard.py:78-91`), not by the response model. This is CFD-2's defect in a currently-safe configuration: the projection is correct today because of what the filter admits, so adding an `event_type` widens the surface with no change to any view. | Apply the same per-`event_type` payload allowlist CFD-2 recommends, so the two surfaces that expose `PipelineEvent.payload` are bounded by one mechanism. Until then, keep the existing `#CRITICAL` comment's requirement, that widening the filter requires reviewing that event writer's payload first, as a review checklist item rather than a comment. | **Medium** |
| **CFD-10** | Several admin routers repeat the same `if not principal.is_admin` widening inline (Section 3), each with its own comment explaining the bypass. The pattern is correct in each instance and load-bearing in all of them, which means a single omission is invisible: a route that forgets the guard looks exactly like a route that never needed one. | Generalize the check into one named dependency (for example `allow_cross_family`) that every widened route declares explicitly, so cross-family reach becomes greppable and testable as a single concept rather than as a recurring idiom. This is the generalization Section 3.1 refers to. | **High** |
| **CFD-11** | Sections 3.11 and 3.12: an admin can mint a child-session bearer token for any family's child (`child_sessions.py:114`) and a durable device-grant token for any family (`device_grants.py:178`), and the second chains into the first. These are the only crossings in this document that hand the caller a **credential** rather than a projection, so "the operator can see this data" and "the operator can act as this child" are being authorized by the same boolean. Neither surface is audit-stamped as a cross-family action the way the review transitions in Section 3.5 are. | Treat credential minting as a distinct capability from cross-family reads rather than as another `is_admin` branch: require an explicit reason, write a `PipelineEvent` for every admin-capacity mint naming the target `profile_id` and `family_id`, and put the two mint paths behind the CFD-10 named dependency so they cannot be reached by an ordinary `is_admin` check. Then decide separately whether operator-capacity minting is needed at all outside a support workflow. | **Critical** |

## 7. What this document does not answer

1. **Resolved by owner ruling on 2026-08-09, not by this document** (Section 2.1): the admin
   capability is internal only, so Section 3 is operator processing rather than third-party
   disclosure. Counsel should confirm the classification holds on the facts, since the ruling
   is a statement about who staffs the role, and the role's authority is genuinely global. The
   question this document cannot answer is whether an operator-personnel characterization survives
   if the operator is a sole individual who is simultaneously a customer of the product, which is
   the actual configuration today.
2. Whether ring-2 recommendation and personalization consent, as built, satisfies 312.5(a)(2)'s
   separate-consent-for-disclosure option, or whether it is a distinct consumer-to-consumer
   arrangement outside that framework.
3. Whether prospective-only revocation on ring-2 flows meets 312.6's revocation expectations.
4. Whether `reading_level_cap` plus accessibility flags constitutes special-category data under
   GDPR Art. 9 in this context.

## 8. Related documents

- [child-origin-dataflow-matrix.md](child-origin-dataflow-matrix.md): the ten child-originated
  events; Event 9 overlaps with Section 4.1 here.
- [records-of-processing-activities.md](records-of-processing-activities.md)
- [coppa-compliance-audit.md](coppa-compliance-audit.md),
  [coppa-gdpr-remediation-plan.md](coppa-gdpr-remediation-plan.md)
- [counsel-engagement-brief.md](counsel-engagement-brief.md): Section 2.1 and Section 7 are inputs
  to it.
- [privacy-notice.md](privacy-notice.md): the 312.4(c)(1) direct notice whose recipient categories
  depend on how Section 2.1's first **OPEN** item resolves.

ADRs, linked rather than named so the repository link checker covers them:

- [ADR-005](../planning/adr/adr-005-mandatory-human-approval.md): the mandatory human approval gate,
  which is what makes the Section 3.5 crossing a required control rather than an incidental one.
- [ADR-016](../planning/adr/adr-016-recommendation-sharing-social-boundary.md): the three-ring
  boundary.
- [ADR-018](../planning/adr/adr-018-childrens-privacy-compliance.md): children's privacy compliance,
  including the 2026-08-10 VPC ruling that supersedes this document's original Section 1 framing.
- [ADR-022](../planning/adr/adr-022-tiered-rls-scoping.md): tiered RLS scoping.
- [ADR-023](../planning/adr/adr-023-story-personalization-slots.md): story personalization slots,
  the subject of Section 4.2.
