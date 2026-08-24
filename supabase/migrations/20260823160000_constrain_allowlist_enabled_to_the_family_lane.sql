-- Hold the D1 family-lane rule at rest, not only at the API write path.
--
-- D1 (ruled 2026-08-23, `UW-C346`) restricts kid- and guardian-triggered
-- generation to `generation/provider.py::FAMILY_LANE_PROVIDERS`. Two layers
-- already enforce it. `build_provider(lane="family")` refuses a forbidden leg
-- at job time, and `api/provider_allowlist.py::_reject_enabling_outside_the_family_lane`
-- returns 422 for any admin write that would leave a forbidden provider's row
-- ENABLED. This constraint is the third layer, `UW-C350` part (b): the API is
-- not the only writer this table has. `20260823140000_align_allowlist_with_d1_lane_ruling.sql`
-- reached it directly, `scripts/seed_dev_data.py` writes every DEFAULT_ALLOWLIST
-- row on a fresh stack, and an operator with a psql prompt bypasses both. A
-- CHECK is the one place that covers all of them at once.
--
-- WHAT THE PREDICATE SAYS, and what it deliberately does not say. The rule is
-- about the ENABLED state, never about existence: an anthropic row MAY exist
-- while disabled, and must be able to. That is not a concession, it is the
-- design `20260823140000` depends on (`AL-589`): the original seed migration
-- inserts those rows `ON CONFLICT DO NOTHING`, which suppresses a re-insert
-- only while the row EXISTS, so a DELETED anthropic row comes back ENABLED on
-- any replay of that seed. Disabled-not-deleted is the only withdrawal that
-- survives a replay. A constraint forbidding the row outright would make that
-- migration unappliable and would break the seed script, which writes all six
-- DEFAULT_ALLOWLIST rows at their declared `enabled` value.
--
-- WHY 'mock' IS NOT IN THE LIST, even though FAMILY_LANE_PROVIDERS contains it.
-- The permitted set here is the INTERSECTION of FAMILY_LANE_PROVIDERS
-- ({mock, openrouter, modal}) with the providers this table may hold at all,
-- `ck_provider_model_allowlist_provider` / `allowlist.py::ALLOWLIST_PROVIDERS`
-- ({anthropic, openrouter, modal}). `mock` is a CI-only test double and is
-- excluded from the allowlist by that sibling constraint, so naming it here
-- would be dead text that reads as a permission. The intersection is
-- {modal, openrouter}, and anthropic is the only provider on which the two
-- constraints actually differ.
--
-- #CRITICAL: security: this pins the current meaning of `enabled`, which is
-- "selectable by the authoring-plan endpoint", the table's only lane-consuming
-- reader (`generation/allowlist.py::is_enabled_allowlist_pair`, called from
-- `story_requests/authoring_plan.py`). Every `build_provider` call site in the
-- tree today passes lane="family" or takes that restrictive default, so an
-- ENABLED row naming a forbidden provider is a pair the admin dialog offers
-- and the worker then refuses, turning a configuration error into a
-- generation-time failure attributed to the job. If an out-of-band ADMIN
-- generation surface is ever built (D1 keeps the direct Anthropic leg
-- legitimate for exactly that), a single `enabled` boolean can no longer carry
-- both answers: that change needs a lane representation on this table, and
-- must revise this constraint and the API guard together, not drop one of them.
-- #VERIFY: tests/integration/test_allowlist_family_lane_constraint.py::
-- test_an_enabled_forbidden_provider_row_is_rejected and
-- ::test_a_disabled_forbidden_provider_row_is_accepted.
--
-- #CRITICAL: data integrity: the two provider literals below are a COPY of a
-- Python constant and can drift from it silently, the same hand-synced-by-
-- contract exposure `DEFAULT_ALLOWLIST` carries. The tie is mechanical rather
-- than a comment: the verify test below reads FAMILY_LANE_PROVIDERS and
-- ALLOWLIST_PROVIDERS from the source, intersects them, and compares the
-- result against `pg_get_constraintdef` on a database built from this whole
-- migration chain. Editing either constant without editing this file fails
-- that test naming both sides.
-- #VERIFY: tests/integration/test_allowlist_family_lane_constraint.py::
-- test_the_constraint_literals_match_the_python_lane_constants.
--
-- #ASSUME: data integrity: no row already violates this, so the ALTER does not
-- fail on apply. It holds because of ORDER: `20260823140000` (a lower version,
-- therefore applied first) sets `enabled = false` for every anthropic row, and
-- the only other providers this table may hold are the two permitted here. A
-- database where that migration did not run, or where an operator re-enabled a
-- withdrawn row by hand afterwards, fails loudly at this ALTER. That is the
-- intended behavior and matches `20260818120000_retire_ollama_provider.sql`'s
-- stance on narrowing a CHECK: an operator who hand-enabled a forbidden pair
-- should see the failure rather than have it silently accepted.
-- #VERIFY: tests/integration/test_allowlist_family_lane_constraint.py::
-- test_the_seeded_rows_satisfy_the_constraint applies the full migration chain
-- to a fresh database, which is this ALTER succeeding against the seeded rows.
--
-- No AUDIT GAP note applies: this migration changes no row, so there is
-- nothing for `provider_model_allowlist_audit` to record. Contrast
-- `20260818120000` and `20260823140000`, which both write rows and both carry
-- that note.
--
-- Idempotent unconditionally: DROP ... IF EXISTS then ADD, the same shape
-- `20260818120000` uses. Deliberately NOT guarded by a conditional over the
-- catalog: a guard of the form `IF EXISTS (... AND pg_get_constraintdef NOT
-- LIKE ...)` is FALSE both when the constraint already matches and when it is
-- absent entirely, so it exits 0 having done nothing on a fresh database
-- (eleven migrations in this repo had that defect; fixed in `f072d583`).

ALTER TABLE "public"."provider_model_allowlist"
    DROP CONSTRAINT IF EXISTS "ck_provider_model_allowlist_enabled_family_lane";

ALTER TABLE "public"."provider_model_allowlist"
    ADD CONSTRAINT "ck_provider_model_allowlist_enabled_family_lane"
    CHECK (
        "enabled" IS FALSE
        OR (("provider")::"text" = ANY ((ARRAY[
            'modal'::character varying,
            'openrouter'::character varying
        ])::"text"[]))
    );
