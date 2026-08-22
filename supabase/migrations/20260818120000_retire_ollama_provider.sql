-- Retire "ollama" as a selectable generation backend.
--
-- Context: the Ollama leg is being removed ahead of the homelab-to-Vultr move
-- (the local GPU that made a self-hosted leg free does not exist in the cloud
-- tier). The adapter, the OLLAMA_* config surface, and the "ollama" member of
-- generation/allowlist.py::ALLOWLIST_PROVIDERS are all gone in the same change,
-- so an allowlist row naming that provider can no longer be built into a
-- provider at generation time. Leaving the row in place would let an admin pick
-- a backend that raises ConfigurationError the moment a job runs.
--
-- Two steps, in this order:
--   1. DELETE the seeded row, so nothing violates the narrowed constraint.
--   2. Narrow ck_provider_model_allowlist_provider to the three live providers,
--      keeping it a mirror of ALLOWLIST_PROVIDERS (the two are hand-synced by
--      contract; see the DEFAULT_ALLOWLIST docstring).
--
-- The DELETE is deliberately a delete rather than an `enabled = false` update.
-- Disabling normally preserves audit history, but here the provider value
-- itself is about to become illegal under the CHECK, so a disabled row would
-- block the ALTER. History is not lost: provider_model_allowlist_audit carries
-- its own provider column with NO provider CHECK constraint, so existing
-- 'ollama' audit rows remain readable and are intentionally left untouched.
--
-- AUDIT GAP, DELIBERATE AND UNCLOSEABLE HERE. Every allowlist delete made
-- through the API writes a provider_model_allowlist_audit row BEFORE the delete,
-- in the same unit of work (api/provider_allowlist.py::delete_allowlist_entry).
-- This migration does not, so the audit table records no row for this removal.
-- That is not an oversight and must not be "fixed" by adding an INSERT here:
-- audit.changed_by is NOT NULL and foreign-keys to public.user(id), and this
-- project has no system or service-account user. The only ways to satisfy the
-- FK are to invent a synthetic user row, which pollutes the user table for
-- every other consumer, or to borrow a real admin's id, which would attribute a
-- deletion to a person who did not perform it. For an audit trail whose purpose
-- is attribution, a misattributed row is strictly worse than an absent one.
--
-- Where the record of this removal actually lives: this migration file and its
-- commit, plus the ADR-003 amendment of 2026-08-18. An operator asking "when and
-- why did ollama stop being allowlistable" is answered there, not by the audit
-- table. Pre-existing 'ollama' audit rows are left untouched and stay readable
-- (that column carries no CHECK), so the history of edits made while the row was
-- live is intact; only this final removal is absent from it.
--
-- #CRITICAL: data integrity: this narrows a CHECK constraint. It fails loudly
-- if any provider_model_allowlist row still names a provider outside the three
-- listed below, which is the intended behavior: an operator who hand-added an
-- ollama row should see the failure rather than have it silently dropped.
-- #VERIFY: after applying, `SELECT DISTINCT provider FROM
-- provider_model_allowlist;` must return only anthropic/openrouter/modal.
--
-- Idempotent: the DELETE is a no-op once the row is gone, and the constraint is
-- dropped with IF EXISTS before being recreated.

DELETE FROM "public"."provider_model_allowlist"
WHERE "provider" = 'ollama';

ALTER TABLE "public"."provider_model_allowlist"
    DROP CONSTRAINT IF EXISTS "ck_provider_model_allowlist_provider";

ALTER TABLE "public"."provider_model_allowlist"
    ADD CONSTRAINT "ck_provider_model_allowlist_provider"
    CHECK ((("provider")::"text" = ANY ((ARRAY[
        'anthropic'::character varying,
        'openrouter'::character varying,
        'modal'::character varying
    ])::"text"[])));
