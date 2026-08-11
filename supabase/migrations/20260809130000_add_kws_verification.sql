-- ADR-018 (KWS Parent Verification Service): the record one verification attempt writes.
--
-- Why this table exists at all. The send leg mints an opaque per-attempt id and hands it
-- to KWS as `externalPayload`; the authoritative `parent-verified` webhook quotes that
-- same value back. Without a row keyed on it, the send leg throws the id away and the
-- delivery arrives with nothing to match against and nowhere to record the outcome.
--
-- `id` IS the minted attempt id, not a separate surrogate key with a correlation column
-- beside it: the value handed to KWS and the value a delivery is looked up by must be
-- the same value, or there are two of them and one chance for them to disagree.
--
-- There is DELIBERATELY no parent_email column, under this or any other name. Keeping
-- the parent's address out of the join is the entire reason the opaque correlation blob
-- exists (src/cyo_adventure/consent/external_payload.py); a column here would put the
-- most sensitive field in the delivery back at the centre of the schema, and it would
-- not survive a guardian changing their address either.
--
-- kws_environment is not decoration. The KWS API reports nothing that identifies which
-- environment answered, so without this column a Test verification is indistinguishable
-- at read time from evidence about a real parent, and the environment split collapses.
-- It is CHECK-constrained here rather than trusted from the writer for that reason.
--
-- enabled_methods is a SNAPSHOT of settings.kws_enabled_methods at send time. The
-- parent-verified event carries no verification-method field, so the set enabled at that
-- moment is the only bound that will ever exist on how the parent was verified, and the
-- vendor cannot reconstruct one afterwards.
--
-- Table and REFERENCES targets are schema-qualified ("public".*): see
-- 20260729000000_add_child_profile_personalization.sql's header comment for why (the
-- baseline migration empties search_path for the rest of the session, so every later
-- migration that creates a table must schema-qualify or fail with "no schema has been
-- selected to create in"). "user" is additionally a reserved word and stays quoted.

CREATE TABLE IF NOT EXISTS "public"."kws_verification" (
    id UUID NOT NULL,
    user_id UUID NOT NULL REFERENCES "public"."user"(id) ON DELETE CASCADE,
    kws_environment VARCHAR(16) NOT NULL,
    status VARCHAR(16) NOT NULL,
    requested_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    resolved_at TIMESTAMPTZ,
    transaction_id VARCHAR(128),
    enabled_methods JSONB NOT NULL,
    CONSTRAINT kws_verification_pkey PRIMARY KEY (id),
    CONSTRAINT ck_kws_verification_status
        CHECK (status IN ('sent', 'verified', 'failed')),
    CONSTRAINT ck_kws_verification_environment
        CHECK (kws_environment IN ('test', 'production')),
    -- Same shape as ck_kid_flag_resolved_pairing: a "still waiting" filter
    -- (status = 'sent') can never disagree with resolved_at IS NULL.
    CONSTRAINT ck_kws_verification_resolution_pairing
        CHECK ((status = 'sent') = (resolved_at IS NULL))
);

-- Postgres indexes the referenced side of a foreign key automatically but never the
-- referencing side; a guardian deletion (CASCADE above) would otherwise sequentially
-- scan this table. Name matches the ORM's index=True on user_id, which the schema-parity
-- gate (tests/integration/test_schema_parity.py) compares by name.
CREATE INDEX IF NOT EXISTS ix_kws_verification_user_id
    ON "public"."kws_verification" (user_id);

-- #CRITICAL: security: RLS is the ONLY gate on the PostgREST path (see
-- 20260729000000_add_child_profile_personalization.sql's identical note); a new table
-- that skips ENABLE ROW LEVEL SECURITY is a silent hole in the "every public table has
-- RLS" invariant established by 20260711200745_enable_rls_all_tables.sql.
-- #VERIFY: tests/integration/test_rls_service_roles.py::
-- test_no_public_table_ships_without_row_level_security asserts that no table in
-- `public` has rowsecurity = false.
ALTER TABLE "public"."kws_verification" ENABLE ROW LEVEL SECURITY;

-- Tier 2 (blanket), not Tier 1 family-scoped, mirroring security_event and
-- reading_activity_day. Tier 1's predicate needs a direct family_id column on the row
-- (see 20260809110000_add_device_download.sql), and this table has none: it is keyed on
-- the guardian, and reaching their family would take a join to "user", which ADR-022's
-- Technical Debt clause explicitly classifies as Tier 2 rather than admitting a subquery
-- into a row-level predicate. Denormalizing family_id onto the row purely to reach Tier 1
-- was rejected: it would widen a consent-evidence record with a second identity that the
-- webhook path never reads and that could then drift from the guardian's actual family.
-- Access control for any future read surface is an app-layer gate, like api/audit.py.
DROP POLICY IF EXISTS service_rw ON "public"."kws_verification";
CREATE POLICY service_rw ON "public"."kws_verification"
    FOR ALL TO cyo_api, cyo_worker USING (true) WITH CHECK (true);

-- RLS policies gate rows only once the GRANT layer admits the role at all; both service
-- roles need the table-level grants too (the omission fails
-- tests/integration/test_rls_service_roles.py::test_every_rls_table_grants_both_service_roles).
GRANT SELECT, INSERT, UPDATE, DELETE ON "public"."kws_verification" TO cyo_api, cyo_worker;

-- Forward-only migration per this project's Supabase CLI convention (ADR-012); no down
-- script.
