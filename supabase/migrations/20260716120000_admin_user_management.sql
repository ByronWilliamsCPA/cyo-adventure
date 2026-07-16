-- WS-J: admin user management (add/remove/edit guardians, admins, kids,
-- families, and cross-family recommendation opt-ins from an admin console).
--
-- Four pieces:
--   1. "user"."status" ('pending' | 'active' | 'deactivated'): a guardian or
--      admin created via JIT onboarding or the seed script starts 'active';
--      an admin-created invite starts 'pending' (its authn_subject is a
--      synthetic placeholder bound to a real Supabase subject by email match
--      on first login, see src/cyo_adventure/api/onboarding.py); 'deactivated'
--      is the soft-remove state. require_principal
--      (src/cyo_adventure/api/deps.py) rejects any non-'active' status.
--   2. "family"."deactivated_at" / "child_profile"."deactivated_at": nullable
--      timestamps (not a status string, unlike "user") because a family or a
--      kid profile only ever has two states.
--   3. "family_connection": a new table for a directional cross-family
--      recommendation opt-in (family_id "views" connected_family_id; the
--      reverse direction is a separate row).
--   4. Widen the two pipeline_event CHECK constraints so admin
--      create/update/deactivate actions on users, families, and family
--      connections can be recorded in the existing append-only event log
--      (src/cyo_adventure/events/models.py::EventType).

alter table "public"."user"
    add column "status" character varying(16) not null default 'active';

-- #CRITICAL: security: keeps the status column within the closed vocabulary
-- api.deps.require_principal relies on; an unmodeled value would either
-- silently authenticate (if the code defaulted open) or 500 (if it coerced
-- through a closed enum), rather than cleanly rejecting.
-- #VERIFY: src/cyo_adventure/db/models.py User.__table_args__ mirrors this;
-- tests/integration/test_admin_users_api.py round-trips the constraint.
alter table "public"."user"
    add constraint "ck_user_status"
    check (("status")::"text" = any ((array['pending'::character varying, 'active'::character varying, 'deactivated'::character varying])::"text"[]));

alter table "public"."family"
    add column "deactivated_at" timestamp with time zone;

alter table "public"."child_profile"
    add column "deactivated_at" timestamp with time zone;

create table if not exists "public"."family_connection" (
    "id" "uuid" not null,
    "family_id" "uuid" not null,
    "connected_family_id" "uuid" not null,
    "created_by" "uuid",
    "created_at" timestamp with time zone default "now"() not null
);

alter table "public"."family_connection" owner to "postgres";

alter table only "public"."family_connection"
    add constraint "family_connection_pkey" primary key ("id");

alter table only "public"."family_connection"
    add constraint "family_connection_family_id_fkey" foreign key ("family_id") references "public"."family"("id");

alter table only "public"."family_connection"
    add constraint "family_connection_connected_family_id_fkey" foreign key ("connected_family_id") references "public"."family"("id");

alter table only "public"."family_connection"
    add constraint "family_connection_created_by_fkey" foreign key ("created_by") references "public"."user"("id");

alter table only "public"."family_connection"
    add constraint "uq_family_connection_pair" unique ("family_id", "connected_family_id");

alter table only "public"."family_connection"
    add constraint "ck_family_connection_not_self" check (("family_id" <> "connected_family_id"));

create index "ix_family_connection_family_id" on "public"."family_connection" using "btree" ("family_id");

create index "ix_family_connection_connected_family_id" on "public"."family_connection" using "btree" ("connected_family_id");

-- Same RLS posture as every other table (20260711200745_enable_rls_all_tables.sql):
-- the backend connects as the "postgres" table owner, which Postgres always
-- exempts from RLS, so this is defense-in-depth against the PostgREST
-- anon/authenticated data path, not a restriction on the backend's own
-- queries. No anon/authenticated policies are added, matching the
-- deny-by-default posture that migration established.
alter table if exists "public"."family_connection" enable row level security;

-- Widen the pipeline_event CHECK constraints (same idempotent technique as
-- 20260713181500_add_device_actor_role_to_pipeline_event.sql) so the three
-- new WS-J event types and three new entity types can be recorded.
DO $$
BEGIN
    IF EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conname = 'ck_pipeline_event_event_type'
          AND conrelid = '"public"."pipeline_event"'::regclass
          AND pg_get_constraintdef(oid) NOT LIKE '%''user_managed''%'
    ) THEN
        ALTER TABLE "public"."pipeline_event"
            DROP CONSTRAINT "ck_pipeline_event_event_type";
        ALTER TABLE "public"."pipeline_event"
            ADD CONSTRAINT "ck_pipeline_event_event_type"
            CHECK ((("event_type")::"text" = ANY ((ARRAY[
                'request_created'::character varying,
                'request_approved'::character varying,
                'request_declined'::character varying,
                'plan_assigned'::character varying,
                'generation_started'::character varying,
                'generation_finished'::character varying,
                'moderation_completed'::character varying,
                'repair_applied'::character varying,
                'sent_back'::character varying,
                'released'::character varying,
                'threshold_changed'::character varying,
                'noise_floor_changed'::character varying,
                'book_assigned'::character varying,
                'rated'::character varying,
                'user_managed'::character varying,
                'family_managed'::character varying,
                'family_connection_changed'::character varying
            ])::"text"[])));
    END IF;
END
$$;

DO $$
BEGIN
    IF EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conname = 'ck_pipeline_event_entity_type'
          AND conrelid = '"public"."pipeline_event"'::regclass
          AND pg_get_constraintdef(oid) NOT LIKE '%''family_connection''%'
    ) THEN
        ALTER TABLE "public"."pipeline_event"
            DROP CONSTRAINT "ck_pipeline_event_entity_type";
        ALTER TABLE "public"."pipeline_event"
            ADD CONSTRAINT "ck_pipeline_event_entity_type"
            CHECK ((("entity_type")::"text" = ANY ((ARRAY[
                'story_request'::character varying,
                'generation_job'::character varying,
                'storybook'::character varying,
                'storybook_version'::character varying,
                'series'::character varying,
                'storybook_assignment'::character varying,
                'rating'::character varying,
                'moderation_threshold'::character varying,
                'moderation_setting'::character varying,
                'user'::character varying,
                'family'::character varying,
                'family_connection'::character varying
            ])::"text"[])));
    END IF;
END
$$;
