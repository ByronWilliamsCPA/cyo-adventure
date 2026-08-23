-- R-11 human-gate measurement (docs/planning/generation-review-workstream-plan-2026-08-22.md
-- Step 3): widen pipeline_event to record a story ENTERING the review queue
-- (publishing/service.py::submit). Adds 'submitted' to event_type; the entity_type it
-- anchors to ('storybook') is already in the entity_type CHECK list, so only event_type
-- changes here. Kept in sync with cyo_adventure.events.models.EventType (see the drift
-- guard in tests/unit/test_pipeline_event_check_vocab.py).
--
-- Why the event is needed at all: MODERATION_COMPLETED marks the FIRST entry to the gate
-- only. POST /storybooks/{id}/submit re-runs no moderation, so a story resubmitted after a
-- send-back re-enters the queue with no durable start timestamp, and every review round past
-- the first has an unmeasurable duration. The actor separates the pipeline's own submit
-- (system) from a human resubmission.
--
-- #CRITICAL: data integrity: every prior migration that touched this CHECK constraint
-- replaces it wholesale with an absolute value list (see 20260717120000_add_kid_flag.sql's
-- header comment for why). The list below is therefore the full cumulative set as of
-- 20260809100000_add_notification_digest_ready_to_pipeline_event.sql, plus 'submitted'.
-- #VERIFY: tests/unit/test_pipeline_event_check_vocab.py's drift guard pins the event_type
-- list against cyo_adventure.db.models._PIPELINE_EVENT_TYPE_VALUES.
--
-- #CRITICAL: data integrity: because these migrations carry absolute lists, filename order
-- is load-bearing. This file must sort after every existing migration; if a later merge
-- introduces another migration touching this same CHECK constraint with an earlier
-- timestamp, it will silently drop 'submitted' back out.
-- #VERIFY: any future migration replacing ck_pipeline_event_event_type must sort after
-- every existing one and must carry the full cumulative list.
--
-- Written to be idempotent (checks the current constraint definition before acting),
-- mirroring 20260809100000_add_notification_digest_ready_to_pipeline_event.sql, so it is a
-- no-op if applied a second time or if the constraint already includes its new value.
DO $$
BEGIN
    IF EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conname = 'ck_pipeline_event_event_type'
          AND conrelid = '"public"."pipeline_event"'::regclass
          AND pg_get_constraintdef(oid) NOT LIKE '%''submitted''%'
    ) THEN
        ALTER TABLE "public"."pipeline_event"
            DROP CONSTRAINT "ck_pipeline_event_event_type";
        ALTER TABLE "public"."pipeline_event"
            ADD CONSTRAINT "ck_pipeline_event_event_type"
            CHECK ((("event_type")::"text" = ANY ((ARRAY['request_created'::character varying, 'request_approved'::character varying, 'request_declined'::character varying, 'plan_assigned'::character varying, 'generation_started'::character varying, 'generation_finished'::character varying, 'moderation_completed'::character varying, 'repair_applied'::character varying, 'sent_back'::character varying, 'released'::character varying, 'threshold_changed'::character varying, 'noise_floor_changed'::character varying, 'book_assigned'::character varying, 'book_unassigned'::character varying, 'rated'::character varying, 'kid_flagged'::character varying, 'flag_resolved'::character varying, 'user_managed'::character varying, 'family_managed'::character varying, 'family_connection_changed'::character varying, 'node_edited'::character varying, 'profile_viewed'::character varying, 'cell_saturated'::character varying, 'personalization_toggled'::character varying, 'ring2_consent_granted'::character varying, 'ring2_consent_revoked'::character varying, 'storybook_archived'::character varying, 'storybook_remoderated'::character varying, 'notification_digest_ready'::character varying, 'submitted'::character varying])::"text"[])));
    END IF;
END
$$;
