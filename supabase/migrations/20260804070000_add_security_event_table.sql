-- OPS-005 follow-up: a durable, queryable audit trail for the security events
-- app.py::_handle_project_error and middleware/security.py::RateLimitMiddleware
-- already log as structured events (security_auth_failed, security_authz_denied,
-- security_rate_limit_exceeded). The log lines are the real-time/alerting
-- surface (catalog: docs/operations/security-events.md); this table is the
-- durable/query-facing counterpart the breach-notification runbook
-- (docs/compliance/breach-notification-runbook.md) needs to reconstruct an
-- incident after the fact, once log retention has rolled off.
--
-- Deliberately NOT an extension of pipeline_event (events/writer.py): that
-- table's Actor value type requires either a real user_id (an authenticated
-- Principal) or the literal 'system' role (events/models.py::Actor.__post_init__,
-- backed by ck_pipeline_event_system_actor_null). An auth failure is neither --
-- there is no Principal to attribute it to (that's the whole point of the
-- failure), only a client IP. Rather than force a third pseudo-actor concept
-- into pipeline_event's accountability model, this is a separate, simpler,
-- append-only table with no actor column at all.
--
-- event_type values are the exact structlog event names, so the EVENT NAME a
-- responder greps in the log is the same string they filter on in a query
-- here -- no separate vocabulary to translate for that one join key. The two
-- are not a full field-for-field mirror: the log line carries richer
-- per-type detail (limit_type, requests_per_minute/burst_size,
-- suppressed_since_last for a rate-limit trip) than this table's columns.
--
-- #CRITICAL: privacy: client_ip is personal data and path can embed a
-- profile identifier (docs/operations/security-events.md section 4 makes the
-- same call for the log line these rows mirror). The append-only trigger
-- below means these rows have NO deletion path at all today: ADR-018
-- requires a hard deletion timeline per data class, and this table does not
-- yet have one. A retention/purge job (mirroring
-- 20260720150000_add_retention_purge_jobs.sql's pattern for other retained
-- data, or reading_activity_day's identical "table now, rollover job later"
-- split) is explicitly OUT OF SCOPE for this migration; only the table and
-- its cascade/RLS/append-only guarantee exist here.
-- #VERIFY: tracked as a follow-up; do not treat this table as satisfying
-- ADR-018 on its own.
--
-- Table and REFERENCES targets are schema-qualified ("public".*): see
-- 20260729000000_add_child_profile_personalization.sql's header comment for
-- why (the baseline migration empties search_path for the rest of the
-- session, so every later migration that creates or alters a table must
-- schema-qualify or fail with "no schema has been selected to create in").

CREATE OR REPLACE FUNCTION "public"."security_event_append_only"() RETURNS "trigger"
    LANGUAGE "plpgsql"
    AS $$
BEGIN
    RAISE EXCEPTION 'security_event is append-only: % is not permitted', TG_OP;
END;
$$;

ALTER FUNCTION "public"."security_event_append_only"() OWNER TO "postgres";

CREATE TABLE IF NOT EXISTS "public"."security_event" (
    "id" UUID NOT NULL,
    "occurred_at" TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
    "event_type" VARCHAR(48) NOT NULL,
    "reason" VARCHAR(200) NOT NULL,
    "client_ip" VARCHAR(45),
    "code" VARCHAR(64),
    "path" VARCHAR(255),
    "method" VARCHAR(10),
    "status_code" SMALLINT,
    "resource" VARCHAR(255),
    CONSTRAINT "security_event_pkey" PRIMARY KEY ("id"),
    CONSTRAINT "ck_security_event_event_type" CHECK (
        (("event_type")::"text" = ANY ((ARRAY[
            'security_auth_failed'::character varying,
            'security_authz_denied'::character varying,
            'security_rate_limit_exceeded'::character varying
        ])::"text"[]))
    )
);

ALTER TABLE "public"."security_event" OWNER TO "postgres";

-- IF NOT EXISTS on every statement below (including the indexes, easy to
-- miss next to CREATE TABLE/TRIGGER's own guards): this migration has not
-- shipped to any environment yet, but every other migration in this forward-
-- only chain (ADR-012) is written re-runnable from a partial application, and
-- this one should not be the first exception.
CREATE INDEX IF NOT EXISTS "ix_security_event_event_type" ON "public"."security_event" USING "btree" ("event_type");
CREATE INDEX IF NOT EXISTS "ix_security_event_occurred_at" ON "public"."security_event" USING "btree" ("occurred_at");
CREATE INDEX IF NOT EXISTS "ix_security_event_client_ip" ON "public"."security_event" USING "btree" ("client_ip");

CREATE OR REPLACE TRIGGER "trg_security_event_append_only"
    BEFORE DELETE OR UPDATE ON "public"."security_event"
    FOR EACH ROW EXECUTE FUNCTION "public"."security_event_append_only"();

-- #CRITICAL: security: RLS is the ONLY gate on the PostgREST path (see
-- 20260729000000_add_child_profile_personalization.sql's identical note); a
-- new table that skips ENABLE ROW LEVEL SECURITY is a silent hole in the
-- "every public table has RLS" invariant established by
-- 20260711200745_enable_rls_all_tables.sql.
-- #VERIFY: tests/integration/test_rls_service_roles.py::
-- test_no_public_table_ships_without_row_level_security asserts that no
-- table in `public` has rowsecurity = false.
ALTER TABLE "public"."security_event" ENABLE ROW LEVEL SECURITY;

-- Tier 2 (blanket), not Tier 1 family-scoped, mirroring pipeline_event and
-- reading_activity_day: rows routinely have no family at all (an anonymous,
-- pre-principal auth failure has no Principal to derive a family_id from),
-- so a family-scoped predicate cannot apply. Access control for any future
-- read surface (an admin security-event API) is an app-layer admin gate,
-- like api/audit.py, not RLS. The append-only trigger above -- not RLS or the
-- GRANT below -- is what actually blocks UPDATE/DELETE; both service roles
-- still need the full grant set per test_every_rls_table_grants_both_service_roles's
-- uniform CRUD-grant invariant, exactly as pipeline_event's existing policy does.
DROP POLICY IF EXISTS service_rw ON "public"."security_event";
CREATE POLICY service_rw ON "public"."security_event"
    FOR ALL TO cyo_api, cyo_worker USING (true) WITH CHECK (true);

-- RLS policies gate rows only once the GRANT layer admits the role at all;
-- both service roles need the table-level grants too (the omission fails
-- tests/integration/test_rls_service_roles.py::
-- test_every_rls_table_grants_both_service_roles).
GRANT SELECT, INSERT, UPDATE, DELETE ON
  "public"."security_event" TO cyo_api, cyo_worker;

-- Forward-only migration per this project's Supabase CLI convention
-- (ADR-012); no down script.
