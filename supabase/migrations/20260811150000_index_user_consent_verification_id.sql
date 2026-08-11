-- ADR-018 D1 follow-up: index the REFERENCING side of fk_user_consent_verification_id.
--
-- Postgres indexes the referenced side of a foreign key (kws_verification.id is already
-- the primary key) but never the referencing side. "user".consent_verification_id
-- therefore has no index, and the constraint is ON DELETE SET NULL, so every delete of a
-- kws_verification row makes the referential-integrity trigger go looking through "user"
-- for rows to null out. With no index that search is a sequential scan of "user", taken
-- once per deleted verification row.
--
-- That is not a hypothetical path. Erasure is the operation this table is built to
-- support: api/families.py's delete-my-family flow removes a family's kws_verification
-- rows, and a subject-erasure request under COPPA/GDPR does the same thing in bulk. The
-- shape that hurts is exactly the shape erasure has, many verification rows deleted in
-- one statement, each one re-scanning the same table.
--
-- Partial, because the column is NULL for every adult who has not completed a
-- KWS-corroborated consent, which today is all of them and after switch-on will still be
-- most rows for a long while. The RI trigger's lookup is an equality (`= $1`), which
-- implies IS NOT NULL, so the planner can prove the partial predicate is satisfied and
-- use this index for the check. Indexing only the non-NULL rows keeps it small enough
-- that the write cost on "user" is close to nothing.
--
-- Not CONCURRENTLY, for the same reason as
-- 20260810180000_add_kws_verification_delivery_health_index.sql: the Supabase CLI runs
-- each migration inside a transaction, and CREATE INDEX CONCURRENTLY cannot run in one.
-- At this scale the brief lock is not a user-visible stall; revisit if that stops being
-- true, which would mean running the CONCURRENTLY form out of band.

CREATE INDEX IF NOT EXISTS ix_user_consent_verification_id
    ON "public"."user" (consent_verification_id)
    WHERE consent_verification_id IS NOT NULL;

-- Forward-only migration per this project's Supabase CLI convention (ADR-012); no down
-- script.
