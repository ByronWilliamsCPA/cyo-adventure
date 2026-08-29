"""ADR-030 Decision 4 read allowlist, expressed as the job's only statements.

Every read the engagement-correlation job performs is one of the statements
below. :data:`READ_ALLOWLIST` is a hand-maintained mirror of ADR-030's Decision 4
table and is **not** derived from these statements, so a statement that reaches
for a denied column fails the allowlist test rather than redefining the
allowlist. That direction is the whole point: the ADR closes the read side by
default, including against columns added to these tables in future.

What is deliberately absent, each denial carrying its ADR reason:

- ``reading_state.path``, ``visit_set``, ``current_node``, ``var_state`` and the
  rest of the traversal block: one child's walk through a story graph is close
  to a behavioural fingerprint, and completion is available from ``completion``
  without any of it.
- ``reading_state.updated_by_device_id`` and the whole ``device_download`` table.
- ``kid_flag.node_id``: a passage pointer is finer than the aggregate this job
  is authorised to produce (Decision 5).
- ``rating.rated_at``/``updated_at``, ``kid_flag.created_at``/``resolved_*``:
  fine-grained timestamps and moderator identities.
- everything on ``child_profile`` except ``id`` and ``family_id``.
- ``storybook_assignment``: guardian behaviour, not child reading outcome.
- ``reading_activity_day``: it has no storybook column at all, so reading time
  cannot be joined per book by any query. A schema fact, not a preference.
- ``storybook_version.blob`` and ``skeleton_slug``: neither is allowlisted, which
  is why the artifact carries no age band and no skeleton slug.

``completion.found_at`` is read cast to a calendar date inside the database, so
the raw timestamp never crosses the connection: Decision 4 admits the column
"truncated to calendar date", and casting in SQL is the only reading of that
under which the untruncated value is never fetched.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Final

from sqlalchemy import Date, cast, select

from cyo_adventure.db.models import (
    ChildProfile,
    Completion,
    KidFlag,
    Rating,
    ReadingState,
    Storybook,
    StorybookVersion,
)

if TYPE_CHECKING:
    import uuid
    from collections.abc import Mapping
    from datetime import date

    from sqlalchemy import Select

# #CRITICAL: security: the closed set of columns this job may read (ADR-030
# Decision 4). Hand-maintained as a mirror of that table, never derived from the
# statements below, so a statement reaching a denied column fails by default.
# #VERIFY: tests/unit/test_engagement_correlation_queries.py::TestReadAllowlist::
# test_every_statement_selects_only_allowlisted_columns and
# ::test_no_denied_column_appears_in_any_compiled_statement.
READ_ALLOWLIST: Final[Mapping[str, frozenset[str]]] = {
    "storybook": frozenset(
        {
            "id",
            "visibility",
            "status",
            "current_published_version",
            "personalization_subject_profile_id",
        }
    ),
    "storybook_version": frozenset({"storybook_id", "version", "moderation_report"}),
    "child_profile": frozenset({"id", "family_id"}),
    "reading_state": frozenset({"child_profile_id", "storybook_id", "version"}),
    "completion": frozenset(
        {"child_profile_id", "storybook_id", "version", "ending_id", "found_at"}
    ),
    "rating": frozenset({"child_profile_id", "storybook_id", "value"}),
    "kid_flag": frozenset({"storybook_id", "version", "profile_id", "reason"}),
}

# Column names on the allowlisted tables that must never appear in a compiled
# statement. Named individually rather than derived, because the failure this
# guards against is a statement quietly acquiring one of them, and a derived
# list would move with the statement.
DENIED_COLUMNS: Final = frozenset(
    {
        "node_id",
        "path",
        "visit_set",
        "current_node",
        "var_state",
        "seed_var_state",
        "save_slots",
        "character_id",
        "state_revision",
        "last_event_id",
        "last_synced_at",
        "updated_by_device_id",
        "display_name",
        "age_band",
        "avatar",
        "pin_hash",
        "rated_at",
        "resolved_by",
        "resolved_at",
        "resolution",
        "blob",
        "blob_ref",
        "skeleton_slug",
        "approved_by",
        "created_by",
    }
)


def storybooks_statement() -> Select[tuple[str, str, str, int | None, object]]:
    """Return the candidate-storybook statement.

    Selects only what Decision 2's categorical exclusions and Decision 3's
    version scoping need. The exclusions are applied in
    :func:`~cyo_adventure.analysis.engagement_correlation.is_eligible` rather
    than in SQL, so a single tested predicate governs them and a query rewrite
    cannot quietly drop one.

    Returns:
        Select: The statement over ``storybook``.
    """
    return select(
        Storybook.id,
        Storybook.visibility,
        Storybook.status,
        Storybook.current_published_version,
        Storybook.personalization_subject_profile_id,
    )


def moderation_reports_statement() -> Select[tuple[str, int, object]]:
    """Return the statement carrying the Stage-4 engagement judgment.

    Returns:
        Select: The statement over ``storybook_version``.
    """
    return select(
        StorybookVersion.storybook_id,
        StorybookVersion.version,
        StorybookVersion.moderation_report,
    )


def reader_families_statement() -> Select[tuple[str, int, uuid.UUID]]:
    """Return the distinct reader-family statement.

    ``reading_state`` is read for distinct-reader identification only; the join
    to ``child_profile`` exists solely to resolve the reading child to the
    family the floor is counted over.

    Returns:
        Select: The statement over ``reading_state`` joined to ``child_profile``.
    """
    return (
        select(
            ReadingState.storybook_id,
            ReadingState.version,
            ChildProfile.family_id,
        )
        .join(ChildProfile, ReadingState.child_profile_id == ChildProfile.id)
        .distinct()
    )


def completion_families_statement() -> Select[tuple[str, int, uuid.UUID, date]]:
    """Return the completion statement, with the timestamp truncated in SQL.

    Returns:
        Select: The statement over ``completion`` joined to ``child_profile``,
            carrying ``found_at`` cast to a calendar date.
    """
    return (
        select(
            Completion.storybook_id,
            Completion.version,
            ChildProfile.family_id,
            cast(Completion.found_at, Date).label("found_on"),
        )
        .join(ChildProfile, Completion.child_profile_id == ChildProfile.id)
        .distinct()
    )


def rating_families_statement() -> Select[tuple[str, int, uuid.UUID]]:
    """Return the rating statement at family grain.

    Returns:
        Select: The statement over ``rating`` joined to ``child_profile``.
    """
    return select(
        Rating.storybook_id,
        Rating.value,
        ChildProfile.family_id,
    ).join(ChildProfile, Rating.child_profile_id == ChildProfile.id)


def flag_families_statement() -> Select[tuple[str, str, uuid.UUID]]:
    """Return the flag statement at family-and-reason grain.

    ``kid_flag.node_id`` is not selected and ``kid_flag.family_id``, which the
    table denormalises, is deliberately not used either: Decision 4 routes the
    family through ``child_profile`` for every outcome table, so one join shape
    governs the floor everywhere.

    Returns:
        Select: The statement over ``kid_flag`` joined to ``child_profile``.
    """
    return (
        select(
            KidFlag.storybook_id,
            KidFlag.reason,
            ChildProfile.family_id,
        )
        .join(ChildProfile, KidFlag.profile_id == ChildProfile.id)
        .distinct()
    )


ALL_STATEMENTS: Final = (
    storybooks_statement,
    moderation_reports_statement,
    reader_families_statement,
    completion_families_statement,
    rating_families_statement,
    flag_families_statement,
)
