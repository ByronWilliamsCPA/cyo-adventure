-- Phase 8a (GDPR Article 30 accountability): widen pipeline_event to record
-- an admin's cross-family read of child-linked data
-- (api/admin_profiles.py::list_admin_profiles), the first READ this audit
-- log covers -- every other event_type value logs a mutation. Adds
-- 'profile_viewed' to event_type and 'child_profile' to entity_type. Kept
-- in sync with cyo_adventure.events.models.EventType and
-- cyo_adventure.db.models._PIPELINE_ENTITY_TYPE_VALUES (see the drift guard
-- in tests/unit/test_pipeline_event_check_vocab.py).
--
-- #CRITICAL: data integrity: every prior migration that touched these CHECK
-- constraints replaces them wholesale with an absolute value list (see
-- 20260717120000_add_kid_flag.sql's header comment for why). The lists below
-- are therefore the full cumulative set as of this migration, plus this
-- migration's own additions.
-- #VERIFY: tests/unit/test_pipeline_event_check_vocab.py's drift guard pins
-- both lists against cyo_adventure.db.models.
--
-- Re-application safe by convergence rather than by inspection: DROP CONSTRAINT
-- IF EXISTS then an unconditional ADD. The guard this replaced acted only when
-- the constraint existed AND lacked the new value, so a database missing it
-- entirely took the false branch and the migration reported success having left
-- the column unconstrained. ADD CONSTRAINT revalidates the table, which is a
-- one-off scan because each file applies once.
ALTER TABLE "public"."pipeline_event"
    DROP CONSTRAINT IF EXISTS "ck_pipeline_event_event_type";
ALTER TABLE "public"."pipeline_event"
    ADD CONSTRAINT "ck_pipeline_event_event_type"
    CHECK ((("event_type")::"text" = ANY ((ARRAY['request_created'::character varying, 'request_approved'::character varying, 'request_declined'::character varying, 'plan_assigned'::character varying, 'generation_started'::character varying, 'generation_finished'::character varying, 'moderation_completed'::character varying, 'repair_applied'::character varying, 'sent_back'::character varying, 'released'::character varying, 'threshold_changed'::character varying, 'noise_floor_changed'::character varying, 'book_assigned'::character varying, 'rated'::character varying, 'kid_flagged'::character varying, 'flag_resolved'::character varying, 'user_managed'::character varying, 'family_managed'::character varying, 'family_connection_changed'::character varying, 'node_edited'::character varying, 'profile_viewed'::character varying])::"text"[])));

ALTER TABLE "public"."pipeline_event"
    DROP CONSTRAINT IF EXISTS "ck_pipeline_event_entity_type";
ALTER TABLE "public"."pipeline_event"
    ADD CONSTRAINT "ck_pipeline_event_entity_type"
    CHECK ((("entity_type")::"text" = ANY ((ARRAY['story_request'::character varying, 'generation_job'::character varying, 'storybook'::character varying, 'storybook_version'::character varying, 'series'::character varying, 'storybook_assignment'::character varying, 'rating'::character varying, 'moderation_threshold'::character varying, 'moderation_setting'::character varying, 'kid_flag'::character varying, 'user'::character varying, 'family'::character varying, 'family_connection'::character varying, 'child_profile'::character varying])::"text"[])));
