-- ADR-018 D1 follow-up: index the columns the delivery-health readiness check reads.
--
-- consent/service.py::verification_delivery_health aggregates the whole table filtered
-- on kws_environment, and it is reached from api/health.py::check_kws_verification,
-- which api/health.py serves PUBLICLY and UNAUTHENTICATED. Two properties make the
-- missing index worth a migration rather than a note:
--
--   1. kws_verification rows are inserted before every send and are never deleted (see
--      api/consent.py's module docstring: exact counts are the whole reason the hourly
--      cap is computed from this table). The scan therefore grows monotonically and has
--      no ceiling.
--   2. The only index on this table today is ix_kws_verification_user_id, created for
--      the foreign key. It has kws_environment nowhere in it, so it cannot serve this
--      predicate at all, and the readiness aggregate is a sequential scan by
--      construction rather than by planner choice.
--
-- Leading column kws_environment because that is the equality term and the only one
-- present on every deployment; requested_at second because the stuck cutoff ranges over
-- it. The index deliberately stops there and does not try to COVER the query: the
-- aggregate's FILTER also reads status, so an index-only scan would need status and
-- resolved_at as third and fourth columns, and that write cost is not worth paying on a
-- table that gains exactly one row per verification email. Bounding the scan to one
-- environment is the whole benefit being bought here.
--
-- Not CONCURRENTLY: the Supabase CLI runs each migration inside a transaction and
-- CREATE INDEX CONCURRENTLY cannot run in one. The table is small enough at this scale
-- that the brief SHARE lock is not a user-visible stall; revisit if that stops being
-- true, which would mean running the CONCURRENTLY form out of band.

CREATE INDEX IF NOT EXISTS ix_kws_verification_environment_requested_at
    ON "public"."kws_verification" (kws_environment, requested_at);

-- Forward-only migration per this project's Supabase CLI convention (ADR-012); no down
-- script.
