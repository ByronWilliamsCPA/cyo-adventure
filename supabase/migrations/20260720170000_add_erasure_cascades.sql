-- GDPR Article 17 / COPPA 312.10 erasure support (remediation plan Phase 3a).
--
-- Every FK in the schema up to this migration is Postgres default NO ACTION:
-- deleting a family or child profile would fail with a foreign-key violation
-- the moment any dependent row exists. This migration adds ON DELETE CASCADE
-- to every family-/child-profile-owned content edge (so a family or profile
-- delete removes its own data atomically) and ON DELETE SET NULL to
-- attribution-only edges (*_by/*_id columns recording who touched a row,
-- where the row itself is not owned by the deleted actor).
--
-- Three edges are deliberately left untouched or handled specially; see the
-- matching #CRITICAL comments on the ORM side (src/cyo_adventure/db/models.py)
-- for the full reasoning, summarized here:
--   1. pipeline_event.actor_id: the FK is DROPPED entirely, not SET NULL.
--      pipeline_event is enforced append-only by a trigger that rejects any
--      UPDATE, and ON DELETE SET NULL is implemented as an UPDATE -- it would
--      be blocked by that same trigger, which would in turn block deleting
--      any user who has ever authored an event. actor_id carries no PII (the
--      payload allowlist already excludes it), so there is no privacy need to
--      null it, only a referential-integrity one that dropping the FK solves
--      without touching the trigger.
--   2. storybook.series_id, story_request.series_id, kid_flag.resolved_by,
--      family_connection.consented_by_{viewer,sharer}_user_id: each is
--      paired with a sibling column by a CHECK constraint (e.g.
--      ck_kid_flag_resolved_pairing), so a bare SET NULL on the FK column
--      alone would violate that CHECK the instant the cascade fires. The
--      series_id cases are provably unreachable (the owning row always
--      cascades away via family_id first); kid_flag.resolved_by is reachable
--      in practice (a resolving admin need not be in the flagged family) and
--      is handled by an explicit application-level UPDATE before delete (see
--      api/families.py's delete-family service).
--   3. device_grant.authorized_by (NOT NULL): left NO ACTION. The
--      authorizing guardian is always in the same family as the grant, which
--      is deleted via the same top-level family cascade (a sibling path, not
--      a chain through this column), so this NOT NULL FK never independently
--      blocks a delete.
--
-- moderation_threshold_audit.changed_by and provider_model_allowlist_audit.
-- changed_by are additionally relaxed from NOT NULL to nullable: both are
-- global admin-config audit tables (unrelated to any family/child data), but
-- their changed_by FK would otherwise block deleting any admin/guardian who
-- has ever edited a threshold or allowlist entry, even via their own
-- family's self-deletion. The audit row (what changed, when) survives;
-- only the "who" attribution is dropped.
--
-- Forward-only migration per this project's Supabase CLI convention
-- (ADR-012); no down script. Every change here is mirrored in
-- src/cyo_adventure/db/models.py's `ondelete=` kwargs, kept in parity by
-- tests/integration/test_schema_parity.py.

-- ---------------------------------------------------------------------
-- CASCADE: family-owned content, deleted along with the family.
-- ---------------------------------------------------------------------

alter table only "public"."series" drop constraint if exists "series_family_id_fkey";
alter table only "public"."series"
    add constraint "series_family_id_fkey" foreign key ("family_id")
    references "public"."family"("id") on delete cascade;

alter table only "public"."user" drop constraint if exists "user_family_id_fkey";
alter table only "public"."user"
    add constraint "user_family_id_fkey" foreign key ("family_id")
    references "public"."family"("id") on delete cascade;

alter table only "public"."child_profile" drop constraint if exists "child_profile_family_id_fkey";
alter table only "public"."child_profile"
    add constraint "child_profile_family_id_fkey" foreign key ("family_id")
    references "public"."family"("id") on delete cascade;

alter table only "public"."family_connection" drop constraint if exists "family_connection_family_id_fkey";
alter table only "public"."family_connection"
    add constraint "family_connection_family_id_fkey" foreign key ("family_id")
    references "public"."family"("id") on delete cascade;

alter table only "public"."family_connection" drop constraint if exists "family_connection_connected_family_id_fkey";
alter table only "public"."family_connection"
    add constraint "family_connection_connected_family_id_fkey" foreign key ("connected_family_id")
    references "public"."family"("id") on delete cascade;

alter table only "public"."storybook" drop constraint if exists "storybook_family_id_fkey";
alter table only "public"."storybook"
    add constraint "storybook_family_id_fkey" foreign key ("family_id")
    references "public"."family"("id") on delete cascade;

alter table only "public"."concept" drop constraint if exists "concept_family_id_fkey";
alter table only "public"."concept"
    add constraint "concept_family_id_fkey" foreign key ("family_id")
    references "public"."family"("id") on delete cascade;

alter table only "public"."story_request" drop constraint if exists "story_request_family_id_fkey";
alter table only "public"."story_request"
    add constraint "story_request_family_id_fkey" foreign key ("family_id")
    references "public"."family"("id") on delete cascade;

alter table only "public"."device_grant" drop constraint if exists "device_grant_family_id_fkey";
alter table only "public"."device_grant"
    add constraint "device_grant_family_id_fkey" foreign key ("family_id")
    references "public"."family"("id") on delete cascade;

alter table only "public"."kid_flag" drop constraint if exists "kid_flag_family_id_fkey";
alter table only "public"."kid_flag"
    add constraint "kid_flag_family_id_fkey" foreign key ("family_id")
    references "public"."family"("id") on delete cascade;

-- ---------------------------------------------------------------------
-- CASCADE: child-profile-owned data, deleted along with the profile.
-- ---------------------------------------------------------------------

alter table only "public"."user" drop constraint if exists "user_child_profile_id_fkey";
alter table only "public"."user"
    add constraint "user_child_profile_id_fkey" foreign key ("child_profile_id")
    references "public"."child_profile"("id") on delete cascade;

alter table only "public"."reading_state" drop constraint if exists "reading_state_child_profile_id_fkey";
alter table only "public"."reading_state"
    add constraint "reading_state_child_profile_id_fkey" foreign key ("child_profile_id")
    references "public"."child_profile"("id") on delete cascade;

alter table only "public"."completion" drop constraint if exists "completion_child_profile_id_fkey";
alter table only "public"."completion"
    add constraint "completion_child_profile_id_fkey" foreign key ("child_profile_id")
    references "public"."child_profile"("id") on delete cascade;

alter table only "public"."rating" drop constraint if exists "rating_child_profile_id_fkey";
alter table only "public"."rating"
    add constraint "rating_child_profile_id_fkey" foreign key ("child_profile_id")
    references "public"."child_profile"("id") on delete cascade;

alter table only "public"."storybook_assignment" drop constraint if exists "storybook_assignment_child_profile_id_fkey";
alter table only "public"."storybook_assignment"
    add constraint "storybook_assignment_child_profile_id_fkey" foreign key ("child_profile_id")
    references "public"."child_profile"("id") on delete cascade;

alter table only "public"."kid_flag" drop constraint if exists "kid_flag_profile_id_fkey";
alter table only "public"."kid_flag"
    add constraint "kid_flag_profile_id_fkey" foreign key ("profile_id")
    references "public"."child_profile"("id") on delete cascade;

-- ---------------------------------------------------------------------
-- CASCADE: storybook-owned data, deleted along with the storybook.
-- ---------------------------------------------------------------------

alter table only "public"."storybook_version" drop constraint if exists "storybook_version_storybook_id_fkey";
alter table only "public"."storybook_version"
    add constraint "storybook_version_storybook_id_fkey" foreign key ("storybook_id")
    references "public"."storybook"("id") on delete cascade;

alter table only "public"."reading_state" drop constraint if exists "reading_state_storybook_id_fkey";
alter table only "public"."reading_state"
    add constraint "reading_state_storybook_id_fkey" foreign key ("storybook_id")
    references "public"."storybook"("id") on delete cascade;

alter table only "public"."reading_state" drop constraint if exists "reading_state_storybook_id_version_fkey";
alter table only "public"."reading_state"
    add constraint "reading_state_storybook_id_version_fkey" foreign key ("storybook_id", "version")
    references "public"."storybook_version"("storybook_id", "version") on delete cascade;

alter table only "public"."completion" drop constraint if exists "completion_storybook_id_version_fkey";
alter table only "public"."completion"
    add constraint "completion_storybook_id_version_fkey" foreign key ("storybook_id", "version")
    references "public"."storybook_version"("storybook_id", "version") on delete cascade;

alter table only "public"."rating" drop constraint if exists "rating_storybook_id_fkey";
alter table only "public"."rating"
    add constraint "rating_storybook_id_fkey" foreign key ("storybook_id")
    references "public"."storybook"("id") on delete cascade;

alter table only "public"."storybook_assignment" drop constraint if exists "storybook_assignment_storybook_id_fkey";
alter table only "public"."storybook_assignment"
    add constraint "storybook_assignment_storybook_id_fkey" foreign key ("storybook_id")
    references "public"."storybook"("id") on delete cascade;

alter table only "public"."kid_flag" drop constraint if exists "kid_flag_storybook_id_fkey";
alter table only "public"."kid_flag"
    add constraint "kid_flag_storybook_id_fkey" foreign key ("storybook_id")
    references "public"."storybook"("id") on delete cascade;

alter table only "public"."kid_flag" drop constraint if exists "kid_flag_storybook_id_version_fkey";
alter table only "public"."kid_flag"
    add constraint "kid_flag_storybook_id_version_fkey" foreign key ("storybook_id", "version")
    references "public"."storybook_version"("storybook_id", "version") on delete cascade;

-- ---------------------------------------------------------------------
-- CASCADE: NOT NULL FKs that would otherwise block a family/concept delete.
-- ---------------------------------------------------------------------

alter table only "public"."generation_job" drop constraint if exists "generation_job_concept_id_fkey";
alter table only "public"."generation_job"
    add constraint "generation_job_concept_id_fkey" foreign key ("concept_id")
    references "public"."concept"("id") on delete cascade;

-- ---------------------------------------------------------------------
-- SET NULL: attribution-only edges (who touched a row the deleted actor
-- does not own).
-- ---------------------------------------------------------------------

alter table only "public"."series" drop constraint if exists "series_created_by_fkey";
alter table only "public"."series"
    add constraint "series_created_by_fkey" foreign key ("created_by")
    references "public"."user"("id") on delete set null;

alter table only "public"."storybook" drop constraint if exists "storybook_created_by_fkey";
alter table only "public"."storybook"
    add constraint "storybook_created_by_fkey" foreign key ("created_by")
    references "public"."user"("id") on delete set null;

alter table only "public"."storybook_version" drop constraint if exists "storybook_version_approved_by_fkey";
alter table only "public"."storybook_version"
    add constraint "storybook_version_approved_by_fkey" foreign key ("approved_by")
    references "public"."user"("id") on delete set null;

alter table only "public"."concept" drop constraint if exists "concept_created_by_fkey";
alter table only "public"."concept"
    add constraint "concept_created_by_fkey" foreign key ("created_by")
    references "public"."user"("id") on delete set null;

alter table only "public"."story_request" drop constraint if exists "story_request_profile_id_fkey";
alter table only "public"."story_request"
    add constraint "story_request_profile_id_fkey" foreign key ("profile_id")
    references "public"."child_profile"("id") on delete set null;

alter table only "public"."story_request" drop constraint if exists "story_request_reviewed_by_fkey";
alter table only "public"."story_request"
    add constraint "story_request_reviewed_by_fkey" foreign key ("reviewed_by")
    references "public"."user"("id") on delete set null;

alter table only "public"."story_request" drop constraint if exists "story_request_concept_id_fkey";
alter table only "public"."story_request"
    add constraint "story_request_concept_id_fkey" foreign key ("concept_id")
    references "public"."concept"("id") on delete set null;

alter table only "public"."story_request" drop constraint if exists "fk_story_request_anchor_storybook_id_storybook";
alter table only "public"."story_request"
    add constraint "fk_story_request_anchor_storybook_id_storybook" foreign key ("anchor_storybook_id")
    references "public"."storybook"("id") on delete set null;

alter table only "public"."storybook_assignment" drop constraint if exists "storybook_assignment_assigned_by_fkey";
alter table only "public"."storybook_assignment"
    add constraint "storybook_assignment_assigned_by_fkey" foreign key ("assigned_by")
    references "public"."user"("id") on delete set null;

alter table only "public"."moderation_threshold" drop constraint if exists "moderation_threshold_updated_by_fkey";
alter table only "public"."moderation_threshold"
    add constraint "moderation_threshold_updated_by_fkey" foreign key ("updated_by")
    references "public"."user"("id") on delete set null;

alter table only "public"."moderation_setting" drop constraint if exists "moderation_setting_updated_by_fkey";
alter table only "public"."moderation_setting"
    add constraint "moderation_setting_updated_by_fkey" foreign key ("updated_by")
    references "public"."user"("id") on delete set null;

alter table only "public"."provider_model_allowlist" drop constraint if exists "provider_model_allowlist_created_by_fkey";
alter table only "public"."provider_model_allowlist"
    add constraint "provider_model_allowlist_created_by_fkey" foreign key ("created_by")
    references "public"."user"("id") on delete set null;

alter table only "public"."provider_model_allowlist" drop constraint if exists "provider_model_allowlist_updated_by_fkey";
alter table only "public"."provider_model_allowlist"
    add constraint "provider_model_allowlist_updated_by_fkey" foreign key ("updated_by")
    references "public"."user"("id") on delete set null;

alter table only "public"."family_connection" drop constraint if exists "family_connection_created_by_fkey";
alter table only "public"."family_connection"
    add constraint "family_connection_created_by_fkey" foreign key ("created_by")
    references "public"."user"("id") on delete set null;

-- ---------------------------------------------------------------------
-- SET NULL + relax NOT NULL: audit tables whose changed_by would otherwise
-- block an admin/guardian's own erasure.
-- ---------------------------------------------------------------------

alter table "public"."moderation_threshold_audit" alter column "changed_by" drop not null;
alter table only "public"."moderation_threshold_audit" drop constraint if exists "moderation_threshold_audit_changed_by_fkey";
alter table only "public"."moderation_threshold_audit"
    add constraint "moderation_threshold_audit_changed_by_fkey" foreign key ("changed_by")
    references "public"."user"("id") on delete set null;

alter table "public"."provider_model_allowlist_audit" alter column "changed_by" drop not null;
alter table only "public"."provider_model_allowlist_audit" drop constraint if exists "provider_model_allowlist_audit_changed_by_fkey";
alter table only "public"."provider_model_allowlist_audit"
    add constraint "provider_model_allowlist_audit_changed_by_fkey" foreign key ("changed_by")
    references "public"."user"("id") on delete set null;

-- ---------------------------------------------------------------------
-- DROP entirely: pipeline_event.actor_id is no longer FK-enforced (see the
-- header comment). The column, its index, and its CHECK constraints are
-- untouched; only referential integrity against user.id is removed.
-- ---------------------------------------------------------------------

alter table only "public"."pipeline_event" drop constraint if exists "pipeline_event_actor_id_fkey";
