-- Guardian self-service invite track (G14): widen "public"."user"."status" to
-- accept 'pending_guardian_invite', a second invite kind that is deliberately
-- NOT the same state as the existing admin-created 'pending'.
--
-- Why a distinct value rather than reusing 'pending': the existing 'pending'
-- row binds straight to 'active' on the invitee's first sign-in
-- (src/cyo_adventure/api/onboarding.py::_bind_pending_invite), which is only
-- safe because an ADMIN created it and thereby vetted the invitee. Once a
-- guardian can create invite rows (POST /api/v1/me/family/invite-guardian),
-- reusing 'pending' would let any guardian pre-claim an arbitrary email
-- address and have its real owner silently bound into the inviting family as
-- an ACTIVE guardian on first sign-in, exposing that family's child profiles
-- to the inviter. A guardian-created invite therefore binds to
-- 'awaiting_approval' instead, so an admin must approve before the account
-- authenticates. See db/models.py's _USER_STATUS_VALUES comment.
--
-- Forward-only and written to be idempotent (checks the current constraint
-- definition before acting), mirroring
-- 20260720160000_add_user_awaiting_approval_status.sql, so it is a no-op if
-- applied a second time or if the constraint already includes the new value.

-- Widen the column itself first: 'pending_guardian_invite' (23 chars) does not
-- fit the current character varying(20), and widening a varchar's length is
-- always a no-op/no-rewrite metadata change in Postgres, so this is safe to
-- run unconditionally (including as a no-op re-run).
ALTER TABLE "public"."user"
    ALTER COLUMN "status" TYPE character varying(32);

DO $$
BEGIN
    IF EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conname = 'ck_user_status'
          AND conrelid = '"public"."user"'::regclass
          AND pg_get_constraintdef(oid) NOT LIKE '%pending_guardian_invite%'
    ) THEN
        ALTER TABLE "public"."user"
            DROP CONSTRAINT "ck_user_status";
        ALTER TABLE "public"."user"
            ADD CONSTRAINT "ck_user_status"
            CHECK ((("status")::"text" = ANY ((ARRAY['pending'::character varying, 'active'::character varying, 'deactivated'::character varying, 'awaiting_approval'::character varying, 'pending_guardian_invite'::character varying])::"text"[])));
    END IF;
END
$$;
