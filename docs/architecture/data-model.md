---
title: "Data Model"
schema_type: common
status: published
owner: core-maintainer
purpose: "ER diagram and description of the 21 ORM tables backing CYO Adventure."
tags:
  - architecture
  - reference
---

CYO Adventure has twenty-one PostgreSQL tables managed by SQLAlchemy 2 async ORM, with
schema migrations applied as plain SQL via the Supabase CLI (`supabase/migrations/`,
ADR-012; Alembic retired). All timestamps are `TIMESTAMP WITH TIME ZONE`. Enum-like
columns (`role`, `status`, `age_band`) are stored as strings and validated at the
application boundary, which keeps schema migrations simple and avoids enum-type churn.

## Entity-Relationship Diagram

![ER Diagram](diagrams/er-diagram.svg)

## Table Reference

### `family`

The ownership root. Every other entity is scoped to a family. Family ownership is
checked on every resource access; a valid token for family A cannot reach family B's
data.

| Column | Type | Notes |
|--------|------|-------|
| id | UUID PK | |
| name | VARCHAR(200) | Display name |
| created_at | TIMESTAMPTZ | Server default |
| deactivated_at | TIMESTAMPTZ NULL | Soft-deactivate; cascades to member users/profiles in the same transaction (reactivation is manual, not cascaded) |

### `user`

An authenticated user within a family. `role` is the single base persona
(`guardian`, `child`, or `admin`); the orthogonal `is_admin` flag is a capability, so
one adult can be a guardian, an admin, or both.

| Column | Type | Notes |
|--------|------|-------|
| id | UUID PK | |
| family_id | UUID FK | family.id |
| role | VARCHAR(16) | `guardian`, `child`, or `admin` |
| is_admin | BOOLEAN | Global admin capability, orthogonal to role; default false. CHECKs keep it off child rows and force it true for the admin role |
| authn_subject | VARCHAR(255) UNIQUE | OIDC `sub` claim; the sole identity key |
| email | VARCHAR(320) NULL | Contact only (Supabase email claim); never an identity key, nullable |
| child_profile_id | UUID FK NULL | child_profile.id; NULL for guardians and admins |
| created_at | TIMESTAMPTZ | |
| status | VARCHAR(16) | `pending` (admin-created invite), `active` (default), or `deactivated` (blocks auth; row and history preserved) |

### `child_profile`

Per-child reading profile. Age band and content caps filter which stories are visible.
`tts_enabled` gates the Web Speech API read-aloud feature.

| Column | Type | Notes |
|--------|------|-------|
| id | UUID PK | |
| family_id | UUID FK | family.id |
| display_name | VARCHAR(120) | Used in PII screening |
| age_band | VARCHAR(16) | one of `3-5`, `5-8`, `8-11`, `10-13`, `13-16`, `16+` |
| reading_level_cap | FLOAT | Flesch-Kincaid cap; default 99.0 |
| allowed_content_flags | JSONB | Per-flag content permissions |
| tts_enabled | BOOLEAN | TTS feature flag |
| avatar | VARCHAR(255) NULL | |
| pin_hash | TEXT NULL | Write-only PIN credential (`pbkdf2_sha256`); never serialized (views expose a `has_pin` bool) |
| created_at | TIMESTAMPTZ | |
| deactivated_at | TIMESTAMPTZ NULL | Soft-remove (WS-J); excluded from pickers/listings and session mint, history preserved |

### `family_connection`

A directional cross-family opt-in for story recommendations (WS-J). `family_id` is the
"viewer" family that opted in to seeing stories sourced from `connected_family_id`; the
relationship is deliberately one-way, so mutual visibility is two rows, not one. No
recommendation engine reads this table yet: WS-J only builds the admin-managed allowlist.

| Column | Type | Notes |
|--------|------|-------|
| id | UUID PK | |
| family_id | UUID FK | family.id; the viewer family that opted in |
| connected_family_id | UUID FK | family.id; the source family whose stories may be recommended |
| created_by | UUID FK NULL | user.id of the admin who created the connection |
| created_at | TIMESTAMPTZ | Server default |

A unique constraint on `(family_id, connected_family_id)` and a check constraint
`family_id <> connected_family_id` prevent duplicate rows and self-connections.

### `series`

A named, family-owned chain of storybooks (WS-B PR 3, decision B2). DB-level linkage
only: books reference a series via `storybook.series_id`/`book_index`; the embedded
document `Series` metadata block (`storybook/models.py`) is not written, so the
cross-book SR-1..SR-7 validator stays dormant until structural chaining is added.
`carries_state` follows the ADR-011 band rule: `False` (episodic) for `3-5`/`5-8`,
`True` for all higher bands.

| Column | Type | Notes |
|--------|------|-------|
| id | UUID PK | |
| family_id | UUID FK | family.id (decision B3; widening is WS-E) |
| title | VARCHAR(120) | Guardian- or admin-ratified series title, screened at intake |
| age_band | VARCHAR(16) | one of `3-5`, `5-8`, `8-11`, `10-13`, `13-16`, `16+`; every book in the series must match |
| carries_state | BOOLEAN | ADR-011 band rule |
| created_by | UUID FK NULL | user.id of ratifying user |
| created_at | TIMESTAMPTZ | |

### `storybook`

The lifecycle row for a story. One row per story id, regardless of how many versions
have been generated. `current_published_version` points to the version visible to
children.

| Column | Type | Notes |
|--------|------|-------|
| id | VARCHAR(120) PK | Stable across versions |
| family_id | UUID FK | family.id |
| current_published_version | INT NULL | NULL until first publish |
| status | VARCHAR(20) | State machine: see below |
| visibility | VARCHAR(16) | `family` (default) or `catalog`; WS-E decision E1/E5 |
| created_by | UUID FK NULL | user.id of guardian who created it |
| series_id | UUID FK NULL | series.id; NULL for a standalone book |
| book_index | INT NULL | 1-based position within the series; NULL iff series_id is NULL |
| created_at | TIMESTAMPTZ | |

**Status values:** `draft`, `in_review`, `needs_revision`, `published`, `archived`
(see `publishing/state_machine.py`). There is no `generating`, `auto_check`, or
`approved` storybook status; staged-generation state lives in `generation_job`, and
publication is the admin approve action.

**Visibility values:** `family` (default, visible only within the owning family) or
`catalog` (browsable/assignable cross-family, WS-E). A unique constraint on
`(series_id, book_index)` and a check constraint pairing `series_id` and
`book_index` (both NULL or both set) enforce series consistency.

### `storybook_version`

An immutable snapshot of a story. Composite primary key `(storybook_id, version)`.

| Column | Type | Notes |
|--------|------|-------|
| storybook_id | VARCHAR(120) PK FK | storybook.id |
| version | INT PK | Monotonically increasing |
| blob | JSONB | Full Storybook JSON (Phase 1 inline storage) |
| blob_ref | VARCHAR(512) NULL | MinIO object key (reserved, Phase 5) |
| validation_report | JSONB NULL | Gate report at generation time |
| moderation_report | JSONB NULL | Moderation report |
| approved_by | UUID FK NULL | Admin user who approved (global, cross-family) |
| published_at | TIMESTAMPTZ NULL | |
| model | VARCHAR(120) NULL | LLM model id used |
| prompt_version | VARCHAR(120) NULL | Prompt template version |
| provider | VARCHAR(120) NULL | Generation provider (`mock`, `anthropic`, `openrouter`, ...), or `import` for the offline authoring import path; NULL for rows predating this column |
| skeleton_slug | VARCHAR(120) NULL | Production skeleton (`skeletons/<band>/<slug>.json`) this version was filled from, or NULL for fresh generation, an imported book, or a row predating this column (WS-C PR2) |
| created_at | TIMESTAMPTZ | |
| cover_image_url | VARCHAR(512) NULL | AI-generated cover art URL |
| cover_status | VARCHAR(20) | `none` (default), `generating`, `ready`, or `failed` |

At launch the Storybook JSON is stored inline in `blob` (JSONB). The `blob_ref`
column is deferred: it holds the MinIO object key once object storage is wired
(ADR-009 defers MinIO to a future object-store target). The schema is versioned at
`2.0` and validated on read with a reject-on-mismatch check; there is no upcaster,
so a stored blob whose `schema_version` does not match is rejected rather than
migrated (ADR-001).

### `reading_state`

Per-child, per-story reading progress. Composite primary key `(child_profile_id, storybook_id)`.
A composite foreign key `(storybook_id, version)` references `storybook_version` to
prevent saving state for a version that does not exist.

| Column | Type | Notes |
|--------|------|-------|
| child_profile_id | UUID PK FK | child_profile.id |
| storybook_id | VARCHAR(120) PK FK | storybook.id |
| version | INT | Pinned via composite FK to storybook_version |
| current_node | VARCHAR(120) | Current node id |
| var_state | JSONB | Variable values (Tier-2 only) |
| path | JSONB | Ordered list of visited node ids |
| visit_set | JSONB | Set of visited nodes (drives `once: true` effects) |
| save_slots | JSONB | Named state snapshots |
| state_revision | INT | Server-owned OCC counter |
| last_event_id | VARCHAR(64) NULL | Idempotency key for offline replay |
| updated_by_device_id | VARCHAR(64) NULL | Device that last wrote |
| last_synced_at | TIMESTAMPTZ NULL | |
| created_at | TIMESTAMPTZ | |
| updated_at | TIMESTAMPTZ | `onupdate=func.now()` |

### `completion`

Records that a child found a particular ending of a story version. Composite
primary key `(child_profile_id, storybook_id, version, ending_id)`.

| Column | Type | Notes |
|--------|------|-------|
| child_profile_id | UUID PK FK | child_profile.id |
| storybook_id | VARCHAR(120) PK | |
| version | INT PK | |
| ending_id | VARCHAR(120) PK | Stable ending id from Storybook |
| found_at | TIMESTAMPTZ | Server default |

### `rating`

A child's 1-5 rating of a storybook. Unlike `completion`, which pins to an
immutable `storybook_version` via a composite FK, a rating is about the *book*
as a whole and is mutable: a child may re-rate, overwriting the prior value.
Composite primary key `(child_profile_id, storybook_id)`.

| Column | Type | Notes |
|--------|------|-------|
| child_profile_id | UUID PK FK | child_profile.id |
| storybook_id | VARCHAR(120) PK FK | storybook.id |
| value | INT | 1-5, enforced by `ck_rating_value_range` |
| rated_at | TIMESTAMPTZ | Server default |
| updated_at | TIMESTAMPTZ | `onupdate=func.now()` |

### `storybook_assignment`

A guardian's grant of one published story to one child profile. Composite primary
key `(child_profile_id, storybook_id)` so a profile is assigned a book at most once.
This table is the read-gate: the library listing and the direct version fetch both
filter on it, so a child sees only stories explicitly assigned to their profile.

| Column | Type | Notes |
|--------|------|-------|
| child_profile_id | UUID PK FK | child_profile.id |
| storybook_id | VARCHAR(120) PK FK | storybook.id |
| assigned_by | UUID FK NULL | user.id of granting guardian; NULL for a system backfill |
| created_at | TIMESTAMPTZ | Server default |

### `device_grant`

A guardian-minted, durable, family-scoped device authorization (ADR-014). Lets a
child pick a profile and read, online or offline, without a live guardian Supabase
session on the device: `POST /v1/child-sessions` and `GET /v1/profiles` accept a
verified device grant as an additional authority alongside the guardian/admin
Supabase bearer, scoped to the grant's own `family_id`. The token itself (HS256,
audience `cyo-device-grant`, 90-day expiry) is never stored; only its unique `jti`
and mint metadata are, here.

| Column | Type | Notes |
|--------|------|-------|
| id | UUID PK | |
| family_id | UUID FK | family.id; the device is authorized for exactly this family |
| authorized_by | UUID FK | user.id of the guardian who minted the grant |
| label | VARCHAR(120) NULL | Guardian-facing device name (e.g. "Kitchen tablet"); never derived from request headers |
| jti | UUID UNIQUE | Matches the token's `jti` claim; the revocation lookup key |
| created_at | TIMESTAMPTZ | |
| revoked_at | TIMESTAMPTZ NULL | `NULL` while active; set (not deleted) on revoke so the guardian-facing device list can show when a device was revoked |

Revocation is enforced online only: the token's `jti` is checked against this
table's `revoked_at` on every use. An already-offline device cannot see a
revocation until it reconnects, an accepted limitation bounded by the 90-day
grant TTL (ADR-014, "Negative / risks"). The signing secret is
`DEVICE_GRANT_SECRET`, validated at startup the same way as `CHILD_SESSION_SECRET`.

### `concept`

The intake form for a guardian's story request. A `ConceptBrief` payload is validated
at the application boundary by the Pydantic model before insertion. Immutable once
written.

| Column | Type | Notes |
|--------|------|-------|
| id | UUID PK | |
| family_id | UUID FK | family.id |
| brief | JSONB | Full ConceptBrief JSON |
| created_by | UUID FK NULL | Guardian user who submitted |
| created_at | TIMESTAMPTZ | |

### `story_request`

A child's free-text story idea awaiting a guardian or admin decision. The request
text is screened at submission (PII guard + Stage-0 classifiers); a bright-line hit
lands the row in the `blocked` state before any guardian reads the raw text. A
guardian or admin then approves it (which builds a `ConceptBrief`, links
`concept_id`, and enters the generation pipeline) or declines it. `family_id` is
denormalized (stored, not derived from `profile_id`) so the guardian list and the
family-scope authz check stay single-table.

| Column | Type | Notes |
|--------|------|-------|
| id | UUID PK | |
| family_id | UUID FK | family.id |
| profile_id | UUID FK NULL | child_profile.id; NULL for a profile-less request (WS-B PR 2) |
| request_text | VARCHAR(500) | Child's short free-text idea |
| status | VARCHAR(16) | `pending`, `approved`, `declined`, or `blocked` |
| initiator_role | VARCHAR(16) | `child` (default), `guardian`, or `admin` |
| age_band | VARCHAR(16) | Required at flush, no default; one of `3-5`, `5-8`, `8-11`, `10-13`, `13-16`, `16+` |
| length | VARCHAR(16) NULL | `short`, `medium`, or `long`; NULL before a guardian confirms it |
| narrative_style | VARCHAR(16) | `prose` (default) or `gamebook` |
| moderation_flags | JSONB NULL | Redacted screening findings; never raw classifier score/source |
| reviewed_by | UUID FK NULL | user.id of guardian/admin who decided |
| reviewed_at | TIMESTAMPTZ NULL | |
| concept_id | UUID FK NULL | concept.id created on approval |
| series_id | UUID FK NULL | series.id this request continues (WS-B PR 3) |
| anchor_storybook_id | VARCHAR(120) FK NULL | storybook.id this soft continuation follows on from |
| proposed_series_title | VARCHAR(120) NULL | Kid's original series title proposal, retained as audit trail |
| created_at | TIMESTAMPTZ | |

**Status values:** `pending`, `approved`, `declined`, `blocked`.

Check constraints enforce: gamebook narrative style is teen-only (`13-16`/`16+`,
`ck_story_request_style_band`); a request proposes a new series title or continues
via an anchor, never both (`ck_story_request_title_anchor_mutex`); and an anchored
request always carries a `series_id` (`ck_story_request_anchor_requires_series`).

### `generation_job`

Tracks one staged-generation attempt for a concept. Status transitions:
`queued -> running -> passed | needs_review | failed`, plus a sixth state,
`awaiting_manual_fill`, set only for `method="skeleton_fill"` + `mechanism="skill"`
jobs and cleared once the human-authored fill is imported.

| Column | Type | Notes |
|--------|------|-------|
| id | UUID PK | |
| concept_id | UUID FK | concept.id |
| status | VARCHAR(20) | `queued`, `running`, `passed`, `needs_review`, `failed`, `awaiting_manual_fill` |
| model | VARCHAR(120) NULL | LLM model id |
| provider | VARCHAR(120) NULL | Provider name |
| prompt_version | VARCHAR(120) NULL | |
| report | JSONB NULL | Full `GenerationOutcome` JSON |
| authoring_metadata | JSONB NULL | Skeleton-fill metadata (skeleton_slug, theme_brief, review stage model overrides); NULL for `fresh_generation` jobs |
| storybook_id | VARCHAR(120) NULL | **Not a FK** (see note) |
| version | INT NULL | Storybook version produced |
| error | VARCHAR(512) NULL | Short error on failure |
| created_at | TIMESTAMPTZ | |
| updated_at | TIMESTAMPTZ | `onupdate=func.now()` |

`storybook_id` is intentionally **not a foreign key**. A job may fail before any
`storybook` row is created; a hard FK constraint would block inserting the failure
record. The application layer verifies the storybook row exists independently when
reading this field.

### `moderation_threshold`

Sparse per-`(age_band, category)` override of the moderation surfacing default.
Absence of a row means the code default applies
(`moderation/thresholds.py::DEFAULT_THRESHOLD`). The table is small (admin-curated),
so policy loads read it whole.

| Column | Type | Notes |
|--------|------|-------|
| id | UUID PK | |
| age_band | VARCHAR(16) | The reader age band this override applies to |
| category | VARCHAR(64) | The moderation category this override applies to |
| min_verdict | VARCHAR(16) | Minimum verdict severity that surfaces to review: `advisory`, `flag`, or `block` |
| min_score | FLOAT NULL | Optional classifier-score floor in [0.0, 1.0]; NULL to use the verdict gate alone |
| updated_by | UUID FK NULL | user.id of admin who last edited |
| updated_at | TIMESTAMPTZ | `onupdate=func.now()` |

A unique constraint on `(age_band, category)` enforces at most one override per pair.

### `moderation_threshold_audit`

Append-only audit of `moderation_threshold` edits (who changed what, when).
Deliberately minimal; the `pipeline_event` log will subsume this role in a future
iteration, so this table stays write-only until then.

| Column | Type | Notes |
|--------|------|-------|
| id | UUID PK | |
| age_band | VARCHAR(16) | Age band of the edited override |
| category | VARCHAR(64) | Moderation category of the edited override |
| action | VARCHAR(16) | `upsert` or `delete` |
| old_min_verdict | VARCHAR(16) NULL | Verdict floor before the edit; NULL on insert |
| new_min_verdict | VARCHAR(16) NULL | Verdict floor after the edit; NULL on delete |
| old_min_score | FLOAT NULL | Score floor before the edit |
| new_min_score | FLOAT NULL | Score floor after the edit |
| changed_by | UUID FK | user.id of admin who made the edit; NOT NULL |
| changed_at | TIMESTAMPTZ | Server default |

### `moderation_setting`

A single named global moderation scalar. Distinct from `moderation_threshold`: this
table holds global scalars (currently one row, key `admin_noise_floor`, seeded at
`0.05`) rather than sparse per-`(age_band, category)` overrides. It denoises the
admin review surface: `ADVISORY` findings scoring below the floor are hidden;
`BLOCK`/`FLAG` findings and unscored findings always surface regardless.

| Column | Type | Notes |
|--------|------|-------|
| key | VARCHAR(64) PK | Setting's unique name (e.g. `admin_noise_floor`) |
| value | FLOAT | Constrained to [0.0, 1.0] |
| updated_by | UUID FK NULL | user.id of admin who last edited |
| updated_at | TIMESTAMPTZ | `onupdate=func.now()` |

### `pipeline_event`

Append-only log of every story-lifecycle transition, written from the same
transaction performing the transition. Rows are enforced append-only by a DB
trigger created in the migration; the ORM never updates or deletes them.
`actor_id` is NULL for system transitions (worker, moderation), which carry
`actor_role='system'`. `payload` is PII-free by contract, gated by
`events/writer.py::_PAYLOAD_ALLOWLIST`.

| Column | Type | Notes |
|--------|------|-------|
| id | UUID PK | |
| occurred_at | TIMESTAMPTZ | Server default |
| actor_id | UUID FK NULL | user.id; NULL iff actor_role is `system` |
| actor_role | VARCHAR(16) | `system`, `guardian`, `child`, `admin`, or `device` (ADR-014; the CHECK constraint's vocabulary is a superset of every valid `Role`, though no event is written with `actor_role='device'` yet, since the device principal is not wired into any event-emitting endpoint) |
| entity_type | VARCHAR(32) | `story_request`, `generation_job`, `storybook`, `storybook_version`, `series`, `storybook_assignment`, `rating`, `moderation_threshold`, `moderation_setting`, `user`, `family`, or `family_connection` |
| entity_id | VARCHAR(255) | The affected row's id; composite ids (e.g. `f"{profile_id}:{storybook_id}"`) can reach ~157 chars |
| event_type | VARCHAR(48) | One of 17 lifecycle event types (`request_created`, `request_approved`, `request_declined`, `plan_assigned`, `generation_started`, `generation_finished`, `moderation_completed`, `repair_applied`, `sent_back`, `released`, `threshold_changed`, `noise_floor_changed`, `book_assigned`, `rated`, `user_managed`, `family_managed`, `family_connection_changed`) |
| from_state | VARCHAR(32) NULL | |
| to_state | VARCHAR(32) NULL | |
| payload | JSONB | PII-free event payload; defaults to `{}` |

### `provider_model_allowlist`

Admin-editable allowlist of `(provider, model_id)` pairs eligible for generation.
Providers are a code-fixed enum (the CHECK constraint); only the model id within a
provider is admin-managed. `mock` is never allowlisted: it is a CI-only test
double, never a real generation backend.

| Column | Type | Notes |
|--------|------|-------|
| id | UUID PK | |
| provider | VARCHAR(32) | One of `anthropic`, `openrouter`, `modal`, `ollama` |
| model_id | VARCHAR(120) | Provider-native model id (e.g. `claude-sonnet-4-6`) |
| enabled | BOOLEAN | Whether this pair is currently selectable; default true |
| display_name | VARCHAR(120) NULL | Optional human label for a future admin UI |
| created_by | UUID FK NULL | user.id of admin who added this row |
| updated_by | UUID FK NULL | user.id of admin who last edited this row |
| created_at | TIMESTAMPTZ | |
| updated_at | TIMESTAMPTZ | `onupdate=func.now()` |

A unique constraint on `(provider, model_id)` enforces at most one row per pair.
Disabling a row (rather than deleting it) preserves audit history.

### `provider_model_allowlist_audit`

Append-only audit of `provider_model_allowlist` edits (who changed what, when),
mirroring `moderation_threshold_audit`.

| Column | Type | Notes |
|--------|------|-------|
| id | UUID PK | |
| provider | VARCHAR(32) | Affected row's provider (natural-key half) |
| model_id | VARCHAR(120) | Affected row's model id (natural-key half) |
| action | VARCHAR(16) | `create`, `update`, or `delete` |
| old_enabled | BOOLEAN NULL | `enabled` value before the edit; NULL on create |
| new_enabled | BOOLEAN NULL | `enabled` value after the edit; NULL on delete |
| changed_by | UUID FK | user.id of admin who made the edit; NOT NULL |
| changed_at | TIMESTAMPTZ | Server default |

## Authorization Pattern

Family ownership is checked on every resource. The `Principal` in `api/deps.py` carries
`family_id` and `profile_ids`. Every endpoint calls `authorize_family()` and/or
`authorize_profile()` before touching any row. See
`docs/planning/authorization-matrix.md` for the full access matrix.
