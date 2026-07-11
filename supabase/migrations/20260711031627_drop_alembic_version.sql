-- Alembic is retired (ADR-012); remove its bookkeeping table where it exists.
-- No-op on environments built from the Supabase baseline.
drop table if exists public.alembic_version;
