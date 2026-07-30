-- A5 incident/pull-everywhere path (capability-register.md): widen
-- pipeline_event to record an admin archiving a published story
-- (publishing/service.py::archive), the sole published->archived hop and the
-- only server-side action that pulls a story from every child's shelf. Adds
-- 'storybook_archived' to event_type; the entity_type it anchors to
-- ('storybook') is already in the entity_type CHECK list (shared with
-- 'released'), so only event_type changes here. Kept in sync with
-- cyo_adventure.events.models.EventType (see the drift guard in
-- tests/unit/test_pipeline_event_check_vocab.py).
--
-- #CRITICAL: data integrity: every prior migration that touched this CHECK
-- constraint replaces it wholesale with an absolute value list (see
-- 20260717120000_add_kid_flag.sql's header comment for why). The list below is
-- therefore the full cumulative set as of this migration, plus
-- 'storybook_archived'.
-- #VERIFY: tests/unit/test_pipeline_event_check_vocab.py's drift guard pins the
-- event_type list against cyo_adventure.db.models._PIPELINE_EVENT_TYPE_VALUES.
--
-- #CRITICAL: data integrity: because these migrations carry absolute lists,
-- filename order is load-bearing. This file was authored as 20260728220000 and
-- renumbered to 20260729050000 when it merged with main's ADR-023 P3/P4 work
-- (20260729020000_add_personalization_event_types.sql). At the original
-- timestamp it would have run FIRST on a fresh database, and the
-- personalization migration would then have dropped 'storybook_archived' back
-- out; on an already-migrated database it would have dropped main's three
-- personalization values instead. Neither side's idempotency guard catches
-- that, because each guard only tests for its own new value.
-- #VERIFY: any future migration replacing ck_pipeline_event_event_type must
-- sort after every existing one and must carry the full cumulative list.
--
-- Written to be idempotent (checks the current constraint definition before
-- acting), mirroring 20260727000000_add_book_unassigned_to_pipeline_event.sql,
-- so it is a no-op if applied a second time or if the constraint already
-- includes its new value.
DO $$
BEGIN
    IF EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conname = 'ck_pipeline_event_event_type'
          AND conrelid = '"public"."pipeline_event"'::regclass
          AND pg_get_constraintdef(oid) NOT LIKE '%''storybook_archived''%'
    ) THEN
        ALTER TABLE "public"."pipeline_event"
            DROP CONSTRAINT "ck_pipeline_event_event_type";
        ALTER TABLE "public"."pipeline_event"
            ADD CONSTRAINT "ck_pipeline_event_event_type"
            CHECK ((("event_type")::"text" = ANY ((ARRAY['request_created'::character varying, 'request_approved'::character varying, 'request_declined'::character varying, 'plan_assigned'::character varying, 'generation_started'::character varying, 'generation_finished'::character varying, 'moderation_completed'::character varying, 'repair_applied'::character varying, 'sent_back'::character varying, 'released'::character varying, 'threshold_changed'::character varying, 'noise_floor_changed'::character varying, 'book_assigned'::character varying, 'book_unassigned'::character varying, 'rated'::character varying, 'kid_flagged'::character varying, 'flag_resolved'::character varying, 'user_managed'::character varying, 'family_managed'::character varying, 'family_connection_changed'::character varying, 'node_edited'::character varying, 'profile_viewed'::character varying, 'cell_saturated'::character varying, 'personalization_toggled'::character varying, 'ring2_consent_granted'::character varying, 'ring2_consent_revoked'::character varying, 'storybook_archived'::character varying])::"text"[])));
    END IF;
END
$$;
