-- ADR-018 D1: wire the KWS verification into the consent register.
--
-- Two columns, for two different jobs.
--
-- kws_verification.location records what was sent to KWS for that attempt. ADR-018 D1
-- calls the location a compliance input rather than a routing detail, because it is what
-- selects which verification methods the parent is offered; the parent-verified event
-- reports neither the location nor the method, so an attempt that does not record it
-- leaves no trace of how the parent could have been verified. Same reasoning as
-- enabled_methods, which this column sits beside. Nullable: rows written before this
-- migration have no location and there is nothing honest to backfill them with.
--
-- "user".consent_verification_id records WHICH verification corroborated a given consent
-- event. Deliberately NOT folded into ck_user_consent_pairing (see
-- 20260802000000_add_user_residence_country_and_adulthood_attestation.sql for that
-- constraint's shape): NULL here is a real and permanent state meaning "recorded under
-- the typed-name-only mechanism, not itself backed by a verification". Every consent
-- record written before today is exactly that, and pairing the column would leave only
-- two ways out, falsifying those records or inventing evidence for them.
--
-- Nothing reads this column to decide whether a guardian may proceed. The gates
-- (api/profiles.py::_require_consent, api/admin_profiles.py::_require_family_consent)
-- ask consent/service.py::has_usable_verification, which queries kws_verification
-- directly, so a guardian who consented before verification existed can satisfy the gate
-- by verifying once without anything rewriting the consent record they already hold.
--
-- ON DELETE SET NULL, not CASCADE: erasing a verification attempt must never take the
-- 16 CFR 312.5(c) consent record with it. Added as a separate ALTER TABLE because "user"
-- and kws_verification now reference each other (kws_verification.user_id points back),
-- which is a cycle no CREATE TABLE ordering can satisfy; the ORM spells the same
-- constraint with use_alter=True for that reason, and tests/integration/
-- test_schema_parity.py compares the two databases the two paths build.
--
-- Table names are schema-qualified ("public".*) because the baseline migration empties
-- search_path for the rest of the session; "user" is additionally a reserved word and
-- stays quoted.

ALTER TABLE "public"."kws_verification"
    ADD COLUMN IF NOT EXISTS location VARCHAR(16);

-- FORMAT only, in the same spirit as ck_user_residence_country_format: an ISO 3166-1
-- alpha-2 country ("US") or an ISO 3166-2 subdivision ("US-CA"). Membership is enforced
-- at the API boundary, and KWS itself rejects codes it does not know, so a membership
-- check here would only add a second list to keep in sync.
ALTER TABLE "public"."kws_verification"
    DROP CONSTRAINT IF EXISTS ck_kws_verification_location_format;
ALTER TABLE "public"."kws_verification"
    ADD CONSTRAINT ck_kws_verification_location_format
    CHECK (location IS NULL OR location ~ '^[A-Z]{2}(-[A-Z0-9]{1,3})?$');

ALTER TABLE "public"."user"
    ADD COLUMN IF NOT EXISTS consent_verification_id UUID;

ALTER TABLE "public"."user"
    DROP CONSTRAINT IF EXISTS fk_user_consent_verification_id;
ALTER TABLE "public"."user"
    ADD CONSTRAINT fk_user_consent_verification_id
    FOREIGN KEY (consent_verification_id)
    REFERENCES "public"."kws_verification"(id) ON DELETE SET NULL;

-- Forward-only migration per this project's Supabase CLI convention (ADR-012); no down
-- script.
