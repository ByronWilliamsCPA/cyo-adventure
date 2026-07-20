-- Self-signup approval track (alongside Phase 2 / ADR-018 D1): widen
-- "public"."user"."status" to accept 'awaiting_approval', a deliberately
-- parallel state to the existing admin-invite 'pending' status -- an
-- uninvited guardian's own first-login JIT provisioning
-- (src/cyo_adventure/api/onboarding.py::_provision_guardian) now starts here
-- instead of 'active', and an admin approves (-> 'active') or denies
-- (-> 'deactivated') via the existing PATCH /admin/users/{id} status
-- transition. See db/models.py's _USER_STATUS_VALUES comment for why this
-- never shares state with 'pending'.
--
-- Written to be idempotent (checks the current constraint definition before
-- acting), mirroring the pipeline_event CHECK-widening migrations, so it is
-- a no-op if applied a second time or if the constraint already includes
-- the new value.
DO $$
BEGIN
    IF EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conname = 'ck_user_status'
          AND conrelid = '"public"."user"'::regclass
          AND pg_get_constraintdef(oid) NOT LIKE '%awaiting_approval%'
    ) THEN
        ALTER TABLE "public"."user"
            DROP CONSTRAINT "ck_user_status";
        ALTER TABLE "public"."user"
            ADD CONSTRAINT "ck_user_status"
            CHECK ((("status")::"text" = ANY ((ARRAY['pending'::character varying, 'active'::character varying, 'deactivated'::character varying, 'awaiting_approval'::character varying])::"text"[])));
    END IF;
END
$$;
