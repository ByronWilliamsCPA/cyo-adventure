-- Phase 2 / ADR-018 D1 (verifiable parental consent): a guardian's
-- signature-capture consent record, layered on the Supabase/Google OAuth
-- login that already authenticates them. A typed full-legal-name
-- attestation counts as the FTC's "sign and submit electronically" method
-- (312.5(b)(2)(i)); consent_ip and consent_accepted_at are the
-- corroborating evidence a controller must be able to produce on request.
-- Written once by src/cyo_adventure/api/onboarding.py::_record_consent and
-- never overwritten afterward.
--
-- Mirrors 20260717160000_add_family_connection_consent.sql's pattern: all
-- four columns nullable, added if-not-exists, with a pairing CHECK so none
-- can be set without the others.

alter table "public"."user"
    add column if not exists "consent_accepted_at" timestamp with time zone;

alter table "public"."user"
    add column if not exists "consent_policy_version" character varying(32);

alter table "public"."user"
    add column if not exists "consent_signer_name" character varying(200);

alter table "public"."user"
    add column if not exists "consent_ip" character varying(64);

DO $$
BEGIN
    ALTER TABLE "public"."user"
        ADD CONSTRAINT "ck_user_consent_pairing"
        CHECK (
            (("consent_accepted_at" IS NULL) = ("consent_policy_version" IS NULL))
            AND (("consent_accepted_at" IS NULL) = ("consent_signer_name" IS NULL))
            AND (("consent_accepted_at" IS NULL) = ("consent_ip" IS NULL))
        );
EXCEPTION
    WHEN duplicate_object THEN NULL;
END $$;
