-- Provider accounting on generation_job: what a job consumed, and what it cost.
--
-- Seven nullable columns rather than one JSONB blob, and deliberately NOT folded into
-- generation_job.report, for one reason that outweighs the convenience: report is
-- purged. The ADR-007 retention rule (Phase 5 pg_cron, with the reviewed-job exemption
-- added in 20260810000000_exempt_reviewed_generation_job_report_from_purge.sql) nulls
-- report to shed raw model output. Cost history has to outlive that. "What has
-- generation cost us this quarter" is asked long after the prose it is derived from is
-- gone, and accounting living inside report would be deleted by a retention rule aimed
-- at something else, silently, with the row still present to make the loss invisible.
--
-- Every column is nullable and NULL means NOT RECORDED, never zero:
--
--   * Rows written before this migration have no accounting and there is nothing
--     honest to backfill them with. Same reasoning as kws_verification.location in
--     20260810120000_add_kws_location_and_consent_verification_link.sql.
--   * A job whose backend reported no token counts is a DIFFERENT state: it has a
--     provider_call_count and a non-zero provider_unknown_calls. Collapsing that into
--     zero tokens would make an un-instrumented provider look free, which is the exact
--     failure the application-layer usage accounting (generation/usage.py) is built to
--     prevent, so the schema must not reintroduce it underneath.
--
-- Consequence for readers: SUM() over these columns across jobs is a LOWER BOUND unless
-- the query also filters on provider_unknown_calls = 0 AND cost_complete, because the
-- sum silently skips NULLs. Nothing in the database can enforce that; it is enforced by
-- cost_complete existing as a stored column so the caller has to look at it.
--
-- cost_usd is NUMERIC(12,6), never a float type. Per-call amounts run to millionths of
-- a dollar (1000 tokens at $5/Mtok is $0.005) and these values are summed across
-- thousands of rows, which is precisely where binary floating point accumulates drift
-- nobody can attribute afterwards. Scale 6 represents a whole-token amount exactly at
-- today's per-Mtok prices; precision 12 leaves six integer digits, so one job would have
-- to cost $999,999 to overflow.
--
-- cost_complete is stored rather than derived because it is not derivable. A run can
-- report every token and still be un-costable, when a model has no entry in
-- core/pricing.py. This column records what the price table knew when the job ran; a
-- reader coming back after the table is filled in cannot reconstruct that.
--
-- Table name is schema-qualified ("public".*) because the baseline migration empties
-- search_path for the rest of the session.
--
-- On locking: ADD COLUMN with no DEFAULT and no constraint is a catalog-only change in
-- Postgres 11+. It takes ACCESS EXCLUSIVE on generation_job but does not rewrite the
-- table and does not scan it, so the lock is held for the catalog update alone. No
-- CHECK constraint is added here for the same reason: a non-negativity check would be
-- the only candidate, and it would force a validation scan to buy a guarantee the
-- writing path already provides (the counts come from
-- generation/usage.py::coerce_token_count, which rejects negatives before they reach a
-- ledger).

ALTER TABLE "public"."generation_job"
    ADD COLUMN IF NOT EXISTS provider_call_count INTEGER;

ALTER TABLE "public"."generation_job"
    ADD COLUMN IF NOT EXISTS provider_unknown_calls INTEGER;

ALTER TABLE "public"."generation_job"
    ADD COLUMN IF NOT EXISTS input_tokens INTEGER;

ALTER TABLE "public"."generation_job"
    ADD COLUMN IF NOT EXISTS output_tokens INTEGER;

ALTER TABLE "public"."generation_job"
    ADD COLUMN IF NOT EXISTS provider_duration_ms INTEGER;

ALTER TABLE "public"."generation_job"
    ADD COLUMN IF NOT EXISTS cost_usd NUMERIC(12, 6);

ALTER TABLE "public"."generation_job"
    ADD COLUMN IF NOT EXISTS cost_complete BOOLEAN;

-- Forward-only migration per this project's Supabase CLI convention (ADR-012); no down
-- script.
