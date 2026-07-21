-- Seed the provider/model allowlist with the canonical default set.
--
-- Context: provider_model_allowlist gates which (provider, model_id) pairs an
-- admin may pick for automated story authoring (generation/allowlist.py,
-- is_enabled_allowlist_pair). The baseline migration
-- (20260710000000_baseline.sql) CREATEs the table but seeds no rows, and the
-- original Alembic seed migration referenced by allowlist.py
-- (migrations/versions/20260709_1000_add_provider_model_allowlist.py) was never
-- ported when the project moved to Supabase CLI migrations (ADR-012). Result:
-- every fresh database (local, staging, prod) starts with an EMPTY allowlist,
-- so the admin authoring dialog renders empty provider/model dropdowns and no
-- automated authoring job can be configured.
--
-- These rows mirror generation/allowlist.py::DEFAULT_ALLOWLIST EXACTLY. The two
-- are hand-synced by contract (see the docstring on DEFAULT_ALLOWLIST).
-- #ASSUME: data integrity: if DEFAULT_ALLOWLIST changes, this seed must change
-- with it; there is no automated check tying the two together.
-- #VERIFY: keep provider/model_id/display_name in lockstep with allowlist.py.
--
-- Idempotent: ON CONFLICT on the uq_provider_model_allowlist_provider_model
-- unique (provider, model_id) constraint makes re-running a no-op, and it will
-- not re-enable or relabel a row an admin has since edited.

INSERT INTO "public"."provider_model_allowlist"
    ("id", "provider", "model_id", "enabled", "display_name")
VALUES
    (gen_random_uuid(), 'anthropic', 'claude-sonnet-4-6', true, 'Claude Sonnet 4.6 (direct)'),
    (gen_random_uuid(), 'anthropic', 'claude-haiku-4-5', true, 'Claude Haiku 4.5 (direct)'),
    (gen_random_uuid(), 'openrouter', 'anthropic/claude-haiku-4.5', true, 'OpenRouter primary (Haiku 4.5)'),
    (gen_random_uuid(), 'openrouter', 'anthropic/claude-sonnet-4.6', true, 'OpenRouter fallback (Sonnet 4.6)'),
    (gen_random_uuid(), 'ollama', 'qwen2.5:14b', true, 'Ollama local default')
ON CONFLICT ("provider", "model_id") DO NOTHING;
