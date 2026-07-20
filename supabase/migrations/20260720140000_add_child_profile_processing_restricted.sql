-- GDPR Article 18 (restriction of processing) / Article 21 (objection):
-- a minimal per-profile flag distinct from "child_profile"."deactivated_at".
-- Deactivation is the existing login/session-level soft-remove;
-- "processing_restricted_at" is the narrower "keep the data, stop actively
-- processing it" state Article 18 describes. A restricted profile still
-- reads its existing library normally; src/cyo_adventure/api/story_requests.py
-- refuses to submit a NEW request for it (the concrete point where this
-- profile's data would newly reach a third-party LLM/classifier provider).
-- Set/cleared only via src/cyo_adventure/api/profiles.py::update_profile
-- (guardian-only).

alter table "public"."child_profile"
    add column if not exists "processing_restricted_at" timestamp with time zone;
