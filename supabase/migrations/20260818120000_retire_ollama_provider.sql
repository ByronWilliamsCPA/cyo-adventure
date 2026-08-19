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
