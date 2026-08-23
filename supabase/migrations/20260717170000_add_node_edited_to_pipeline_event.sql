-- G6: the lightweight passage editor with re-review widens
-- pipeline_event.event_type to accept 'node_edited', the append-only audit
-- record of a prose-only node edit (payload carries the node id only, never
-- the edited prose; api/node_edit.py). Kept in sync with
-- cyo_adventure.events.models.EventType (see the drift guard in
-- tests/unit/test_pipeline_event_check_vocab.py).
--
-- #CRITICAL: data integrity: every prior migration that touched this CHECK
-- replaces it wholesale with an absolute value list (see
-- 20260717120000_add_kid_flag.sql's header comment for why). The list below
-- is therefore the full cumulative set as of this migration (everything
-- 20260717120000_add_kid_flag.sql last established), plus 'node_edited', not
-- just this migration's own addition.
-- #VERIFY: tests/unit/test_pipeline_event_check_vocab.py's drift guard pins
-- the event_type list against cyo_adventure.events.models.EventType.
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
    CHECK ((("event_type")::"text" = ANY ((ARRAY['request_created'::character varying, 'request_approved'::character varying, 'request_declined'::character varying, 'plan_assigned'::character varying, 'generation_started'::character varying, 'generation_finished'::character varying, 'moderation_completed'::character varying, 'repair_applied'::character varying, 'sent_back'::character varying, 'released'::character varying, 'threshold_changed'::character varying, 'noise_floor_changed'::character varying, 'book_assigned'::character varying, 'rated'::character varying, 'kid_flagged'::character varying, 'flag_resolved'::character varying, 'user_managed'::character varying, 'family_managed'::character varying, 'family_connection_changed'::character varying, 'node_edited'::character varying])::"text"[])));
