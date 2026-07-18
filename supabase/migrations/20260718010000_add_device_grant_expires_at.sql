-- #CRITICAL: timing: apply this migration BEFORE deploying the image that adds
-- DeviceGrant.expires_at to the ORM (db/models.py). Every full-entity
-- select(DeviceGrant) from the new code (the revocation check on every online
-- device-token use, plus the family device list) emits this column; against a
-- database without it, asyncpg raises UndefinedColumn and those paths 500
-- (migrate-before-deploy, mirroring 20260711204606_add_user_email.sql).
--
-- #252: persist the device grant's expiry on the row. Previously the 90-day
-- TTL (ADR-014) lived only inside the JWT, so an unrevoked-but-expired grant
-- (a "ghost": it can no longer mint a child session, yet its revoked_at is
-- NULL) still appeared in the guardian's active-device list. Storing expires_at
-- lets that list filter "revoked_at IS NULL AND expires_at > now()", so the
-- (correct) decision to drop revoked_at from the list wire schema rests on an
-- accurate "present == usable" invariant.
--
-- Three steps so the column can be NOT NULL without a DB default (which keeps
-- it in schema-parity with the ORM, whose column has no server_default):
--   1. add it nullable,
--   2. backfill existing rows from created_at + the documented 90-day TTL
--      (the exact TTL a pre-existing token was signed with is not recoverable;
--      the default is the best-available approximation and only affects rows
--      minted before this migration),
--   3. enforce NOT NULL now that every row has a value.

ALTER TABLE "public"."device_grant"
    ADD COLUMN IF NOT EXISTS "expires_at" timestamp with time zone;

UPDATE "public"."device_grant"
    SET "expires_at" = "created_at" + interval '90 days'
    WHERE "expires_at" IS NULL;

ALTER TABLE "public"."device_grant"
    ALTER COLUMN "expires_at" SET NOT NULL;

COMMENT ON COLUMN "public"."device_grant"."expires_at" IS
    'Wall-clock expiry (UTC), stamped at mint from the device-grant TTL (ADR-014). Lets the active-device list exclude unrevoked-but-expired ghosts (#252).';
