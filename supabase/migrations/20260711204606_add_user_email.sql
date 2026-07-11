-- P6-03 (JIT guardian provisioning): add a nullable email contact column to
-- public."user". The email is captured from the Supabase user at first-login
-- onboarding for receipts and consent records (P7-02); it may be an Apple
-- private-relay address and may change. It is contact data ONLY and is NEVER
-- an identity key: authn_subject remains the sole key. The column is nullable
-- so a subject with no email claim still provisions, and no unique constraint
-- or index is added (nothing joins or de-duplicates on this column).

ALTER TABLE "public"."user"
    ADD COLUMN IF NOT EXISTS "email" character varying(320);

COMMENT ON COLUMN "public"."user"."email" IS 'Contact data only (receipts/consent, P6-03/P7-02); from the Supabase user, may be an Apple relay address. NEVER an identity key; authn_subject is the key.';
