---
title: "Cross-Family Disclosure Map"
schema_type: planning
status: draft
owner: core-maintainer
purpose: "One definitive record of every surface on which data about a child reaches an actor outside that child's family, field by field, with the actor's capacity, the authorization gate, the consent basis, and the COPPA disclosure classification for each; the adult-originated counterpart to the child-origin dataflow matrix."
tags:
  - compliance
  - privacy
  - security
component: Development-Tools
source: "Direct review of src/cyo_adventure/api/ (all routers), src/cyo_adventure/api/deps.py, src/cyo_adventure/api/personalization.py, src/cyo_adventure/db/models.py at commit d0613a87 (v0.70.0, 2026-08-09), extending docs/compliance/child-origin-dataflow-matrix.md (v2.0) to the adult-originated surfaces that document's scope excludes, and reading against docs/planning/adr/adr-016-recommendation-sharing-social-boundary.md, adr-018-childrens-privacy-compliance.md, adr-022 (RLS tiering), adr-023 (personalization)"
---

> **Status**: Draft | **Version**: 1.1 | **Compiled**: 2026-08-09 | **Updated**: 2026-08-09
> (owner ruling on CFD-1 recorded in Section 2.1)
> **Code reviewed at**: commit `d0613a87` (`chore(release): v0.70.0 (#660)`) on `main`
> **Scope**: every FastAPI route in `src/cyo_adventure/api/` whose authorization allows a
> caller to receive data about a child who is not in the caller's own family.

## 0. Important disclaimer

This is an engineering-derived record, not legal advice. It states what the code does and names the
legal question each behaviour raises; it does not answer those questions. Every classification below
marked **OPEN** is a question for counsel, not a conclusion this document reaches.

## 1. Why this document exists separately

[`child-origin-dataflow-matrix.md`](child-origin-dataflow-matrix.md) traces ten events **a child
triggers**. That scoping is deliberate and correct for its purpose, and it means exactly one of its
ten events crosses a family boundary (Event 9, ring-2 recommendations). Every other cross-family
path in this application is **adult-originated**: an admin opens a review queue, a guardian consents
to a family connection, an admin creates a profile in another family. Those paths carry child data
across the same boundary, and no existing document enumerates them.

The gap matters beyond bookkeeping. Under 16 CFR 312.5(b)(2), the **email-plus** consent method is
available only to an operator that makes **no disclosure of children's personal information to third
parties**. Whether the surfaces in Section 3 are "disclosures to third parties" therefore does not
merely determine what has to be written in a privacy notice: it determines which verifiable parental
consent methods are legally available to this product at all. The disclosure question is upstream of
the vendor question.

For the admin surfaces specifically that question is now answered: see the owner ruling in
Section 2.1. Email-plus nonetheless remains unavailable on two independent grounds that the ruling
does not touch, also set out there, so the enumeration below still has to be complete rather than
stopping once the admin question closed.

## 2. The boundary, and the two capacities that cross it

A "family boundary crossing" here means: an authenticated actor receives a field describing a
`ChildProfile` whose `family_id` differs from the actor's own `family_id`.

Two mechanisms produce a crossing, and they are legally different:

**The admin capability.** `Principal.is_admin` is an orthogonal boolean, not a role. `deps.py:142`
declares it; the invariants at `deps.py:157-171` force `Role.ADMIN` to imply `is_admin=True` while
leaving `Role.GUARDIAN` free to carry it. One adult can therefore be a guardian of their own family
**and** an admin over every other family at the same time. `deps.py:184-202` (`acting_role`) is the
only place that distinguishes the two capacities, and it does so **only for the audit stamp**: a
dual-role adult acting outside their own family is stamped `admin`. Authorization itself is not
routed through it; each admin surface checks the bare `is_admin` boolean.

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

Consequences, which apply to every surface in Section 3:

- Section 3 is **not third-party disclosure**. It is the operator processing data it collected, and
  it is covered by the operator's own processing plus "support for the internal operations of the
  website or online service" (16 CFR 312.2) where an internal-operations characterization is needed
  at all.
- The amended Rule's **separate consent for non-integral third-party disclosure** obligation does
  **not** attach on account of the admin surfaces.
- The direct notice under 312.4(c)(1) need not name an admin recipient category, because there is
  no external recipient here to name.
- Section 3 places no constraint of its own on which consent methods are available, including
  email-plus.

**What the ruling does not do.** It does not make email-plus available. Email-plus under
312.5(b)(2) is conditioned on the operator making no disclosure of children's personal information
to third parties **at all**, and two independent grounds already foreclose it, neither of which
involves the admin capability:

1. **Third-party processors.** A child's free-text story wish reaches external classifiers and
   model providers. The child-origin dataflow matrix establishes at least one confirmed adverse
   case: the Google Perspective request sets no `doNotStore` field, so the content is usable for
   the vendor's own model building, which defeats the internal-operations characterization for that
   vendor specifically (matrix sections at lines 186-207 and 828-833; code fix tracked as issue
   **#659**). The Anthropic direct leg sits outside the OpenRouter zero-data-retention guardrail.
2. **Consumer-to-consumer ring-2 flows.** Section 4 discloses a child's real `display_name` to
   another household. Another family is a third party regardless of how the admin capability is
   staffed.

So the ruling **simplifies** the analysis and removes an open architectural question; it does not
change the consent-method conclusion. The vendor comparison stands where it stood.

**What still needs to happen, and why it is now smaller.** The ruling is a statement about how the
product is operated. The code does not yet enforce it: `Principal.is_admin` can be set on any
guardian's `User` row, and `POST /api/v1/admin/users` (`admin_users.py:264`) is a live route for
creating adults. The code's own comments already assume the ruling (`approval.py:108` calls the
admin "the backend safety-review operator"), so what remains is to make an asserted operational
fact into an enforced invariant, which is ordinary work rather than an open question. Until it is
enforced, the ruling is a policy that a future configuration change could silently falsify, and it
would falsify a compliance premise rather than merely a design intent. See Section 6, item CFD-1.

## 3. Operator-capacity crossings (the admin capability)

Ten surfaces. Ordered by sensitivity of the field set, not by route path.

### 3.1 `GET /api/v1/admin/story-requests` (highest sensitivity: free text)

`story_requests.py:827-868`. Global across every family; `family_id` is an optional **filter**, not
a scope (`story_requests.py:863-864`).

| Field | Source | Notes |
| --- | --- | --- |
| `request_text` | `StoryRequest.request_text` | **Free text.** When `initiator_role == "child"` this is the child's own typed story wish, the child-origin matrix's Event 6. Suppressed only for `status == "blocked"` rows (`_to_view`, story_requests.py:240+). |
| `profile_id` | `StoryRequest.profile_id` | Persistent identifier for a specific child. |
| `age_band` | `StoryRequest.age_band` | Age range of a specific child. |
| `interpretation` | `StoryRequest.interpretation` | Derived from the child's text (WS-7 K19 projection). |
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
adult's everyday list. The global scope is an explicit, separate route. That is the right pattern
and Section 6 recommends generalizing it.

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
data" (register A13) and is itself a compliance control. The recommendation in Section 6 is a
payload field allowlist, not removal.

### 3.3 `GET /api/v1/admin/profiles` (broadest identity surface)

`admin_profiles.py:146`, projected by `_view` at `admin_profiles.py:116-142`.

Returns, for **every child in every family**: `id`, `family_id`, `display_name` (the child's real
first name in the common case), `age_band`, `reading_level_cap`, `avatar`, `tts_enabled`,
`reduce_motion`, `has_pin`, `status`, `created_at`.

`display_name` is the single field the codebase treats as most sensitive elsewhere: it renders
directly into a child's own story prose and carries a denylist gate at every write point
(`profiles.py:231-268`). This route is where it crosses the family boundary in bulk.

`reading_level_cap` and `tts_enabled`/`reduce_motion` warrant separate mention: a reading level
materially below the age band, combined with text-to-speech and reduced motion, is a reasonable
proxy for a **disability or learning difference**. Under GDPR that is special-category data (Art.
9); under COPPA it is ordinary personal information but is exactly the kind of inference a
data-minimization review should catch. Nothing in the admin console's stated purpose requires
accessibility settings to be cross-family readable.

### 3.4 `POST` and `PATCH /api/v1/admin/profiles` (cross-family write)

`admin_profiles.py:199` and `admin_profiles.py:289`. Same field set, written rather than read, into
an arbitrary family.

**Correcting a prior note:** an earlier working note recorded that `create_admin_profile` skips the
consent check. At `d0613a87` it does not. `_require_family_consent` (`admin_profiles.py:70-115`)
queries the **target** family for any non-child `User` with `consent_accepted_at IS NOT NULL` and
raises `BusinessLogicError(rule="vpc_required")` otherwise; it is called at `admin_profiles.py:226`,
ordered deliberately after the family 404 so a caller naming a nonexistent family learns that rather
than being told about a vacuously absent consent record. Both admin write points also run
`validate_display_name` (`admin_profiles.py:228`, `admin_profiles.py:272`).

The gate reads any non-`child` role, not only `guardian`, which is correct: an adult holding the
admin base role can still be the parent of their own family, and a guardian-only gate would lock
such a family out while adding no protection.

### 3.5 Review surface, approval transitions, and node edit (full story text)

- `GET` review surface: `approval.py::_load_review_target`
  (`approval.py:203-245`) plus
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
de-identified with respect to the personalization channel. Section 6 recommends pinning it with a
test so a future change that bakes values into stored prose fails loudly.

The residual free-text risk on this surface is different and unpinned: a child's `request_text`
(3.1) can itself name the child, and generated prose derived from it can echo that name. The PII
egress guard in 3.6 addresses the LLM leg of that risk but not the human-review leg.

### 3.6 `POST /api/v1/admin/rescreen` and `POST /api/v1/admin/remoderate/{id}/{version}`

`rescreen.py:121`, `remoderate.py:567`.

Cross-family content re-review. Both, along with `node_edit.py` and `generation.py`, call a
`_family_child_names` helper that loads **the subject family's** child display names:

- `node_edit.py:295-312` (docstring is explicit:
  "the story's family, not necessarily the caller's, for the admin cross-family case")
- `remoderate.py:283`
- `story_requests.py:112-125`
- `generation.py:227`

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

### 3.8 `GET /api/v1/admin/family-connections`

`family_connections.py:80`, returning `FamilyConnectionView` (`schemas.py:2788-2796`): `family_id`,
`family_name`, `connected_family_id`, `connected_family_name`.

Family-level identifiers only. `family_name` is adult-supplied and commonly a surname, so it is
personal information about the household, but it is not child-originated and no child field crosses
here.

### 3.9 `GET /api/v1/admin/moderation/dashboard` and `/suggestions`

`moderation_dashboard.py:59`, `moderation_dashboard.py:119`. Aggregate threshold statistics. No
per-child field identified in this pass; treat as **aggregate-only pending a field-level re-check**
if the dashboard gains drill-down.

### 3.10 `GET`, `POST`, `PATCH /api/v1/admin/users`

`admin_users.py:213`, `admin_users.py:264`, `admin_users.py:370`. Adult accounts across families.
Adult data, outside COPPA's child scope, but it is the route through which the admin capability
itself is granted, which makes it the control point for Section 2.1.

## 4. Consumer-to-consumer crossings (family to family, no operator capacity)

These are the crossings the child-origin matrix classifies as carrying "their own, separate consent
bar rather than riding on D1". Both are gated on a dual-consented `FamilyConnection`.

### 4.1 Ring-2 recommendations

`recommendations.py:365-380`. For a `ring == "connection"` item, `recommender_name` is set to
`rater.display_name`: **the other family's child's real name**, paired with a book title and a star
rating.

This is the child-origin matrix's Event 9, already classified there as a consumer-to-consumer
disclosure under 312.5(a) with prospective-only revocation. Nothing in this pass changes that
classification; it is repeated here so this document is complete on its own terms.

### 4.2 Ring-2 personalization (ADR-023)

`personalization.py:1104-1160` (`_ring2_values`), reached through
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

`family_connections.py:413`, returning `FamilyConnectionMineItem` (`schemas.py:2820-2836`):
`counterpart_family_id`, `counterpart_family_name`, `direction`, `my_consent`, `active`.

Family-level only. Deliberately narrower than the admin view (the docstring at
`schemas.py:2814-2817` says so: "the caller's own family's side of each directional connection it
touches, never the full admin view"). No child field crosses at connection-management time; a
guardian consenting to a connection is consenting before knowing which children are on the other
side.

## 5. Surfaces verified as NOT crossing the boundary

Recorded so a future reader does not have to re-derive the negative.

| Surface | Scoping evidence |
| --- | --- |
| `GET /api/v1/story-requests` | Family-scoped for **every** caller including admins (`story_requests.py:791-797`); a child token is further narrowed to its own `profile_ids`. |
| `GET /api/v1/notifications` | Guardian-only and family-scoped; **explicitly rejects an admin-only adult** because `Principal.family_id` has no guardian meaning for one (`notifications.py:180-200`). |
| `GET /api/v1/families/me/budget` | `ctx.principal.family_id`, guardian-or-admin, own family only (`story_requests.py:905-943`). |
| `GET /api/v1/me` export | Own family only; this is the 312.6 parental review mechanism, and it correctly includes tombstoned personalization rows and per-slot ring flags (`me.py:75-230`). |
| `GET /api/v1/profiles` | `_view` at `profiles.py:95-110`, own family. |
| Ring-1 personalization | `_family_profile_ids(session, subject.family_id)`; sibling references are validated same-family at write time and re-checked at render (`personalization.py:1075-1091`). |
| `api/offline_downloads.py`, `api/reading_history.py`, `api/assignments.py`, `api/library.py`, `api/child_sessions.py`, `api/device_grants.py`, `api/covers.py` | `display_name` and profile reads are keyed on the caller's `family_id` or an `authorize_profile` check. |

## 6. Findings and recommended work

| ID | Finding | Recommendation | Priority |
| --- | --- | --- | --- |
| **CFD-1** | **RULED 2026-08-09 (owner): the admin capability is internal only; an admin is operator personnel, never a third party.** Section 3 is therefore not third-party disclosure. The residual is that the code does not enforce the ruling: `Principal.is_admin` can be set on any guardian's `User` row, so a configuration change could silently falsify what is now a compliance premise rather than a design intent. | Record the ruling in an ADR; enforce it with a settings-backed allowlist of admin-eligible subjects, checked at `POST /api/v1/admin/users` and at any capability grant, with a test asserting a non-allowlisted subject cannot be granted `is_admin`. | **High** (was Critical; the legal question is answered, the enforcement is not built) |
| **CFD-2** | `GET /api/v1/admin/audit` projects `payload` as an unfiltered `dict[str, object]` (`audit.py:335`) over an event log that receives child free text. Any future payload field widens the surface with no review signal. | Replace the pass-through with a per-`event_type` field allowlist; unknown keys drop rather than pass. Add a test that a novel payload key does not reach the wire. | **High** |
| **CFD-3** | `GET /api/v1/admin/story-requests` returns child-authored free text plus `profile_id` and `age_band` across families. | Confirm the admin console actually renders `request_text` for triage; if a redacted or interpretation-only view suffices for the queue, project that and fetch full text only on explicit drill-down, so bulk listing is not bulk free-text egress. | **High** |
| **CFD-4** | `GET /api/v1/admin/profiles` returns `reading_level_cap`, `tts_enabled`, `reduce_motion` cross-family; jointly a disability proxy. | Drop accessibility and reading-level fields from the admin list projection unless a named admin workflow needs them. | **Medium** |
| **CFD-5** | Sentinel-based personalization keeps real names out of stored prose, so cross-family human review runs on de-identified content. This is load-bearing for Section 3.5 but is not pinned by a test. | Add a test asserting no stored `StorybookVersion` content matches a resolved personalization value, and that the review surface returns sentinels. | **Medium** |
| **CFD-6** | The ring-2 personalization consent model (per-recipient, per-slot, versioned, revocable, non-observable denial) is exactly the shape the account-level VPC consent ledger needs, and is undocumented as prior art. | Cite `_ring2_values` and `ChildProfilePersonalizationConsent` in the VPC design as the in-repo reference implementation. | **Medium** |
| **CFD-7** | `acting_role` (`deps.py:184-202`) distinguishes the two capacities for audit stamps only; authorization reads the bare `is_admin` boolean. | Consider routing cross-family authorization through the same helper, so "acting as admin" is one concept rather than two that can drift. | **Low** |

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
- `docs/planning/adr/adr-016-recommendation-sharing-social-boundary.md` (the three-ring boundary),
  ADR-018 (children's privacy compliance), ADR-022 (RLS tiering), ADR-023 (personalization).
