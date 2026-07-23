"""SQLAlchemy ORM models for the operational entities (tech-spec data model).

These map the Postgres tables that back the reader: family ownership, users and
their roles, per-child profiles, storybooks and their immutable versions, and the
per-child reading state and completions. The Storybook content blob is stored
inline on ``storybook_version.blob`` for Phase 1 (the MinIO ``blob_ref`` path is
deferred); see the module note on the blob column.

Enumerated columns (role, status, age band) are stored as strings validated at
the application boundary rather than native Postgres enums, which keeps schema
migrations simple and avoids enum-type churn.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    func,
    text,
)
from sqlalchemy import text as sa_text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from cyo_adventure.core.database import Base
from cyo_adventure.storybook.evaluator import VarState
from cyo_adventure.storybook.models import AgeBand

# All timestamps are stored timezone-aware (TIMESTAMP WITH TIME ZONE).
_TS = DateTime(timezone=True)

# Foreign-key target column names, named once to avoid duplicated string literals.
_FK_FAMILY = "family.id"
_FK_USER = "user.id"
_FK_CHILD_PROFILE = "child_profile.id"
_FK_STORYBOOK = "storybook.id"
_FK_CONCEPT = "concept.id"
_FK_SERIES = "series.id"
_FK_STORYBOOK_VERSION_STORYBOOK_ID = "storybook_version.storybook_id"
_FK_STORYBOOK_VERSION_VERSION = "storybook_version.version"

# ON DELETE action, named once to avoid duplicated string literals.
_ONDELETE_SET_NULL = "SET NULL"

# The single, well-known "system catalog" family that owns admin-initiated
# catalog-origin content (#173). Instead of making family_id nullable across
# StoryRequest/Concept/Storybook (and reworking every family-scoped authz check
# for a null owner), a catalog-origin request is owned by this fixed sentinel
# family; family_id stays a hard NOT NULL invariant everywhere, and the book
# reaches the shelf the normal way, becoming globally visible only when an admin
# publishes it with visibility='catalog' (ADR-005 human approval unchanged).
# The row is seeded by supabase/migrations (production) and the integration
# conftest (create_all tests); this UUID MUST match that seed. It is a stable,
# permanent sentinel and must never be reused for a real family.
# #CRITICAL: data integrity: this id is a load-bearing constant; the seed row
# must exist before any catalog-origin request is created, or its family_id FK
# insert fails. The "0ca7a109" prefix is a mnemonic for "catalog".
# #VERIFY: test_story_requests_authored catalog-origin tests + the seed
# migration's ON CONFLICT DO NOTHING insert.
CATALOG_FAMILY_ID = uuid.UUID("0ca7a109-0000-4000-8000-000000000000")
CATALOG_FAMILY_NAME = "Catalog (system)"

# The five storybook lifecycle states, named once for the CHECK constraint.
_STORYBOOK_STATUS_VALUES = (
    "'draft', 'in_review', 'needs_revision', 'published', 'archived'"
)

# The two visibility states for published books (WS-E, decision E1), named once
# for the CHECK constraint.
_STORYBOOK_VISIBILITY_VALUES = "'family', 'catalog'"

# The six generation-job lifecycle states, named once for the CHECK constraint.
# "awaiting_manual_fill" is set only for method="skeleton_fill" +
# mechanism="skill" jobs (see story_requests/authoring_plan.py), and cleared by
# generation/import_story.py::resume_manual_fill once the human-authored fill
# is imported.
_GENERATION_JOB_STATUS_VALUES = (
    "'queued', 'running', 'passed', 'needs_review', 'failed', 'awaiting_manual_fill'"
)

# The four story-request lifecycle states, named once for the CHECK constraint.
_STORY_REQUEST_STATUS_VALUES = "'pending', 'approved', 'declined', 'blocked'"

# Derived from the AgeBand enum so the at-rest CHECK can never drift from the
# application vocabulary; adding a band changes this SQL and thereby forces a
# new Supabase migration (the schema-parity gate in
# tests/integration/test_schema_parity.py flags the constraint difference).
_AGE_BAND_VALUES = ", ".join(f"'{band.value}'" for band in AgeBand)

# The three story-request initiator roles, length bands, and narrative styles
# (WS-B), named once for their CHECK constraints.
_STORY_REQUEST_INITIATOR_VALUES = "'child', 'guardian', 'admin'"
_STORY_REQUEST_LENGTH_VALUES = "'short', 'medium', 'long'"
_STORY_REQUEST_STYLE_VALUES = "'prose', 'gamebook'"

# The four cover-generation lifecycle states, named once for the CHECK constraint.
_COVER_STATUS_VALUES = "'none', 'generating', 'ready', 'failed'"

# The append-only pipeline_event vocabularies, named once for their CHECK
# constraints. event_type would ideally be derived from the EventType enum
# (see _AGE_BAND_VALUES for that pattern), but cyo_adventure.events.__init__
# imports events.writer, which imports db.models, so importing
# cyo_adventure.events.models from here creates a circular import; the
# values are listed verbatim instead and must be kept in sync with
# cyo_adventure.events.models.EventType by hand (see
# tests/unit/test_pipeline_event_check_vocab.py, the drift guard for this
# list).
_PIPELINE_EVENT_TYPE_VALUES = (
    "'request_created', 'request_approved', 'request_declined', "
    "'plan_assigned', 'generation_started', 'generation_finished', "
    "'moderation_completed', 'repair_applied', 'sent_back', 'released', "
    "'threshold_changed', 'noise_floor_changed', 'book_assigned', 'rated', "
    "'kid_flagged', 'flag_resolved', "
    "'user_managed', 'family_managed', 'family_connection_changed', "
    "'node_edited', 'profile_viewed', 'cell_saturated'"
)
_PIPELINE_ACTOR_ROLE_VALUES = "'system', 'guardian', 'child', 'admin', 'device'"
_PIPELINE_ENTITY_TYPE_VALUES = (
    "'story_request', 'generation_job', 'storybook', 'storybook_version', "
    "'series', 'storybook_assignment', 'rating', 'moderation_threshold', "
    "'moderation_setting', 'kid_flag', 'user', 'family', 'family_connection', "
    "'child_profile'"
)

# The four admin-user lifecycle states (WS-J admin user management, plus the
# self-signup approval track added alongside Phase 2): a guardian/admin
# created via the seed script is always 'active'; a row admin-created ahead
# of first sign-in starts 'pending' (see api/onboarding.py's email-match
# bind) and is trusted immediately once bound, since an admin already vetted
# it by creating the invite; an UNINVITED guardian's own first-login JIT
# provisioning (api/onboarding.py::_provision_guardian) starts
# 'awaiting_approval' instead of 'active' -- a deliberately parallel track
# from the invite flow, never sharing its 'pending' status value, so the two
# have no shared state to collide on (in particular, api/admin_users.py's
# duplicate-pending-invite-by-email check has nothing to do with this state).
# An admin approves ('awaiting_approval' -> 'active') or denies
# ('awaiting_approval' -> 'deactivated') via the existing
# PATCH /admin/users/{id} status transition. 'deactivated' blocks
# authentication (api/deps.py::require_principal) without deleting the row.
_USER_STATUS_VALUES = "'pending', 'active', 'deactivated', 'awaiting_approval'"


class UUIDPrimaryKeyMixin:
    """A UUID surrogate primary key, client-side defaulted via ``uuid.uuid4``.

    Mixed in alongside ``Base`` (never in place of it) on every ORM class
    whose primary key is a plain UUID surrogate. Excluded from ``Storybook``
    (``String`` natural key), ``ModerationSetting`` (``String`` natural key),
    and the five composite-primary-key tables (``StorybookVersion``,
    ``ReadingState``, ``Completion``, ``Rating``, ``StorybookAssignment``),
    which define their own primary keys.
    """

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)


class CreatedAtMixin:
    """A server-defaulted insert timestamp (UTC, TIMESTAMPTZ)."""

    created_at: Mapped[datetime] = mapped_column(_TS, server_default=func.now())


class UpdatedAtMixin:
    """A server-defaulted timestamp that also refreshes on every update."""

    updated_at: Mapped[datetime] = mapped_column(
        _TS, server_default=func.now(), onupdate=func.now()
    )


class Family(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    """A family: the ownership root for users, profiles, and stories."""

    __tablename__ = "family"
    __table_args__ = (
        CheckConstraint(
            "monthly_story_quota IS NULL OR monthly_story_quota >= 0",
            name="ck_family_monthly_story_quota_non_negative",
        ),
    )

    name: Mapped[str] = mapped_column(String(200))
    # ADR-015 G7: the guardian cost gate's per-family monthly spend ceiling
    # (spend = story requests that entered "approved" in the current UTC
    # calendar month, see story_requests/service.py::family_monthly_spend).
    # NULL means "use the platform default"
    # (settings.default_monthly_story_quota) rather than freezing a stale
    # per-row copy of that default at family-creation time, so raising the
    # platform default automatically lifts every family that has not been
    # given an explicit override.
    # #CRITICAL: payment/financial: this is the ceiling that gates real LLM
    # generation spend (ADR-003/ADR-015); a bug that treats NULL as
    # "unlimited" instead of "platform default" would let a family bypass
    # the cost gate entirely.
    # #VERIFY: story_requests/service.py::_resolve_family_quota is the only
    # reader; tests/unit/test_story_requests.py pins the None-falls-back
    # case and tests/integration/test_story_requests_budget.py pins the
    # override case end to end.
    monthly_story_quota: Mapped[int | None] = mapped_column(default=None)
    # Nullable timestamp rather than a status string (contrast User.status):
    # a family only ever has two states, so "when was it deactivated" is
    # strictly more useful than a third enum value would be. Set by
    # api/families.py's admin PATCH; deactivating a family cascades to
    # deactivate every member User/ChildProfile in the same transaction (so
    # the auth hot path only ever needs to check User.status), but
    # reactivating a family does NOT auto-reactivate its members (deliberate
    # asymmetry: an admin reactivates people individually).
    deactivated_at: Mapped[datetime | None] = mapped_column(_TS, default=None)


class Series(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    """A named, family-owned chain of storybooks (WS-B PR 3, decision B2).

    DB-level linkage only in WS-B: books reference a series via
    ``storybook.series_id``/``book_index``; the embedded document ``Series``
    metadata block (storybook/models.py) is NOT written, so the SR-1..SR-7
    cross-book validator stays dormant until WS-G adds structural chaining.

    Attributes:
        id: Surrogate primary key.
        family_id: Owning family (NOT NULL, decision B3; widening is WS-E).
        title: Guardian- or admin-ratified series title (screened at intake).
        age_band: The band every book in the series targets; continuations
            must match it (approval rejects a mismatch).
        carries_state: ADR-011 band rule: False (episodic) for '3-5'/'5-8',
            True for all higher bands.
        created_by: The ratifying user, or None.
        created_at: Wall-clock insert time (UTC, TIMESTAMPTZ).
    """

    __tablename__ = "series"
    __table_args__ = (
        CheckConstraint(
            f"age_band IN ({_AGE_BAND_VALUES})",
            name="ck_series_age_band",
        ),
    )

    # #CRITICAL: data-integrity: CASCADE (Phase 3a, GDPR/COPPA erasure): a
    # family's own series are family-owned content, deleted along with it.
    # #VERIFY: tests/integration/test_deletion_drill.py.
    family_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey(_FK_FAMILY, ondelete="CASCADE"), index=True
    )
    title: Mapped[str] = mapped_column(String(120))
    age_band: Mapped[str] = mapped_column(String(16))
    carries_state: Mapped[bool] = mapped_column()
    # SET NULL (Phase 3a): a deleted guardian's attribution is dropped; the
    # series row (family-owned content) survives independently of who
    # created it.
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey(_FK_USER, ondelete=_ONDELETE_SET_NULL), default=None
    )


class User(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    """An authenticated user (guardian, child, or admin) within a family.

    ``role`` is the single base persona; the ``is_admin`` flag is an
    orthogonal capability so one adult can be a guardian, an admin, or both:
    ``('guardian', false)`` is a plain guardian, ``('guardian', true)`` is a
    guardian who also holds the global admin capability, and ``('admin', *)``
    is an admin-only adult (the auth boundary treats the admin base role as
    implying the capability regardless of the flag).
    """

    __tablename__ = "user"
    # #CRITICAL: security: ``role`` is coerced to the closed Role enum at the auth
    # boundary (api/deps.py); this CHECK is the at-rest backstop so a non-API write
    # path cannot persist an unmodeled role that would then drive authorization.
    # The second CHECK keeps the admin capability off child rows: a child user
    # must never carry is_admin, since the flag grants global review/approval
    # power at the auth boundary.
    # #VERIFY: api/deps.Role(user.role) raises on any value outside this set;
    # api/deps.Principal.__post_init__ derives is_admin for the admin base role.
    __table_args__ = (
        CheckConstraint("role IN ('guardian', 'child', 'admin')", name="ck_user_role"),
        CheckConstraint(
            "role <> 'child' OR is_admin = false", name="ck_user_child_not_admin"
        ),
        CheckConstraint(
            "role <> 'admin' OR is_admin = true", name="ck_user_admin_role_flag"
        ),
        CheckConstraint(f"status IN ({_USER_STATUS_VALUES})", name="ck_user_status"),
        # Phase 2 / ADR-018 D1 (VPC): the four consent columns are set or
        # cleared together; there is no legitimate state with a signer name
        # but no timestamp, or vice versa. Mirrors
        # ck_family_connection_viewer_consent_pairing's pattern.
        # api/onboarding.py::_record_consent is the sole writer and already
        # only ever sets all four together or none; this CHECK is the at-rest
        # backstop for any other write path.
        # #VERIFY: tests/integration/test_onboarding_api.py::
        # test_onboarding_records_consent_once_and_is_idempotent.
        CheckConstraint(
            "(consent_accepted_at IS NULL) = (consent_policy_version IS NULL) "
            "AND (consent_accepted_at IS NULL) = (consent_signer_name IS NULL) "
            "AND (consent_accepted_at IS NULL) = (consent_ip IS NULL)",
            name="ck_user_consent_pairing",
        ),
    )

    # #CRITICAL: data-integrity: CASCADE (Phase 3a, GDPR/COPPA erasure): every
    # guardian/admin/child login row in a deleted family is deleted with it.
    # #VERIFY: tests/integration/test_deletion_drill.py.
    family_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey(_FK_FAMILY, ondelete="CASCADE"), index=True
    )
    role: Mapped[str] = mapped_column(String(16))
    # #CRITICAL: timing dependencies: migration
    # supabase/migrations/20260712000000_user_is_admin.sql must be applied
    # BEFORE an image carrying this column deploys. Every full-entity
    # select(User) (the auth path in api/deps.py::require_principal runs one
    # per authenticated request) emits this column; against a database
    # without it, asyncpg raises UndefinedColumn and every authenticated
    # endpoint 500s.
    # #VERIFY: apply the migration in each environment ahead of the image
    # rollout (migrate-before-deploy), per the header comment in the
    # migration file.
    is_admin: Mapped[bool] = mapped_column(
        server_default=sa_text("false"), default=False
    )
    authn_subject: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    # Contact data ONLY, never an identity key. Populated from the Supabase
    # user's email claim at JIT onboarding (P6-03) for receipts and consent
    # records (P7-02 fills consent); may be an Apple private-relay address and
    # may change. ``authn_subject`` is the sole key: nothing joins, authorizes,
    # or de-duplicates on this column, and it is nullable so a subject with no
    # email claim still provisions.
    # #CRITICAL: timing dependencies: migration
    # supabase/migrations/20260711204606_add_user_email.sql must be applied
    # BEFORE an image carrying this column deploys. Every full-entity
    # select(User) (the auth path in api/deps.py runs one per request) emits
    # this column; against a database without it, asyncpg raises
    # UndefinedColumn and every authenticated endpoint 500s.
    # #VERIFY: apply the migration in each environment ahead of the image
    # rollout (migrate-before-deploy), per the header comment in the
    # migration file.
    email: Mapped[str | None] = mapped_column(String(320), default=None)
    # Null for guardians; set for a child user to the single profile it may act on.
    # #CRITICAL: data-integrity: CASCADE (Phase 3a): deleting a ChildProfile
    # (the child's primary identity) also deletes its login binding, so a
    # child-profile-only deletion never strands a login row with no profile.
    # #VERIFY: tests/integration/test_deletion_drill.py.
    child_profile_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey(_FK_CHILD_PROFILE, ondelete="CASCADE"), default=None
    )
    # #CRITICAL: security: 'pending' is an admin-created invite row (WS-J):
    # its authn_subject is a synthetic placeholder (api/admin_users.py's
    # _PENDING_SUBJECT_PREFIX) that no real JWT can ever carry, but
    # require_principal ALSO rejects any non-'active' status explicitly as
    # defense in depth (same "unknown subject" message as an unrecognized
    # subject, so status is never a distinguishable oracle). 'deactivated' is
    # the soft-remove state for an admin/guardian; the row and its history
    # (stories, ratings, events) are preserved.
    # #VERIFY: tests/integration/test_admin_users_api.py::
    # test_deactivated_guardian_cannot_authenticate,
    # test_pending_invite_cannot_authenticate.
    # String(20): 'awaiting_approval' (17 chars) is the longest value in
    # _USER_STATUS_VALUES; String(16) truncated it (StringDataRightTruncationError).
    status: Mapped[str] = mapped_column(
        String(20), default="active", server_default=sa_text("'active'")
    )
    # #CRITICAL: security: Phase 2 / ADR-018 D1 verifiable-parental-consent
    # record. A guardian's typed full-legal-name attestation counts as the
    # FTC's "sign and submit electronically" method (312.5(b)(2)(i)) layered
    # on the OAuth login that already authenticates them; consent_ip and
    # consent_accepted_at are the corroborating evidence a controller must be
    # able to produce on request. Written once by
    # api/onboarding.py::_record_consent and never overwritten afterward (a
    # future re-consent-on-policy-change flow would be a distinct, explicit
    # action, not an implicit overwrite of an existing record).
    # #VERIFY: tests/integration/test_onboarding_api.py::
    # test_onboarding_records_consent_once_and_is_idempotent.
    consent_accepted_at: Mapped[datetime | None] = mapped_column(_TS, default=None)
    consent_policy_version: Mapped[str | None] = mapped_column(String(32), default=None)
    consent_signer_name: Mapped[str | None] = mapped_column(String(200), default=None)
    # #ASSUME: data-integrity: stored as the request's observed
    # request.client.host, which reflects the real client address (not the
    # trusted reverse proxy's) because uvicorn's forwarded_allow_ips already
    # trusts X-Forwarded-For from that proxy (see SECURITY.md's HTTPS
    # redirect note for the same trust boundary). A raw string, not a
    # Postgres INET column: this is an evidentiary record, never queried or
    # joined on, so INET's validation/operator features add nothing here.
    consent_ip: Mapped[str | None] = mapped_column(String(64), default=None)


class ChildProfile(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    """A per-child reading profile with age band and content caps."""

    __tablename__ = "child_profile"
    __table_args__ = (
        CheckConstraint(
            "monthly_request_envelope IS NULL OR monthly_request_envelope >= 0",
            name="ck_child_profile_monthly_request_envelope_non_negative",
        ),
        # Phase 4c: backs purge_stale_deactivated_profile_activity's WHERE
        # clause (supabase/migrations/20260720150000_add_retention_purge_jobs.sql).
        Index(
            "ix_child_profile_deactivated_at",
            "deactivated_at",
            postgresql_where=sa_text("deactivated_at IS NOT NULL"),
        ),
    )

    # #CRITICAL: data-integrity: CASCADE (Phase 3a, GDPR/COPPA erasure): a
    # family's own child profiles are deleted along with it.
    # #VERIFY: tests/integration/test_deletion_drill.py.
    family_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey(_FK_FAMILY, ondelete="CASCADE"), index=True
    )
    display_name: Mapped[str] = mapped_column(String(120))
    age_band: Mapped[str] = mapped_column(String(16))
    reading_level_cap: Mapped[float] = mapped_column(default=99.0)
    # #ASSUME: data integrity: keys are a subset of {"violence", "scariness",
    # "peril"} mapping to a ContentFlagLevel value (api/schemas.py
    # ContentFlagCaps); a missing key means "no override, defer to the
    # band's own ceiling" (validator/band_profile.py), never "no limit". The
    # column itself carries no CHECK constraint on shape; api/profiles.py is
    # the only writer and validates every value before it lands here.
    # #VERIFY: tests/integration/test_profiles.py content-flag-cap tests;
    # tests/unit/test_story_requests.py brief-derivation tests read this dict
    # back through brief_from_request.
    allowed_content_flags: Mapped[dict[str, object]] = mapped_column(
        JSONB, default=dict
    )
    # G2: guardian-set free-list theme exclusions for this child (e.g.
    # "spiders", "magic"), distinct from the band-derived content-flag
    # ceilings above. Nullable: unset means no additional exclusions, not an
    # empty-list default, so a profile created before this column existed
    # reads back as None rather than a spurious []. api/profiles.py is the
    # only writer; each entry is lowercased, control-character-stripped, and
    # length-capped there before it reaches this column.
    banned_themes: Mapped[list[str] | None] = mapped_column(JSONB, default=None)
    tts_enabled: Mapped[bool] = mapped_column(default=False)
    avatar: Mapped[str | None] = mapped_column(String(255), default=None)
    # #CRITICAL: security: write-only PIN credential material (P6-07), encoded
    # as pbkdf2_sha256$iters$salt$hash by core/pin.py. No API response may ever
    # serialize this column; profile views expose a derived has_pin bool only.
    # #VERIFY: tests/integration/test_profiles.py::test_pin_hash_never_serialized
    # asserts the raw response JSON never contains "pin_hash".
    pin_hash: Mapped[str | None] = mapped_column(Text, default=None)
    # ADR-015 G3: guardian-set per-child pre-authorization ("let this child's
    # requests auto-consent"). False by default: a guardian must explicitly
    # opt a child in. request_auto_approve alone is not sufficient to
    # auto-approve anything -- monthly_request_envelope must ALSO be set (see
    # below); the two columns are independent so a guardian can flip this on
    # ahead of setting an envelope without accidentally auto-approving under
    # an implicit "unlimited" envelope.
    request_auto_approve: Mapped[bool] = mapped_column(default=False)
    # The number of this child's own requests that may auto-approve in the
    # current UTC calendar month before new requests fall back to the
    # pending queue (story_requests/service.py::can_auto_approve). NULL means
    # "no envelope set", which by itself blocks auto-approval even when
    # request_auto_approve is True: pre-authorization delegates the click,
    # never the liability (ADR-015), so there is no implicit-unlimited state.
    # #CRITICAL: payment/financial: this bounds how much of the family's
    # budget one child can auto-spend without a guardian's per-request
    # click; a bug that treats NULL as "no limit" would let a
    # mis-configured profile drain the family's whole monthly quota.
    # #VERIFY: story_requests/service.py::can_auto_approve treats
    # monthly_request_envelope IS NULL as "cannot auto-approve", never as
    # unlimited; tests/unit/test_story_requests.py pins this.
    monthly_request_envelope: Mapped[int | None] = mapped_column(default=None)
    # Soft-remove (WS-J admin user management): a deactivated profile is
    # excluded from every listing a picker or guardian console reads
    # (api/deps.py::_resolve_profiles, api/profiles.py::list_profiles) and
    # api/child_sessions.py refuses to mint a new session for it, but its
    # reading history, ratings, and events are preserved.
    # #VERIFY: tests/integration/test_admin_profiles_api.py::
    # test_deactivated_profile_excluded_from_listing_and_session_mint.
    deactivated_at: Mapped[datetime | None] = mapped_column(_TS, default=None)
    # GDPR Article 18 (restriction of processing) / Article 21 (objection):
    # deliberately distinct from deactivated_at. Deactivation is the login/
    # session-level soft-remove above; this is the narrower "keep the data,
    # stop actively processing it" state Article 18 describes -- a restricted
    # profile still reads its existing library and login normally, but
    # api/story_requests.py refuses to submit a NEW request for it (the
    # concrete point where this profile's data would newly reach a
    # third-party LLM/classifier provider). Set/cleared only via
    # api/profiles.py::update_profile (guardian-only).
    # #VERIFY: tests/integration/test_profiles.py::
    # test_restrict_processing_blocks_new_story_requests.
    processing_restricted_at: Mapped[datetime | None] = mapped_column(_TS, default=None)


class FamilyConnection(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    """A directional cross-family opt-in for story recommendations (WS-J).

    ``family_id`` is the "viewer": the family that has opted in to seeing
    recommendations sourced from ``connected_family_id``. The relationship is
    deliberately one-way (admin decision): family_id -> connected_family_id
    does not imply the reverse, so mutual visibility is two rows, not one.
    The `Rating` model's (child_profile_id, storybook_id) grain was already
    shaped for the recommendation join (see its docstring); ``api/
    recommendations.py`` (K17) is the sole reader.

    ADR-016 (register G17): admin creation of a row is a permission edge only,
    never consent. A connection is ACTIVE, and contributes to K17
    recommendations, only when BOTH ``consented_by_viewer_user_id`` and
    ``consented_by_sharer_user_id`` are set; either guardian may revoke their
    own side at any time by clearing it back to ``None``, which deactivates
    the connection immediately (there is no separate stored "active" flag to
    fall out of sync -- it is always the two-columns-non-null check).

    Attributes:
        id: Surrogate primary key.
        family_id: The family opted in to receiving recommendations (viewer).
        connected_family_id: The family whose stories may be recommended.
        created_by: The admin who created the connection, or ``None``.
        created_at: Wall-clock insert time (UTC, TIMESTAMPTZ).
        consented_by_viewer_user_id: The viewer-side guardian's ``User.id``
            who consented, or ``None`` if the viewer has not (or no longer)
            consented.
        consented_by_viewer_at: When the viewer-side consent was recorded, or
            ``None``. Paired with ``consented_by_viewer_user_id`` (both null
            or both set; enforced by the migration's CHECK).
        consented_by_sharer_user_id: The sharer-side guardian's ``User.id``
            who consented, or ``None``.
        consented_by_sharer_at: When the sharer-side consent was recorded, or
            ``None``. Paired with ``consented_by_sharer_user_id``.
    """

    __tablename__ = "family_connection"
    __table_args__ = (
        CheckConstraint(
            "family_id <> connected_family_id", name="ck_family_connection_not_self"
        ),
        UniqueConstraint(
            "family_id", "connected_family_id", name="uq_family_connection_pair"
        ),
        CheckConstraint(
            "(consented_by_viewer_user_id IS NULL) = (consented_by_viewer_at IS NULL)",
            name="ck_family_connection_viewer_consent_pairing",
        ),
        CheckConstraint(
            "(consented_by_sharer_user_id IS NULL) = (consented_by_sharer_at IS NULL)",
            name="ck_family_connection_sharer_consent_pairing",
        ),
        # Mirrors the consent migration's partial index backing the K17
        # "active connections where I am the viewer" lookup; the schema-parity
        # test compares migration-built and ORM-built schemas, so it must
        # exist on both sides.
        Index(
            "ix_family_connection_active_viewer",
            "family_id",
            postgresql_where=sa_text(
                "consented_by_viewer_user_id IS NOT NULL"
                " AND consented_by_sharer_user_id IS NOT NULL"
            ),
        ),
    )

    # #CRITICAL: data-integrity: CASCADE both sides (Phase 3a): the connection
    # is a permission edge between two families, not identity data with its
    # own retention value; if either family is deleted, the edge is meaningless.
    # #VERIFY: tests/integration/test_deletion_drill.py.
    family_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey(_FK_FAMILY, ondelete="CASCADE"), index=True
    )
    connected_family_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey(_FK_FAMILY, ondelete="CASCADE"), index=True
    )
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey(_FK_USER, ondelete=_ONDELETE_SET_NULL), default=None
    )
    # #CRITICAL: data-integrity: deliberately NOT ondelete=SET NULL. The
    # viewer/sharer consent-pairing CHECK constraints below require
    # user_id and at to be null together; a bare SET NULL on only the
    # user_id FK would violate that CHECK the instant a cascade fires,
    # independent of whether this row is also being deleted in the same
    # statement (Postgres checks a non-deferred CHECK immediately per
    # affected row, not after the whole cascade resolves). This is safe:
    # every consenting user is a guardian in family_id or connected_family_id,
    # and this row already CASCADEs (above) whenever either family is
    # deleted, which is the only way this codebase ever deletes a User row.
    # A future feature that deletes one guardian while their family survives
    # would need to explicitly clear both columns in application code first.
    # #VERIFY: tests/integration/test_deletion_drill.py.
    consented_by_viewer_user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey(_FK_USER), default=None
    )
    consented_by_viewer_at: Mapped[datetime | None] = mapped_column(_TS, default=None)
    consented_by_sharer_user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey(_FK_USER), default=None
    )
    consented_by_sharer_at: Mapped[datetime | None] = mapped_column(_TS, default=None)


class Storybook(CreatedAtMixin, Base):
    """A story's lifecycle row; one per story id regardless of version."""

    __tablename__ = "storybook"
    # #CRITICAL: data integrity: ``status`` is the lifecycle ORM boundary, coerced
    # to the closed Status enum in publishing/state_machine.py; this CHECK is the
    # at-rest backstop so no write path persists a status outside the five resting
    # states. GenerationJob.status is a SEPARATE lifecycle with its own CHECK
    # (ck_generation_job_status), defined on that model.
    # #VERIFY: Status(storybook.status) raises on any value outside this set.
    __table_args__ = (
        CheckConstraint(
            f"status IN ({_STORYBOOK_STATUS_VALUES})",
            name="ck_storybook_status",
        ),
        CheckConstraint(
            f"visibility IN ({_STORYBOOK_VISIBILITY_VALUES})",
            name="ck_storybook_visibility",
        ),
        UniqueConstraint(
            "series_id", "book_index", name="uq_storybook_series_book_index"
        ),
        CheckConstraint(
            "book_index IS NULL OR book_index >= 1",
            name="ck_storybook_book_index",
        ),
        CheckConstraint(
            "(series_id IS NULL) = (book_index IS NULL)",
            name="ck_storybook_series_index_pairing",
        ),
    )

    id: Mapped[str] = mapped_column(String(120), primary_key=True)
    # #CRITICAL: data-integrity: CASCADE (Phase 3a, GDPR/COPPA erasure): a
    # family's own storybooks are family-owned content, deleted with it.
    # #VERIFY: tests/integration/test_deletion_drill.py.
    family_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey(_FK_FAMILY, ondelete="CASCADE"), index=True
    )
    current_published_version: Mapped[int | None] = mapped_column(default=None)
    status: Mapped[str] = mapped_column(String(20), default="draft")
    # #CRITICAL: security: ``visibility`` widens who can browse/assign this book
    # (WS-E decision E1/E5); the CHECK is the at-rest backstop and the app
    # boundary coerces through publishing.state_machine.Visibility.
    # #VERIFY: Visibility(storybook.visibility) raises on any value outside the set.
    visibility: Mapped[str] = mapped_column(
        String(16), default="family", server_default=text("'family'")
    )
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey(_FK_USER, ondelete=_ONDELETE_SET_NULL), default=None
    )
    # #CRITICAL: data-integrity: deliberately NOT ondelete=SET NULL, unlike
    # most nullable *_by/​*_id references in this file. The
    # ck_storybook_series_index_pairing CHECK requires series_id and
    # book_index to be null together; a bare SET NULL here would violate it
    # immediately (book_index is a plain int, not a FK the cascade can also
    # null). Not a real gap: this row always CASCADEs (family_id, above)
    # whenever its family is deleted, which is the same family that owns the
    # series, so there is no scenario in this codebase where a Series row is
    # deleted while its Storybook rows survive.
    series_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey(_FK_SERIES), default=None
    )
    book_index: Mapped[int | None] = mapped_column(default=None)


class StorybookVersion(CreatedAtMixin, Base):
    """An immutable version of a story, including its content blob.

    The Storybook JSON is stored inline on ``blob`` for Phase 1; ``blob_ref`` is
    reserved for the MinIO object key once object storage is wired (Phase 5).
    """

    __tablename__ = "storybook_version"

    # #CRITICAL: data-integrity: CASCADE (Phase 3a): a version is owned
    # entirely by its storybook; deleting the storybook deletes every version.
    # #VERIFY: tests/integration/test_deletion_drill.py.
    storybook_id: Mapped[str] = mapped_column(
        ForeignKey(_FK_STORYBOOK, ondelete="CASCADE"), primary_key=True
    )
    version: Mapped[int] = mapped_column(primary_key=True)
    blob: Mapped[dict[str, object]] = mapped_column(JSONB)
    blob_ref: Mapped[str | None] = mapped_column(String(512), default=None)
    validation_report: Mapped[dict[str, object] | None] = mapped_column(
        JSONB, default=None
    )
    moderation_report: Mapped[dict[str, object] | None] = mapped_column(
        JSONB, default=None
    )
    approved_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey(_FK_USER, ondelete=_ONDELETE_SET_NULL), default=None
    )
    published_at: Mapped[datetime | None] = mapped_column(_TS, default=None)
    model: Mapped[str | None] = mapped_column(String(120), default=None)
    prompt_version: Mapped[str | None] = mapped_column(String(120), default=None)
    # Which generation provider produced this version ("mock", "anthropic",
    # "openrouter", ...), or the "import" sentinel for a version created via
    # the offline authoring import path (generation/import_story.py) rather
    # than the live worker. Nullable: backfilled rows predating this column
    # (and any future write path that forgets to stamp it) simply have no
    # provenance recorded, which degrades to "unknown" for display, not an error.
    provider: Mapped[str | None] = mapped_column(String(120), default=None)
    # Which production skeleton (skeletons/<band>/<slug>.json) this version was
    # filled from, or None for a fresh_generation version, an imported book, or
    # any version predating this column (WS-C PR2). Set once, at persist time,
    # from the job's authoring_metadata["skeleton_slug"]; never backfilled.
    skeleton_slug: Mapped[str | None] = mapped_column(String(120), default=None)
    cover_image_url: Mapped[str | None] = mapped_column(String(512), default=None)
    cover_status: Mapped[str] = mapped_column(
        String(20), default="none", server_default="none"
    )

    __table_args__ = (
        CheckConstraint(
            f"cover_status IN ({_COVER_STATUS_VALUES})",
            name="ck_storybook_version_cover_status",
        ),
    )


class ReadingState(CreatedAtMixin, UpdatedAtMixin, Base):
    """Per-child, per-story reading progress with revision-based concurrency.

    ``visit_set`` is persisted as a JSON list (it drives ``once: true`` effects)
    and ``last_event_id`` records the most recently applied write so idempotent
    replays of an offline queue are no-ops.
    """

    __tablename__ = "reading_state"
    __table_args__ = (
        # A saved state is pinned to a concrete published version; the composite
        # FK prevents persisting a reading state for a version that does not exist.
        # CASCADE (Phase 3a): the version this state is pinned to is deleted
        # along with its storybook (see StorybookVersion.storybook_id).
        # #VERIFY: tests/integration/test_deletion_drill.py.
        ForeignKeyConstraint(
            ["storybook_id", "version"],
            [_FK_STORYBOOK_VERSION_STORYBOOK_ID, _FK_STORYBOOK_VERSION_VERSION],
            ondelete="CASCADE",
        ),
    )

    # #CRITICAL: data-integrity: CASCADE both FKs (Phase 3a): reading state is
    # child-linked data, purged with either the profile or the story it is
    # pinned to.
    # #VERIFY: tests/integration/test_deletion_drill.py.
    child_profile_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey(_FK_CHILD_PROFILE, ondelete="CASCADE"), primary_key=True
    )
    storybook_id: Mapped[str] = mapped_column(
        ForeignKey(_FK_STORYBOOK, ondelete="CASCADE"), primary_key=True
    )
    version: Mapped[int] = mapped_column()
    current_node: Mapped[str] = mapped_column(String(120))
    var_state: Mapped[VarState] = mapped_column(JSONB, default=dict)
    path: Mapped[list[str]] = mapped_column(JSONB, default=list)
    visit_set: Mapped[list[str]] = mapped_column(JSONB, default=list)
    save_slots: Mapped[dict[str, object]] = mapped_column(JSONB, default=dict)
    state_revision: Mapped[int] = mapped_column(default=0)
    last_event_id: Mapped[str | None] = mapped_column(String(64), default=None)
    updated_by_device_id: Mapped[str | None] = mapped_column(String(64), default=None)
    last_synced_at: Mapped[datetime | None] = mapped_column(_TS, default=None)


class Completion(Base):
    """Records that a child found a particular ending of a story version."""

    __tablename__ = "completion"
    __table_args__ = (
        # CASCADE (Phase 3a): the version this completion is pinned to is
        # deleted along with its storybook (see StorybookVersion.storybook_id).
        # #VERIFY: tests/integration/test_deletion_drill.py.
        ForeignKeyConstraint(
            ["storybook_id", "version"],
            [_FK_STORYBOOK_VERSION_STORYBOOK_ID, _FK_STORYBOOK_VERSION_VERSION],
            ondelete="CASCADE",
        ),
    )

    # #CRITICAL: data-integrity: CASCADE (Phase 3a): completions are
    # child-linked data, purged with the profile.
    # #VERIFY: tests/integration/test_deletion_drill.py.
    child_profile_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey(_FK_CHILD_PROFILE, ondelete="CASCADE"), primary_key=True
    )
    storybook_id: Mapped[str] = mapped_column(String(120), primary_key=True)
    version: Mapped[int] = mapped_column(primary_key=True)
    ending_id: Mapped[str] = mapped_column(String(120), primary_key=True)
    found_at: Mapped[datetime] = mapped_column(_TS, server_default=func.now())


class Rating(UpdatedAtMixin, Base):
    """A child's 1-5 rating of a storybook.

    Unlike ``Completion``, which pins to an immutable ``storybook_version`` via a
    composite FK, a rating is about the *book* as a whole and is **mutable**: a
    child may re-rate, overwriting the prior value. The coarser
    ``(child_profile_id, storybook_id)`` grain is also what the cross-family
    lineage join in Phase B will need.
    """

    __tablename__ = "rating"
    __table_args__ = (
        CheckConstraint("value BETWEEN 1 AND 5", name="ck_rating_value_range"),
    )

    # #CRITICAL: data-integrity: CASCADE both FKs (Phase 3a): ratings are
    # child-linked data, purged with either the profile or the storybook.
    # #VERIFY: tests/integration/test_deletion_drill.py.
    child_profile_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey(_FK_CHILD_PROFILE, ondelete="CASCADE"), primary_key=True
    )
    storybook_id: Mapped[str] = mapped_column(
        String(120), ForeignKey(_FK_STORYBOOK, ondelete="CASCADE"), primary_key=True
    )
    # #CRITICAL: data integrity: ``value`` is bounded 1-5 at the API boundary by
    # RatingBody and enforced at rest by the ck_rating_value_range CHECK above,
    # so a non-API write path (admin script, backfill, raw SQL) cannot persist an
    # out-of-range value that would then be served back to clients.
    # #VERIFY: RatingBody schema tests cover the boundary; the DB CHECK is the
    # at-rest backstop.
    value: Mapped[int] = mapped_column()
    rated_at: Mapped[datetime] = mapped_column(_TS, server_default=func.now())


class StorybookAssignment(CreatedAtMixin, Base):
    """A guardian's grant of one published story to one child profile.

    Composite-keyed on ``(child_profile_id, storybook_id)`` so a profile is
    assigned a book at most once. ``assigned_by`` records the granting guardian,
    or NULL for a system backfill (the migration that preserves pre-assignment
    visibility). This table is the read-gate: the library listing and the direct
    version fetch both filter on it, so a child sees only stories explicitly
    assigned to their profile.
    """

    __tablename__ = "storybook_assignment"
    # #CRITICAL: security: this row is the sole authority for whether a child may
    # see a story; the composite PK indexes the child-side lookup, and the extra
    # index serves the storybook-side lookup used by the guardian assign list and
    # the migration backfill. A missing/duplicate row must not silently widen or
    # narrow visibility.
    # #VERIFY: composite PK enforces at-most-one; api/library.py gates both read
    # paths on an EXISTS/IN over this table.
    __table_args__ = (Index("ix_storybook_assignment_storybook_id", "storybook_id"),)

    # #CRITICAL: data-integrity: CASCADE both FKs (Phase 3a): an assignment
    # grant is child-linked, purged with either the profile or the storybook.
    # #VERIFY: tests/integration/test_deletion_drill.py.
    child_profile_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey(_FK_CHILD_PROFILE, ondelete="CASCADE"), primary_key=True
    )
    storybook_id: Mapped[str] = mapped_column(
        String(120), ForeignKey(_FK_STORYBOOK, ondelete="CASCADE"), primary_key=True
    )
    assigned_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey(_FK_USER, ondelete=_ONDELETE_SET_NULL), default=None
    )


class Concept(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    """A generation concept brief: the intake form for a story request.

    One Concept row is created per guardian request and holds the serialized
    ``ConceptBrief`` payload. A concept drives one or more ``GenerationJob``
    attempts; the brief is immutable once written.

    Attributes:
        id: Surrogate primary key.
        family_id: Owning family; all access checks are scoped to this.
        brief: The full ``ConceptBrief`` JSON blob (age band, topic, constraints,
            etc.). Schema is validated at the application boundary before insert.
        created_by: The guardian user who submitted the concept. Nullable because
            the system may create concepts without a logged-in user in tests.
        created_at: Wall-clock insert time (UTC, TIMESTAMPTZ).
    """

    __tablename__ = "concept"

    # #CRITICAL: data-integrity: CASCADE (Phase 3a, GDPR/COPPA erasure): a
    # family's own concepts are family-owned content, deleted with it. Also
    # cascades to GenerationJob.concept_id below (NOT NULL there), which
    # would otherwise block this delete with an FK violation.
    # #VERIFY: tests/integration/test_deletion_drill.py.
    family_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey(_FK_FAMILY, ondelete="CASCADE"), index=True
    )
    # #ASSUME: data integrity: ``brief`` shape is validated by ConceptBrief
    # Pydantic model before insertion; the DB stores raw JSON with no
    # column-level schema constraint.
    # #VERIFY: ensure all write paths go through ConceptBrief.model_validate
    # before calling session.add(Concept(...)).
    brief: Mapped[dict[str, object]] = mapped_column(JSONB)
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey(_FK_USER, ondelete=_ONDELETE_SET_NULL), default=None
    )


class StoryRequest(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    """A child's free-text story idea awaiting a guardian or admin decision.

    Submitted by a child (running under the guardian token in R1). The request
    text is screened at submission (PII guard + Stage-0 classifiers); a
    bright-line hit lands the row in the ``blocked`` state before any guardian
    reads the raw text. A guardian or admin then approves it (which builds a
    ``ConceptBrief`` and enters the generation pipeline, linking ``concept_id``)
    or declines it.

    ``family_id`` is denormalized (stored, not derived from ``profile_id``) so
    the guardian list and the family-scope authz check stay single-table; a
    profile never changes family, so the value cannot drift.

    Attributes:
        id: Surrogate primary key.
        family_id: Owning family; all guardian access is scoped to this.
        profile_id: The requesting child profile, or ``None`` for a
            profile-less request (WS-B PR 2).
        request_text: The child's short free-text idea (<= 500 chars).
        status: Lifecycle state (pending, approved, declined, blocked).
        initiator_role: Who submitted the request (child, guardian, admin).
        age_band: The reading band the request targets. Required at flush
            with no default: every creation path must set it explicitly (from
            the requesting profile, or from the guardian's confirmation), so a
            missed path fails loudly instead of silently drifting.
        length: The requested story length (short, medium, long), or ``None``
            before a guardian confirms it.
        narrative_style: The requested narrative style (prose, gamebook).
        moderation_flags: Redacted screening findings (category/verdict/message
            plus a blocked flag), or ``None`` before screening. Never raw
            classifier score/source.
        interpretation: The serialized WS-7 ``RequestInterpretation`` (K19): the
            kid/guardian reflection of what was built in versus set aside and
            why, or ``None`` before the general layer runs. Phase-3 personal
            data (deletion rides this row; export must include it; the
            declined/blocked 30-day purge nulls each element's premise-derived
            ``element`` phrase, keeping dispositions/reasons/template texts).
            Blocked rows never carry premise-derived element text (CR-1).
        reviewed_by: The guardian/admin who approved or declined, or ``None``.
        reviewed_at: When the decision was recorded, or ``None``.
        approved_at: When the request entered ``approved`` specifically, or
            ``None`` for a request that is still pending, was declined, or
            was blocked. Distinct from ``reviewed_at`` (shared by both the
            approve and decline transitions) so ADR-015's monthly spend
            derivation (story_requests/service.py::family_monthly_spend) can
            filter on approval alone without also relying on ``status`` to
            disambiguate; stamped once, in ``_build_concept``, and never
            updated afterward (a request's lifecycle is one-way: it never
            re-enters ``pending`` after reaching ``approved``).
        concept_id: The concept created on approval, or ``None``.
        series_id: The series this request continues, or ``None`` for a
            standalone request (WS-B PR 3).
        anchor_storybook_id: The storybook this soft continuation follows on
            from, or ``None``.
        proposed_series_title: The kid's original series title proposal,
            retained as an audit trail after ratification or request decline.
        created_at: Wall-clock insert time (UTC, TIMESTAMPTZ).
    """

    __tablename__ = "story_request"
    # #CRITICAL: data integrity: ``status``, ``initiator_role``, ``age_band``,
    # ``length``, and ``narrative_style`` are closed vocabularies; these CHECKs
    # are the at-rest backstop (mirroring ck_generation_job_status) so no write
    # path persists a value outside them. ck_story_request_style_band is the
    # child-safety backstop for ADR-011: gamebook branching is teen-only
    # ('13-16', '16+'), so no row can pair a gamebook request with a younger
    # band even if an application bug slips one past the API.
    # #VERIFY: the API boundary rejects out-of-vocabulary values first:
    # api/schemas.py::StoryRequestStatus coercion for status, and
    # StoryRequestApproveBody's AgeBand/Length/NarrativeStyle enums plus its
    # _style_allowed_for_band validator (which mirrors style_band) at approve.
    __table_args__ = (
        CheckConstraint(
            f"status IN ({_STORY_REQUEST_STATUS_VALUES})",
            name="ck_story_request_status",
        ),
        CheckConstraint(
            f"initiator_role IN ({_STORY_REQUEST_INITIATOR_VALUES})",
            name="ck_story_request_initiator_role",
        ),
        CheckConstraint(
            f"age_band IN ({_AGE_BAND_VALUES})",
            name="ck_story_request_age_band",
        ),
        CheckConstraint(
            f"length IS NULL OR length IN ({_STORY_REQUEST_LENGTH_VALUES})",
            name="ck_story_request_length",
        ),
        CheckConstraint(
            f"narrative_style IN ({_STORY_REQUEST_STYLE_VALUES})",
            name="ck_story_request_narrative_style",
        ),
        CheckConstraint(
            "narrative_style = 'prose' OR age_band IN ('13-16', '16+')",
            name="ck_story_request_style_band",
        ),
        # A request may propose a NEW series title or continue an existing
        # series via an anchor, never both. The name reflects the two columns
        # actually constrained (proposed_series_title, anchor_storybook_id);
        # ``series_id`` is guarded separately below.
        CheckConstraint(
            "NOT (proposed_series_title IS NOT NULL "
            "AND anchor_storybook_id IS NOT NULL)",
            name="ck_story_request_title_anchor_mutex",
        ),
        # #ASSUME: data-integrity: an anchored (continuation) request always
        # carries the anchor's series id; generation.series_link relies on it
        # to assign book_index, so a null series_id on an anchored row would
        # silently drop the storybook out of its series.
        # #VERIFY: every anchored-insert path sets series_id from resolve_anchor
        # (api/story_requests.py kid + authored create); this constraint blocks
        # a drifted row from a manual edit or a future code path.
        CheckConstraint(
            "anchor_storybook_id IS NULL OR series_id IS NOT NULL",
            name="ck_story_request_anchor_requires_series",
        ),
        Index("ix_story_request_family_status", "family_id", "status"),
        Index("ix_story_request_profile_status", "profile_id", "status"),
        Index("ix_story_request_status", "status"),
        # ADR-015: the guardian cost gate and the budget endpoint both query
        # "approved rows for this family/profile since <month start>"; these
        # back that access pattern the same way the *_status indexes above
        # back the status-scoped ones.
        Index("ix_story_request_family_approved_at", "family_id", "approved_at"),
        Index("ix_story_request_profile_approved_at", "profile_id", "approved_at"),
        # Phase 4c: backs purge_blocked_declined_story_request_text's WHERE
        # clause (supabase/migrations/20260720150000_add_retention_purge_jobs.sql).
        Index("ix_story_request_status_reviewed_at", "status", "reviewed_at"),
    )

    # #CRITICAL: data-integrity: CASCADE (Phase 3a, GDPR/COPPA erasure): a
    # family's own story requests are family-owned content, deleted with it.
    # #VERIFY: tests/integration/test_deletion_drill.py.
    family_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey(_FK_FAMILY, ondelete="CASCADE")
    )
    # SET NULL (Phase 3a): deleting one child profile de-links their
    # requests rather than deleting them; the family-owned request (and its
    # moderation history) survives at the family level.
    profile_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey(_FK_CHILD_PROFILE, ondelete=_ONDELETE_SET_NULL), default=None
    )
    request_text: Mapped[str] = mapped_column(String(500))
    status: Mapped[str] = mapped_column(String(16), default="pending")
    initiator_role: Mapped[str] = mapped_column(
        String(16), default="child", server_default="child"
    )
    age_band: Mapped[str] = mapped_column(String(16))
    length: Mapped[str | None] = mapped_column(String(16), default=None)
    narrative_style: Mapped[str] = mapped_column(
        String(16), default="prose", server_default="prose"
    )
    # #CRITICAL: security: redacted findings only (category/verdict/message +
    # blocked flag); raw classifier score/source and the child's raw text of a
    # blocked request are NEVER stored here or surfaced to a guardian.
    # #VERIFY: story_requests/screening.py builds this via the GuardianFinding
    # projection; test_story_requests covers the redaction shape.
    moderation_flags: Mapped[dict[str, object] | None] = mapped_column(
        JSONB, default=None
    )
    # #CRITICAL: security: one serialized RequestInterpretation (WS-7 K19), the
    # kid/guardian reflection of what was built in vs set aside and why. This is
    # Phase-3 PERSONAL DATA tied to the child's request: deletion rides this
    # parent story_request row (the Phase 3a purge/cascade must enumerate this
    # table); the future guardian export (Phase 3c) MUST include it; and the
    # declined/blocked 30-day retention purge nulls each element's `element`
    # phrase while keeping dispositions/reasons/template texts (catalog prose,
    # not premise content), matching the redacted-retention posture. Blocked
    # rows NEVER carry premise-derived element text to begin with (CR-1). Old
    # rows stay NULL (the migration does not backfill).
    # #VERIFY: supabase/migrations/20260720000000_add_story_request_interpretation.sql
    # adds the column and the purge job; story_requests/interpretation.py's echo
    # floor keeps `element` phrases echo-safe before they are persisted here.
    interpretation: Mapped[dict[str, object] | None] = mapped_column(
        JSONB, default=None
    )
    reviewed_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey(_FK_USER, ondelete=_ONDELETE_SET_NULL), default=None
    )
    reviewed_at: Mapped[datetime | None] = mapped_column(_TS, default=None)
    approved_at: Mapped[datetime | None] = mapped_column(_TS, default=None)
    concept_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey(_FK_CONCEPT, ondelete=_ONDELETE_SET_NULL), default=None
    )
    # #CRITICAL: data-integrity: deliberately NOT ondelete=SET NULL, unlike
    # most nullable references here. ck_story_request_anchor_requires_series
    # requires series_id to be set whenever anchor_storybook_id is set; a bare
    # SET NULL on series_id alone (with anchor_storybook_id still set) would
    # violate that CHECK. Not a real gap: this row always CASCADEs (family_id,
    # above) whenever its family is deleted, the same family that owns the
    # series, so there is no scenario in this codebase where a Series row is
    # deleted while a referencing StoryRequest survives.
    series_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey(_FK_SERIES), default=None
    )
    anchor_storybook_id: Mapped[str | None] = mapped_column(
        String(120),
        ForeignKey(_FK_STORYBOOK, ondelete=_ONDELETE_SET_NULL),
        default=None,
    )
    proposed_series_title: Mapped[str | None] = mapped_column(String(120), default=None)


_MIN_VERDICT_VALUES = "'advisory', 'flag', 'block'"


class ModerationThreshold(UUIDPrimaryKeyMixin, UpdatedAtMixin, Base):
    """Sparse per-(age_band, category) override of the surfacing default.

    Absence of a row means the code default applies
    (``moderation/thresholds.py::DEFAULT_THRESHOLD``). The table is small
    (admin-curated), so policy loads read it whole.

    Attributes:
        id: Surrogate primary key.
        age_band: The reader age band this override applies to.
        category: The moderation category this override applies to.
        min_verdict: Minimum verdict severity that surfaces to review
            (one of ``advisory``, ``flag``, ``block``).
        min_score: Optional classifier-score floor in [0.0, 1.0], or
            ``None`` to use the verdict gate alone.
        updated_by: The admin who last edited this override, or ``None``.
        updated_at: Last edit time (UTC, TIMESTAMPTZ).
    """

    __tablename__ = "moderation_threshold"
    # #CRITICAL: data integrity / security: these overrides gate which
    # moderation findings surface for review by age band; a row persisted with
    # an unknown min_verdict or an out-of-range min_score could silently relax
    # what content reaches children, and an unknown age_band would be a dead
    # row the loader silently skips. The ck_moderation_threshold_age_band,
    # ck_moderation_threshold_min_verdict, and ck_moderation_threshold_min_score
    # CHECKs are the at-rest backstop against any non-API write path (admin
    # script, backfill, raw SQL).
    # #VERIFY: moderation/thresholds.py validates at the application boundary;
    # tests/integration/test_moderation_threshold_migration.py round-trips the
    # migration that creates both CHECKs.
    __table_args__ = (
        CheckConstraint(
            f"age_band IN ({_AGE_BAND_VALUES})",
            name="ck_moderation_threshold_age_band",
        ),
        CheckConstraint(
            f"min_verdict IN ({_MIN_VERDICT_VALUES})",
            name="ck_moderation_threshold_min_verdict",
        ),
        CheckConstraint(
            "min_score IS NULL OR (min_score >= 0.0 AND min_score <= 1.0)",
            name="ck_moderation_threshold_min_score",
        ),
        UniqueConstraint(
            "age_band", "category", name="uq_moderation_threshold_band_category"
        ),
    )

    age_band: Mapped[str] = mapped_column(String(16))
    category: Mapped[str] = mapped_column(String(64))
    min_verdict: Mapped[str] = mapped_column(String(16))
    min_score: Mapped[float | None] = mapped_column(default=None)
    # SET NULL (Phase 3a): this is a global admin-config row, not family- or
    # child-owned; a deleted admin's attribution is dropped, the override
    # itself survives.
    updated_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey(_FK_USER, ondelete=_ONDELETE_SET_NULL), default=None
    )


class ModerationThresholdAudit(UUIDPrimaryKeyMixin, Base):
    """Append-only audit of threshold edits (who changed what, when).

    Deliberately minimal: WS-D's pipeline_event log will subsume this role;
    keep this table write-only until then.

    Attributes:
        id: Surrogate primary key.
        age_band: The age band of the edited override.
        category: The moderation category of the edited override.
        action: What happened, either ``upsert`` or ``delete``.
        old_min_verdict: Verdict floor before the edit, or ``None`` on insert.
        new_min_verdict: Verdict floor after the edit, or ``None`` on delete.
        old_min_score: Score floor before the edit, or ``None``.
        new_min_score: Score floor after the edit, or ``None``.
        changed_by: The admin who made the edit, or ``None`` if that admin's
            account has since been erased (Phase 3a; see RAD tag).
        changed_at: When the edit was recorded (UTC, TIMESTAMPTZ).
    """

    __tablename__ = "moderation_threshold_audit"
    # #ASSUME: data integrity: the audit trail is only trustworthy if every row
    # names a known action; a typo'd action written by a non-API path (script,
    # raw SQL) would silently corrupt the "who changed what" record. No age_band
    # CHECK here on purpose: audit rows are history, and retiring a band must
    # not invalidate old records.
    # #VERIFY: the WS-A admin API writes only 'upsert'/'delete';
    # tests/integration/test_moderation_threshold_migration.py round-trips the
    # migration that creates this CHECK.
    __table_args__ = (
        CheckConstraint(
            "action IN ('upsert', 'delete')",
            name="ck_moderation_threshold_audit_action",
        ),
    )

    age_band: Mapped[str] = mapped_column(String(16))
    category: Mapped[str] = mapped_column(String(64))
    action: Mapped[str] = mapped_column(String(16))  # 'upsert' | 'delete'
    old_min_verdict: Mapped[str | None] = mapped_column(String(16), default=None)
    new_min_verdict: Mapped[str | None] = mapped_column(String(16), default=None)
    old_min_score: Mapped[float | None] = mapped_column(default=None)
    new_min_score: Mapped[float | None] = mapped_column(default=None)
    # #CRITICAL: security / data integrity: every threshold edit is
    # attributable AT WRITE TIME (the WS-A admin API always stamps a real
    # admin here; there is no code path that inserts NULL). The column is
    # nullable with ON DELETE SET NULL, not NOT NULL, specifically so a
    # guardian/admin's Article 17 self-deletion (Phase 3a) is never blocked
    # by an FK violation on audit rows from before their account was erased;
    # the audit row (what changed, when) survives, only the "who" attribution
    # is dropped. Rows are append-only by convention (no update/delete path in
    # the application layer) until WS-D's pipeline_event log subsumes this
    # table.
    # #VERIFY: the round-trip test in
    # tests/integration/test_moderation_threshold_migration.py covers the
    # migration that creates this FK; the WS-A admin API must write one audit
    # row per upsert/delete and never mutate existing rows;
    # tests/integration/test_deletion_drill.py covers the erasure path.
    changed_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey(_FK_USER, ondelete=_ONDELETE_SET_NULL), default=None
    )
    changed_at: Mapped[datetime] = mapped_column(_TS, server_default=func.now())


class PipelineEvent(UUIDPrimaryKeyMixin, Base):
    """Append-only log of every story-lifecycle transition (WS-D capture layer).

    Written from the transaction performing the transition (spec decision D1). Rows
    are enforced append-only by a DB trigger created in the migration; the ORM never
    updates or deletes them. ``actor_id`` is NULL for system transitions (worker,
    moderation), which carry ``actor_role='system'`` (spec decision D2). ``payload``
    is PII-free by contract, gated by events/writer.py::_PAYLOAD_ALLOWLIST (D3).
    """

    __tablename__ = "pipeline_event"
    __table_args__ = (
        CheckConstraint(
            f"event_type IN ({_PIPELINE_EVENT_TYPE_VALUES})",
            name="ck_pipeline_event_event_type",
        ),
        CheckConstraint(
            f"actor_role IN ({_PIPELINE_ACTOR_ROLE_VALUES})",
            name="ck_pipeline_event_actor_role",
        ),
        CheckConstraint(
            f"entity_type IN ({_PIPELINE_ENTITY_TYPE_VALUES})",
            name="ck_pipeline_event_entity_type",
        ),
        # Spec D2 coupling: system transitions carry no user id; user
        # transitions always do. Enforced at the durable layer so a bad
        # writer (backfill, raw insert, or a future call site) cannot store a
        # contradictory row that the Actor value type alone would not catch.
        CheckConstraint(
            "(actor_role = 'system') = (actor_id IS NULL)",
            name="ck_pipeline_event_system_actor_null",
        ),
        Index("ix_pipeline_event_entity", "entity_type", "entity_id"),
        Index("ix_pipeline_event_event_type", "event_type"),
        Index("ix_pipeline_event_occurred_at", "occurred_at"),
    )

    occurred_at: Mapped[datetime] = mapped_column(_TS, server_default=func.now())
    # #CRITICAL: data-integrity: deliberately NOT a ForeignKey (Phase 3a). This
    # table is enforced append-only by a DB trigger that rejects any UPDATE or
    # DELETE (module docstring); a FK with ON DELETE SET NULL would still fail
    # under that trigger, since SET NULL is implemented as an UPDATE, so it
    # would BLOCK deleting any user who has ever authored an event -- nearly
    # every guardian. actor_id carries no PII (events/writer.py's payload
    # allowlist already excludes it entirely; this is an opaque UUID), so
    # there is no privacy need to null it on erasure, only a referential-
    # integrity one; dropping the FK (like the existing polymorphic
    # entity_id, which was never a FK either) leaves an inert historical
    # reference once its user is deleted, exactly like entity_id already does
    # for a deleted entity. See Phase 4d's Article 17(3) retention
    # justification for pipeline_event as a whole.
    # #VERIFY: tests/integration/test_deletion_drill.py.
    actor_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    actor_role: Mapped[str] = mapped_column(String(16))
    entity_type: Mapped[str] = mapped_column(String(32))
    # Composite entity_ids (e.g. f"{profile_id}:{storybook_id}") concatenate a
    # UUID with a String(120) Storybook.id, so the value can reach ~157 chars;
    # 255 keeps the append-only write from aborting the shared transition
    # transaction (spec D1) on a long storybook id.
    entity_id: Mapped[str] = mapped_column(String(255))
    event_type: Mapped[str] = mapped_column(String(48))
    from_state: Mapped[str | None] = mapped_column(String(32), nullable=True)
    to_state: Mapped[str | None] = mapped_column(String(32), nullable=True)
    payload: Mapped[dict[str, object]] = mapped_column(
        JSONB, nullable=False, server_default=sa_text("'{}'::jsonb")
    )


class ModerationSetting(UpdatedAtMixin, Base):
    """A single named global moderation scalar (WS-A admin noise-floor addendum).

    Distinct from ``ModerationThreshold``: this table holds global scalars
    (currently one row, key ``admin_noise_floor``, seeded at 0.05) rather than
    sparse per-(age_band, category) overrides. It denoises the admin review
    surface: ADVISORY findings scoring below the floor are hidden so a
    genuine low-but-real score is not lost in a wall of near-zero advisories;
    BLOCK/FLAG findings and unscored findings always surface regardless.

    Deliberately has no append-only audit table (unlike
    ``moderation_threshold_audit``), only ``updated_by``/``updated_at``: this
    is a single low-churn scalar, and full change history is deferred to the
    ``pipeline_event`` log rather than duplicated here. This is an
    intentional YAGNI call, not a missed one; don't flag the asymmetry with
    ``ModerationThreshold`` as a defect.

    Attributes:
        key: The setting's unique name (e.g. ``admin_noise_floor``).
        value: The scalar value, constrained to [0.0, 1.0].
        updated_by: The admin who last edited this setting, or ``None``.
        updated_at: Last edit time (UTC, TIMESTAMPTZ).
    """

    __tablename__ = "moderation_setting"
    # #ASSUME: security: admin_noise_floor controls which ADVISORY findings
    # surface on the admin moderation review surface; a row persisted with an
    # out-of-range value could hide real signal behind an over-wide floor (or
    # defeat the denoise with a floor of 0). The ck_moderation_setting_value
    # CHECK is the at-rest backstop against any non-API write path.
    # #VERIFY: the application boundary (Task A3's PUT endpoint) validates
    # to [0, 1] before writing; tests/integration/test_moderation_setting_migration.py
    # round-trips the migration that creates this CHECK.
    __table_args__ = (
        CheckConstraint(
            "value >= 0 AND value <= 1", name="ck_moderation_setting_value"
        ),
    )

    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    value: Mapped[float] = mapped_column()
    # SET NULL (Phase 3a): global admin-config row; a deleted admin's
    # attribution is dropped, the setting itself survives.
    updated_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey(_FK_USER, ondelete=_ONDELETE_SET_NULL), default=None
    )


_ALLOWLIST_PROVIDER_VALUES = "'anthropic', 'openrouter', 'modal', 'ollama'"


class ProviderModelAllowlist(UUIDPrimaryKeyMixin, CreatedAtMixin, UpdatedAtMixin, Base):
    """Admin-editable allowlist of (provider, model_id) pairs eligible for generation.

    Providers are a code-fixed enum (the CHECK below); only the model id
    within a provider is admin-managed. ``mock`` is never allowlisted: it is
    a CI-only test double, never a real generation backend.

    Attributes:
        id: Surrogate primary key.
        provider: One of the fixed provider names (see the CHECK constraint).
        model_id: The provider-native model id (e.g. ``claude-sonnet-4-6``,
            ``anthropic/claude-sonnet-4.6``).
        enabled: Whether this pair is currently selectable. Disabling a row
            (rather than deleting it) preserves audit history.
        display_name: Optional human label for a future admin UI.
        created_by: The admin who added this row, or ``None``.
        updated_by: The admin who last edited this row, or ``None``.
        created_at: Insert time (UTC, TIMESTAMPTZ).
        updated_at: Last edit time (UTC, TIMESTAMPTZ).
    """

    __tablename__ = "provider_model_allowlist"
    # #CRITICAL: security: this is the control that keeps free-string model
    # ids out of billing; the ck_provider_model_allowlist_provider CHECK is
    # the at-rest backstop against any non-API write path (admin script,
    # backfill, raw SQL) introducing an unrecognized billing backend.
    # #VERIFY: generation/allowlist.py::is_enabled_allowlist_pair is the
    # single read path the authoring-plan endpoint trusts; both this CHECK and
    # that helper are round-tripped by
    # tests/integration/test_provider_model_allowlist_migration.py and
    # tests/integration/test_allowlist.py.
    __table_args__ = (
        CheckConstraint(
            f"provider IN ({_ALLOWLIST_PROVIDER_VALUES})",
            name="ck_provider_model_allowlist_provider",
        ),
        UniqueConstraint(
            "provider", "model_id", name="uq_provider_model_allowlist_provider_model"
        ),
    )

    provider: Mapped[str] = mapped_column(String(32))
    model_id: Mapped[str] = mapped_column(String(120))
    enabled: Mapped[bool] = mapped_column(default=True, server_default=text("true"))
    display_name: Mapped[str | None] = mapped_column(String(120), default=None)
    # SET NULL (Phase 3a): global admin-config row; a deleted admin's
    # attribution is dropped, the allowlist entry itself survives.
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey(_FK_USER, ondelete=_ONDELETE_SET_NULL), default=None
    )
    updated_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey(_FK_USER, ondelete=_ONDELETE_SET_NULL), default=None
    )


class ProviderModelAllowlistAudit(UUIDPrimaryKeyMixin, Base):
    """Append-only audit of allowlist edits (who changed what, when).

    Deliberately minimal, mirroring ``ModerationThresholdAudit``: WS-D's
    pipeline_event log will subsume this role; keep this table write-only
    until then.

    Attributes:
        id: Surrogate primary key.
        provider: The affected row's provider (natural-key half).
        model_id: The affected row's model id (natural-key half).
        action: What happened: ``create``, ``update``, or ``delete``.
        old_enabled: The ``enabled`` value before the edit, or ``None`` on create.
        new_enabled: The ``enabled`` value after the edit, or ``None`` on delete.
        changed_by: The admin who made the edit, or ``None`` if that admin's
            account has since been erased (Phase 3a; see RAD tag).
        changed_at: When the edit was recorded (UTC, TIMESTAMPTZ).
    """

    __tablename__ = "provider_model_allowlist_audit"
    # #ASSUME: data integrity: the audit trail is only trustworthy if every
    # row names a known action; a typo'd action written by a non-API path
    # would silently corrupt the "who changed what" record.
    # #VERIFY: api/provider_allowlist.py writes only 'create'/'update'/'delete';
    # tests/integration/test_provider_model_allowlist_migration.py round-trips
    # the migration that creates this CHECK.
    __table_args__ = (
        CheckConstraint(
            "action IN ('create', 'update', 'delete')",
            name="ck_provider_model_allowlist_audit_action",
        ),
    )

    provider: Mapped[str] = mapped_column(String(32))
    model_id: Mapped[str] = mapped_column(String(120))
    action: Mapped[str] = mapped_column(String(16))
    old_enabled: Mapped[bool | None] = mapped_column(default=None)
    new_enabled: Mapped[bool | None] = mapped_column(default=None)
    # #CRITICAL: security / data integrity: every allowlist edit is
    # attributable AT WRITE TIME (the admin API always stamps a real admin
    # here; there is no code path that inserts NULL). Nullable with ON DELETE
    # SET NULL, not NOT NULL, so a guardian/admin's Article 17 self-deletion
    # (Phase 3a) is never blocked by an FK violation on audit rows from
    # before their account was erased; the audit row survives, only the
    # "who" attribution is dropped. Rows are append-only by convention (no
    # update/delete path in the application layer).
    # #VERIFY: tests/integration/test_provider_allowlist_api.py asserts one
    # audit row per POST/PUT/DELETE with the correct changed_by and
    # old/new_enabled pairing; tests/integration/test_deletion_drill.py
    # covers the erasure path.
    changed_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey(_FK_USER, ondelete=_ONDELETE_SET_NULL), default=None
    )
    changed_at: Mapped[datetime] = mapped_column(_TS, server_default=func.now())


class GenerationJob(UUIDPrimaryKeyMixin, CreatedAtMixin, UpdatedAtMixin, Base):
    """Tracks a single staged-generation attempt for a Concept.

    One job row is created when a generation run is enqueued. The status
    transitions from ``queued`` to ``running``, then to ``passed``,
    ``needs_review``, or ``failed``. The ``report`` column stores the full
    ``GenerationOutcome`` payload once the job completes.

    ``storybook_id`` is stored as a plain nullable ``String(120)`` rather than
    a foreign key. A job may fail before any ``storybook`` row exists, so a
    hard FK would block inserting the failure record. The application layer is
    responsible for linking the job to the correct storybook after a successful
    run.

    Attributes:
        id: Surrogate primary key.
        concept_id: The concept this job was generated from.
        status: Lifecycle state (queued, running, passed, needs_review, failed).
            Stored as a string; validated at the application boundary.
        model: LLM model identifier used for generation.
        provider: LLM provider name (e.g. ``anthropic``, ``openai``).
        prompt_version: Semver-style tag for the prompt template revision.
        report: Full ``GenerationOutcome`` JSON including metrics and flags.
        storybook_id: String key of the produced storybook row, set only when
            the job reaches ``passed`` or ``needs_review``. Not a FK -- see
            class docstring.
        version: Storybook version number produced by this job.
        error: Short error message when status is ``failed``.
        created_at: Wall-clock insert time (UTC, TIMESTAMPTZ).
        updated_at: Updated on every status transition (UTC, TIMESTAMPTZ).
    """

    __tablename__ = "generation_job"
    # #CRITICAL: data integrity: ``status`` is a closed lifecycle; this CHECK is the
    # at-rest backstop (mirroring ck_storybook_status) so no write path persists a
    # status outside the five values. Application writes use only these values.
    # #VERIFY: see migration c3d4e5f6a7b8; values match _GENERATION_JOB_STATUS_VALUES.
    __table_args__ = (
        CheckConstraint(
            f"status IN ({_GENERATION_JOB_STATUS_VALUES})",
            name="ck_generation_job_status",
        ),
        # Mirrors the ADR-007 purge migration's index backing the daily
        # "terminal jobs older than 30 days" sweep; the schema-parity test
        # requires migration-built and ORM-built schemas to agree.
        Index("ix_generation_job_status_updated_at", "status", "updated_at"),
    )

    # #CRITICAL: data-integrity: CASCADE (Phase 3a, GDPR/COPPA erasure): this
    # FK is NOT NULL, so it MUST cascade rather than SET NULL; Concept.family_id
    # already CASCADEs when a family is deleted, and without this cascade too,
    # that concept delete would itself fail with an FK violation from any
    # GenerationJob still referencing it.
    # #VERIFY: tests/integration/test_deletion_drill.py.
    concept_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey(_FK_CONCEPT, ondelete="CASCADE"), index=True
    )
    status: Mapped[str] = mapped_column(String(20), default="queued")
    model: Mapped[str | None] = mapped_column(String(120), default=None)
    provider: Mapped[str | None] = mapped_column(String(120), default=None)
    prompt_version: Mapped[str | None] = mapped_column(String(120), default=None)
    # #CRITICAL: privacy: raw multi-stage LLM outputs; purge per ADR-007 after
    # 30 days or when the linked storybook version reaches "published" status.
    # ADR-007 designates this column admin/system-only. Per the 2026-07-16
    # ruling, GET /generation-jobs/{id} (api/generation.py::get_generation_job)
    # returns it only when the caller holds the admin capability
    # (Principal.is_admin, which covers a dual-role guardian+admin); a plain
    # guardian gets None. The admin reviews generation output first, and the
    # guardian reaches the result through the normal post-approval surfaces
    # instead. The list endpoint (GenerationJobListView) never selects this
    # column at all, for any principal.
    # #VERIFY: Phase 5 scheduled pg_cron job nulls this column (ADR-009 moved the
    # ADR-007 retention purge from RQ to pg_cron); this field is never exposed
    # to a child principal. There is no separate stage_log column today;
    # persisting a redacted stage log for post-purge auditability is a Phase 5
    # task (see ADR-007).
    # #ASSUME: data integrity: ``report`` schema is determined by
    # GenerationOutcome at the application layer; no DB-level constraint
    # enforces its shape.
    # #VERIFY: all readers must tolerate None and partial report dicts (e.g.
    # when a job fails mid-run before a full report is assembled).
    report: Mapped[dict[str, object] | None] = mapped_column(JSONB, default=None)
    # #ASSUME: data-integrity: shape is {"skeleton_slug": str, "theme_brief":
    # dict, "review_stage1_model": str | None, "review_stage2_model": str |
    # None} for method="skeleton_fill" jobs (see
    # story_requests/authoring_plan.py::build_authoring_plan); the two
    # review_* overrides are always written but may be null. None for
    # method="fresh_generation" jobs. No DB-level constraint enforces this.
    # #VERIFY: readers (api/generation.py::get_generation_job,
    # generation/worker.py::_review_stage2_override) must tolerate a missing or
    # wrong-typed key rather than trust the shape.
    authoring_metadata: Mapped[dict[str, object] | None] = mapped_column(
        JSONB, default=None
    )
    # #ASSUME: data integrity: ``storybook_id`` is NOT a FK intentionally.
    # A job may fail before any storybook row is created; a hard FK constraint
    # would prevent inserting the failure record. The application layer must
    # verify the storybook row exists independently when reading this field.
    # #VERIFY: any code path that reads storybook_id and joins to storybook
    # must handle the case where the storybook row is absent.
    storybook_id: Mapped[str | None] = mapped_column(String(120), default=None)
    version: Mapped[int | None] = mapped_column(default=None)
    error: Mapped[str | None] = mapped_column(String(512), default=None)


class DeviceGrant(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    """A guardian-minted, revocable device authorization (ADR-014 phase 1).

    A row here is the durable, database-backed counterpart to a device grant
    JWT (``core/device_grant.py``): the token's ``jti`` claim matches this
    row's ``jti`` column, so revocation (setting ``revoked_at``) is checked
    against this table on every online use of the token. The token itself is
    never stored; only its unique id and mint metadata are.

    Attributes:
        id: Surrogate primary key.
        family_id: The family this device is authorized for (NOT NULL).
        authorized_by: The guardian ``User.id`` who minted the grant.
        label: An optional guardian-facing name for the device
            ("Kitchen tablet"), so the device-list UI can show something more
            useful than a bare id. Never derived from request headers
            (User-Agent, etc.) to avoid trusting client-supplied identity.
        jti: The unique id embedded in the token's ``jti`` claim. Unique so a
            lookup by jti (the revocation check) is unambiguous.
        created_at: Wall-clock insert time (UTC, TIMESTAMPTZ).
        revoked_at: Wall-clock revocation time, or ``None`` while active.
            Nullable rather than a boolean flag so the guardian-facing device
            list can show *when* a device was revoked.
        expires_at: Wall-clock expiry (UTC, TIMESTAMPTZ), stamped at mint from
            the same TTL the JWT is signed with. The token itself carries the
            expiry too, but persisting it here lets the active-device list
            exclude an unrevoked-but-expired grant (a ghost that can no longer
            mint a child session yet would otherwise still show as active), so
            "present in the list" means "actually usable" (#252).
    """

    __tablename__ = "device_grant"

    # #CRITICAL: data-integrity: CASCADE (Phase 3a, GDPR/COPPA erasure): a
    # family's own device grants are deleted with it. authorized_by
    # deliberately keeps no ondelete action: the authorizing guardian is
    # always in this same family (deleted via the same cascade, a sibling
    # path off family.id rather than a chain through this row), so the
    # NOT NULL FK never independently blocks a delete in practice.
    # #VERIFY: tests/integration/test_deletion_drill.py.
    family_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey(_FK_FAMILY, ondelete="CASCADE"), index=True
    )
    authorized_by: Mapped[uuid.UUID] = mapped_column(ForeignKey(_FK_USER))
    label: Mapped[str | None] = mapped_column(String(120), default=None)
    jti: Mapped[uuid.UUID] = mapped_column(Uuid, unique=True)
    revoked_at: Mapped[datetime | None] = mapped_column(_TS, default=None)
    # NOT NULL with no DB default: every real row supplies it (mint stamps it,
    # the backfill migration set it for pre-existing rows), and omitting a
    # default keeps this trivially in schema-parity with the migration. The
    # app always provides the value, so no default is needed as a safety net.
    expires_at: Mapped[datetime] = mapped_column(_TS)


# The two closed vocabularies for KidFlag, named once for their CHECK
# constraints (mirrors the _STORY_REQUEST_*_VALUES pattern above).
_KID_FLAG_REASON_VALUES = "'did_not_like', 'scared_me', 'confusing'"
_KID_FLAG_RESOLUTION_VALUES = "'dismissed', 'archived_book', 'noted'"


class KidFlag(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    """A child's structured "I didn't like this / this scared me" signal (K15).

    Feeds the admin moderation queue (A1) directly via this table, and,
    downstream, the guardian alert feed (G10) as a ``pipeline_event``
    projection built separately (this table does not itself notify a
    guardian). ``family_id`` is denormalized from the flagging profile
    (mirrors ``StoryRequest.family_id``) so the admin queue stays
    single-table.

    # #CRITICAL: privacy: ADR-016's no-free-text principle -- a kid flag
    # carries NO child-authored free text, by design. ``reason`` is a closed
    # vocabulary (see ``ck_kid_flag_reason``) and ``node_id`` is a story-graph
    # node identifier, not prose; this table has no text column a child could
    # write into, so there is nothing here for a human to moderate before a
    # grown-up sees it.
    # #VERIFY: api/schemas.py::KidFlagCreateBody has no free-text field and
    # forbids extra keys (``extra="forbid"``); tests/unit/test_flags_api.py
    # asserts an injected free-text field is rejected.

    Attributes:
        id: Surrogate primary key.
        family_id: Owning family; all admin/guardian access is scoped to this.
        profile_id: The flagging child's profile.
        storybook_id: The storybook being read when the flag was raised.
        version: The storybook version being read when the flag was raised.
        reason: Closed-vocabulary flag reason: did_not_like, scared_me, or
            confusing.
        node_id: The passage (story graph node id) being read when flagged,
            or ``None`` if the client could not resolve one.
        created_at: Wall-clock insert time (UTC, TIMESTAMPTZ).
        resolved_by: The admin who resolved this flag, or ``None`` while open.
        resolved_at: When the flag was resolved, or ``None`` while open.
        resolution: The admin's resolution (dismissed, archived_book, noted),
            or ``None`` while open.
    """

    __tablename__ = "kid_flag"
    # #CRITICAL: data integrity: ``reason``/``resolution`` are closed
    # vocabularies; these CHECKs are the at-rest backstop (mirroring
    # ck_story_request_status) so no write path persists a value outside
    # them. The resolved-pairing CHECK keeps resolved_by/resolved_at
    # consistent so the admin "open" filter (resolved_at IS NULL) never
    # silently disagrees with resolved_by.
    # #VERIFY: api/schemas.py coerces reason/resolution to the closed Literal
    # at the API boundary before insert; api/flags.py's resolve handler
    # always sets resolved_by/resolved_at/resolution together, never
    # partially.
    __table_args__ = (
        # CASCADE (Phase 3a): the version this flag was raised against is
        # deleted along with its storybook (see StorybookVersion.storybook_id).
        # #VERIFY: tests/integration/test_deletion_drill.py.
        ForeignKeyConstraint(
            ["storybook_id", "version"],
            [_FK_STORYBOOK_VERSION_STORYBOOK_ID, _FK_STORYBOOK_VERSION_VERSION],
            ondelete="CASCADE",
        ),
        CheckConstraint(
            f"reason IN ({_KID_FLAG_REASON_VALUES})",
            name="ck_kid_flag_reason",
        ),
        CheckConstraint(
            f"resolution IS NULL OR resolution IN ({_KID_FLAG_RESOLUTION_VALUES})",
            name="ck_kid_flag_resolution",
        ),
        CheckConstraint(
            "(resolved_by IS NULL) = (resolved_at IS NULL)",
            name="ck_kid_flag_resolved_pairing",
        ),
        Index("ix_kid_flag_resolved_created", "resolved_at", "created_at"),
    )

    # #CRITICAL: data-integrity: CASCADE both FKs (Phase 3a): a flag is
    # child-linked data, purged with either the family or the flagging
    # profile.
    # #VERIFY: tests/integration/test_deletion_drill.py.
    family_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey(_FK_FAMILY, ondelete="CASCADE"), index=True
    )
    profile_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey(_FK_CHILD_PROFILE, ondelete="CASCADE"), index=True
    )
    storybook_id: Mapped[str] = mapped_column(
        String(120), ForeignKey(_FK_STORYBOOK, ondelete="CASCADE")
    )
    version: Mapped[int] = mapped_column()
    reason: Mapped[str] = mapped_column(String(16))
    node_id: Mapped[str | None] = mapped_column(String(120), default=None)
    # #CRITICAL: data-integrity: deliberately NOT ondelete=SET NULL, unlike
    # most nullable *_by references. ck_kid_flag_resolved_pairing requires
    # resolved_by and resolved_at to be null together; a bare SET NULL on
    # resolved_by alone (with resolved_at still set) would violate that
    # CHECK. Unlike the other *_by cases in this file, this one IS reachable
    # in practice: the resolving admin need not be in the flagged family
    # (any admin can resolve any family's flags), so that admin's OWN
    # whole-family self-deletion would otherwise be blocked by an FK
    # violation here. The deletion endpoint (api/families.py) must
    # explicitly UPDATE kid_flag SET resolved_by=NULL, resolved_at=NULL,
    # resolution=NULL for every row this family's users resolved, BEFORE
    # deleting the family -- reopening those flags is the only choice that
    # keeps the pairing CHECK satisfied once the resolver is erased.
    # #VERIFY: tests/integration/test_deletion_drill.py::
    # test_deleting_admin_family_reopens_kid_flags_they_resolved.
    resolved_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey(_FK_USER), default=None
    )
    resolved_at: Mapped[datetime | None] = mapped_column(_TS, default=None)
    resolution: Mapped[str | None] = mapped_column(String(16), default=None)
