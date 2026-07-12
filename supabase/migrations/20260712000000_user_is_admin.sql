-- Dual admin/guardian roles (see docs/planning/admin-guardian-dual-roles-plan.md).
-- "role" stays the single base persona (guardian/child/admin) and "is_admin" is
-- an orthogonal capability flag, so one adult account can be a guardian, an
-- admin-only adult, or both (role='guardian', is_admin=true).
--
-- The auth boundary (src/cyo_adventure/api/deps.py, Principal.__post_init__)
-- treats the 'admin' base role as implying the capability regardless of the
-- flag, so the backfill below is for at-rest consistency, not correctness.

-- NOT NULL DEFAULT false: existing rows are filled with false immediately, and
-- any insert path that omits is_admin (raw SQL, external tooling, an older app
-- version mid-deploy that predates this column) gets false rather than a NOT
-- NULL violation. The backfill below then flips admins to true.
alter table "public"."user" add column "is_admin" boolean not null default false;

update "public"."user" set "is_admin" = true where "role" = 'admin';

-- #CRITICAL: security: a child user must never carry the admin capability;
-- the flag grants global review/approval power at the auth boundary.
-- #VERIFY: ck_user_child_not_admin rejects (role='child', is_admin=true) at rest;
-- the ORM mirror lives in src/cyo_adventure/db/models.py (User.__table_args__).
alter table "public"."user"
    add constraint "ck_user_child_not_admin"
    check (("role" <> 'child') or ("is_admin" = false));

-- #CRITICAL: security: an admin-role row must always carry the admin
-- capability; the backfill above sets this for existing rows, and this
-- constraint keeps a future admin-role insert from ever persisting with the
-- flag unset, which would be a data-corruption state the auth boundary
-- should never have to reason about (see the header comment: the boundary
-- already treats the admin base role as implying the capability, so this
-- constraint is at-rest consistency, not correctness).
-- #VERIFY: ck_user_admin_role_flag rejects (role='admin', is_admin=false) at rest;
-- the ORM mirror lives in src/cyo_adventure/db/models.py (User.__table_args__).
alter table "public"."user"
    add constraint "ck_user_admin_role_flag"
    check (("role" <> 'admin') or ("is_admin" = true));
