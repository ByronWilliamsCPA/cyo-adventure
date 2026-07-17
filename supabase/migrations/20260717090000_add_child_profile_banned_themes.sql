-- G2: per-child content controls. `allowed_content_flags` (jsonb) already
-- exists on "public"."child_profile" but has never been surfaced by the API;
-- this migration adds its sibling, `banned_themes`, a nullable jsonb list of
-- guardian-set free-list theme exclusions for that one child (e.g. "spiders",
-- "magic"), distinct from the band-derived content-flag ceilings that
-- `allowed_content_flags` overrides. Nullable so a profile created before
-- this migration reads back as NULL (no exclusions) rather than a
-- backfilled empty array masquerading as an explicit "reviewed, none set".
--
-- src/cyo_adventure/api/profiles.py is the only writer; every entry is
-- lowercased, control-character-stripped, and length-capped there before it
-- reaches this column. src/cyo_adventure/story_requests/brief.py reads both
-- columns back to populate a generated ConceptBrief's `content_nogo` and
-- `special_constraints` for that child.

alter table "public"."child_profile"
    add column if not exists "banned_themes" "jsonb";
