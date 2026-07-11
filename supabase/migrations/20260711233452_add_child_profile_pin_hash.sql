-- P6-07: optional guardian-set PIN for the kid profile picker.
-- Nullable, write-only credential material (pbkdf2_sha256$iters$salt$hash);
-- no API response ever returns this column, views expose has_pin only.
alter table if exists public.child_profile
    add column if not exists pin_hash text;
