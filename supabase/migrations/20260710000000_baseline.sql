


SET statement_timeout = 0;
SET lock_timeout = 0;
SET idle_in_transaction_session_timeout = 0;
SET client_encoding = 'UTF8';
SET standard_conforming_strings = on;
SELECT pg_catalog.set_config('search_path', '', false);
SET check_function_bodies = false;
SET xmloption = content;
SET client_min_messages = warning;
SET row_security = off;


COMMENT ON SCHEMA "public" IS 'standard public schema';



CREATE OR REPLACE FUNCTION "public"."pipeline_event_append_only"() RETURNS "trigger"
    LANGUAGE "plpgsql"
    AS $$
BEGIN
    RAISE EXCEPTION 'pipeline_event is append-only: % is not permitted', TG_OP;
END;
$$;


ALTER FUNCTION "public"."pipeline_event_append_only"() OWNER TO "postgres";

SET default_tablespace = '';

SET default_table_access_method = "heap";


CREATE TABLE IF NOT EXISTS "public"."child_profile" (
    "id" "uuid" NOT NULL,
    "family_id" "uuid" NOT NULL,
    "display_name" character varying(120) NOT NULL,
    "age_band" character varying(16) NOT NULL,
    "reading_level_cap" double precision NOT NULL,
    "allowed_content_flags" "jsonb" NOT NULL,
    "tts_enabled" boolean NOT NULL,
    "avatar" character varying(255),
    "created_at" timestamp with time zone DEFAULT "now"() NOT NULL
);


ALTER TABLE "public"."child_profile" OWNER TO "postgres";


CREATE TABLE IF NOT EXISTS "public"."completion" (
    "child_profile_id" "uuid" NOT NULL,
    "storybook_id" character varying(120) NOT NULL,
    "version" integer NOT NULL,
    "ending_id" character varying(120) NOT NULL,
    "found_at" timestamp with time zone DEFAULT "now"() NOT NULL
);


ALTER TABLE "public"."completion" OWNER TO "postgres";


CREATE TABLE IF NOT EXISTS "public"."concept" (
    "id" "uuid" NOT NULL,
    "family_id" "uuid" NOT NULL,
    "brief" "jsonb" NOT NULL,
    "created_by" "uuid",
    "created_at" timestamp with time zone DEFAULT "now"() NOT NULL
);


ALTER TABLE "public"."concept" OWNER TO "postgres";


CREATE TABLE IF NOT EXISTS "public"."family" (
    "id" "uuid" NOT NULL,
    "name" character varying(200) NOT NULL,
    "created_at" timestamp with time zone DEFAULT "now"() NOT NULL
);


ALTER TABLE "public"."family" OWNER TO "postgres";


CREATE TABLE IF NOT EXISTS "public"."generation_job" (
    "id" "uuid" NOT NULL,
    "concept_id" "uuid" NOT NULL,
    "status" character varying(20) NOT NULL,
    "model" character varying(120),
    "provider" character varying(120),
    "prompt_version" character varying(120),
    "report" "jsonb",
    "storybook_id" character varying(120),
    "version" integer,
    "error" character varying(512),
    "created_at" timestamp with time zone DEFAULT "now"() NOT NULL,
    "updated_at" timestamp with time zone DEFAULT "now"() NOT NULL,
    "authoring_metadata" "jsonb",
    CONSTRAINT "ck_generation_job_status" CHECK ((("status")::"text" = ANY ((ARRAY['queued'::character varying, 'running'::character varying, 'passed'::character varying, 'needs_review'::character varying, 'failed'::character varying, 'awaiting_manual_fill'::character varying])::"text"[])))
);


ALTER TABLE "public"."generation_job" OWNER TO "postgres";


CREATE TABLE IF NOT EXISTS "public"."moderation_setting" (
    "key" character varying(64) NOT NULL,
    "value" double precision NOT NULL,
    "updated_by" "uuid",
    "updated_at" timestamp with time zone DEFAULT "now"() NOT NULL,
    CONSTRAINT "ck_moderation_setting_value" CHECK ((("value" >= (0)::double precision) AND ("value" <= (1)::double precision)))
);


ALTER TABLE "public"."moderation_setting" OWNER TO "postgres";


CREATE TABLE IF NOT EXISTS "public"."moderation_threshold" (
    "id" "uuid" NOT NULL,
    "age_band" character varying(16) NOT NULL,
    "category" character varying(64) NOT NULL,
    "min_verdict" character varying(16) NOT NULL,
    "min_score" double precision,
    "updated_by" "uuid",
    "updated_at" timestamp with time zone DEFAULT "now"() NOT NULL,
    CONSTRAINT "ck_moderation_threshold_age_band" CHECK ((("age_band")::"text" = ANY ((ARRAY['3-5'::character varying, '5-8'::character varying, '8-11'::character varying, '10-13'::character varying, '13-16'::character varying, '16+'::character varying])::"text"[]))),
    CONSTRAINT "ck_moderation_threshold_min_score" CHECK ((("min_score" IS NULL) OR (("min_score" >= (0.0)::double precision) AND ("min_score" <= (1.0)::double precision)))),
    CONSTRAINT "ck_moderation_threshold_min_verdict" CHECK ((("min_verdict")::"text" = ANY ((ARRAY['advisory'::character varying, 'flag'::character varying, 'block'::character varying])::"text"[])))
);


ALTER TABLE "public"."moderation_threshold" OWNER TO "postgres";


CREATE TABLE IF NOT EXISTS "public"."moderation_threshold_audit" (
    "id" "uuid" NOT NULL,
    "age_band" character varying(16) NOT NULL,
    "category" character varying(64) NOT NULL,
    "action" character varying(16) NOT NULL,
    "old_min_verdict" character varying(16),
    "new_min_verdict" character varying(16),
    "old_min_score" double precision,
    "new_min_score" double precision,
    "changed_by" "uuid" NOT NULL,
    "changed_at" timestamp with time zone DEFAULT "now"() NOT NULL,
    CONSTRAINT "ck_moderation_threshold_audit_action" CHECK ((("action")::"text" = ANY ((ARRAY['upsert'::character varying, 'delete'::character varying])::"text"[])))
);


ALTER TABLE "public"."moderation_threshold_audit" OWNER TO "postgres";


CREATE TABLE IF NOT EXISTS "public"."pipeline_event" (
    "id" "uuid" NOT NULL,
    "occurred_at" timestamp with time zone DEFAULT "now"() NOT NULL,
    "actor_id" "uuid",
    "actor_role" character varying(16) NOT NULL,
    "entity_type" character varying(32) NOT NULL,
    "entity_id" character varying(255) NOT NULL,
    "event_type" character varying(48) NOT NULL,
    "from_state" character varying(32),
    "to_state" character varying(32),
    "payload" "jsonb" DEFAULT '{}'::"jsonb" NOT NULL,
    CONSTRAINT "ck_pipeline_event_actor_role" CHECK ((("actor_role")::"text" = ANY ((ARRAY['system'::character varying, 'guardian'::character varying, 'child'::character varying, 'admin'::character varying])::"text"[]))),
    CONSTRAINT "ck_pipeline_event_entity_type" CHECK ((("entity_type")::"text" = ANY ((ARRAY['story_request'::character varying, 'generation_job'::character varying, 'storybook'::character varying, 'storybook_version'::character varying, 'series'::character varying, 'storybook_assignment'::character varying, 'rating'::character varying, 'moderation_threshold'::character varying, 'moderation_setting'::character varying])::"text"[]))),
    CONSTRAINT "ck_pipeline_event_event_type" CHECK ((("event_type")::"text" = ANY ((ARRAY['request_created'::character varying, 'request_approved'::character varying, 'request_declined'::character varying, 'plan_assigned'::character varying, 'generation_started'::character varying, 'generation_finished'::character varying, 'moderation_completed'::character varying, 'repair_applied'::character varying, 'sent_back'::character varying, 'released'::character varying, 'threshold_changed'::character varying, 'noise_floor_changed'::character varying, 'book_assigned'::character varying, 'rated'::character varying])::"text"[]))),
    CONSTRAINT "ck_pipeline_event_system_actor_null" CHECK (((("actor_role")::"text" = 'system'::"text") = ("actor_id" IS NULL)))
);


ALTER TABLE "public"."pipeline_event" OWNER TO "postgres";


CREATE TABLE IF NOT EXISTS "public"."provider_model_allowlist" (
    "id" "uuid" NOT NULL,
    "provider" character varying(32) NOT NULL,
    "model_id" character varying(120) NOT NULL,
    "enabled" boolean DEFAULT true NOT NULL,
    "display_name" character varying(120),
    "created_by" "uuid",
    "updated_by" "uuid",
    "created_at" timestamp with time zone DEFAULT "now"() NOT NULL,
    "updated_at" timestamp with time zone DEFAULT "now"() NOT NULL,
    CONSTRAINT "ck_provider_model_allowlist_provider" CHECK ((("provider")::"text" = ANY ((ARRAY['anthropic'::character varying, 'openrouter'::character varying, 'modal'::character varying, 'ollama'::character varying])::"text"[])))
);


ALTER TABLE "public"."provider_model_allowlist" OWNER TO "postgres";


CREATE TABLE IF NOT EXISTS "public"."provider_model_allowlist_audit" (
    "id" "uuid" NOT NULL,
    "provider" character varying(32) NOT NULL,
    "model_id" character varying(120) NOT NULL,
    "action" character varying(16) NOT NULL,
    "old_enabled" boolean,
    "new_enabled" boolean,
    "changed_by" "uuid" NOT NULL,
    "changed_at" timestamp with time zone DEFAULT "now"() NOT NULL,
    CONSTRAINT "ck_provider_model_allowlist_audit_action" CHECK ((("action")::"text" = ANY ((ARRAY['create'::character varying, 'update'::character varying, 'delete'::character varying])::"text"[])))
);


ALTER TABLE "public"."provider_model_allowlist_audit" OWNER TO "postgres";


CREATE TABLE IF NOT EXISTS "public"."rating" (
    "child_profile_id" "uuid" NOT NULL,
    "storybook_id" character varying(120) NOT NULL,
    "value" integer NOT NULL,
    "rated_at" timestamp with time zone DEFAULT "now"() NOT NULL,
    "updated_at" timestamp with time zone DEFAULT "now"() NOT NULL,
    CONSTRAINT "ck_rating_value_range" CHECK ((("value" >= 1) AND ("value" <= 5)))
);


ALTER TABLE "public"."rating" OWNER TO "postgres";


CREATE TABLE IF NOT EXISTS "public"."reading_state" (
    "child_profile_id" "uuid" NOT NULL,
    "storybook_id" character varying(120) NOT NULL,
    "version" integer NOT NULL,
    "current_node" character varying(120) NOT NULL,
    "var_state" "jsonb" NOT NULL,
    "path" "jsonb" NOT NULL,
    "visit_set" "jsonb" NOT NULL,
    "save_slots" "jsonb" NOT NULL,
    "state_revision" integer NOT NULL,
    "last_event_id" character varying(64),
    "updated_by_device_id" character varying(64),
    "last_synced_at" timestamp with time zone,
    "created_at" timestamp with time zone DEFAULT "now"() NOT NULL,
    "updated_at" timestamp with time zone DEFAULT "now"() NOT NULL
);


ALTER TABLE "public"."reading_state" OWNER TO "postgres";


CREATE TABLE IF NOT EXISTS "public"."series" (
    "id" "uuid" NOT NULL,
    "family_id" "uuid" NOT NULL,
    "title" character varying(120) NOT NULL,
    "age_band" character varying(16) NOT NULL,
    "carries_state" boolean NOT NULL,
    "created_by" "uuid",
    "created_at" timestamp with time zone DEFAULT "now"() NOT NULL,
    CONSTRAINT "ck_series_age_band" CHECK ((("age_band")::"text" = ANY ((ARRAY['3-5'::character varying, '5-8'::character varying, '8-11'::character varying, '10-13'::character varying, '13-16'::character varying, '16+'::character varying])::"text"[])))
);


ALTER TABLE "public"."series" OWNER TO "postgres";


CREATE TABLE IF NOT EXISTS "public"."story_request" (
    "id" "uuid" NOT NULL,
    "family_id" "uuid" NOT NULL,
    "profile_id" "uuid",
    "request_text" character varying(500) NOT NULL,
    "status" character varying(16) NOT NULL,
    "moderation_flags" "jsonb",
    "reviewed_by" "uuid",
    "reviewed_at" timestamp with time zone,
    "concept_id" "uuid",
    "created_at" timestamp with time zone DEFAULT "now"() NOT NULL,
    "initiator_role" character varying(16) DEFAULT 'child'::character varying NOT NULL,
    "age_band" character varying(16) NOT NULL,
    "length" character varying(16),
    "narrative_style" character varying(16) DEFAULT 'prose'::character varying NOT NULL,
    "series_id" "uuid",
    "anchor_storybook_id" character varying(120),
    "proposed_series_title" character varying(120),
    CONSTRAINT "ck_story_request_age_band" CHECK ((("age_band")::"text" = ANY ((ARRAY['3-5'::character varying, '5-8'::character varying, '8-11'::character varying, '10-13'::character varying, '13-16'::character varying, '16+'::character varying])::"text"[]))),
    CONSTRAINT "ck_story_request_anchor_requires_series" CHECK ((("anchor_storybook_id" IS NULL) OR ("series_id" IS NOT NULL))),
    CONSTRAINT "ck_story_request_initiator_role" CHECK ((("initiator_role")::"text" = ANY ((ARRAY['child'::character varying, 'guardian'::character varying, 'admin'::character varying])::"text"[]))),
    CONSTRAINT "ck_story_request_length" CHECK ((("length" IS NULL) OR (("length")::"text" = ANY ((ARRAY['short'::character varying, 'medium'::character varying, 'long'::character varying])::"text"[])))),
    CONSTRAINT "ck_story_request_narrative_style" CHECK ((("narrative_style")::"text" = ANY ((ARRAY['prose'::character varying, 'gamebook'::character varying])::"text"[]))),
    CONSTRAINT "ck_story_request_status" CHECK ((("status")::"text" = ANY ((ARRAY['pending'::character varying, 'approved'::character varying, 'declined'::character varying, 'blocked'::character varying])::"text"[]))),
    CONSTRAINT "ck_story_request_style_band" CHECK (((("narrative_style")::"text" = 'prose'::"text") OR (("age_band")::"text" = ANY ((ARRAY['13-16'::character varying, '16+'::character varying])::"text"[])))),
    CONSTRAINT "ck_story_request_title_anchor_mutex" CHECK ((NOT (("proposed_series_title" IS NOT NULL) AND ("anchor_storybook_id" IS NOT NULL))))
);


ALTER TABLE "public"."story_request" OWNER TO "postgres";


CREATE TABLE IF NOT EXISTS "public"."storybook" (
    "id" character varying(120) NOT NULL,
    "family_id" "uuid" NOT NULL,
    "current_published_version" integer,
    "status" character varying(20) NOT NULL,
    "created_by" "uuid",
    "created_at" timestamp with time zone DEFAULT "now"() NOT NULL,
    "series_id" "uuid",
    "book_index" integer,
    "visibility" character varying(16) DEFAULT 'family'::character varying NOT NULL,
    CONSTRAINT "ck_storybook_book_index" CHECK ((("book_index" IS NULL) OR ("book_index" >= 1))),
    CONSTRAINT "ck_storybook_series_index_pairing" CHECK ((("series_id" IS NULL) = ("book_index" IS NULL))),
    CONSTRAINT "ck_storybook_status" CHECK ((("status")::"text" = ANY ((ARRAY['draft'::character varying, 'in_review'::character varying, 'needs_revision'::character varying, 'published'::character varying, 'archived'::character varying])::"text"[]))),
    CONSTRAINT "ck_storybook_visibility" CHECK ((("visibility")::"text" = ANY ((ARRAY['family'::character varying, 'catalog'::character varying])::"text"[])))
);


ALTER TABLE "public"."storybook" OWNER TO "postgres";


CREATE TABLE IF NOT EXISTS "public"."storybook_assignment" (
    "child_profile_id" "uuid" NOT NULL,
    "storybook_id" character varying(120) NOT NULL,
    "assigned_by" "uuid",
    "created_at" timestamp with time zone DEFAULT "now"() NOT NULL
);


ALTER TABLE "public"."storybook_assignment" OWNER TO "postgres";


CREATE TABLE IF NOT EXISTS "public"."storybook_version" (
    "storybook_id" character varying(120) NOT NULL,
    "version" integer NOT NULL,
    "blob" "jsonb" NOT NULL,
    "blob_ref" character varying(512),
    "validation_report" "jsonb",
    "moderation_report" "jsonb",
    "approved_by" "uuid",
    "published_at" timestamp with time zone,
    "model" character varying(120),
    "prompt_version" character varying(120),
    "created_at" timestamp with time zone DEFAULT "now"() NOT NULL,
    "provider" character varying(120),
    "cover_image_url" character varying(512),
    "cover_status" character varying(20) DEFAULT 'none'::character varying NOT NULL,
    "skeleton_slug" character varying(120),
    CONSTRAINT "ck_storybook_version_cover_status" CHECK ((("cover_status")::"text" = ANY ((ARRAY['none'::character varying, 'generating'::character varying, 'ready'::character varying, 'failed'::character varying])::"text"[])))
);


ALTER TABLE "public"."storybook_version" OWNER TO "postgres";


CREATE TABLE IF NOT EXISTS "public"."user" (
    "id" "uuid" NOT NULL,
    "family_id" "uuid" NOT NULL,
    "role" character varying(16) NOT NULL,
    "authn_subject" character varying(255) NOT NULL,
    "child_profile_id" "uuid",
    "created_at" timestamp with time zone DEFAULT "now"() NOT NULL,
    CONSTRAINT "ck_user_role" CHECK ((("role")::"text" = ANY ((ARRAY['guardian'::character varying, 'child'::character varying, 'admin'::character varying])::"text"[])))
);


ALTER TABLE "public"."user" OWNER TO "postgres";



ALTER TABLE ONLY "public"."child_profile"
    ADD CONSTRAINT "child_profile_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."completion"
    ADD CONSTRAINT "completion_pkey" PRIMARY KEY ("child_profile_id", "storybook_id", "version", "ending_id");



ALTER TABLE ONLY "public"."concept"
    ADD CONSTRAINT "concept_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."family"
    ADD CONSTRAINT "family_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."generation_job"
    ADD CONSTRAINT "generation_job_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."moderation_setting"
    ADD CONSTRAINT "moderation_setting_pkey" PRIMARY KEY ("key");



ALTER TABLE ONLY "public"."moderation_threshold_audit"
    ADD CONSTRAINT "moderation_threshold_audit_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."moderation_threshold"
    ADD CONSTRAINT "moderation_threshold_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."pipeline_event"
    ADD CONSTRAINT "pipeline_event_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."provider_model_allowlist_audit"
    ADD CONSTRAINT "provider_model_allowlist_audit_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."provider_model_allowlist"
    ADD CONSTRAINT "provider_model_allowlist_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."rating"
    ADD CONSTRAINT "rating_pkey" PRIMARY KEY ("child_profile_id", "storybook_id");



ALTER TABLE ONLY "public"."reading_state"
    ADD CONSTRAINT "reading_state_pkey" PRIMARY KEY ("child_profile_id", "storybook_id");



ALTER TABLE ONLY "public"."series"
    ADD CONSTRAINT "series_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."story_request"
    ADD CONSTRAINT "story_request_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."storybook_assignment"
    ADD CONSTRAINT "storybook_assignment_pkey" PRIMARY KEY ("child_profile_id", "storybook_id");



ALTER TABLE ONLY "public"."storybook"
    ADD CONSTRAINT "storybook_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."storybook_version"
    ADD CONSTRAINT "storybook_version_pkey" PRIMARY KEY ("storybook_id", "version");



ALTER TABLE ONLY "public"."moderation_threshold"
    ADD CONSTRAINT "uq_moderation_threshold_band_category" UNIQUE ("age_band", "category");



ALTER TABLE ONLY "public"."provider_model_allowlist"
    ADD CONSTRAINT "uq_provider_model_allowlist_provider_model" UNIQUE ("provider", "model_id");



ALTER TABLE ONLY "public"."storybook"
    ADD CONSTRAINT "uq_storybook_series_book_index" UNIQUE ("series_id", "book_index");



ALTER TABLE ONLY "public"."user"
    ADD CONSTRAINT "user_pkey" PRIMARY KEY ("id");



CREATE INDEX "ix_child_profile_family_id" ON "public"."child_profile" USING "btree" ("family_id");



CREATE INDEX "ix_concept_family_id" ON "public"."concept" USING "btree" ("family_id");



CREATE INDEX "ix_generation_job_concept_id" ON "public"."generation_job" USING "btree" ("concept_id");



CREATE INDEX "ix_pipeline_event_entity" ON "public"."pipeline_event" USING "btree" ("entity_type", "entity_id");



CREATE INDEX "ix_pipeline_event_event_type" ON "public"."pipeline_event" USING "btree" ("event_type");



CREATE INDEX "ix_pipeline_event_occurred_at" ON "public"."pipeline_event" USING "btree" ("occurred_at");



CREATE INDEX "ix_series_family_id" ON "public"."series" USING "btree" ("family_id");



CREATE INDEX "ix_story_request_family_status" ON "public"."story_request" USING "btree" ("family_id", "status");



CREATE INDEX "ix_story_request_profile_status" ON "public"."story_request" USING "btree" ("profile_id", "status");



CREATE INDEX "ix_story_request_status" ON "public"."story_request" USING "btree" ("status");



CREATE INDEX "ix_storybook_assignment_storybook_id" ON "public"."storybook_assignment" USING "btree" ("storybook_id");



CREATE INDEX "ix_storybook_family_id" ON "public"."storybook" USING "btree" ("family_id");



CREATE UNIQUE INDEX "ix_user_authn_subject" ON "public"."user" USING "btree" ("authn_subject");



CREATE INDEX "ix_user_family_id" ON "public"."user" USING "btree" ("family_id");



CREATE OR REPLACE TRIGGER "trg_pipeline_event_append_only" BEFORE DELETE OR UPDATE ON "public"."pipeline_event" FOR EACH ROW EXECUTE FUNCTION "public"."pipeline_event_append_only"();



ALTER TABLE ONLY "public"."child_profile"
    ADD CONSTRAINT "child_profile_family_id_fkey" FOREIGN KEY ("family_id") REFERENCES "public"."family"("id");



ALTER TABLE ONLY "public"."completion"
    ADD CONSTRAINT "completion_child_profile_id_fkey" FOREIGN KEY ("child_profile_id") REFERENCES "public"."child_profile"("id");



ALTER TABLE ONLY "public"."completion"
    ADD CONSTRAINT "completion_storybook_id_version_fkey" FOREIGN KEY ("storybook_id", "version") REFERENCES "public"."storybook_version"("storybook_id", "version");



ALTER TABLE ONLY "public"."concept"
    ADD CONSTRAINT "concept_created_by_fkey" FOREIGN KEY ("created_by") REFERENCES "public"."user"("id");



ALTER TABLE ONLY "public"."concept"
    ADD CONSTRAINT "concept_family_id_fkey" FOREIGN KEY ("family_id") REFERENCES "public"."family"("id");



ALTER TABLE ONLY "public"."story_request"
    ADD CONSTRAINT "fk_story_request_anchor_storybook_id_storybook" FOREIGN KEY ("anchor_storybook_id") REFERENCES "public"."storybook"("id");



ALTER TABLE ONLY "public"."story_request"
    ADD CONSTRAINT "fk_story_request_series_id_series" FOREIGN KEY ("series_id") REFERENCES "public"."series"("id");



ALTER TABLE ONLY "public"."storybook"
    ADD CONSTRAINT "fk_storybook_series_id_series" FOREIGN KEY ("series_id") REFERENCES "public"."series"("id");



ALTER TABLE ONLY "public"."generation_job"
    ADD CONSTRAINT "generation_job_concept_id_fkey" FOREIGN KEY ("concept_id") REFERENCES "public"."concept"("id");



ALTER TABLE ONLY "public"."moderation_setting"
    ADD CONSTRAINT "moderation_setting_updated_by_fkey" FOREIGN KEY ("updated_by") REFERENCES "public"."user"("id");



ALTER TABLE ONLY "public"."moderation_threshold_audit"
    ADD CONSTRAINT "moderation_threshold_audit_changed_by_fkey" FOREIGN KEY ("changed_by") REFERENCES "public"."user"("id");



ALTER TABLE ONLY "public"."moderation_threshold"
    ADD CONSTRAINT "moderation_threshold_updated_by_fkey" FOREIGN KEY ("updated_by") REFERENCES "public"."user"("id");



ALTER TABLE ONLY "public"."pipeline_event"
    ADD CONSTRAINT "pipeline_event_actor_id_fkey" FOREIGN KEY ("actor_id") REFERENCES "public"."user"("id");



ALTER TABLE ONLY "public"."provider_model_allowlist_audit"
    ADD CONSTRAINT "provider_model_allowlist_audit_changed_by_fkey" FOREIGN KEY ("changed_by") REFERENCES "public"."user"("id");



ALTER TABLE ONLY "public"."provider_model_allowlist"
    ADD CONSTRAINT "provider_model_allowlist_created_by_fkey" FOREIGN KEY ("created_by") REFERENCES "public"."user"("id");



ALTER TABLE ONLY "public"."provider_model_allowlist"
    ADD CONSTRAINT "provider_model_allowlist_updated_by_fkey" FOREIGN KEY ("updated_by") REFERENCES "public"."user"("id");



ALTER TABLE ONLY "public"."rating"
    ADD CONSTRAINT "rating_child_profile_id_fkey" FOREIGN KEY ("child_profile_id") REFERENCES "public"."child_profile"("id");



ALTER TABLE ONLY "public"."rating"
    ADD CONSTRAINT "rating_storybook_id_fkey" FOREIGN KEY ("storybook_id") REFERENCES "public"."storybook"("id");



ALTER TABLE ONLY "public"."reading_state"
    ADD CONSTRAINT "reading_state_child_profile_id_fkey" FOREIGN KEY ("child_profile_id") REFERENCES "public"."child_profile"("id");



ALTER TABLE ONLY "public"."reading_state"
    ADD CONSTRAINT "reading_state_storybook_id_fkey" FOREIGN KEY ("storybook_id") REFERENCES "public"."storybook"("id");



ALTER TABLE ONLY "public"."reading_state"
    ADD CONSTRAINT "reading_state_storybook_id_version_fkey" FOREIGN KEY ("storybook_id", "version") REFERENCES "public"."storybook_version"("storybook_id", "version");



ALTER TABLE ONLY "public"."series"
    ADD CONSTRAINT "series_created_by_fkey" FOREIGN KEY ("created_by") REFERENCES "public"."user"("id");



ALTER TABLE ONLY "public"."series"
    ADD CONSTRAINT "series_family_id_fkey" FOREIGN KEY ("family_id") REFERENCES "public"."family"("id");



ALTER TABLE ONLY "public"."story_request"
    ADD CONSTRAINT "story_request_concept_id_fkey" FOREIGN KEY ("concept_id") REFERENCES "public"."concept"("id");



ALTER TABLE ONLY "public"."story_request"
    ADD CONSTRAINT "story_request_family_id_fkey" FOREIGN KEY ("family_id") REFERENCES "public"."family"("id");



ALTER TABLE ONLY "public"."story_request"
    ADD CONSTRAINT "story_request_profile_id_fkey" FOREIGN KEY ("profile_id") REFERENCES "public"."child_profile"("id");



ALTER TABLE ONLY "public"."story_request"
    ADD CONSTRAINT "story_request_reviewed_by_fkey" FOREIGN KEY ("reviewed_by") REFERENCES "public"."user"("id");



ALTER TABLE ONLY "public"."storybook_assignment"
    ADD CONSTRAINT "storybook_assignment_assigned_by_fkey" FOREIGN KEY ("assigned_by") REFERENCES "public"."user"("id");



ALTER TABLE ONLY "public"."storybook_assignment"
    ADD CONSTRAINT "storybook_assignment_child_profile_id_fkey" FOREIGN KEY ("child_profile_id") REFERENCES "public"."child_profile"("id");



ALTER TABLE ONLY "public"."storybook_assignment"
    ADD CONSTRAINT "storybook_assignment_storybook_id_fkey" FOREIGN KEY ("storybook_id") REFERENCES "public"."storybook"("id");



ALTER TABLE ONLY "public"."storybook"
    ADD CONSTRAINT "storybook_created_by_fkey" FOREIGN KEY ("created_by") REFERENCES "public"."user"("id");



ALTER TABLE ONLY "public"."storybook"
    ADD CONSTRAINT "storybook_family_id_fkey" FOREIGN KEY ("family_id") REFERENCES "public"."family"("id");



ALTER TABLE ONLY "public"."storybook_version"
    ADD CONSTRAINT "storybook_version_approved_by_fkey" FOREIGN KEY ("approved_by") REFERENCES "public"."user"("id");



ALTER TABLE ONLY "public"."storybook_version"
    ADD CONSTRAINT "storybook_version_storybook_id_fkey" FOREIGN KEY ("storybook_id") REFERENCES "public"."storybook"("id");



ALTER TABLE ONLY "public"."user"
    ADD CONSTRAINT "user_child_profile_id_fkey" FOREIGN KEY ("child_profile_id") REFERENCES "public"."child_profile"("id");



ALTER TABLE ONLY "public"."user"
    ADD CONSTRAINT "user_family_id_fkey" FOREIGN KEY ("family_id") REFERENCES "public"."family"("id");
