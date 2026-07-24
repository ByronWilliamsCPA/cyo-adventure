-- Guardian-set per-child motion preference: when true, the reader/library
-- frontend treats this child's session as if prefers-reduced-motion were set
-- (band-tokens.css), regardless of the device's own OS-level preference.
-- Set/cleared only via src/cyo_adventure/api/profiles.py::update_profile
-- (guardian-only) or src/cyo_adventure/api/admin_profiles.py (admin-only).

alter table "public"."child_profile"
    add column if not exists "reduce_motion" boolean not null default false;
