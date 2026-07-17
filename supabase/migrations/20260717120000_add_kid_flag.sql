-- K15: a child's structured "I didn't like this / this scared me" signal.
-- Feeds the admin moderation queue (A1) directly via this table, and later
-- the guardian alert feed (G10) as a pipeline_event projection (built by a
-- sibling workstream; not touched here). ADR-016's no-free-text principle:
-- this table carries no child-authored text column, only a closed-vocabulary
-- reason and a story-graph node id, so a grown-up sees a safe, structured
-- signal, never raw child prose.
--
-- Mirrors reading_state/completion: a composite FK pins (storybook_id,
-- version) to an actual storybook_version row, in addition to the plain FK
-- on storybook_id to storybook itself.

create table if not exists "public"."kid_flag" (
    "id" "uuid" not null,
    "family_id" "uuid" not null,
    "profile_id" "uuid" not null,
    "storybook_id" character varying(120) not null,
    "version" integer not null,
    "reason" character varying(16) not null,
    "node_id" character varying(120),
    "created_at" timestamp with time zone default "now"() not null,
    "resolved_by" "uuid",
    "resolved_at" timestamp with time zone,
    "resolution" character varying(16),
    constraint "ck_kid_flag_reason" check ((("reason")::"text" = ANY ((ARRAY['did_not_like'::character varying, 'scared_me'::character varying, 'confusing'::character varying])::"text"[]))),
    constraint "ck_kid_flag_resolution" check ((("resolution" IS NULL) OR (("resolution")::"text" = ANY ((ARRAY['dismissed'::character varying, 'archived_book'::character varying, 'noted'::character varying])::"text"[])))),
    constraint "ck_kid_flag_resolved_pairing" check ((("resolved_by" IS NULL) = ("resolved_at" IS NULL)))
);

alter table "public"."kid_flag" owner to "postgres";

alter table only "public"."kid_flag"
    add constraint "kid_flag_pkey" primary key ("id");

alter table only "public"."kid_flag"
    add constraint "kid_flag_family_id_fkey" foreign key ("family_id") references "public"."family"("id");

alter table only "public"."kid_flag"
    add constraint "kid_flag_profile_id_fkey" foreign key ("profile_id") references "public"."child_profile"("id");

alter table only "public"."kid_flag"
    add constraint "kid_flag_storybook_id_fkey" foreign key ("storybook_id") references "public"."storybook"("id");

alter table only "public"."kid_flag"
    add constraint "kid_flag_storybook_id_version_fkey" foreign key ("storybook_id", "version") references "public"."storybook_version"("storybook_id", "version");

alter table only "public"."kid_flag"
    add constraint "kid_flag_resolved_by_fkey" foreign key ("resolved_by") references "public"."user"("id");

create index "ix_kid_flag_family_id" on "public"."kid_flag" using "btree" ("family_id");

create index "ix_kid_flag_profile_id" on "public"."kid_flag" using "btree" ("profile_id");

create index "ix_kid_flag_resolved_created" on "public"."kid_flag" using "btree" ("resolved_at", "created_at");

-- Same deny-by-default RLS posture as every other table (see
-- 20260711200745_enable_rls_all_tables.sql): the backend connects as the
-- "postgres" table owner, which Postgres always exempts from RLS, so this is
-- defense-in-depth against the PostgREST anon/authenticated data path, not a
-- restriction on the backend's own queries. No anon/authenticated policies
-- are added, matching the posture every other table in this codebase uses.
alter table if exists "public"."kid_flag" enable row level security;

-- Widen the pipeline_event.event_type CHECK to accept the two new K15 event
-- types ('kid_flagged', 'flag_resolved'), and pipeline_event.entity_type to
-- accept 'kid_flag', keeping both in sync with
-- cyo_adventure.events.models.EventType and the entity_type literals used by
-- api/flags.py (see the drift guard in
-- tests/unit/test_pipeline_event_check_vocab.py for event_type; entity_type
-- has no such guard, by design -- see that test module's trailing comment).
--
-- Written to be idempotent (checks the current constraint definition before
-- acting), mirroring 20260713181500_add_device_actor_role_to_pipeline_event.sql,
-- so it is a no-op if applied a second time or if the constraint already
-- includes the new values.
DO $$
BEGIN
    IF EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conname = 'ck_pipeline_event_event_type'
          AND conrelid = '"public"."pipeline_event"'::regclass
          AND pg_get_constraintdef(oid) NOT LIKE '%''kid_flagged''%'
    ) THEN
        ALTER TABLE "public"."pipeline_event"
            DROP CONSTRAINT "ck_pipeline_event_event_type";
        ALTER TABLE "public"."pipeline_event"
            ADD CONSTRAINT "ck_pipeline_event_event_type"
            CHECK ((("event_type")::"text" = ANY ((ARRAY['request_created'::character varying, 'request_approved'::character varying, 'request_declined'::character varying, 'plan_assigned'::character varying, 'generation_started'::character varying, 'generation_finished'::character varying, 'moderation_completed'::character varying, 'repair_applied'::character varying, 'sent_back'::character varying, 'released'::character varying, 'threshold_changed'::character varying, 'noise_floor_changed'::character varying, 'book_assigned'::character varying, 'rated'::character varying, 'kid_flagged'::character varying, 'flag_resolved'::character varying])::"text"[])));
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
          AND pg_get_constraintdef(oid) NOT LIKE '%''kid_flag''%'
    ) THEN
        ALTER TABLE "public"."pipeline_event"
            DROP CONSTRAINT "ck_pipeline_event_entity_type";
        ALTER TABLE "public"."pipeline_event"
            ADD CONSTRAINT "ck_pipeline_event_entity_type"
            CHECK ((("entity_type")::"text" = ANY ((ARRAY['story_request'::character varying, 'generation_job'::character varying, 'storybook'::character varying, 'storybook_version'::character varying, 'series'::character varying, 'storybook_assignment'::character varying, 'rating'::character varying, 'moderation_threshold'::character varying, 'moderation_setting'::character varying, 'kid_flag'::character varying])::"text"[])));
    END IF;
END
$$;
