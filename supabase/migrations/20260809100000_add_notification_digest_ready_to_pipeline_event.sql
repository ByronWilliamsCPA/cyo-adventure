-- S9 server-scheduled digest job (docs/planning/roadmap.md Phase 4c; capability register
-- S9): widen pipeline_event to record a periodic, batched per-family notification digest,
-- distinct from the real-time poll/SSE feed (notifications/digest.py::run_notification_digest).
-- Adds 'notification_digest_ready' to event_type; the entity_type it anchors to ('family') is
-- already in the entity_type CHECK list, so only event_type changes here. Kept in sync with
-- cyo_adventure.events.models.EventType (see the drift guard in
-- tests/unit/test_pipeline_event_check_vocab.py).
--
-- #CRITICAL: data integrity: every prior migration that touched this CHECK constraint
-- replaces it wholesale with an absolute value list (see 20260717120000_add_kid_flag.sql's
-- header comment for why). The list below is therefore the full cumulative set as of this
-- migration, plus 'notification_digest_ready'.
-- #VERIFY: tests/unit/test_pipeline_event_check_vocab.py's drift guard pins the event_type
-- list against cyo_adventure.db.models._PIPELINE_EVENT_TYPE_VALUES.
--
-- #CRITICAL: data integrity: because these migrations carry absolute lists, filename order
-- is load-bearing. This file must sort after every existing migration; if a later merge
-- introduces another migration touching this same CHECK constraint with an earlier
-- timestamp, it will silently drop 'notification_digest_ready' back out.
-- #VERIFY: any future migration replacing ck_pipeline_event_event_type must sort after
-- every existing one and must carry the full cumulative list.
--
-- Written to be idempotent (checks the current constraint definition before acting),
-- mirroring 20260731000000_add_storybook_remoderated_to_pipeline_event.sql, so it is a
-- no-op if applied a second time or if the constraint already includes its new value.
DO $$
BEGIN
    IF EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conname = 'ck_pipeline_event_event_type'
          AND conrelid = '"public"."pipeline_event"'::regclass
          AND pg_get_constraintdef(oid) NOT LIKE '%''notification_digest_ready''%'
    ) THEN
        ALTER TABLE "public"."pipeline_event"
            DROP CONSTRAINT "ck_pipeline_event_event_type";
        ALTER TABLE "public"."pipeline_event"
            ADD CONSTRAINT "ck_pipeline_event_event_type"
            CHECK ((("event_type")::"text" = ANY ((ARRAY['request_created'::character varying, 'request_approved'::character varying, 'request_declined'::character varying, 'plan_assigned'::character varying, 'generation_started'::character varying, 'generation_finished'::character varying, 'moderation_completed'::character varying, 'repair_applied'::character varying, 'sent_back'::character varying, 'released'::character varying, 'threshold_changed'::character varying, 'noise_floor_changed'::character varying, 'book_assigned'::character varying, 'book_unassigned'::character varying, 'rated'::character varying, 'kid_flagged'::character varying, 'flag_resolved'::character varying, 'user_managed'::character varying, 'family_managed'::character varying, 'family_connection_changed'::character varying, 'node_edited'::character varying, 'profile_viewed'::character varying, 'cell_saturated'::character varying, 'personalization_toggled'::character varying, 'ring2_consent_granted'::character varying, 'ring2_consent_revoked'::character varying, 'storybook_archived'::character varying, 'storybook_remoderated'::character varying, 'notification_digest_ready'::character varying])::"text"[])));
    END IF;
END
$$;
