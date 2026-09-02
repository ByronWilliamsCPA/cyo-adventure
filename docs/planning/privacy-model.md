---
title: "Privacy and Provider Data-Handling Model"
schema_type: planning
status: active
owner: core-maintainer
purpose: "Document the data classification, retention rules, privacy controls, and open blockers for CYO Adventure's generation pipeline."
tags:
  - planning
  - architecture
component: Development-Tools
source: "docs/planning/tech-spec.md sections Privacy controls, Data Protection, Security (2026-06-20)"
---

# Privacy and Provider Data-Handling Model

> **Status**: Active | **Version**: 0.3 | **Updated**: 2026-07-29

## Overview

CYO Adventure serves children across deployment tiers. Because stories are
machine-generated and read by minors, the privacy controls and provider data-handling
decisions are Phase-0 hard blockers: they must be resolved before any real LLM call is
made in Phase 2. Privacy posture is tier-specific: the dev and family / homelab tiers may
keep all data local, while the public tier hosts child-linked data on Supabase-managed
Postgres (a US processor). ADR-008 and ADR-009 amend ADR-004's original absolute "no
child data on third-party infrastructure" stance for the public tier; that stance still
governs the homelab / family tier.

This document covers data classification, what is and is not allowed in prompts, raw
output retention, moderation report persistence, deletion readiness, and prompt-injection
defense. Open blockers that gate the Phase 0 exit and the first Phase 2 LLM call are
listed at the end.

---

## Data Classification

Child-linked data is any record that can be associated with an identified or identifiable
child. The following are classified as child-linked:

- `child_profile` rows: `display_name`, `age_band`, `reading_level_cap`,
  `allowed_content_flags`, `tts_enabled`, `avatar`.
- `reading_state` rows: `current_node`, `var_state`, `path`, `save_slots`, keyed by
  `child_profile_id`.
- `completion` rows: `ending_id`, `found_at`, keyed by `child_profile_id`.
- Raw LLM generation outputs stored in `generation_job.report` (a Postgres JSONB
  column), if they were generated in a context where a concept brief containing profile
  attributes was used. Per ADR-007 as amended 2026-07-16, `GET /generation-jobs/{id}`
  exposes this field only to principals with the admin capability (a dual-role adult
  qualifies via that capability); guardians receive job status, stage log, and error
  information without `report`. The list endpoint and every child-facing endpoint
  exclude it entirely.
- `child_profile_personalization` rows: guardian-supplied personalization slot values
  (`value_text`, `value_enum`, `value_profile_id`) and the profile-level
  `real_name_ring1_enabled`/`real_name_ring2_enabled` flags, keyed by `child_profile_id`
  (ADR-023). Same tier as the `child_profile` fields above: guardian-supplied, never
  sent to a provider, never persisted into story content, delivered to family devices
  only as a values payload resolved at read time. Retention: life of the profile,
  purged by the existing profile-deactivation grace window in the retention table
  (`docs/compliance/coppa-gdpr-remediation-plan.md:712`).
- `personalization_disclosure_consent` rows: the ring-2 disclosure consent record
  (`consent_accepted_at`, `consent_policy_version`, `consent_signer_name`,
  `consent_ip`, `covered_slot_types`, `sibling_authority_attested`), keyed by
  `child_profile_id` (ADR-023 P4). Same tier as `User`'s own consent columns
  (`db/models.py:416-426`): consent evidence, not reading data. Retention should
  follow the consent-evidence rationale rather than the reading-data rationale;
  flagged for the same counsel pass as ADR-018 D1.
- The client-held personalization values payload: child-linked data at rest on a
  device, in the same category as the offline `reading_states` store already covered
  by the SEC-F5 sign-out purge (`frontend/src/offline/db.ts:192-201`). **Shared-device
  isolation (risk R20), RESOLVED 2026-07-28 (owner): accepted for v1.** A shared
  family device is a shared trust boundary; no per-profile encryption and no
  in-memory-only mode ship in v1.

The following are not child-linked on their own (they link to a family or a story, not
to an individual child):

- `storybook` and `storybook_version` records (family-linked, not child-linked).
- `concept` and `generation_job` records (family-linked).
- Moderation reports attached to `storybook_version` (persisted for audit; no child
  identifier unless a profile ID appears in the flagged text, which the privacy controls
  below prevent).

---

## No Real Child PII in Prompts

Concept briefs pass age band and a fictional reader profile to the LLM. They must not
contain:

- A real child's name (use fictional names or role descriptions such as "the protagonist").
- A real child's birthdate or age in a way that links to an identified individual.
- Sensitive traits, medical conditions, learning differences, or behavioral notes tied to
  a real child.
- Family member names or other identifying personal details.

The concept brief intake fields are: `title?`, `premise`, `protagonist` (name/age/role,
must be fictional), `point_of_view` (default 2nd person), `age_band`, `reading_level_target`,
`tier`, `tone`, `themes_allowed[]`, `content_nogo[]`, `target_node_count`, `ending_count`,
`structure_pattern`, `desired_variables[]?`, `special_constraints[]?`.

`age_band` is a categorical value (one of the six bands "3-5", "5-8", "8-11", "10-13",
"13-16", "16+"); it identifies a generation target, not an individual child. The backend must validate that the concept brief does not
contain free-text fields with real names before dispatching to the provider.

**Child-initiated requests (shipped in WS-B of the story-lifecycle redesign; budget-consent
semantics added by ADR-015)**: a child-typed story wish is child-provided free text and is
likely to contain the child's own name or friends' names. Current behavior, verified in
`api/story_requests.py`: wish text is screened at intake against the family's child-profile
names and for safety, and a blocked wish persists as a `blocked` row that proceeds nowhere.
The wish reaches the **generation** provider only after guardian approval converts it into a
concept, and the PII guard runs on the resulting brief before that egress. Note, however,
that the intake **screening** step itself sends the wish text to the external moderation
classifiers described in the next section, so those services are data-handling
counterparties for child-typed text as well as for generated prose.

---

## Raw LLM Outputs and Prompt Text

Raw LLM outputs (the full text returned by the provider for each stage) and the prompt
text sent to the provider are admin-only (ADR-007 as amended 2026-07-16). They are no longer
uniformly short-lived: as of ADR-007's 2026-08-10 and 2026-08-11 amendments, a raw output that
a human reached a decision about is retained for the life of the storybook, and only an
undecided one is short-lived. The detail is in the second bullet.

- **Prompt text**: store the prompt template version and a hash, not the full rendered
  prompt, where the rendered text could carry child-specific detail. The hash allows
  audit without persisting the content.
- **Raw generation outputs**: stored in `generation_job.report`, a Postgres JSONB column
  (not object storage; there is no `raw_output_ref` field). The purpose was originally
  debugging and repair-pass analysis alone; ADR-007's 2026-08-10 amendment added a second,
  broader one: calibrating the review scorecard against the decision a human actually made.
  That is a purpose change as well as a window change, and it is what justifies the longer
  retention below rather than the debugging need, which is satisfied inside 30 days.
  The retention window is defined (ADR-007): purge 30
  days after job completion, via a `pg_cron` job (ADR-009), **except** where a human
  reached a review decision about the storybook the job produced, which ADR-007's
  2026-08-10 amendment exempts so the raw output can be paired with the reviewer's
  decision. ADR-007's 2026-08-11 amendment withdrew the original "or on publish, whichever
  comes first" leg: publishing is now an exemption from the purge rather than a trigger for
  it, because the immediate on-publish null in `publishing/service.py::approve` fired before
  the approve half of the exemption could ever apply. The `pg_cron` job is built and
  scheduled (`20260718000000_add_report_retention_purge.sql`, predicate amended by
  `20260810000000_exempt_reviewed_generation_job_report_from_purge.sql`); it is no longer
  the unbuilt Phase 5 deliverable this section once described.

  The exemption has a boundary worth stating here rather than only in the retention policy:
  it is evaluated when the nightly sweep runs, not when the human decides. A job whose
  storybook is still `in_review` on day 31 is purged, and a later approval cannot restore the
  column, so the pairing this exemption exists to enable only happens for reviews that
  conclude inside the 30 days. See `docs/compliance/data-retention-policy.md` Section 4 and
  `UW-C227`.

  ```python
  # #CRITICAL: data integrity: generation_job.report holds raw LLM output that may
  #            carry child-derived detail; it must be purged and never leaked.
  # #VERIFY: the pg_cron purge job (30 days post-completion, minus the human-decided
  #          exemption) is scheduled before the public tier goes live; confirm report
  #          stays off child-facing endpoints and the job-list endpoint.
  ```

- **Access control**: `generation_job.report` is returned by `GET /generation-jobs/{id}`
  only to principals with the admin capability (ADR-007 as amended 2026-07-16; the
  admin reviews first, then the parent receives content through post-approval surfaces).
  It is excluded from the list endpoint (job status only) and every child-facing
  endpoint, and is not accessible via the story-serving path.

Moderation reports (the per-node flags and the moderation API response) persist with the
`storybook_version` record for audit. They contain node IDs and flag categories, not raw
child data.

---

## External Moderation Classifiers (Stage 0, first-line filter)

This is a deliberate design decision, not an incidental integration: **all AI-generated
story prose** runs through external moderation classifiers as the first-line safety filter,
precisely so that safety does not depend on a parent reading every path in detail. The
human gates (guardian oversight, admin approval per ADR-005) sit on top of this floor, not
in place of it.

Current mechanism (`moderation/classifiers.py`, wired in `moderation/pipeline.py`): when
keys are configured, every generated node's prose is sent per-node to the **OpenAI
Moderation API** and **Google Perspective API** during Stage 0 of the moderation pipeline.
The same classifiers screen child-typed story-request text at intake
(`story_requests/screening.py`). Both services are therefore standing data-handling
counterparties for two data categories:

- **Generated story prose** (family-linked content produced by the pipeline; the PII guard
  keeps real child detail out of the prompts that produce it).
- **Child-typed request text** (child-provided free text, screened before storage).

Consequences for the provider data-handling review (Blocker 1 below): OpenAI and Google
(Perspective) must be included alongside the generation leg (OpenRouter) and the LLM
review leg when confirming retention terms. **Since the 2026-07-28 narrowing, this leg is
where Blocker 1's force sits** (Blocker 1b). The distinction is route control, not whether
typed words egress at all: a child's own typed words reach the generation leg too, verbatim,
because `ConceptBrief.premise` is `request.request_text` unaltered
(`story_requests/brief.py:197`) and the brief is fenced into the generation prompt. What is
different here is that the classifier leg calls OpenAI Moderation and Google Perspective
**directly**, so it inherits none of the OpenRouter workspace guardrail that constrains the
generation route, and ADR-023's proposed render-time substitution does nothing for it either
(it addresses identifiers, not free text). Classifier calls should remain content-only:
no child identifier, profile id, or family id accompanies the text, and failures are
logged by node id only.

Ring-2 recommendation sharing (guardian-connected families, the cousins case) is a new
child-linked data flow: a recommendation visible to a connected family carries the
recommending child's display name and a reading signal (book plus rating) into another
household. Controls, binding per
[ADR-016](./adr/adr-016-recommendation-sharing-social-boundary.md):

- Visibility exists only along a directional, revocable `family_connection` with active
  guardian consent on both sides; revocation removes visibility immediately.
- Payloads are structured data only (book reference, display name, rating); never free
  text, reading progress, request text, or profile attributes beyond the display name.
- Ring-3 global aggregation (future) must be anonymized: no per-child or per-family
  identifier may reach or be inferable from a global recommendation, with a
  minimum-population threshold before aggregates surface.
- Deletion-readiness: recommendations and connections are family-linked rows in known
  tables and must be included in family erasure.

---

## Deletion Readiness

A full deletion subsystem is a later deliverable. The requirement at Phase 0 is that the
data model does not make deletion impossible. The following rules apply:

- Child-linked data must be kept in known, enumerable places: `child_profile` rows in
  Postgres, `reading_state` rows in Postgres, `completion` rows in Postgres, and raw
  generation outputs in the `generation_job.report` JSONB column in Postgres.
- Child-linked data must not be scattered through structured logs, Sentry breadcrumbs, or
  application-level caches that are not enumerated in the data model.
- Sentry must not receive a child's reading content beyond a node ID or story ID. Exception
  events should carry correlation IDs, not reading-state snapshots.
- When a child profile is deleted, the owning service must be able to identify and purge
  all associated `reading_state` and `completion` rows. Cascades must be defined in the
  Alembic schema.

---

## Prompt-Injection Defense

Concept brief text is untrusted input. A malicious or malformed brief must not alter the
system prompt, bypass the safety constraints, or cause the model to produce content that
skips moderation.

Defense controls:

- The system prompt and safety constraints sent to the provider are fixed templates,
  rendered from versioned template files. Brief content is inserted only into designated
  user-turn slots and is never concatenated into the system prompt.
- The moderation pass runs independently of the generating model. Even if a brief causes
  the generator to produce unsafe content, the independent moderation pass and the
  mandatory guardian approval step remain in the path.
- Brief fields are validated against a strict schema before dispatch. Free-text fields
  (`premise`, `protagonist`, `special_constraints`) are length-limited and stripped of
  control characters before insertion.
- The generation orchestrator logs the prompt template version and the brief hash with
  every job. Any anomaly in moderation flags can be correlated back to the brief that
  triggered it.

**Available but not enabled (recorded 2026-07-28)**: the OpenRouter workspace offers a free,
no-added-latency, OWASP-inspired regex scan for common injection techniques, with an
allow-list for phrases that should never trigger it. Every defense listed above is ours and
runs in-process; this would be an independent fourth layer at the egress boundary. It is
**disabled** as of this record. The reason it is not simply switched on is false positives:
a children's adventure brief can legitimately contain instruction-shaped phrasing, and a
blocked generation is a visible product failure rather than a silent one. Worth trialling
with the allow-list in reach; not a default yes.

---

## OPEN BLOCKERS

The following blocker is split into two sub-items. Only 1b (the classifier and review leg)
gates anything; 1a (the generation leg) is narrowed to a documentation item and gates
nothing. A second former blocker (homelab reachability through Pangolin) has since been
resolved; see [Resolved Blockers](#resolved-blockers) below.

### Blocker 1: LLM Provider Data-Handling Terms

**Narrowed 2026-07-28.** This blocker was originally written as one undifferentiated gate
over every model counterparty, and it stopped all generation ("No generation call may be
made with a real concept brief until it is resolved"). It is now split, because the two
legs do not carry the same data and never did.

#### 1a. Generation leg (OpenRouter): NARROWED to a documentation item

```python
# #CRITICAL: external resource: retention posture on the generation leg rests on a
#            mutable platform guardrail (dated snapshot), not on an executed DPA.
# #VERIFY: re-confirm the OpenRouter workspace guardrail state at P7-08 and on any
#          credential rotation; execute the DPA and record both in
#          docs/compliance/processor-dpa-checklist.md.
```

The generation leg no longer gates dispatch. The reasoning, in the order it matters:

1. **No registered child identifier can reach it.** `assert_prompt_pii_safe`
   (`generation/pii.py:229-289`) raises and fails the job rather than redacting, over both
   the `system` and `user` blocks, and briefs fall back to a fictional `"Explorer"`
   (`story_requests/brief.py:79-81`).
2. **That is not expected to change under personalization, though the answer is proposed
   rather than settled.** ADR-023 *proposes* resolving guardian-opt-in personalization
   client-side at render time over sentinels the server stores and serves unchanged, rather
   than at generation time. It is `status: proposed` with counsel sign-off open and no code
   written yet, and it is a third route rather than the rejected Route B (which would have put
   real names into provider prompts and into `storybook_version.blob`). If ADR-023 is not
   adopted, this reason lapses.
3. **Routing on the OpenRouter leg is constrained at the platform, not by policy.** A
   guardrail on a dedicated, key-scoped OpenRouter workspace (configured 2026-07-28) requires
   zero-data-retention endpoints across non-frontier, Anthropic, OpenAI, Google, and xAI
   routing, and disables all three data-training paths (paid-trains, free-trains,
   free-publishes-prompts). The guardrail's plugins-and-tools carve-out does not reach this
   app: the generation request body contains no `plugins` or `tools` key
   (`generation/providers/openrouter.py:154-164`). **This covers the OpenRouter route only.**
   The direct-Anthropic leg (`generation/providers/anthropic.py`, selectable as
   `generation_provider="anthropic"` and seeded in the admin allowlist) is built and bypasses
   the guardrail; confining production generation to the guarded route is an open item, not an
   existing control. Full state, limits, and that open item: ADR-003's 2026-07-28 amendment.
4. **A second, independent egress chokepoint now exists.** Key-level Sensitive Info
   Detection redacts email, phone, SSN, credit-card, and IP patterns request-side, outside
   our process and after `assert_prompt_pii_safe` has already hard-failed on the overlapping
   ones. Person-name and address redaction are deliberately **off**: the protagonist name is
   intentional fictional story content, and addresses are already a hard fail here. See
   ADR-003 for the full reasoning, which should be read before anyone "completes" those
   checkboxes.

**What is still true, and is why this is narrowed rather than closed**: briefs carry a
coarse age band, guardian-set `banned_themes`, content-flag caps, and free-typed premise
text. That is child-*derived* content, so the generation leg is identifier-free, not
PII-free, and its terms still belong in the P7-08 processor record. A routing guardrail is
also not a contract: no DPA has been executed, and console settings are mutable, so the
configuration above is a dated snapshot rather than a permanent property.

**Counterparty change, 2026-07-28**: the ZDR toggles disable first-party Anthropic, OpenAI,
and Google AI Studio endpoints rather than those model families, so generation traffic now
reaches them through AWS Bedrock, Microsoft Azure, and Google Vertex. Those three are in
scope as sub-processors for the generation leg. This does not affect the classifier leg
below, which calls OpenAI Moderation directly.

**Status**: NARROWED. Not a dispatch gate. DPA execution and a re-confirmation of the
guardrail state remain P7-08 deliverables; `docs/compliance/processor-dpa-checklist.md`
still carries the OpenRouter row as unexecuted.

#### 1b. Classifier and review leg: OPEN, and this is now the real blocker

```python
# #CRITICAL: external resource: retention terms for the Stage-0 classifiers, which
#            receive child-TYPED free text, are unconfirmed.
# #VERIFY: confirm terms per counterparty before the public tier ships; record here.
```

This leg is different in kind, and the original blocker's force belongs here. The Stage-0
external classifiers receive **child-typed request text** at intake
(`story_requests/screening.py`) and **every node of generated prose** during moderation (see
the External Moderation Classifiers section above). They are called directly, so nothing about
the OpenRouter workspace guardrail reaches them, and ADR-023's proposed render-time
substitution does not touch them either: it addresses identifiers, and this is the child's own
free text, sent verbatim, before storage.

The **LLM review provider** stays in scope here but for a different reason, and an earlier
draft gave the wrong one. It is not a child-typed-text path: it is built from the same
`build_openrouter_leg` adapter as generation
(`moderation/review_provider.py`), and `review_openrouter_model` defaults to an Anthropic model
(`core/config.py:562`), so when `review_provider="openrouter"` the review leg rides the **same
guardrailed route** as generation and carries **generated prose**, not child-typed words. What
it still needs is the same terms confirmation every counterparty needs, plus the caveat that
its posture is inherited from the generation-route guardrail and moves with it.

**Required action**: confirm the applicable retention path for each classifier counterparty
and the review provider, and record the outcome (provider, route, contract reference or API
tier, effective date) here. Note that the Perspective counterparty is separately in flux
under the Stage-0 Perspective sunset work; that changes who is on this list, not whether the
confirmation is needed.

**Status**: OPEN. This is the standing Blocker 1 referenced by
[ADR-018](./adr/adr-018-childrens-privacy-compliance.md) item 6.

---

## Resolved Blockers

### Blocker 2 (resolved): Homelab Reachability Through Pangolin (P0-10)

The homelab needed to be reachable through the Pangolin zero-trust ingress before
integration tests and the CI environment could reach the deployed stack. This was plan
item P0-10 and a Phase 0 exit condition.

**Resolution**: the homelab stack is reachable through Pangolin and has been live in
production since 2026-07-05 at `https://cyo.williamshome.family` (Cloudflare, Pangolin
VPS, WireGuard tunnel, docker-host Traefik). R1 (the internal web release) is
feature-complete as of 2026-07-03 and has been exercised end to end against this live
URL, including guardian email/password sign-in through Supabase (ADR-009) and the full
guardian-authoring to kid-reading journey. The 2026-07-07 record also cited `/health/live`
and `/health/ready` "returning 200"; that leg of the evidence is withdrawn as of 2026-08-04
(`UW-L04`). Those requests were answered by an nginx stub rather than by the application, so
the 200 proved nothing about database connectivity. This does not change the blocker's
disposition, which rests on the sign-in and reading journey above, but the probe evidence
itself must not be cited: readiness became genuinely reachable only once the canonical
`/api/v1/health/ready` path existed. See `docs/planning/roadmap.md` (Phase 5 success criteria: "✅
Deployed behind Pangolin with Supabase guardian login (ADR-009)") and
`docs/planning/r1-live-e2e-checklist.md` for the live verification record. Note this
blocker was scoped to the homelab / family tier only; on the public tier, Supabase is the
identity provider (Supabase OIDC, ADR-009) and Supabase-managed Postgres is the
datastore, so Pangolin ingress and a self-hosted IdP do not apply there.

**Status**: RESOLVED (2026-07-05, verified live 2026-07-07; the health-probe leg of that
verification was withdrawn 2026-08-04, see `UW-L04`).

---

## If Shared Beyond Family

### Ring-2 disclosure (existing, guardian-authorized)

Personalization values also flow beyond the immediate family through the ring-2
disclosure design (ADR-016, ADR-023 section 3). This is a designed, guardian-gated flow,
not a future Phase 7 deliverable, and it carries its own controls distinct from the
public-tier checklist below:

- **Which slot types can cross**: protagonist first name, sibling/family-child name, pet
  species, pet name, trusted-adult kinship label, favorites (color, food, hobby), and
  home type. Pronouns and the dedication line never cross ring 2 (ADR-023 taxonomy, ring
  ceiling column).
- **Under which consent**: the mutual, directional `family_connection` consent (active
  guardian approval on both sides) plus a separate, per-profile, per-connection
  disclosure consent (`personalization_disclosure_consent`, scoped by
  `covered_slot_types`). The sibling slot additionally requires
  `sibling_authority_attested` and the referenced sibling's own ring-2 enablement and
  consent on that same connection.
- **Revocation is prospective, not retroactive**: revoking a connection or a disclosure
  consent stops future reads and future device syncs immediately, but does not
  retroactively claw back a values payload already synced to a connected family's
  device. Guardian-facing copy for revocation must say so rather than implying
  retroactive erasure.

### Public tier (future, ADR-008 / ADR-009)

The controls above are calibrated for private family use and the homelab / family tier.
The public tier (ADR-008 / ADR-009) takes this beyond private family use, so COPPA and
Kids Category compliance become launch blockers. That compliance work is a future Phase 7
deliverable and is not yet done. Before the public tier launches, revisit with legal
counsel:

- COPPA (US) and state-level children's privacy equivalents.
- ICO Age Appropriate Design Code (UK) as a design reference.
- Age assurance and verifiable parental consent mechanisms.
- Retention and deletion policy suitable for a public service.
- Vendor terms covering the LLM provider, storage, and auth for a non-family audience.
- Incident response plan and a published privacy notice.

This note is a design reference, not legal advice.

---

## Related Documents

- [Tech Spec: Security](./tech-spec.md#security)
- [Tech Spec: Privacy controls](./tech-spec.md#privacy-controls-family-only)
- [Phase 0 Decision Log](../phase0-decisions.md)
- [ADR-003: Frontier LLM for generation](./adr/adr-003-frontier-llm-generation.md)
- [ADR-004: Homelab-first deployment](./adr/adr-004-homelab-first-deployment.md) (governs the homelab / family tier)
- [ADR-007: Raw output retention](./adr/adr-007-raw-output-retention.md)
- [ADR-008: Public app store launch](./adr/adr-008-public-app-store-launch.md)
- [ADR-009: Supabase platform (managed Postgres, OIDC)](./adr/adr-009-supabase-platform.md)
- [ADR-016: Recommendation sharing and the three-ring social
  boundary](./adr/adr-016-recommendation-sharing-social-boundary.md)
- [ADR-023: Story personalization slots](./adr/adr-023-story-personalization-slots.md)
