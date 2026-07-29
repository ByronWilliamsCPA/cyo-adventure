-- ADR-023 P4/P5 (story personalization, Task B6): widen pipeline_event's
-- entity_type CHECK to cover the two new entities the personalization API
-- (src/cyo_adventure/api/personalization.py) writes events against:
-- 'child_profile_personalization' (a slot toggle/edit, PERSONALIZATION_TOGGLED)
-- and 'personalization_consent' (a ring-2 disclosure consent grant/revoke,
-- RING2_CONSENT_GRANTED/RING2_CONSENT_REVOKED). The latter is deliberately
-- shorter than the ORM table name PersonalizationDisclosureConsent maps to
-- ("personalization_disclosure_consent" is 35 characters, too long for
-- entity_type's existing varchar(32) column) rather than widening the
-- column, since no other entity_type value is close to that width and a
-- shorter label reads just as clearly in the audit log.
--
-- 20260729020000_add_personalization_event_types.sql added the paired
-- event_type values but this entity_type addition was missed at the time;
-- this migration closes that gap. Kept in sync with
-- cyo_adventure.db.models._PIPELINE_ENTITY_TYPE_VALUES (there is no drift
-- guard test for entity_type; see the module docstring in
-- tests/unit/test_pipeline_event_check_vocab.py for why entity_type has no
-- enum source to derive from).
--
-- #CRITICAL: data integrity: every prior migration that touched this CHECK
-- constraint replaces it wholesale with an absolute value list (see
-- 20260717120000_add_kid_flag.sql's header comment for why). The list below
-- is therefore the full cumulative set as of
-- 20260720120000_add_profile_viewed_to_pipeline_event.sql, plus this
-- migration's two additions.
-- #VERIFY: tests/integration/test_personalization_api.py exercises both new
-- entity_type values via record_event calls in
-- src/cyo_adventure/api/personalization.py.
--
-- Written to be idempotent (checks the current constraint definition before
-- acting), mirroring 20260729020000_add_personalization_event_types.sql, so
-- it is a no-op if applied a second time or if the constraint already
-- includes its new values.
-- Converge on the widened CHECK from any starting state. The guard is
-- three-way on purpose:
--   already widened -> do nothing (the re-run case this guard exists for);
--   present but narrow -> drop and re-add;
--   absent entirely -> add it.
-- An earlier revision tested only "present but narrow", so a database that
-- had lost the constraint silently stayed unconstrained: the migration
-- reported success while leaving entity_type accepting anything at all.
-- Skipping work you were asked to do is not idempotency.
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conname = 'ck_pipeline_event_entity_type'
          AND conrelid = '"public"."pipeline_event"'::regclass
          AND pg_get_constraintdef(oid) LIKE '%''personalization_consent''%'
    ) THEN
        ALTER TABLE "public"."pipeline_event"
            DROP CONSTRAINT IF EXISTS "ck_pipeline_event_entity_type";
        ALTER TABLE "public"."pipeline_event"
            ADD CONSTRAINT "ck_pipeline_event_entity_type"
            CHECK ((("entity_type")::"text" = ANY ((ARRAY['story_request'::character varying, 'generation_job'::character varying, 'storybook'::character varying, 'storybook_version'::character varying, 'series'::character varying, 'storybook_assignment'::character varying, 'rating'::character varying, 'moderation_threshold'::character varying, 'moderation_setting'::character varying, 'kid_flag'::character varying, 'user'::character varying, 'family'::character varying, 'family_connection'::character varying, 'child_profile'::character varying, 'child_profile_personalization'::character varying, 'personalization_consent'::character varying])::"text"[])));
    END IF;
END
$$;
