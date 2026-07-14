-- ADR-014 phase 1: widen the pipeline_event.actor_role CHECK constraint to
-- accept 'device', keeping it in sync with the api.deps.Role enum (which now
-- has a DEVICE member) per the drift guard in
-- tests/unit/test_pipeline_event_check_vocab.py. No pipeline event is
-- written with actor_role='device' in phase 1 (the device principal is not
-- yet wired into any event-emitting endpoint; that is phase 2), but the
-- CHECK constraint's vocabulary is required to be a superset of every valid
-- Role value regardless of current usage, so the actor_role column accepts
-- the value the moment a phase 2 endpoint starts writing it, without a
-- follow-up migration.
--
-- Written to be idempotent (checks the current constraint definition before
-- acting) so it is a no-op if applied a second time or if the constraint
-- already includes 'device'.
DO $$
BEGIN
    IF EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conname = 'ck_pipeline_event_actor_role'
          AND conrelid = '"public"."pipeline_event"'::regclass
          AND pg_get_constraintdef(oid) NOT LIKE '%''device''%'
    ) THEN
        ALTER TABLE "public"."pipeline_event"
            DROP CONSTRAINT "ck_pipeline_event_actor_role";
        ALTER TABLE "public"."pipeline_event"
            ADD CONSTRAINT "ck_pipeline_event_actor_role"
            CHECK ((("actor_role")::"text" = ANY ((ARRAY['system'::character varying, 'guardian'::character varying, 'child'::character varying, 'admin'::character varying, 'device'::character varying])::"text"[])));
    END IF;
END
$$;
