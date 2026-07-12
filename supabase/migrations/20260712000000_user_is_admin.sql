-- Dual admin/guardian roles (see docs/planning/admin-guardian-dual-roles-plan.md).
-- "role" stays the single base persona (guardian/child/admin) and "is_admin" is
-- an orthogonal capability flag, so one adult account can be a guardian, an
-- admin-only adult, or both (role='guardian', is_admin=true).
--
-- The auth boundary (src/cyo_adventure/api/deps.py, Principal.__post_init__)
-- treats the 'admin' base role as implying the capability regardless of the
-- flag, so the backfill below is for at-rest consistency, not correctness.

alter table "public"."user" add column "is_admin" boolean;

update "public"."user" set "is_admin" = ("role" = 'admin');

alter table "public"."user" alter column "is_admin" set not null;

-- #CRITICAL: security: a child user must never carry the admin capability;
-- the flag grants global review/approval power at the auth boundary.
-- #VERIFY: ck_user_child_not_admin rejects (role='child', is_admin=true) at rest;
-- the ORM mirror lives in src/cyo_adventure/db/models.py (User.__table_args__).
alter table "public"."user"
    add constraint "ck_user_child_not_admin"
    check (("role" <> 'child') or ("is_admin" = false));
