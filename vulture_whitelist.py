"""Vulture dead-code baseline: findings adjudicated during the UW-F22 sweep.

71 of the 72 entries here were reviewed during the 2026-07-31 vulture
calibration (UW-F22, UW-F23) and found to be structurally consumed rather than
dead: Pydantic model fields read by FastAPI's serializer, SQLAlchemy attributes
set through the ORM, TypedDict keys read by the type checker, AST visitor
methods dispatched by name, enum members selected by value, and re-exported
imports. Vulture cannot see any of those callers, so it reports them at its
flat 60% confidence.

The 72nd is not a false positive. ``forwarded_allow_ips`` is a REAL finding
whose fix is deferred to UW-F25, and it is tagged inline below so the deferral
stays greppable rather than hiding among the adjudicated entries. Suppressing
it is what keeps ``uv run vulture`` at exit 0; the register row, not this file,
is what keeps it scheduled. Search this file for ``UW-`` before treating it as
a list of things that are known-fine.

The point of a baseline is that ``uv run vulture`` exits 0 on a clean tree, so
a NEW finding is a real signal rather than noise item 73. It takes effect
through ``paths`` in ``[tool.vulture]``; a whitelist that is not scanned does
nothing, and living at the repository root is not enough.

Regenerating (the ``src/ scripts/`` arguments are load-bearing):

    uv run vulture src/ scripts/ --make-whitelist > /tmp/wl.py

Positional paths override the configured ``paths`` list, which is what keeps
this file out of its own regeneration. Running plain
``uv run vulture --make-whitelist`` instead scans the whitelist alongside the
source, finds nothing left to report, and writes an EMPTY file that silently
un-suppresses every entry. Paste this docstring back on top afterwards; the
generator does not reproduce it.

Caveat worth knowing before adding to it: these entries are name-based, not
location-based. ``_.updated_by`` suppresses an unused ``updated_by`` attribute
ANYWHERE in the scanned tree, not only at the line in its trailing comment.
Widening this file therefore widens the blind spot; prefer fixing the finding.

Nothing imports or executes this file. The bare names below are deliberately
undefined; they exist only so vulture's parser counts them as uses, which is
why the file is excluded from Ruff and BasedPyright.
"""

passage_id  # unused variable (scripts/capture_stage0_baseline.py:173)
openai_flags  # unused variable (scripts/capture_stage0_baseline.py:190)
corpus_sha256  # unused variable (scripts/capture_stage0_baseline.py:206)
git_commit  # unused variable (scripts/capture_stage0_baseline.py:211)
_.openai_flags  # unused attribute (scripts/capture_stage0_baseline.py:583)
_.visit_AnnAssign  # unused method (scripts/check_type_hints.py:49)
_.consented_by_viewer_at  # unused attribute (src/cyo_adventure/api/family_connections.py:473)
_.consented_by_sharer_at  # unused attribute (src/cyo_adventure/api/family_connections.py:476)
_.consented_by_viewer_at  # unused attribute (src/cyo_adventure/api/family_connections.py:527)
_.consented_by_sharer_at  # unused attribute (src/cyo_adventure/api/family_connections.py:530)
KidFlagReasonLiteral  # unused import (src/cyo_adventure/api/flags.py:28)
KidFlagResolutionLiteral  # unused import (src/cyo_adventure/api/flags.py:28)
JobStatusLiteral  # unused import (src/cyo_adventure/api/generation.py:45)
uptime_seconds  # unused variable (src/cyo_adventure/api/health.py:78)
python_version  # unused variable (src/cyo_adventure/api/health.py:80)
MinVerdict  # unused import (src/cyo_adventure/api/moderation_dashboard.py:17)
MinVerdict  # unused import (src/cyo_adventure/api/moderation_thresholds.py:11)
_.updated_by  # unused attribute (src/cyo_adventure/api/moderation_thresholds.py:199)
_.updated_by  # unused attribute (src/cyo_adventure/api/moderation_thresholds.py:377)
ProviderName  # unused import (src/cyo_adventure/api/provider_allowlist.py:13)
_.updated_by  # unused attribute (src/cyo_adventure/api/provider_allowlist.py:196)
JobStatusLiteral  # unused import (src/cyo_adventure/api/story_requests.py:32)
# UW-F25: DEFERRED TRUE POSITIVE, not an adjudicated false positive. The
# setting really is never read; uvicorn's --forwarded-allow-ips CLI flag is
# what takes effect. Suppressed only to keep the baseline at exit 0. Delete
# this entry when UW-F25 lands, and do not let a regeneration quietly restore
# it without this comment.
forwarded_allow_ips  # unused variable (src/cyo_adventure/core/config.py:794)
run_cover_job_sync  # unused function (src/cyo_adventure/covers/worker.py:39)
word_count_a  # unused variable (src/cyo_adventure/diversity/leaf.py:54)
word_count_b  # unused variable (src/cyo_adventure/diversity/leaf.py:55)
min_d_uni  # unused variable (src/cyo_adventure/diversity/leaf.py:84)
max_d_uni  # unused variable (src/cyo_adventure/diversity/leaf.py:85)
provenance  # unused variable (src/cyo_adventure/diversity/panel.py:87)
CAP_BOUNDS  # unused variable (src/cyo_adventure/flywheel/cadence.py:58)
ALLOWLIST_PROVIDERS  # unused variable (src/cyo_adventure/generation/allowlist.py:25)
differentiation_level  # unused variable (src/cyo_adventure/generation/authoring_metadata.py:106)
variation_axis  # unused variable (src/cyo_adventure/generation/authoring_metadata.py:107)
age  # unused variable (src/cyo_adventure/generation/concept.py:158)
ending_summary  # unused variable (src/cyo_adventure/generation/concept.py:193)
variable_names  # unused variable (src/cyo_adventure/generation/concept.py:194)
point_of_view  # unused variable (src/cyo_adventure/generation/concept.py:242)
reading_level_target  # unused variable (src/cyo_adventure/generation/concept.py:250)
tone  # unused variable (src/cyo_adventure/generation/concept.py:261)
themes_allowed  # unused variable (src/cyo_adventure/generation/concept.py:266)
target_node_count  # unused variable (src/cyo_adventure/generation/concept.py:286)
structure_pattern  # unused variable (src/cyo_adventure/generation/concept.py:296)
desired_variables  # unused variable (src/cyo_adventure/generation/concept.py:317)
special_constraints  # unused variable (src/cyo_adventure/generation/concept.py:322)
_.combined  # unused property (src/cyo_adventure/generation/prompts.py:97)
make_canned_story_response  # unused function (src/cyo_adventure/generation/provider.py:683)
_.is_clean  # unused property (src/cyo_adventure/moderation/report.py:137)
lineage_version  # unused variable (src/cyo_adventure/mutation/bundle.py:152)
lineage_version  # unused variable (src/cyo_adventure/mutation/bundle.py:209)
expected_sha256  # unused variable (src/cyo_adventure/mutation/bundle.py:668)
actual_sha256  # unused variable (src/cyo_adventure/mutation/bundle.py:669)
TAU_STRUCT  # unused variable (src/cyo_adventure/mutation/floors.py:104)
M4  # unused variable (src/cyo_adventure/mutation/operators.py:4192)
_.require  # unused method (src/cyo_adventure/mutation/ops.py:164)
_.current_ending_id  # unused method (src/cyo_adventure/player/engine.py:130)
_.snapshot  # unused method (src/cyo_adventure/player/state.py:84)
interpretation_version  # unused variable (src/cyo_adventure/story_requests/interpretation.py:322)
kid_summary  # unused variable (src/cyo_adventure/story_requests/interpretation.py:325)
guardian_summary  # unused variable (src/cyo_adventure/story_requests/interpretation.py:326)
_.reviewed_by  # unused attribute (src/cyo_adventure/story_requests/service.py:677)
_.reviewed_by  # unused attribute (src/cyo_adventure/story_requests/service.py:872)
MEDIUM  # unused variable (src/cyo_adventure/storybook/models.py:183)
LONG  # unused variable (src/cyo_adventure/storybook/models.py:184)
PERIL  # unused variable (src/cyo_adventure/storybook/models.py:201)
SCARY_IMAGERY  # unused variable (src/cyo_adventure/storybook/models.py:202)
CONFLICT  # unused variable (src/cyo_adventure/storybook/models.py:203)
SAD_MOMENT  # unused variable (src/cyo_adventure/storybook/models.py:204)
safety_scope  # unused variable (src/cyo_adventure/storybook/models.py:478)
GLOBAL  # unused variable (src/cyo_adventure/storybook/theme_contract.py:110)
ROUTE  # unused variable (src/cyo_adventure/storybook/theme_contract.py:111)
TRACK  # unused variable (src/cyo_adventure/storybook/theme_contract.py:112)
