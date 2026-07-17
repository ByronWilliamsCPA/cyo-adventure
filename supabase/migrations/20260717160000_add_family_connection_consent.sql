-- ADR-016 ring-2 delivery: dual-guardian consent for "public"."family_connection"
-- (register G17). PR #267 shipped the connection substrate admin-managed only;
-- ADR-016's Decision section requires ACTIVE consent from BOTH families'
-- guardians before any recommendation flows along a directional connection.
-- "family_id" is the viewer side (opts in to seeing "connected_family_id"'s
-- recommendations); this migration adds one nullable (user, timestamp) pair per
-- side. A connection is ACTIVE only when both pairs are set; a guardian
-- revoking their side sets that pair back to null, which deactivates the
-- connection immediately (no separate "active" column: it is always derived
-- from "both consent columns are non-null", so there is nothing to fall out of
-- sync). Consent is never implied by the admin who created the row: the
-- columns start null on every existing and newly created connection.
--
-- src/cyo_adventure/api/family_connections.py's new guardian consent
-- endpoints (POST/DELETE .../consent) are the sole writers; src/cyo_adventure/
-- api/recommendations.py (K17) is the sole reader of the dual-consent state,
-- enforced with a #CRITICAL security gate (a connection with only one side
-- consented contributes zero recommendations, never a partial result).

alter table "public"."family_connection"
    add column if not exists "consented_by_viewer_user_id" "uuid";

alter table "public"."family_connection"
    add column if not exists "consented_by_viewer_at" timestamp with time zone;

alter table "public"."family_connection"
    add column if not exists "consented_by_sharer_user_id" "uuid";

alter table "public"."family_connection"
    add column if not exists "consented_by_sharer_at" timestamp with time zone;

DO $$
BEGIN
    ALTER TABLE "public"."family_connection"
        ADD CONSTRAINT "family_connection_consented_by_viewer_user_id_fkey"
        FOREIGN KEY ("consented_by_viewer_user_id") REFERENCES "public"."user"("id");
EXCEPTION
    WHEN duplicate_object THEN NULL;
END $$;

DO $$
BEGIN
    ALTER TABLE "public"."family_connection"
        ADD CONSTRAINT "family_connection_consented_by_sharer_user_id_fkey"
        FOREIGN KEY ("consented_by_sharer_user_id") REFERENCES "public"."user"("id");
EXCEPTION
    WHEN duplicate_object THEN NULL;
END $$;

-- Pairing CHECKs: a consent user id and its timestamp are set or cleared
-- together, matching the ORM's (user FK, timestamp) pair semantics -- never a
-- timestamp with no recorded consenting guardian, or vice versa.
DO $$
BEGIN
    ALTER TABLE "public"."family_connection"
        ADD CONSTRAINT "ck_family_connection_viewer_consent_pairing"
        CHECK ((("consented_by_viewer_user_id" IS NULL) = ("consented_by_viewer_at" IS NULL)));
EXCEPTION
    WHEN duplicate_object THEN NULL;
END $$;

DO $$
BEGIN
    ALTER TABLE "public"."family_connection"
        ADD CONSTRAINT "ck_family_connection_sharer_consent_pairing"
        CHECK ((("consented_by_sharer_user_id" IS NULL) = ("consented_by_sharer_at" IS NULL)));
EXCEPTION
    WHEN duplicate_object THEN NULL;
END $$;

-- Back the K17 recommendations read path's "active connections where I am
-- the viewer" lookup (family_id = my family AND both consent columns set).
create index if not exists "ix_family_connection_active_viewer"
    on "public"."family_connection" using "btree" ("family_id")
    where (("consented_by_viewer_user_id" is not null) and ("consented_by_sharer_user_id" is not null));
