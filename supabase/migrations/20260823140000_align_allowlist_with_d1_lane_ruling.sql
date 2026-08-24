-- Align provider_model_allowlist with the D1 generation-lane ruling.
--
-- D1 (ruled 2026-08-23, `UW-C346`; docs/planning/generation-review-workstream-plan-2026-08-22.md
-- section 3) fixes which leg fills a kid- or guardian-triggered story: OpenRouter
-- or Modal, running `deepseek/deepseek-v4-pro` for the fill and
-- `deepseek/deepseek-v4-flash` for the review. The operator's own Anthropic
-- subscription is confined to out-of-band admin content generation, because
-- routing family-triggered work through it is outside that account's terms.
--
-- Two changes, both about making the API and the worker agree:
--
-- 1. ADD the two DeepSeek rows. `generation/allowlist.py::is_enabled_allowlist_pair`
--    is the single read path the authoring-plan endpoint trusts, so without a row
--    here an admin cannot select the model the settings default now runs, and the
--    ruling would hold only as a default rather than as a choice.
--
-- 2. DISABLE the two direct-anthropic rows. `generation/provider.py::build_provider`
--    now refuses the direct `anthropic` leg on the "family" lane, and every job
--    this covers was created by a guardian for a family, either from a story
--    request or from the legacy concept intake (`POST /concepts/{id}/generate`,
--    which carries no authoring metadata and so resolves the global default
--    provider), so an ENABLED anthropic row is a pair this endpoint accepts and
--    the worker then fails on. The failure would surface at generation time,
--    attributed to the job rather than to the configuration that caused it.
--
-- #CRITICAL: security: DISABLE, never DELETE. `20260721230000_seed_provider_model_allowlist.sql`
-- inserts these two rows with `ON CONFLICT ("provider", "model_id") DO NOTHING`,
-- which suppresses a re-insert only while the row EXISTS. A deleted row is
-- therefore re-inserted ENABLED by any replay of that seed, silently restoring
-- the pair this migration exists to withdraw. Disabling is the state that
-- survives a replay, and it also leaves the admin UI able to show what was
-- withdrawn rather than making it vanish. Reproduced 2026-08-23 against a local
-- Supabase database: replaying the seed after this migration inserts 0 rows and
-- leaves both anthropic rows disabled, whereas deleting them first and then
-- replaying the seed re-inserts both with enabled = true.
-- #VERIFY: tests/unit/test_allowlist.py::
-- test_the_direct_anthropic_rows_are_retained_but_disabled pins the code-side
-- mirror; `SELECT provider, model_id, enabled FROM provider_model_allowlist
-- ORDER BY provider, model_id;` after applying must show both anthropic rows
-- with enabled = false and both deepseek rows with enabled = true.
--
-- #CRITICAL: data integrity: these rows mirror
-- `generation/allowlist.py::DEFAULT_ALLOWLIST` EXACTLY, including
-- `display_name` and `enabled`. The two are hand-synced by contract; the only
-- automated tie is the row COUNT
-- (tests/unit/test_allowlist.py::test_default_allowlist_has_six_seed_rows) and
-- the lane-coherence check over the code-side constant, neither of which reads
-- this file.
-- #VERIFY: keep provider/model_id/display_name/enabled in lockstep with
-- DEFAULT_ALLOWLIST whenever either side changes.
--
-- #ASSUME: payment/financial: `deepseek/deepseek-v4-pro` is priced in
-- `core/pricing.py` against its `azure/us` endpoint, not against the slug's
-- default route, and `core/pricing.py::ENDPOINT_PINS` is what makes a request
-- actually reach that endpoint. Selecting this pair through the allowlist runs
-- the same pinned path, because the pin is resolved per slug inside
-- `build_openrouter_leg` rather than per call site.
-- #VERIFY: tests/unit/test_openrouter_provider_pin.py::
-- test_a_priced_pin_is_applied_when_the_caller_names_no_order.
--
-- AUDIT GAP: this UPDATE writes no provider_model_allowlist_audit row, for the
-- same reason `20260818120000_retire_ollama_provider.sql` states in full:
-- changed_by is NOT NULL and foreign-keys to public.user(id), and this project
-- has no system or service-account user to attribute a migration-driven change
-- to. See that migration's comment for the complete reasoning; it is not
-- repeated here.
--
-- Idempotent, under two different re-run policies for the two statements
-- below, and the difference is deliberate rather than an inconsistency:
--
-- The INSERT is ON CONFLICT DO NOTHING on the natural key, not DO UPDATE: an
-- admin who has since renamed or re-enabled one of the two deepseek rows
-- through the API should not have that edit silently reverted by a re-run.
--
-- The UPDATE is a no-op once both anthropic rows already read false, but it
-- does NOT preserve an admin's edit the way the INSERT does. Every re-run
-- re-applies enabled = false (and the display_name CASE) to provider =
-- 'anthropic' unconditionally, overriding any rename or re-enable an admin
-- has made through the API since. That is correct under D1: the ruling
-- withdraws the anthropic provider from the family lane wholesale, not only
-- the two model ids seeded on 2026-07-21, so an admin-added anthropic row of
-- any model id is exactly what this statement exists to catch, and the WHERE
-- clause is scoped to the whole provider for that reason.

INSERT INTO "public"."provider_model_allowlist"
    ("id", "provider", "model_id", "enabled", "display_name")
VALUES
    (gen_random_uuid(), 'openrouter', 'deepseek/deepseek-v4-pro', true,
     'OpenRouter fill (DeepSeek V4 Pro)'),
    (gen_random_uuid(), 'openrouter', 'deepseek/deepseek-v4-flash', true,
     'OpenRouter review (DeepSeek V4 Flash)')
ON CONFLICT ("provider", "model_id") DO NOTHING;

UPDATE "public"."provider_model_allowlist"
SET "enabled" = false,
    "display_name" = CASE "model_id"
        WHEN 'claude-sonnet-4-6' THEN 'Claude Sonnet 4.6 (direct, withdrawn)'
        WHEN 'claude-haiku-4-5' THEN 'Claude Haiku 4.5 (direct, withdrawn)'
        ELSE "display_name"
    END,
    "updated_at" = now()
WHERE "provider" = 'anthropic';
