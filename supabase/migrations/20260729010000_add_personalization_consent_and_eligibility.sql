-- ADR-023 P4 (Task B2): ring-2 disclosure consent evidence, the viewer-side
-- receive switch, the storybook personalization subject link, and the
-- per-version eligibility/sentinel-manifest columns. Design plan sections
-- 5.3 (consent), 8.2 (subject link), and 8.6 (viewer switch) are the
-- authority; this migration transcribes those settled shapes.
--
-- #CRITICAL: data-integrity: "family_connection_id" is ON DELETE SET NULL,
-- never CASCADE. A ring-2 disclosure consent is an evidentiary record (GDPR
-- Article 7(1), COPPA 312.5): it must outlive the connection it was granted
-- on, because disputes over what was authorized arise precisely after a
-- relationship ends. Deleting the connection tombstones this row
-- (family_connection_id -> NULL, revoked_at stamped by the caller) instead
-- of destroying it; deleting the child profile still removes the row
-- entirely, because the data subject is gone. See design plan 5.3, "The
-- connection cascade would destroy the evidence, so it must not cascade".
-- #VERIFY: tests/integration/test_personalization_consent_tombstone.py
-- asserts both halves: connection deletion tombstones, profile deletion
-- removes.
--
-- Table and REFERENCES targets are schema-qualified ("public".*), matching
-- 20260729000000_add_child_profile_personalization.sql: the baseline
-- migration empties search_path for the rest of the session (see that
-- migration's header for the full explanation), so every DDL statement
-- applied afterward through the same connection must qualify explicitly.

CREATE TABLE IF NOT EXISTS "public"."personalization_disclosure_consent" (
    id UUID NOT NULL,
    child_profile_id UUID NOT NULL REFERENCES "public"."child_profile"(id) ON DELETE CASCADE,
    family_connection_id UUID REFERENCES "public"."family_connection"(id) ON DELETE SET NULL,
    connected_family_label VARCHAR(200),
    covered_slot_types JSONB,
    sibling_authority_attested BOOLEAN NOT NULL DEFAULT FALSE,
    consent_accepted_at TIMESTAMPTZ,
    consent_policy_version VARCHAR(32),
    consent_signer_name VARCHAR(200),
    consent_ip VARCHAR(64),
    revoked_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (id),
    -- Mirrors "public"."user"."ck_user_consent_pairing" exactly (db/models.py
    -- User, :306-329): the four consent columns are set or cleared together,
    -- so the record is either fully signed or entirely unsigned, never a
    -- partial evidentiary claim.
    CONSTRAINT ck_pdc_consent_pairing CHECK (
        (consent_accepted_at IS NULL) = (consent_policy_version IS NULL)
        AND (consent_accepted_at IS NULL) = (consent_signer_name IS NULL)
        AND (consent_accepted_at IS NULL) = (consent_ip IS NULL))
);

-- Surrogate PK plus a partial unique index (not a composite PK), because
-- tombstoning nulls family_connection_id: at most one LIVE consent row per
-- (profile, connection), but any number of tombstoned rows with the same
-- profile once family_connection_id is NULL. See design plan 5.3, "PK
-- choice, stated because this repo has both patterns".
CREATE UNIQUE INDEX IF NOT EXISTS uq_pdc_profile_connection
    ON "public"."personalization_disclosure_consent" (child_profile_id, family_connection_id)
    WHERE family_connection_id IS NOT NULL;

-- 8.6: the viewer-side receive switch. Default TRUE: signing a
-- family_connection's own consent already implies willingness to receive
-- from that connection, so this is an opt-out, not an opt-in.
ALTER TABLE "public"."family"
    ADD COLUMN IF NOT EXISTS personalization_receive_enabled BOOLEAN NOT NULL DEFAULT TRUE;

-- 8.2: the personalization subject. SET NULL (not CASCADE, the one deviation
-- from this table's usual family_id/child_profile_id CASCADE pattern):
-- deleting the requesting profile must not delete a book another family has
-- on their shelf, but it must sever the personalization link so the book
-- reverts to generic everywhere (the erasure mechanism described in 8.5).
ALTER TABLE "public"."storybook"
    ADD COLUMN IF NOT EXISTS personalization_subject_profile_id UUID
        REFERENCES "public"."child_profile"(id) ON DELETE SET NULL;

-- Per-version eligibility flags and the derived sentinel manifest (Task R3).
ALTER TABLE "public"."storybook_version"
    ADD COLUMN IF NOT EXISTS personalization_eligible BOOLEAN NOT NULL DEFAULT FALSE,
    ADD COLUMN IF NOT EXISTS pronoun_parameterized BOOLEAN NOT NULL DEFAULT FALSE,
    ADD COLUMN IF NOT EXISTS sentinel_manifest JSONB;

COMMENT ON COLUMN "public"."storybook_version"."sentinel_manifest" IS
    'Stage R re-scope: the per-node token multiset that deterministic re-insertion actually produced (storybook/reinsertion.py build_manifest), written at re-insertion time, NOT a contract-prescribed expectation. Keyed {"tokens": {<node_id>: [...], "<node_id>::ending_title": [...]}}. Rescreen and at-rest checks read this column rather than re-deriving expectations from the contract; node-edit/repair adoption update it in place.';
