-- Seed moderation_threshold with a visible, behaviour-preserving default grid.
--
-- Context (`RS-B2`, docs/planning/review-screen-remediation-plan-2026-08-31.md):
-- the owner's ruling was that moderation cutoff scores should scale by age
-- band. The mechanism now exists on both lanes (the guardian lane via
-- ThresholdPolicy.surfaces, the admin lane via `RS-B3`'s
-- moderation/thresholds.py::admin_noise_floor_for), but moderation_threshold
-- held ZERO rows in every environment including production, so the admin
-- console's threshold editor rendered an empty table and the feature read as
-- unimplemented. This seed makes the grid visible and editable.
--
-- WHAT THIS DOES NOT DO: it does not pick any cutoff. Every row carries
-- min_score = NULL, which moderation/thresholds.py::admin_noise_floor_for
-- resolves as "fall back to the flat admin noise floor", and min_verdict =
-- 'flag', which is byte-identical to
-- moderation/thresholds.py::DEFAULT_THRESHOLD. So both lanes behave exactly as
-- they did before this migration ran, on every band and every category.
-- Choosing the actual per-band numbers is `RS-CAL4`, which is blocked on a
-- fresh six-band recall capture (`RS-CAL3`); once it rules, the ruling is a
-- console edit through PUT /api/v1/admin/moderation-thresholds/{age_band},
-- not another migration.
--
-- WHY min_score = NULL AND NOT TODAY'S FLAT FLOOR (0.05): a row's min_score,
-- when present, WINS over the global moderation_setting noise floor. Seeding
-- a concrete number into every cell would therefore make that global dial
-- inert for every seeded pair, silently retiring the operator's one emergency
-- control. A NULL falls through to it instead, so the dial stays live.
-- #CRITICAL: security: if a future edit to this file replaces NULL with a
-- number, the flat floor stops applying to that pair and the global kill
-- switch quietly loses coverage. Any concrete score belongs in a console edit
-- with an audit row behind it, not in a migration nobody reviews again.
-- #VERIFY: tests/unit/test_admin_noise_floor.py::
-- test_a_row_without_a_min_score_falls_back_to_the_flat_floor
--
-- CATEGORY SCOPE: the six GRADED Stage-0 categories only, mirroring
-- moderation/thresholds.py::GRADED_SCORE_CATEGORIES exactly. The other seven
-- of the 13 live OpenAI categories are BRIGHT LINE
-- (moderation/classifiers.py::_OPENAI_BRIGHTLINE): a flagged bright-line
-- category BLOCKS, admin_surfaces never hides a BLOCK, and so a score floor on
-- one of them cannot change what any reviewer sees. Seeding a cell whose dial
-- does nothing would be an invitation to tune it.
--
-- BANDS: all six of storybook/models.py::AgeBand, which is also the domain the
-- ck_moderation_threshold_age_band CHECK constraint enforces.
--
-- Idempotent: ON CONFLICT on uq_moderation_threshold_band_category (added in
-- 20260710000000_baseline.sql, verified present in production) makes a re-run a
-- no-op, and DO NOTHING means it will never overwrite a cutoff an admin has
-- since set through the console. That last property is why this is DO NOTHING
-- and not DO UPDATE: a DO UPDATE here would silently revert every operator
-- decision on the next migration replay.
--
-- 6 bands x 6 graded categories = 36 rows.

INSERT INTO "public"."moderation_threshold"
    ("id", "age_band", "category", "min_verdict", "min_score")
SELECT
    gen_random_uuid(),
    "band",
    "category",
    'flag',
    NULL
FROM
    (VALUES ('3-5'), ('5-8'), ('8-11'), ('10-13'), ('13-16'), ('16+'))
        AS "bands" ("band"),
    (VALUES
        ('harassment'),
        ('hate'),
        ('illicit'),
        ('self-harm'),
        ('violence'),
        ('violence/graphic')
    ) AS "categories" ("category")
ON CONFLICT ("age_band", "category") DO NOTHING;
