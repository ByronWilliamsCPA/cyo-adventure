-- ADR-014 phase 1: device grants (durable, revocable, family-scoped device
-- authorization). A guardian mints a device_grant JWT
-- (src/cyo_adventure/core/device_grant.py) once per shared device; this
-- table is the durable, database-backed counterpart the token's embedded
-- "jti" claim is checked against for revocation on every online use. The
-- token itself is never stored, only its unique id and mint metadata.
--
-- Phase 1 only adds the table, the token plumbing, and the
-- POST/GET/DELETE /v1/device-grants management endpoints. Wiring the grant
-- into the child-session mint and the profiles endpoint as an additional
-- authority (alongside the guardian/admin Supabase bearer) is phase 2.

create table if not exists "public"."device_grant" (
    "id" "uuid" not null,
    "family_id" "uuid" not null,
    "authorized_by" "uuid" not null,
    "label" character varying(120),
    "jti" "uuid" not null,
    "created_at" timestamp with time zone default "now"() not null,
    "revoked_at" timestamp with time zone
);

alter table "public"."device_grant" owner to "postgres";

alter table only "public"."device_grant"
    add constraint "device_grant_pkey" primary key ("id");

alter table only "public"."device_grant"
    add constraint "device_grant_jti_key" unique ("jti");

alter table only "public"."device_grant"
    add constraint "device_grant_family_id_fkey" foreign key ("family_id") references "public"."family"("id");

alter table only "public"."device_grant"
    add constraint "device_grant_authorized_by_fkey" foreign key ("authorized_by") references "public"."user"("id");

create index "ix_device_grant_family_id" on "public"."device_grant" using "btree" ("family_id");

-- Same RLS posture as every other table (see
-- 20260711200745_enable_rls_all_tables.sql): the backend connects as the
-- "postgres" table owner, which Postgres always exempts from RLS, so this is
-- defense-in-depth against the PostgREST anon/authenticated data path, not a
-- restriction on the backend's own queries. No anon/authenticated policies
-- are added, matching the deny-by-default posture the prior migration
-- established; this table carries the same "never issue a Supabase client
-- session to a device/child" property that posture depends on.
alter table if exists "public"."device_grant" enable row level security;
