-- ADR-015: budget-consent delta (G7 guardian cost gate, complete; G13
-- interim per-family spend accounting; G3 per-child pre-authorization
-- envelopes). No request may spend generation budget until a guardian (or
-- the platform, for admin-authored catalog requests) consents; this
-- migration adds the columns that back that gate and its per-child
-- delegation setting. No ledger table yet (tracked as a G13 follow-up):
-- spend is derived by counting "public"."story_request" rows that entered
-- "approved" in the current UTC calendar month, which is why this
-- migration also adds "approved_at" (distinct from the existing
-- "reviewed_at", which is shared with the decline transition and cannot by
-- itself disambiguate "approved this month" from "declined this month").
--
-- src/cyo_adventure/story_requests/service.py is the sole writer of
-- "approved_at" (stamped once, in _build_concept, never updated afterward)
-- and the sole reader of the three budget columns added here; the FastAPI
-- Settings field "default_monthly_story_quota" (src/cyo_adventure/core/
-- config.py) is the platform-wide fallback a NULL "monthly_story_quota"
-- resolves to.

alter table "public"."family"
    add column if not exists "monthly_story_quota" integer;

-- "request_auto_approve" is NOT NULL on the ORM side
-- (ChildProfile.request_auto_approve: Mapped[bool] = mapped_column(default=False))
-- but carries NO server_default (mirrors "tts_enabled" in the baseline: a
-- plain "boolean NOT NULL" column, Python-side default only). Added nullable
-- first, backfilled, then constrained, rather than
-- "ADD COLUMN ... DEFAULT false NOT NULL", so the final catalog state has no
-- persisted column default -- matching what Base.metadata.create_all would
-- produce and what tests/integration/test_schema_parity.py checks for.
alter table "public"."child_profile"
    add column if not exists "request_auto_approve" boolean;

update "public"."child_profile"
    set "request_auto_approve" = false
    where "request_auto_approve" is null;

alter table "public"."child_profile"
    alter column "request_auto_approve" set not null;

alter table "public"."child_profile"
    add column if not exists "monthly_request_envelope" integer;

alter table "public"."story_request"
    add column if not exists "approved_at" timestamp with time zone;

DO $$
BEGIN
    ALTER TABLE "public"."family"
        ADD CONSTRAINT "ck_family_monthly_story_quota_non_negative"
        CHECK ((("monthly_story_quota" IS NULL) OR ("monthly_story_quota" >= 0)));
EXCEPTION
    WHEN duplicate_object THEN NULL;
END $$;

DO $$
BEGIN
    ALTER TABLE "public"."child_profile"
        ADD CONSTRAINT "ck_child_profile_monthly_request_envelope_non_negative"
        CHECK ((("monthly_request_envelope" IS NULL) OR ("monthly_request_envelope" >= 0)));
EXCEPTION
    WHEN duplicate_object THEN NULL;
END $$;

-- Back the "approved rows for this family/profile since <month start>" access
-- pattern the guardian cost gate and the new GET /families/me/budget
-- endpoint both use, mirroring the existing *_status composite indexes on
-- this table.
create index if not exists "ix_story_request_family_approved_at"
    on "public"."story_request" using "btree" ("family_id", "approved_at");

create index if not exists "ix_story_request_profile_approved_at"
    on "public"."story_request" using "btree" ("profile_id", "approved_at");
