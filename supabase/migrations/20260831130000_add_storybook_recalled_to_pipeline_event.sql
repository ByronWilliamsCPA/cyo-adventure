-- `RS-C1` (docs/planning/review-screen-remediation-plan-2026-08-31.md section 8): widen
-- pipeline_event to record a published book being RECALLED back to the human review gate
-- (publishing/service.py::recall, the sole published->in_review hop per
-- publishing/state_machine.py). Adds 'storybook_recalled' to event_type; the entity_type it
-- anchors to ('storybook') is already in the entity_type CHECK list, so only event_type
-- changes here. Kept in sync with cyo_adventure.events.models.EventType (see the drift
-- guard in tests/unit/test_pipeline_event_check_vocab.py).
--
-- Why a distinct event rather than reusing an existing one: STORYBOOK_ARCHIVED means the
-- book's life ended (archived is absorbing), and SENT_BACK means a reviewer rejected a book
-- that was never published. A recall is neither, and its payload carries a reason_code from
-- a vocabulary only a published book can draw on ('threshold_change'), which is what lets a
-- later reader tell a threshold-driven recheck from a safety pull. The archive composer's
-- own docstring (notifications/registry.py) records not being able to make that distinction
-- as a limitation it had to alert on unconditionally.
--
-- #CRITICAL: data integrity: every prior migration that touched this CHECK constraint
-- replaces it wholesale with an absolute value list (see 20260717120000_add_kid_flag.sql's
-- header comment for why). The list below is therefore the full cumulative set as of
-- 20260823120000_add_submitted_to_pipeline_event.sql, plus 'storybook_recalled'.
-- #VERIFY: tests/unit/test_pipeline_event_check_vocab.py::
-- test_newest_event_type_check_migration_carries_full_vocab pins this file's list against
-- the EventType enum, and resolves "newest" dynamically rather than by filename.
--
-- #CRITICAL: data integrity: because these migrations carry absolute lists, filename order
-- is load-bearing. This file must sort after every existing migration; a later merge that
-- introduces another migration replacing this same CHECK with an earlier timestamp will
-- silently drop 'storybook_recalled' back out, and the application will start failing every
-- recall with a CHECK violation at INSERT time (which is exactly how this constraint was
-- discovered during `RS-C1`: the Python enum, the writer's payload allowlist and the ORM
-- mirror were all updated, and the database still refused the row).
-- #VERIFY: any future migration replacing ck_pipeline_event_event_type must sort after
-- every existing one and must carry the full cumulative list.
--
-- Re-application safe by convergence rather than by inspection: DROP CONSTRAINT IF EXISTS
-- then an unconditional ADD, matching 20260823120000. A conditional guard would take the
-- false branch on a database missing the constraint entirely and report success having left
-- the column unconstrained.
ALTER TABLE "public"."pipeline_event"
    DROP CONSTRAINT IF EXISTS "ck_pipeline_event_event_type";
ALTER TABLE "public"."pipeline_event"
    ADD CONSTRAINT "ck_pipeline_event_event_type"
    CHECK ((("event_type")::"text" = ANY ((ARRAY['request_created'::character varying, 'request_approved'::character varying, 'request_declined'::character varying, 'plan_assigned'::character varying, 'generation_started'::character varying, 'generation_finished'::character varying, 'moderation_completed'::character varying, 'repair_applied'::character varying, 'sent_back'::character varying, 'released'::character varying, 'threshold_changed'::character varying, 'noise_floor_changed'::character varying, 'book_assigned'::character varying, 'book_unassigned'::character varying, 'rated'::character varying, 'kid_flagged'::character varying, 'flag_resolved'::character varying, 'user_managed'::character varying, 'family_managed'::character varying, 'family_connection_changed'::character varying, 'node_edited'::character varying, 'profile_viewed'::character varying, 'cell_saturated'::character varying, 'personalization_toggled'::character varying, 'ring2_consent_granted'::character varying, 'ring2_consent_revoked'::character varying, 'storybook_archived'::character varying, 'storybook_remoderated'::character varying, 'notification_digest_ready'::character varying, 'submitted'::character varying, 'storybook_recalled'::character varying])::"text"[])));
