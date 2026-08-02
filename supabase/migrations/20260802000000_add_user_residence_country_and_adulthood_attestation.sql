-- O-117 / O-119 (pre-launch compliance): residence country and adulthood
-- attestation, recorded on the adult ``user`` account rather than on
-- ``child_profile``.
--
-- residence_country: ISO 3166-1 alpha-2, nullable. Without a recorded
-- country signal the DSA Art. 2(1) and GDPR Art. 3(2) targeting tests cannot
-- be answered, and a market can be excluded by design rather than by hope.
-- Sized VARCHAR(2), not guessed at: alpha-2 codes are exactly two
-- characters, and a prior String(N) guess on this table truncated
-- 'awaiting_approval' in production (see db/models.py's status column
-- comment), so this column's width is derived from the actual value domain.
--
-- adulthood_attested_at: timezone-aware timestamp, nullable. Every age
-- regime that can attach at R2 locates its duty on the adult account, not
-- the kid profile; today age data lives only on child_profile.age_band and
-- series.age_band, neither of which is the adult signing the account into
-- existence.
--
-- Both are NEW columns on "user", not a reinterpretation of the existing
-- consent_accepted_at / consent_policy_version / consent_signer_name /
-- consent_ip quartet: that attestation text is "I am this child's parent or
-- legal guardian" (guardianship), not an age claim, and an attestation is
-- only worth the text that was shown. No separate attestation-version
-- column either: the new checkbox ships inside the same versioned consent
-- form, so consent_policy_version already records what text was shown when
-- the adulthood box was checked.
--
-- A guardian who consented before this migration keeps NULL in both new
-- columns: there is no re-consent-on-policy-change flow (mirrors
-- consent_accepted_at's own "written once, never overwritten" contract).
--
-- Table is schema-qualified ("public".*): see
-- 20260729000000_add_child_profile_personalization.sql's header comment for
-- why (the baseline migration empties search_path for the rest of the
-- session).

ALTER TABLE "public"."user"
    ADD COLUMN IF NOT EXISTS residence_country VARCHAR(2),
    ADD COLUMN IF NOT EXISTS adulthood_attested_at TIMESTAMPTZ;

-- DROP-then-ADD keeps re-application idempotent, matching
-- 20260801050000_add_child_profile_gamification_settings.sql's pattern for
-- a CHECK layered on an already IF NOT EXISTS-guarded ADD COLUMN.
ALTER TABLE "public"."user"
    DROP CONSTRAINT IF EXISTS ck_user_residence_country_format;
ALTER TABLE "public"."user"
    ADD CONSTRAINT ck_user_residence_country_format
        CHECK (residence_country IS NULL OR residence_country ~ '^[A-Z]{2}$');

-- RLS needs no change: policies on public."user" are the column-agnostic
-- USING (true) WITH CHECK (true) service-role policies added by
-- 20260720170200_add_service_role_policies.sql, and "user" carries no
-- tier-1 scoped policy for these two columns to interact with.

-- Forward-only migration per this project's Supabase CLI convention
-- (ADR-012); no down script.
