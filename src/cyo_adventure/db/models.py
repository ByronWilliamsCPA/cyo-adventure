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
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Numeric,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    func,
    text,
)
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
# ADR-028: the second column of the composite FK target on Character
# (child_profile_id, family_id) -> (child_profile.id, child_profile.family_id).
# Named alongside _FK_CHILD_PROFILE rather than inlined as a literal, matching
# the two-named-constants convention ReadingState/Completion use for their
# own composite ForeignKeyConstraint targets.
_FK_CHILD_PROFILE_FAMILY_ID = "child_profile.family_id"
_FK_STORYBOOK = "storybook.id"
_FK_CONCEPT = "concept.id"
_FK_SERIES = "series.id"
_FK_STORYBOOK_VERSION_STORYBOOK_ID = "storybook_version.storybook_id"
_FK_STORYBOOK_VERSION_VERSION = "storybook_version.version"
_FK_FAMILY_CONNECTION = "family_connection.id"

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

# W3.4: the selectable range for ChildProfile.ring_goal_days, named once so the
# CHECK constraint below and the Pydantic bound in api/schemas.py (which imports
# these) state the same numbers rather than four hand-written copies. The cap
# guarantees one free day a week survives a guardian's most aggressive setting
# (gamification-recommendation-2026-08-01.md, "Plan defaults" item 4); NULL
# still means "no override, follow the P-A band default" and is unconstrained
# by either bound.
RING_GOAL_DAYS_MIN = 1
RING_GOAL_DAYS_MAX = 6

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

# The cover-generation lifecycle states, named once for the CHECK constraint.
# 'pending_review' (H2, security-hardening-plan-2026-07.md) sits between
# 'generating' and 'ready': a generated image never reaches 'ready' (and
# therefore is never carried by an API response to a child library card, see
# api/library.py's cover_status == "ready" gate) without an explicit admin
# approval (StorybookVersion.cover_approved_by/cover_approved_at, stamped by
# covers.service.approve_cover). The status gates API reads only; direct
# object-storage reads are governed separately (covers/storage.py).
_COVER_STATUS_VALUES = "'none', 'generating', 'pending_review', 'ready', 'failed'"

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
    "'threshold_changed', 'noise_floor_changed', 'book_assigned', "
    "'book_unassigned', 'rated', "
    "'kid_flagged', 'flag_resolved', "
    "'user_managed', 'family_managed', 'family_connection_changed', "
    "'node_edited', 'profile_viewed', 'cell_saturated', "
    # ADR-023 P3/P4 (Task B4): added alongside
    # supabase/migrations/20260729020000_add_personalization_event_types.sql.
    "'personalization_toggled', 'ring2_consent_granted', "
    "'ring2_consent_revoked', "
    "'storybook_archived', "
    "'storybook_remoderated', "
    # S9 digest job. Added alongside
    # supabase/migrations/20260809100000_add_notification_digest_ready_to_pipeline_event.sql,
    # which is the newest migration to replace this CHECK and therefore carries
    # the full cumulative value list.
    "'notification_digest_ready', "
    # R-11 human-gate measurement. Added alongside
    # supabase/migrations/20260823120000_add_submitted_to_pipeline_event.sql.
    "'submitted', "
    # `RS-C1` recall (published -> in_review). Added alongside
    # supabase/migrations/20260831130000_add_storybook_recalled_to_pipeline_event.sql,
    # which is the newest migration to replace this CHECK and therefore carries
    # the full cumulative value list.
    "'storybook_recalled'"
)
_PIPELINE_ACTOR_ROLE_VALUES = "'system', 'guardian', 'child', 'admin', 'device'"
_PIPELINE_ENTITY_TYPE_VALUES = (
    "'story_request', 'generation_job', 'storybook', 'storybook_version', "
    "'series', 'storybook_assignment', 'rating', 'moderation_threshold', "
    "'moderation_setting', 'kid_flag', 'user', 'family', 'family_connection', "
    "'child_profile', "
    # ADR-023 P3/P4 (Task B6): added alongside
    # supabase/migrations/20260729030000_add_personalization_entity_types.sql.
    # 'personalization_consent' (not the longer
    # 'personalization_disclosure_consent') so the value fits entity_type's
    # String(32) column.
    "'child_profile_personalization', 'personalization_consent'"
)

# OPS-005 follow-up: the security_event.event_type CHECK vocabulary. Values
# are the exact structlog event names app.py::_handle_project_error and
# middleware/security.py::RateLimitMiddleware already emit (security_audit.py
# is the single writer for both), so the EVENT NAME a responder greps in the
# log is the same string they filter on in a security_event query -- no
# separate vocabulary to translate for that one join key. The two are not a
# full field-for-field mirror, though: the log line carries richer per-type
# detail (limit_type, requests_per_minute/burst_size, suppressed_since_last
# for a rate-limit trip; docs/operations/security-events.md section 2 is the
# authoritative field list) than the coarser durable row does.
# Hand-maintained here rather than imported (would create a circular import
# from db/models.py into security_audit.py, mirroring the _PIPELINE_EVENT_TYPE_VALUES
# note above); tests/unit/test_security_event_check_vocab.py guards drift.
_SECURITY_EVENT_TYPE_VALUES = (
    "'security_auth_failed', 'security_authz_denied', 'security_rate_limit_exceeded'"
)

# The five admin-user lifecycle states (WS-J admin user management, plus the
# self-signup approval track added alongside Phase 2, plus the guardian
# self-service invite track added by G14). A guardian/admin created via the
# seed script is always 'active'. There are two DISTINCT invite kinds, and
# the distinction is load-bearing for authorization:
#
#   'pending' is an ADMIN-created invite, made through the admin-users
#   endpoint. It binds to 'active' on first sign-in, because an admin
#   already vetted the invitee by creating it.
#
#   'pending_guardian_invite' is a GUARDIAN-created invite, made through the
#   guardian self-service co-parent invite endpoint (G14). NO admin vetted
#   it, so it binds to 'awaiting_approval' rather than 'active': the invited
#   person joins the inviting family only after an admin approves. Without
#   this split, any guardian could pre-claim a stranger's email address and
#   capture its owner into their family on that person's first sign-in.
#
# An UNINVITED guardian's own first-login JIT provisioning
# (api/onboarding.py::_provision_guardian) also starts 'awaiting_approval'
# instead of 'active'. An admin approves ('awaiting_approval' -> 'active')
# or denies ('awaiting_approval' -> 'deactivated') via the existing
# PATCH /admin/users/{id} status transition. 'deactivated' blocks
# authentication (api/deps.py::require_principal) without deleting the row.
#
# Only 'active' authenticates; api/deps.py::require_principal is written as a
# deny-by-default `!= "active"` check, so every state added here is rejected
# until explicitly promoted.
USER_STATUS_ADMIN_INVITE = "pending"
USER_STATUS_GUARDIAN_INVITE = "pending_guardian_invite"
# #CRITICAL: security: every query that looks up "an unbound invite for this
# email" MUST cover BOTH kinds. Matching only 'pending' would let a
# guardian-created invite escape the duplicate-invite guard
# (api/admin_users.py::create_pending_invite), which in turn would let two
# unbound rows share one email and make onboarding's scalar() bind
# ambiguous.
# #VERIFY: tests/integration/test_me_invite_guardian_api.py::
# test_guardian_invite_then_admin_invite_same_email_is_409.
USER_PENDING_INVITE_STATUSES = (USER_STATUS_ADMIN_INVITE, USER_STATUS_GUARDIAN_INVITE)
_USER_STATUS_VALUES = (
    "'pending', 'active', 'deactivated', 'awaiting_approval', 'pending_guardian_invite'"
)

# ADR-023 P4: the closed personalization slot_type vocabulary for
# ChildProfilePersonalization, plus the narrower ring-2 subset (the "shared
# with connected families" ceiling: pronoun_set and dedication are
# ring-1-only, since a pronoun set is a grammatical choice rather than an
# identity shared outward, and a dedication names the book's giver, not its
# reader). Hand-maintained here in parallel with
# storybook.theme_contract.PERSONALIZATION_FIELDS (the application-layer
# source of truth) rather than imported, to keep this module's import surface
# unchanged; kept in sync by tests/unit/test_personalization_vocab_drift.py.
_PERSONALIZATION_SLOT_TYPE_VALUES = (
    "'protagonist_first_name', 'pronoun_set', 'sibling_name', 'pet_species', "
    "'pet_name', 'kinship_label', 'favorite_color', 'favorite_food', "
    "'favorite_hobby', 'home_type', 'dedication', 'character_name'"
)
_PERSONALIZATION_RING2_SLOT_TYPE_VALUES = (
    "'protagonist_first_name', 'sibling_name', 'pet_species', 'pet_name', "
    "'kinship_label', 'favorite_color', 'favorite_food', 'favorite_hobby', "
    "'home_type'"
)

# ADR-018: the four states one KWS parent-verification attempt can be in, and
# the two KWS environments an attempt can have run against. Exported (no
# leading underscore) because ``consent/service.py`` writes these exact strings
# and must not spell them a second time: a service-side typo would otherwise be
# caught only at INSERT time, by the CHECK constraints below, in production.
KWS_VERIFICATION_STATUS_SENT = "sent"
KWS_VERIFICATION_STATUS_VERIFIED = "verified"
KWS_VERIFICATION_STATUS_FAILED = "failed"
# #CRITICAL: data integrity: `send_failed` and `failed` are different facts and
# collapsing them loses a compliance-relevant one. `failed` is KWS's answer
# about a parent, delivered inbound: this adult was not verified. `send_failed`
# is our own outbound leg giving up, and says nothing at all about the parent.
# Reading a `send_failed` row as a refusal would record a false negative about
# an adult nobody ever asked; counting it as an inbound delivery would tell the
# delivery-health alarm the return path works when only our own timeout code
# ran.
# #VERIFY: tests/unit/test_kws_verification_service.py::
# test_a_send_failure_is_not_counted_as_a_delivery.
KWS_VERIFICATION_STATUS_SEND_FAILED = "send_failed"
_KWS_VERIFICATION_STATUS_VALUES = "'sent', 'verified', 'failed', 'send_failed'"
# The statuses that mean a delivery from KWS actually reached us. A refusal
# counts: it travelled the same inbound path a success does, which is what
# consent/service.py::verification_delivery_health is asking about.
KWS_VERIFICATION_DELIVERED_STATUSES = (
    KWS_VERIFICATION_STATUS_VERIFIED,
    KWS_VERIFICATION_STATUS_FAILED,
)
# Mirrors the Literal on ``core.config.Settings.kws_environment``. Hand-written
# rather than derived from that Literal for the same reason
# _SECURITY_EVENT_TYPE_VALUES is hand-written: importing core.config here would
# add an import edge from the ORM layer into settings for one two-element list.
# tests/unit/test_kws_verification_model.py::
# test_at_rest_environment_vocabulary_matches_the_setting guards the drift.
KWS_ENVIRONMENT_TEST = "test"
KWS_ENVIRONMENT_PRODUCTION = "production"
_KWS_ENVIRONMENT_VALUES = f"'{KWS_ENVIRONMENT_TEST}', '{KWS_ENVIRONMENT_PRODUCTION}'"


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
    # ADR-023 P4 / design plan 8.6: the viewer-side receive switch. Defaults
    # True because signing this family's own FamilyConnection consent already
    # implies willingness to receive personalized content from that
    # connection; this is a persistent per-family opt-OUT, not an opt-in, and
    # is evaluated viewer-side before any sharer-side lookup (8.4 condition
    # 0). Deliberately not an evidentiary consent record: no signature, no
    # policy version, just a stored preference, matching 8.6's "a notice
    # fixes surprise; a signature would not fix it any better".
    personalization_receive_enabled: Mapped[bool] = mapped_column(
        server_default=text("true"), default=True
    )


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
        # O-117: mirrors the CHECK added by
        # supabase/migrations/20260802000000_add_user_residence_country_and_adulthood_attestation.sql;
        # NULL (no signal recorded yet) is always allowed, a non-null value
        # must be two uppercase ASCII letters. This is a FORMAT check only:
        # it accepts any two-letter string, including an unassigned code
        # ("ZZ", "XX", "QQ"), not just a real ISO 3166-1 alpha-2 code.
        # Real ISO membership is enforced one layer up, at the API boundary
        # (api/schemas.py::_normalize_residence_country, against
        # api/residence_countries.py::ASSIGNED_RESIDENCE_COUNTRY_CODES); this
        # CHECK is defense-in-depth for any write path that bypasses that
        # validator, not the membership gate itself.
        CheckConstraint(
            "residence_country IS NULL OR residence_country ~ '^[A-Z]{2}$'",
            name="ck_user_residence_country_format",
        ),
        # O-117/O-119: mirrors the CHECK added by
        # supabase/migrations/20260802000000_add_user_residence_country_and_adulthood_attestation.sql.
        # api/onboarding.py::_record_consent is the sole writer and already
        # only ever sets residence_country and adulthood_attested_at together
        # (alongside the consent_* quartet, never before it); this CHECK is
        # the at-rest backstop for any other write path, mirroring
        # ck_user_consent_pairing's own role for the original quartet. Two
        # requirements: (1) the two new columns are set or cleared together,
        # same "no partial claim" shape as the consent quartet; (2) whenever
        # they carry a value, consent_accepted_at must also be non-null, so
        # an at-rest row can never record a country/adulthood attestation
        # with no corroborating consent record. An already-consented row from
        # before this migration has both new columns NULL, which satisfies
        # clause (1) trivially and short-circuits clause (2) via the OR, so
        # this ALTER TABLE cannot fail against existing production data.
        # #VERIFY: tests/integration/test_onboarding_api.py::
        # test_onboarding_records_consent_once_and_is_idempotent.
        CheckConstraint(
            "(residence_country IS NULL) = (adulthood_attested_at IS NULL) "
            "AND (residence_country IS NULL OR consent_accepted_at IS NOT NULL)",
            name="ck_user_residence_adulthood_pairing",
        ),
        # #ASSUME: data-integrity: Postgres indexes the REFERENCED side of a
        # foreign key, never the referencing side, so without this
        # fk_user_consent_verification_id's ON DELETE SET NULL makes the
        # referential-integrity trigger sequentially scan "user" once per
        # deleted kws_verification row. Erasure is the path that hurts:
        # api/families.py's delete-my-family removes a family's verification
        # rows, and a COPPA/GDPR subject-erasure request does the same in
        # bulk, which is many deletes each re-scanning the same table.
        # Partial because the column is NULL for everyone who has not
        # completed a KWS-corroborated consent; the trigger's lookup is an
        # equality, which implies IS NOT NULL, so the planner can still use
        # it.
        # #VERIFY: keep in step with supabase/migrations/
        # 20260811150000_index_user_consent_verification_id.sql;
        # tests/integration/test_schema_parity.py compares the two databases
        # the two paths build, so dropping either half fails there.
        Index(
            "ix_user_consent_verification_id",
            "consent_verification_id",
            postgresql_where=text("consent_verification_id IS NOT NULL"),
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
    is_admin: Mapped[bool] = mapped_column(server_default=text("false"), default=False)
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
    # #CRITICAL: security: 'pending' and 'pending_guardian_invite' are the two
    # invite-row states (see _USER_STATUS_VALUES above). Both carry a
    # synthetic placeholder authn_subject (api/admin_users.py's
    # _PENDING_SUBJECT_PREFIX) that no real JWT can ever carry, but
    # require_principal ALSO rejects any non-'active' status explicitly as
    # defense in depth (same "unknown subject" message as an unrecognized
    # subject, so status is never a distinguishable oracle). The two differ
    # only in where onboarding's bind lands them: 'pending' (admin-vetted)
    # -> 'active'; 'pending_guardian_invite' (NOT admin-vetted, created by a
    # guardian via POST /me/family/invite-guardian) -> 'awaiting_approval',
    # so a guardian cannot silently pull an arbitrary email address into
    # their own family. 'deactivated' is the soft-remove state for an
    # admin/guardian; the row and its history (stories, ratings, events) are
    # preserved.
    # #VERIFY: tests/integration/test_admin_users_api.py::
    # test_deactivated_guardian_cannot_authenticate,
    # test_pending_invite_cannot_authenticate; tests/integration/
    # test_me_invite_guardian_api.py::
    # test_guardian_invited_user_binds_to_awaiting_approval_not_active.
    # #CRITICAL: timing dependencies: migration
    # supabase/migrations/20260729060000_add_user_guardian_invite_status.sql
    # widens BOTH this column (to varchar(32)) and the ck_user_status CHECK,
    # and must be applied BEFORE an image carrying
    # 'pending_guardian_invite' deploys; otherwise the invite INSERT fails
    # with StringDataRightTruncationError / a CHECK violation at runtime.
    # #VERIFY: apply the migration in each environment ahead of the image
    # rollout (migrate-before-deploy), per the header comment in the
    # migration file.
    # String(32): 'pending_guardian_invite' (23 chars) is the longest value in
    # _USER_STATUS_VALUES; String(16) truncated 'awaiting_approval' before
    # (StringDataRightTruncationError), and String(20) would truncate this one.
    status: Mapped[str] = mapped_column(
        String(32), default="active", server_default=text("'active'")
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
    # O-117 (pre-launch compliance): ISO 3166-1 alpha-2 country of residence,
    # recorded on the adult account rather than Family (a family could span
    # countries), so the DSA Art. 2(1) and GDPR Art. 3(2) targeting tests can
    # be answered; without a recorded country signal a market can be
    # excluded by design rather than by hope. Written once by
    # api/onboarding.py::_record_consent alongside the existing consent_*
    # quartet, never overwritten afterward (mirrors consent_accepted_at's own
    # contract): a guardian who consented before this column existed keeps
    # NULL here, since there is no re-consent-on-policy-change flow.
    # String(2): ISO 3166-1 alpha-2 is exactly two characters; the format is
    # additionally enforced at rest by ck_user_residence_country_format
    # above. A prior String(N) guess on this same table truncated
    # 'awaiting_approval' in production (see the status column's comment
    # below in this class for that incident), so this width is derived from
    # the value domain, not guessed.
    # #CRITICAL: timing dependencies: migration
    # supabase/migrations/20260802000000_add_user_residence_country_and_adulthood_attestation.sql
    # must be applied BEFORE an image carrying this column deploys. Every
    # full-entity select(User) (the auth path in api/deps.py::require_principal
    # runs one per authenticated request) emits this column; against a
    # database without it, asyncpg raises UndefinedColumn and every
    # authenticated endpoint 500s.
    # #VERIFY: apply the migration in each environment ahead of the image
    # rollout (migrate-before-deploy), per the header comment in the
    # migration file.
    residence_country: Mapped[str | None] = mapped_column(String(2), default=None)
    # O-119 (pre-launch compliance): adulthood attestation timestamp. Every
    # age regime that can attach at R2 locates its duty on the adult
    # account, not the kid profile; today age data lives only on
    # ChildProfile.age_band and Series.age_band, neither of which is the
    # adult signing the account into existence. Written once by
    # api/onboarding.py::_record_consent in the same call that writes the
    # existing consent_* quartet, and never overwritten afterward for the
    # same reason. There is deliberately no separate attestation-version
    # column: the new checkbox ships inside the same versioned consent form,
    # so consent_policy_version already records what text was shown when it
    # was checked.
    # #CRITICAL: timing dependencies: migration
    # supabase/migrations/20260802000000_add_user_residence_country_and_adulthood_attestation.sql
    # must be applied BEFORE an image carrying this column deploys. Every
    # full-entity select(User) (the auth path in api/deps.py::require_principal
    # runs one per authenticated request) emits this column; against a
    # database without it, asyncpg raises UndefinedColumn and every
    # authenticated endpoint 500s.
    # #VERIFY: apply the migration in each environment ahead of the image
    # rollout (migrate-before-deploy), per the header comment in the
    # migration file.
    adulthood_attested_at: Mapped[datetime | None] = mapped_column(_TS, default=None)
    # ADR-018 D1: which KWS verification attempt corroborated THIS consent
    # event. Evidence, not a gate: nothing reads this column to decide whether
    # a guardian may proceed (``consent/service.py::has_usable_verification``
    # asks that question of kws_verification directly, so a guardian who
    # consented before verification existed can still verify later without
    # anything rewriting their historical record).
    #
    # Deliberately NOT added to ck_user_consent_pairing. NULL here is a real
    # and permanent state with a specific meaning: "this consent event was
    # recorded under the typed-name-only mechanism, and was not itself backed
    # by a verification". Pairing it with consent_accepted_at would make every
    # such row violate the CHECK, and the only ways out would be to falsify
    # those records or to invent evidence for them.
    #
    # use_alter=True because "user" and kws_verification reference each other
    # (that table's user_id points back here), which is a cycle CREATE TABLE
    # cannot order; SQLAlchemy emits this one as a separate ALTER TABLE, which
    # is also how the migration spells it. ON DELETE SET NULL rather than
    # CASCADE: erasing the verification attempt must never take the 16 CFR
    # 312.5(c) consent record with it.
    # #ASSUME: data-integrity: the guardian-deletion path deletes both rows in
    # one statement, so the CASCADE on kws_verification.user_id and this
    # SET NULL fire against each other inside the same command.
    # #VERIFY: tests/integration/test_deletion_drill.py::
    # test_deleting_a_verification_keeps_the_consent_record (the SET NULL
    # itself: flipping this to CASCADE fails it) and
    # ::test_delete_my_family_removes_the_kws_verification_rows (the two
    # constraints firing together). Do NOT cite
    # test_delete_my_family_removes_everything: it seeds no kws_verification
    # row at all, so it exercises neither half of this cycle.
    consent_verification_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey(
            "kws_verification.id",
            ondelete="SET NULL",
            use_alter=True,
            name="fk_user_consent_verification_id",
        ),
        default=None,
    )


class ChildProfile(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    """A per-child reading profile with age band and content caps."""

    __tablename__ = "child_profile"
    __table_args__ = (
        CheckConstraint(
            "monthly_request_envelope IS NULL OR monthly_request_envelope >= 0",
            name="ck_child_profile_monthly_request_envelope_non_negative",
        ),
        # W3.4: mirrors the CHECK added by
        # supabase/migrations/20260801050000_add_child_profile_gamification_settings.sql;
        # NULL (band default) is always allowed, a non-null goal must sit in
        # the selectable range the gamification recommendation's "Plan
        # defaults" item 4 fixes (max 6, one guaranteed free day). Built from
        # the constants above rather than spelled out, so this bound and the
        # Pydantic one in api/schemas.py (which imports them) cannot drift.
        CheckConstraint(
            "ring_goal_days IS NULL OR ring_goal_days BETWEEN "
            f"{RING_GOAL_DAYS_MIN} AND {RING_GOAL_DAYS_MAX}",
            name="ck_child_profile_ring_goal_days_range",
        ),
        # Phase 4c: backs purge_stale_deactivated_profile_activity's WHERE
        # clause (supabase/migrations/20260720150000_add_retention_purge_jobs.sql).
        Index(
            "ix_child_profile_deactivated_at",
            "deactivated_at",
            postgresql_where=text("deactivated_at IS NOT NULL"),
        ),
        # ADR-028: backs Character.fk_character_profile_family, the composite
        # FK that keeps a character's denormalized family_id honest against
        # its owning profile's actual family.
        UniqueConstraint(
            "family_id",
            "id",
            name="uq_child_profile_family_id_id",
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
    # Guardian-set per-child motion preference: when true, the reader/library
    # frontend collapses age-band animation to the same reduced-motion state
    # as the OS-level prefers-reduced-motion media query (see band-tokens.css).
    reduce_motion: Mapped[bool] = mapped_column(default=False)
    # ADR-023 P4: guardian consent ring toggles for this child's OWN real name
    # (as opposed to the per-slot ring flags on ChildProfilePersonalization,
    # which cover every other personalization slot plus a sibling's name).
    # ring1_enabled permits the name into this family's own stories;
    # ring2_enabled additionally permits it into stories shared with
    # connected families (FamilyConnection). Both default False: a real
    # name is never personalized in without an explicit guardian opt-in.
    real_name_ring1_enabled: Mapped[bool] = mapped_column(
        server_default=text("false"), default=False
    )
    real_name_ring2_enabled: Mapped[bool] = mapped_column(
        server_default=text("false"), default=False
    )
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
    # W3.4 (kid-appeal-implementation-plan.md; gamification-recommendation-
    # 2026-08-01.md section 4/P-A): per-profile gamification toggles. The
    # weekly-ring pair is nullable-means-band-default (mirrors banned_themes'
    # "None = no override" contract, not "None = empty"); resolution into a
    # concrete on/off + goal happens server-side in
    # api/progress.py::_resolve_ring_settings so every client (kid, future
    # guardian display) reads the SAME resolved values rather than each
    # re-implementing the P-A band table.
    # #CRITICAL: data-integrity: a NULL here must resolve to the P-A band
    # default, never to "off"/"0", or a profile that has never been touched by
    # a guardian would silently lose its band-appropriate ring instead of
    # getting it.
    # #VERIFY: tests/unit/test_progress_api_unit.py::TestResolveRingSettings;
    # tests/integration/test_profiles.py gamification-fields round-trip tests.
    ring_enabled: Mapped[bool | None] = mapped_column(default=None)
    ring_goal_days: Mapped[int | None] = mapped_column(default=None)
    badges_enabled: Mapped[bool] = mapped_column(
        server_default=text("true"), default=True
    )
    time_capture_paused: Mapped[bool] = mapped_column(
        server_default=text("false"), default=False
    )


class ChildProfilePersonalization(CreatedAtMixin, UpdatedAtMixin, Base):
    """A guardian-set personalization value for one (profile, slot) pair.

    ADR-023 P4: each row binds one of the closed ``slot_type`` vocabulary's
    values (mirrored from ``storybook.theme_contract.PERSONALIZATION_FIELDS``)
    to exactly one of three value shapes (free text, a closed enum choice, or
    a reference to another profile, e.g. a sibling), never more than one at a
    time, EXCEPT ``character_name`` (ADR-028), whose row carries none of the
    three: its value lives in ``Character.name`` and is synthesized at
    resolve time, so its consent row is a bare toggle. ``ring1_enabled``/
    ``ring2_enabled`` are per-slot consent flags: ring 1 permits the value
    into this family's own stories, ring 2 additionally permits it into
    stories shared with connected families (``FamilyConnection``).

    #CRITICAL: security: ``ck_cpp_ring2_ceiling`` is a DB CHECK, not just API
    validation, so ``pronoun_set`` and ``dedication`` rows are structurally
    incapable of carrying ``ring2_enabled = true`` even if a future API
    bypasses application-layer validation.
    #VERIFY: tests/unit/test_personalization_vocab_drift.py pins both CHECK
    lists against ``PERSONALIZATION_FIELDS``.
    """

    __tablename__ = "child_profile_personalization"
    __table_args__ = (
        CheckConstraint(
            f"slot_type IN ({_PERSONALIZATION_SLOT_TYPE_VALUES})",
            name="ck_cpp_slot_type",
        ),
        # Renamed from ck_cpp_exactly_one_value: character_name (ADR-028) is
        # the one slot_type whose value lives outside this table entirely
        # (synthesized at resolve time from the active Character's name), so
        # its row must carry NONE of the three value columns rather than
        # exactly one. The other eleven slot types keep the original
        # exactly-one rule unchanged.
        # #CRITICAL: data integrity: this is a real design collision, not a
        # relaxation. Storing the character's name a second time in
        # value_text would make a second, driftable copy of the same fact;
        # the CASE keeps character_name structurally incapable of carrying
        # any value at all.
        # #VERIFY: tests/unit/test_personalization_vocab_drift.py::
        # test_orm_value_cardinality_constraint_present (the ORM text) and
        # tests/integration/test_personalization_purge.py::
        # test_character_name_row_carrying_a_value_is_rejected_by_the_database
        # (the CHECK actually executing against Postgres).
        CheckConstraint(
            "CASE WHEN slot_type = 'character_name' "
            "THEN (value_text IS NULL AND value_enum IS NULL "
            "AND value_profile_id IS NULL) "
            "ELSE ((value_text IS NOT NULL)::int + (value_enum IS NOT NULL)::int "
            "+ (value_profile_id IS NOT NULL)::int = 1) END",
            name="ck_cpp_value_cardinality",
        ),
        CheckConstraint(
            f"NOT ring2_enabled OR slot_type IN "
            f"({_PERSONALIZATION_RING2_SLOT_TYPE_VALUES})",
            name="ck_cpp_ring2_ceiling",
        ),
        # Postgres indexes the referenced side of an FK automatically but never
        # the referencing side, so a sibling-profile deletion would sequentially
        # scan this table without it. The (child_profile_id, slot_type) primary
        # key already covers the other FK.
        Index("ix_cpp_value_profile_id", "value_profile_id"),
    )

    # #CRITICAL: data-integrity: CASCADE both FKs: a personalization value is
    # child-linked data, purged with either the owning profile or (for a
    # value_profile_id reference, e.g. a sibling) the referenced profile.
    # #VERIFY: tests/integration/test_deletion_drill.py.
    child_profile_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey(_FK_CHILD_PROFILE, ondelete="CASCADE"), primary_key=True
    )
    slot_type: Mapped[str] = mapped_column(String(32), primary_key=True)
    value_text: Mapped[str | None] = mapped_column(Text, default=None)
    value_enum: Mapped[str | None] = mapped_column(String(64), default=None)
    value_profile_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey(_FK_CHILD_PROFILE, ondelete="CASCADE"), default=None
    )
    ring1_enabled: Mapped[bool] = mapped_column(
        server_default=text("false"), default=False
    )
    ring2_enabled: Mapped[bool] = mapped_column(
        server_default=text("false"), default=False
    )


# The canonical character attribute vocabulary, mirrored from
# storybook.character_vocabulary.CANONICAL_CHARACTER_VARIABLES (the
# application-layer source of truth) rather than imported, to keep this
# module's import surface unchanged. Kept in sync by
# tests/unit/test_character_vocab_drift.py, which is the same guard
# _PERSONALIZATION_SLOT_TYPE_VALUES relies on.
_CHARACTER_ATTRIBUTE_NAMES = "'archetype', 'might', 'wits', 'nerve'"

# Per-name ranges. archetype is 0-6 (0 = not chosen, 1-6 index
# ARCHETYPE_ROSTER); the three stats are 0-2. Expressed as one constraint
# rather than four so a row can never satisfy a range belonging to a
# different name.
_CHARACTER_ATTRIBUTE_VALUE_RANGE = (
    "(name = 'archetype' AND value_int BETWEEN 0 AND 6) "
    "OR (name IN ('might', 'wits', 'nerve') AND value_int BETWEEN 0 AND 2)"
)

# The six archetype names, mirrored from
# storybook.character_vocabulary.ARCHETYPE_ROSTER (the application-layer
# source of truth) rather than imported, for the same import-surface reason
# as _CHARACTER_ATTRIBUTE_NAMES above. Order does not matter here (unlike
# ARCHETYPE_ROSTER's own ordering, which is a wire-format code assignment);
# this constant only bounds set membership for the CHECK constraint. Kept in
# sync by tests/unit/test_character_vocab_drift.py.
_CHARACTER_ARCHETYPE_NAMES = (
    "'scout', 'guardian', 'trickster', 'scholar', 'healer', 'wildheart'"
)

# The twelve selectable avatar look ids (avatar_01 through avatar_12).
# Hand-maintained rather than imported for the same reason as the two
# constants above; kept in sync by tests/unit/test_character_vocab_drift.py.
_CHARACTER_LOOK_IDS = (
    "'avatar_01', 'avatar_02', 'avatar_03', 'avatar_04', "
    "'avatar_05', 'avatar_06', 'avatar_07', 'avatar_08', "
    "'avatar_09', 'avatar_10', 'avatar_11', 'avatar_12'"
)


class Character(UUIDPrimaryKeyMixin, CreatedAtMixin, UpdatedAtMixin, Base):
    """A persistent reader character owned by one child profile (ADR-028).

    ``family_id`` is denormalized from the owning profile so this table can
    carry the ADR-022 Tier 1 ``family_scoped`` RLS policy, which needs the
    family on the row rather than via a join. The composite foreign key to
    ``child_profile (family_id, id)`` is what keeps the denormalized value
    honest.

    ``is_active`` and ``retired_at`` are two spellings of one fact and are
    kept agreeing by a CHECK; a partial unique index allows any number of
    retired characters per profile but exactly one active.

    #ASSUME: data integrity: ``archetype`` (this string column, e.g.
    ``"scout"``) and the ``CharacterAttribute`` row named ``"archetype"``
    (an int code, e.g. ``1``, keyed by position in
    ``storybook/character_vocabulary.py::ARCHETYPE_ROSTER`` via
    ``ARCHETYPE_CODES``) are two independent representations of the same
    fact, and nothing in the schema ties them together: no CHECK, trigger,
    or FK compares this column against ``character_attribute``. The
    invariant holds today purely at the application layer, by construction:
    ``characters/seeding.py::initial_attributes`` writes both from the same
    ``archetype`` argument in the same ``create_character`` transaction
    (``api/characters.py``), ``CharacterUpdateBody`` has no ``archetype``
    field so a PATCH can never change this column, and
    ``characters/progression.py::_PROGRESSION_VARIABLES`` explicitly
    excludes ``ARCHETYPE_VARIABLE_NAME`` so book-completion writes can never
    touch the attribute row either. A future writer that adds any other path
    to either representation (a new PATCH field, a progression variable, a
    direct ORM update) can silently desync them; nothing downstream of the
    write would notice. Deliberately not closing this with a new DB-level
    trigger or CHECK in this fix pass: a trigger on a live table carries
    lock risk disproportionate to reinforcing an invariant two independent,
    already-reviewed write-path restrictions already hold.
    #VERIFY: no test proves the cross-representation invariant from the
    schema's side, and saying so is the honest answer; the write-path
    restrictions above are covered by
    tests/integration/test_characters_api.py::
    test_patch_with_archetype_is_rejected_not_silently_dropped (PATCH never
    accepts archetype) and
    tests/integration/test_character_progression.py::
    test_archetype_is_never_raised_by_a_completion (a book completion never
    touches the attribute row), but neither test would catch a NEW writer
    that bypassed both.
    """

    __tablename__ = "character"
    __table_args__ = (
        ForeignKeyConstraint(
            ["child_profile_id", "family_id"],
            [_FK_CHILD_PROFILE, _FK_CHILD_PROFILE_FAMILY_ID],
            ondelete="CASCADE",
            name="fk_character_profile_family",
        ),
        CheckConstraint(
            "NOT (is_active AND retired_at IS NOT NULL)",
            name="ck_character_not_active_and_retired",
        ),
        CheckConstraint(
            f"archetype IN ({_CHARACTER_ARCHETYPE_NAMES})",
            name="ck_character_archetype",
        ),
        CheckConstraint(
            f"look IN ({_CHARACTER_LOOK_IDS})",
            name="ck_character_look",
        ),
        CheckConstraint(
            "books_completed >= 0",
            name="ck_character_books_completed_non_negative",
        ),
        Index(
            "uq_character_one_active",
            "child_profile_id",
            unique=True,
            postgresql_where=text("is_active"),
        ),
        Index("ix_character_child_profile_id", "child_profile_id"),
    )

    child_profile_id: Mapped[uuid.UUID] = mapped_column()
    family_id: Mapped[uuid.UUID] = mapped_column()
    name: Mapped[str] = mapped_column(String(32))
    archetype: Mapped[str] = mapped_column(String(16))
    look: Mapped[str] = mapped_column(String(16))
    is_active: Mapped[bool] = mapped_column(server_default=text("true"), default=True)
    books_completed: Mapped[int] = mapped_column(server_default=text("0"), default=0)
    retired_at: Mapped[datetime | None] = mapped_column(_TS, default=None)


class CharacterAttribute(Base):
    """One canonical attribute value for one character (ADR-028).

    ``value_bool`` is deliberately absent in v1: every canonical variable is
    an int, because Tier-2 conditions are a JSONLogic subset with no string
    comparison and no boolean carry need has been demonstrated. Adding it
    later is additive; removing a shipped column is not.

    #ASSUME: data integrity: the row with ``name == "archetype"`` on this
    table stores the SAME fact as ``Character.archetype`` above, just coded
    as an int (``storybook/character_vocabulary.py::ARCHETYPE_CODES``, 1-6
    by roster position) instead of a string, because Tier-2 conditions can
    only compare ints. See ``Character.archetype``'s docstring for the full
    account of why nothing in the schema enforces the two agreeing, and
    which application-layer restrictions hold the invariant instead.
    #VERIFY: same citations as ``Character.archetype``; no schema-level test
    exists for this table either.
    """

    __tablename__ = "character_attribute"
    __table_args__ = (
        CheckConstraint(
            f"name IN ({_CHARACTER_ATTRIBUTE_NAMES})",
            name="ck_character_attribute_name",
        ),
        CheckConstraint(
            _CHARACTER_ATTRIBUTE_VALUE_RANGE,
            name="ck_character_attribute_value_range",
        ),
    )

    character_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("character.id", ondelete="CASCADE"), primary_key=True
    )
    name: Mapped[str] = mapped_column(String(16), primary_key=True)
    value_int: Mapped[int] = mapped_column()


class CharacterBookCompletion(CreatedAtMixin, Base):
    """One row per (reading_state, character) that has been written back.

    #CRITICAL: data integrity: this composite primary key IS the writeback
    idempotency mechanism. A child who reaches a satisfying ending, goes
    offline, and replays the queued completion must not increment
    books_completed twice, and an application-side "have we done this
    already?" read is racy under concurrent sync. INSERT ... ON CONFLICT DO
    NOTHING against this key makes the second attempt a no-op in the
    database.
    #VERIFY: the schema-level mechanism (this primary key shape) is pinned
    today by tests/unit/test_character_models.py::
    test_completion_pk_is_what_makes_writeback_idempotent. The behavioral
    no-double-increment case is covered by
    tests/integration/test_character_progression.py::
    test_a_replayed_completion_does_not_increment_twice.

    ``ending_id`` is stored but deliberately NOT part of this key: a
    character can be credited for a given storybook exactly once, forever,
    including across a re-read and across a later version of the same book,
    and a completion recorded at a different ending for a pair already
    credited is a no-op rather than a conflict. See
    characters/progression.py's module docstring for the full rationale.
    """

    __tablename__ = "character_book_completion"
    __table_args__ = (
        ForeignKeyConstraint(
            ["reading_state_child_profile_id", "reading_state_storybook_id"],
            ["reading_state.child_profile_id", "reading_state.storybook_id"],
            ondelete="CASCADE",
            name="fk_cbc_reading_state",
        ),
        # character_id is the trailing column of the composite primary key
        # above, so the PK index cannot serve a CASCADE delete from
        # character (a scan for that column needs it leading). Postgres
        # never indexes the referencing side of a foreign key automatically
        # (see ix_character_child_profile_id's comment for the same rule).
        Index(
            "ix_character_book_completion_character_id",
            "character_id",
        ),
    )

    reading_state_child_profile_id: Mapped[uuid.UUID] = mapped_column(primary_key=True)
    reading_state_storybook_id: Mapped[str] = mapped_column(
        String(120), primary_key=True
    )
    character_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("character.id", ondelete="CASCADE"), primary_key=True
    )
    ending_id: Mapped[str] = mapped_column(String(120))


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
            postgresql_where=text(
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


class PersonalizationDisclosureConsent(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    """A signed ring-2 disclosure consent: one profile, one connection, one scope.

    ADR-023 P4 (design plan 5.3). Distinct from ``FamilyConnection``'s own
    dual-guardian consent (which merely permits recommendations to flow, K17):
    this is the sharer guardian's separate, per-slot-scoped consent that
    permits ``ChildProfilePersonalization``/real-name values to flow across
    that connection specifically. ``covered_slot_types`` is the scope of the
    disclosure; re-consent supersedes this row in place with a new
    ``consent_accepted_at``/``consent_policy_version``, and narrowing
    ``covered_slot_types`` does not require re-signing (owner decision,
    ADR-023 OD-5(c)).

    #CRITICAL: data-integrity: ``family_connection_id`` is ``ondelete="SET
    NULL"``, never CASCADE. This row is an evidentiary record (GDPR Article
    7(1), COPPA 312.5): the connection it was granted on can be deleted
    (``FamilyConnection`` rows are hard-deleted, never soft-deactivated)
    while the proof that consent was once given must survive as a scrubbed
    tombstone naming only that authorization happened and what it covered,
    never a slot value. Deleting the ``child_profile_id`` instead removes the
    row entirely: the data subject is gone, so there is nothing left to
    evidence.
    #VERIFY: tests/integration/test_personalization_consent_tombstone.py.

    Uses a surrogate UUID PK plus a partial unique index on
    ``(child_profile_id, family_connection_id) WHERE family_connection_id IS
    NOT NULL``, not a composite PK: tombstoning nulls half of what would
    otherwise be the natural key, so a composite PK (as
    ``ChildProfilePersonalization`` uses) cannot express "at most one live
    consent per (profile, connection), any number of tombstones after".
    """

    __tablename__ = "personalization_disclosure_consent"
    __table_args__ = (
        Index(
            "uq_pdc_profile_connection",
            "child_profile_id",
            "family_connection_id",
            unique=True,
            postgresql_where=text("family_connection_id IS NOT NULL"),
        ),
        # Referencing-side FK index: family_connection_id is ON DELETE SET
        # NULL, so every family_connection deletion scans this table without
        # it. The partial unique index above does not serve that lookup,
        # because it is keyed on child_profile_id first and excludes the NULL
        # rows the deletion is about to create.
        Index("ix_pdc_family_connection_id", "family_connection_id"),
        # Mirrors ck_user_consent_pairing (User, :306-329) exactly: the four
        # consent columns are set or cleared together, so this record is
        # either fully signed or entirely unsigned, never a partial claim.
        CheckConstraint(
            "(consent_accepted_at IS NULL) = (consent_policy_version IS NULL) "
            "AND (consent_accepted_at IS NULL) = (consent_signer_name IS NULL) "
            "AND (consent_accepted_at IS NULL) = (consent_ip IS NULL)",
            name="ck_pdc_consent_pairing",
        ),
    )

    # #CRITICAL: data-integrity: CASCADE (Phase 3a, GDPR/COPPA erasure): the
    # subject profile's own erasure removes every consent evidencing THEIR
    # disclosure, live or tombstoned alike.
    # #VERIFY: tests/integration/test_personalization_consent_tombstone.py,
    # tests/integration/test_deletion_drill.py (Task B3).
    child_profile_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey(_FK_CHILD_PROFILE, ondelete="CASCADE")
    )
    # #CRITICAL: data-integrity: SET NULL, not CASCADE. See the class
    # docstring: a deleted connection must not destroy the evidence that
    # consent was once given on it.
    # #VERIFY: tests/integration/test_personalization_consent_tombstone.py.
    family_connection_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey(_FK_FAMILY_CONNECTION, ondelete=_ONDELETE_SET_NULL), default=None
    )
    # Denormalized at signing time so the record stays legible after the
    # connection row (and thus its connected_family_id) is gone.
    connected_family_label: Mapped[str | None] = mapped_column(
        String(200), default=None
    )
    covered_slot_types: Mapped[list[str] | None] = mapped_column(JSONB, default=None)
    # Set only for a consent whose covered_slot_types includes the sibling
    # slot; see design plan 10.1 for the attestation ceremony this backs.
    sibling_authority_attested: Mapped[bool] = mapped_column(
        server_default=text("false"), default=False
    )
    consent_accepted_at: Mapped[datetime | None] = mapped_column(_TS, default=None)
    consent_policy_version: Mapped[str | None] = mapped_column(String(32), default=None)
    consent_signer_name: Mapped[str | None] = mapped_column(String(200), default=None)
    consent_ip: Mapped[str | None] = mapped_column(String(64), default=None)
    # Explicit revocation, distinct from deletion/tombstoning: a guardian can
    # revoke while the connection (and thus family_connection_id) still exists.
    revoked_at: Mapped[datetime | None] = mapped_column(_TS, default=None)


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
        # Referencing-side FK index. This is the highest-value of the three
        # personalization FK indexes: storybook is the largest table in the
        # schema, and the ADR-023 8.5 erasure path fires this ON DELETE SET
        # NULL once per profile deletion, sequentially scanning the whole
        # table without it.
        Index(
            "ix_storybook_personalization_subject_profile_id",
            "personalization_subject_profile_id",
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
    # ADR-023 P4 / design plan 8.2: whose profile this book's sentinel slots
    # resolve against, set at generation time from the requesting profile.
    # #CRITICAL: data-integrity: SET NULL, deliberately the one deviation
    # from this table's own family_id CASCADE pattern above. Deleting the
    # subject's profile must not delete a book another family has on their
    # shelf; it must sever the link so the book reverts to generic
    # everywhere (design plan 8.5, 8.7).
    # #VERIFY: tests/integration/test_deletion_drill.py (Task B3).
    personalization_subject_profile_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey(_FK_CHILD_PROFILE, ondelete=_ONDELETE_SET_NULL), default=None
    )


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
    # #CRITICAL: security: UW-M07 defense-in-depth stopgap. The R2 object key
    # (covers/storage.py::cover_object_key) was deterministic from
    # (storybook_id, version) alone, so a public bucket binding (the root
    # cause, closed at the Cloudflare level 2026-07-30) let anyone who could
    # guess a storybook id enumerate every cover. This salt, generated once
    # per cover by covers/service.py::generate_cover, is folded into the key
    # so knowing storybook_id and version is no longer sufficient even if the
    # public binding is ever mistakenly restored. NULL for every row created
    # before this column existed; cover_object_key falls back to the legacy
    # unsalted key for those so already-uploaded objects keep resolving
    # without an R2-side rename.
    # #VERIFY: tests/unit/test_cover_storage.py::
    # test_cover_object_key_includes_salt_when_present.
    cover_object_salt: Mapped[str | None] = mapped_column(String(32), default=None)
    # #CRITICAL: security: H2 (security-hardening-plan-2026-07.md) closure --
    # these two columns are the cover-art analogue of approved_by/published_at
    # above: the sole record that a human (not the image provider, not the
    # generation worker) reviewed a generated cover before any API read path
    # could serve it to a child (direct object-storage access is a separate
    # control, see covers/storage.py). NULL on a 'ready' row means the cover
    # predates the gate, which the backfill in
    # supabase/migrations/20260728000000_add_cover_approval_gate.sql demotes
    # back to 'pending_review' rather than grandfathering as approved.
    # covers.service.approve_cover is the only writer of both, and it
    # requires cover_status == "pending_review" beforehand (see that
    # function's docstring for the full transition contract).
    # #VERIFY: tests/integration/test_cover_service.py::
    # test_approve_cover_stamps_approver_and_timestamp.
    cover_approved_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey(_FK_USER, ondelete=_ONDELETE_SET_NULL), default=None
    )
    cover_approved_at: Mapped[datetime | None] = mapped_column(_TS, default=None)
    # ADR-023 P4: does this version's blob carry any sentinel-bound slots at
    # all (safe to publish; says nothing about whose values). Off by default;
    # set by the fill/import path only when the skeleton contract declares
    # personalizable slots.
    personalization_eligible: Mapped[bool] = mapped_column(
        server_default=text("false"), default=False
    )
    # A separate, narrower flag (design plan section 2/5): whether this
    # version's contract additionally parameterizes pronouns. Off by
    # default, set only by an explicit per-skeleton audit; never implied by
    # personalization_eligible alone.
    pronoun_parameterized: Mapped[bool] = mapped_column(
        server_default=text("false"), default=False
    )
    # Stage R re-scope (Task R3): the per-node token multiset that
    # deterministic re-insertion actually produced
    # (storybook/reinsertion.py::build_manifest), stamped at persist time
    # from the transform that ran pre-persist. NOT a contract-prescribed
    # expectation. Keyed
    # {"tokens": {<node_id>: [...], "<node_id>::ending_title": [...]}}.
    # NULL means no transform ran for this version (a sentinel-free import,
    # or a resume whose reference skeleton could not be computed), not "the
    # transform found nothing".
    #
    # WRITTEN by generation/persistence.py::persist_storybook, the write path
    # both fill routes share, and by scripts/retrofit_personalization.py, the
    # ADR-023 in-place content migration. NOT YET READ: rescreen
    # (moderation/rescreen.py) and the other at-rest checks still re-derive
    # their expectations from the contract, which is the prescriptive
    # semantics Stage R set out to replace; repointing them at this column,
    # and updating a node's entry in place on node-edit/repair adoption, is
    # the remaining half of Task R3. Do not describe those reads as existing
    # until they do.
    sentinel_manifest: Mapped[dict[str, object] | None] = mapped_column(
        JSONB, default=None
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
        # ADR-028: character_id has no index of its own (unlike storybook_id
        # and child_profile_id above, which are covered by the primary key);
        # a character deletion (SET NULL below) would otherwise sequentially
        # scan this table. Postgres never indexes the referencing side of a
        # foreign key automatically (see ix_character_child_profile_id's
        # comment for the same rule).
        Index("ix_reading_state_character_id", "character_id"),
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
    # ADR-028: the persistent character bound to this reading session, and
    # the character-attribute snapshot it was seeded from. Both nullable: an
    # unseeded reading state (no character carried into this book) is the
    # normal case, not an error. SET NULL, not CASCADE: deleting a character
    # must not delete the child's reading progress in the books that
    # character played.
    character_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("character.id", ondelete="SET NULL"), default=None
    )
    seed_var_state: Mapped[VarState | None] = mapped_column(JSONB, default=None)


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


class ReadingActivityDay(UpdatedAtMixin, Base):
    """A child's active-reading-seconds bucket for one calendar day (W3.3).

    Day-grain by design (S10 posture; gamification-recommendation-2026-08-01.md
    section 2.4/5): no session rows and no timestamp finer than a day ever
    reaches the server. ``active_seconds`` accumulates a client-measured,
    idle-gated, visibility-gated active-reading total via idempotent
    ``POST /me/reading-time`` flushes (``api/reading_time.py``); the server
    additively clamps each flush rather than trusting it verbatim (see that
    module for the clamp).

    ``last_flush_id`` is a deliberate addition beyond the recommendation's
    literal data-model sketch (section 5 lists only child_profile_id,
    activity_date, active_seconds, updated_at): the kid-appeal-implementation-
    plan.md W3.3 task explicitly authorizes "a simple per-(profile, date)
    last_flush_id column" as an acceptable idempotency strategy, mirroring
    ``ReadingState.last_event_id``.

    #ASSUME: concurrency: single-slot idempotency (the LAST applied flush id
    only, not a set of every id ever seen) assumes the client single-flights
    retries of one flush before starting the next, exactly like
    ReadingState.last_event_id. The residual window is A-B-A across devices:
    device 1 loses the ack for flush A, device 2 lands flush B, device 1
    retries A, and A is applied twice. Note the direction, since it is easy to
    get backwards: the accumulate itself is an ON CONFLICT DO UPDATE in
    api/reading_time.py::accumulate_stmt, so racing writes SUM correctly and
    cannot lose an increment or collide on the primary key; only the A-B-A
    replay above can over-count. Acceptable here because this is a literacy
    signal, not a billing ledger (recommendation section 2.4), and the
    per-flush clamp in api/reading_time.py bounds one duplicate to 6h.
    #VERIFY: tests/unit/test_reading_time_api_unit.py covers replay dedup and
    pins the A-B-A residual explicitly.

    Retention: the kid-appeal-implementation-plan.md "Plan defaults" section
    (item 2) adopts a 12-month retention default for day-grain rows, after
    which detail rolls into a running total (lifetime days-read survives) --
    to be entered into the ADR-018 counsel bundle and the privacy model's
    data classification. Enforcing that rollover (a scheduled purge/aggregate
    job) is explicitly OUT OF SCOPE for this change; this docstring and the
    plan document the decision, no code here implements it yet. Do not infer
    a retention job exists from this table's presence.
    """

    __tablename__ = "reading_activity_day"
    __table_args__ = (
        CheckConstraint(
            "active_seconds >= 0", name="ck_reading_activity_day_active_seconds"
        ),
    )

    # #CRITICAL: data-integrity: CASCADE (Phase 3a): reading-time accrual is
    # child-linked behavioral data, purged with the profile.
    # #VERIFY: tests/integration/test_deletion_drill.py.
    child_profile_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey(_FK_CHILD_PROFILE, ondelete="CASCADE"), primary_key=True
    )
    activity_date: Mapped[date] = mapped_column(Date, primary_key=True)
    active_seconds: Mapped[int] = mapped_column(default=0, server_default=text("0"))
    last_flush_id: Mapped[str | None] = mapped_column(String(64), default=None)


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
        resulting_storybook_id: The storybook this request produced, stamped
            once at publish (``publishing/service.py::approve``), or
            ``None`` before publish. See the column's own comment for the
            resolution path and why publish (not generation) is the stamp
            point (W0.4).
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
    # W0.4 (kid-appeal-implementation-plan.md, design review section 4.1): the
    # storybook this request actually produced, or None until publish. Stamped
    # exactly once, in publishing/service.py::approve() (the sole
    # draft/in_review -> published transition), by resolving
    # GenerationJob WHERE (storybook_id, version) == the approved storybook's
    # (id, version) to a concept_id, then StoryRequest WHERE concept_id ==
    # that concept_id -- the same two-hop resolution
    # _stamp_request_interpretation (generation/worker.py) already uses for
    # the K19 interpretation write, reused here instead of adding a third way
    # to walk request -> concept -> job -> storybook. Never set at generation
    # time (job/storybook creation): a story is fully moderated and
    # human-approved by the time this column is non-null, so a kid seeing it
    # never learns of an unpublished or rejected draft (api/story_requests.py
    # ``_to_view`` exposes it with no further narrowing for exactly this
    # reason; see the #ASSUME there). Never updated after (a request produces
    # at most one storybook; a re-run after a failure creates a new
    # GenerationJob/Storybook pair tied to the same concept_id, and only the
    # run that actually reaches approve() stamps this field).
    # #CRITICAL: data-integrity: SET NULL, not CASCADE. A storybook row is
    # never deleted by any live application code path today (no admin
    # "delete storybook" endpoint exists; family deletion CASCADEs both the
    # storybook and the story_request together via family_id, so that path
    # never triggers this SET NULL in practice either). This is still the
    # correct ondelete action, matching every other nullable non-owning
    # reference on this row (profile_id, reviewed_by, concept_id,
    # anchor_storybook_id): the request itself is family-owned content that
    # must survive a storybook row vanishing by any other means (a manual
    # admin fixup, a future hard-delete tool, direct SQL), not silently fail
    # to delete or drag the request down with it.
    # #VERIFY: tests/integration/test_deletion_drill.py and
    # tests/unit/test_publishing_service_unit.py::
    # test_approve_stamps_resulting_storybook_id_and_survives_storybook_delete.
    resulting_storybook_id: Mapped[str | None] = mapped_column(
        String(120),
        ForeignKey(_FK_STORYBOOK, ondelete=_ONDELETE_SET_NULL),
        default=None,
    )


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
        # The report-purge send-back exemption probes this table by
        # (entity_type, entity_id, event_type). Without support that is a
        # sequential scan of an append-only log on every nightly sweep. Declared
        # here as well as in the migration because test_schema_parity compares
        # the two and an index present in only one is drift.
        Index(
            "ix_pipeline_event_entity_event_type",
            "entity_type",
            "entity_id",
            "event_type",
        ),
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
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )


class SecurityEvent(UUIDPrimaryKeyMixin, Base):
    """Append-only audit trail for auth failures, denials, and rate-limit trips.

    Written by ``security_audit.py::record_security_event``, the durable
    counterpart to the ``security_auth_failed``/``security_authz_denied``/
    ``security_rate_limit_exceeded`` structured log events
    ``app.py::_handle_project_error`` and
    ``middleware/security.py::RateLimitMiddleware`` emit (OPS-005 follow-up).
    Rows are enforced append-only by a DB trigger created in the migration,
    like ``PipelineEvent``; the ORM never updates or deletes them.

    Deliberately has no actor column (unlike ``PipelineEvent``): many rows
    have no authenticated principal at all -- an auth failure has no
    ``Principal`` to attribute it to, only a ``client_ip``. See the
    migration's header comment for why this is a separate table rather than
    a ``PipelineEvent`` extension.
    """

    __tablename__ = "security_event"
    __table_args__ = (
        CheckConstraint(
            f"event_type IN ({_SECURITY_EVENT_TYPE_VALUES})",
            name="ck_security_event_event_type",
        ),
        Index("ix_security_event_event_type", "event_type"),
        Index("ix_security_event_occurred_at", "occurred_at"),
        Index("ix_security_event_client_ip", "client_ip"),
    )

    occurred_at: Mapped[datetime] = mapped_column(_TS, server_default=func.now())
    event_type: Mapped[str] = mapped_column(String(48))
    # #ASSUME: data-integrity: reason is always one of this codebase's fixed,
    # developer-authored `msg = "..."` literals (AuthenticationError/
    # AuthorizationError messages) or a rate-limit `limit_type` token, never
    # caller input; security_audit.py truncates to this bound as a backstop
    # only, matching events/writer.py's _MAX_PAYLOAD_STR_LEN convention.
    # #VERIFY: tests/unit/test_security_audit.py.
    reason: Mapped[str] = mapped_column(String(200))
    client_ip: Mapped[str | None] = mapped_column(String(45), nullable=True)
    # The exception's machine-readable error_code (e.g. the AuthenticationError/
    # AuthorizationError class default, or "PIN_MISMATCH" from
    # api/child_sessions.py); unset for a rate-limit row, which has no
    # exception to draw one from. Lets a detection rule key on e.g.
    # PIN_MISMATCH without string-matching `reason`
    # (docs/operations/security-events.md section 2).
    code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    path: Mapped[str | None] = mapped_column(String(255), nullable=True)
    method: Mapped[str | None] = mapped_column(String(10), nullable=True)
    status_code: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)
    # The authz-denial resource identifier only (already pruned of value/
    # context by app.py's _client_safe_error before it reaches this writer);
    # unset for auth-failure and rate-limit rows.
    resource: Mapped[str | None] = mapped_column(String(255), nullable=True)


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


_ALLOWLIST_PROVIDER_VALUES = "'anthropic', 'openrouter', 'modal'"

# The providers an ENABLED allowlist row may name, mirroring the
# ck_provider_model_allowlist_enabled_family_lane CHECK added by
# 20260823160000_constrain_allowlist_enabled_to_the_family_lane.sql. This is
# the INTERSECTION of generation/provider.py::FAMILY_LANE_PROVIDERS with
# _ALLOWLIST_PROVIDER_VALUES above, not a copy of either: 'mock' is family-lane
# permitted but excluded from this table entirely by the sibling CHECK, and
# 'anthropic' may hold a row here but only a DISABLED one (D1, `UW-C346`).
# Spelled as a literal here rather than imported, for the same reason
# _ALLOWLIST_PROVIDER_VALUES is: db/ does not import generation/.
_FAMILY_LANE_ENABLED_PROVIDER_VALUES = "'modal', 'openrouter'"


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
    # #CRITICAL: security: the second CHECK is the at-rest half of the D1
    # family-lane rule (`UW-C350`(b)): a row whose provider is outside
    # generation/provider.py::FAMILY_LANE_PROVIDERS may EXIST but may not be
    # ENABLED, because every reader of this table resolves to a family-lane
    # generation job. Existence stays legal deliberately: the withdrawn
    # anthropic rows are disabled rather than deleted, since the original seed
    # migration's ON CONFLICT DO NOTHING would re-insert a deleted row ENABLED
    # on any replay (`AL-589`). This mirror exists because the migration and
    # the ORM are compared structurally; it is not a second enforcement point.
    # #VERIFY: tests/integration/test_schema_parity.py::
    # test_migrations_match_orm_models pins this against the migration, and
    # tests/integration/test_allowlist_family_lane_constraint.py pins the
    # migration's own predicate against FAMILY_LANE_PROVIDERS.
    __table_args__ = (
        CheckConstraint(
            f"provider IN ({_ALLOWLIST_PROVIDER_VALUES})",
            name="ck_provider_model_allowlist_provider",
        ),
        CheckConstraint(
            f"enabled IS FALSE OR provider IN ({_FAMILY_LANE_ENABLED_PROVIDER_VALUES})",
            name="ck_provider_model_allowlist_enabled_family_lane",
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
        provider_call_count: Provider calls this run made, across every stage
            and both models. NULL means not recorded, never zero.
        provider_unknown_calls: How many of those calls reported no usable
            token count. Non-zero makes the token and cost columns beside it
            lower bounds rather than totals.
        input_tokens: Prompt tokens summed over the run's recorded calls.
        output_tokens: Completion tokens summed the same way.
        provider_duration_ms: Wall-clock milliseconds spent inside provider
            calls, which is not the job's total runtime.
        cost_usd: Summed per-call cost as ``Decimal``, never float. A lower
            bound whenever ``cost_complete`` is False.
        cost_complete: Whether every call was both fully priced and fully
            counted. Not derivable from the other columns; see the field
            comment.
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
    # 30 days, EXCEPT when a human reached a review decision about the storybook
    # this job produced (published/archived, or a "sent_back" pipeline_event),
    # which the 2026-08-10 amendment exempts so the raw output can be paired with
    # the reviewer's decision in the review-scorecard calibration corpus.
    # Publishing is now an exemption from the purge, not a trigger for it: the
    # 2026-08-11 amendment removed publishing/service.py::approve's immediate
    # on-publish null, which had defeated the approve half of that exemption
    # (within src/, approve is the only path that sets "published", and it
    # nulled the report in the same transaction). The nightly pg_cron sweep is
    # now the only thing that nulls this column.
    # #CRITICAL: data integrity: the exemption is evaluated when the SWEEP runs,
    # not when the human decides, so it does not protect a slow review. A job at
    # status "passed" whose storybook is still "in_review" on day 31 is purged;
    # an approval on day 32 flips the storybook to "published" but cannot restore
    # the column. The calibration-corpus purpose therefore holds only for reviews
    # that conclude inside 30 days of the job's last update. This is a property of
    # the 2026-08-10 predicate, not of the 2026-08-11 amendment, and closing it
    # means changing the predicate (an updated_at touch on decision, or dropping
    # the status filter for undecided storybooks), which is an owner decision.
    # #VERIFY: test_slow_review_report_is_purged_before_the_human_decides in
    # tests/unit/test_report_retention.py pins the current behaviour so this
    # window cannot be believed away; tracked as UW-C227.
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
    # ------------------------------------------------------------------
    # Provider accounting (what this job consumed and what it cost).
    # ------------------------------------------------------------------
    # #CRITICAL: data integrity: these are typed columns rather than keys
    # inside ``report`` BECAUSE ``report`` is purged (ADR-007, the Phase 5
    # pg_cron job above). Cost history has to outlive prompt retention: the
    # question "what has generation cost us" is asked months later, long after
    # the raw output it is derived from is gone. A usage blob folded into
    # ``report`` would be deleted by a retention rule aimed at something else
    # entirely, and nothing would report the loss.
    # #VERIFY: any future retention rule must leave these columns alone; the
    # purge exemption test (tests/integration/test_generation_models.py) and
    # the report-purge migration are the two places that would have to change.
    #
    # #ASSUME: data integrity: every column here is nullable and NULL means
    # "not recorded", never "zero". Rows written before this migration have no
    # accounting at all, and a job whose backend reported no usage is a
    # different state again (``provider_call_count`` set,
    # ``provider_unknown_calls`` non-zero). Collapsing either into 0 would make
    # an un-instrumented run look free.
    # #VERIFY: readers must treat NULL as unknown and must not SUM these
    # columns across jobs without also checking ``provider_unknown_calls`` and
    # ``cost_complete``; a SUM over a mix of recorded and unrecorded jobs is a
    # lower bound, not a total.
    provider_call_count: Mapped[int | None] = mapped_column(default=None)
    provider_unknown_calls: Mapped[int | None] = mapped_column(default=None)
    input_tokens: Mapped[int | None] = mapped_column(default=None)
    output_tokens: Mapped[int | None] = mapped_column(default=None)
    provider_duration_ms: Mapped[int | None] = mapped_column(default=None)
    # #CRITICAL: payment/financial: NUMERIC, never a float column. Per-call
    # amounts run to millionths of a dollar (a 1000-token call at $5/Mtok is
    # $0.005) and these values are summed across thousands of jobs, which is
    # exactly the regime where binary floating point accumulates a drift no
    # reader can attribute.
    #
    # Precision and scale fail in OPPOSITE ways, which is why the writer
    # cannot simply assign. Scale 6 does NOT hold every amount exactly: a
    # 3-token call at $1.25/Mtok is $0.00000375, eight fractional digits, and
    # Postgres rounds the excess away SILENTLY. Precision 12 leaves 6 integer
    # digits, and an amount past $999,999 is not rounded but RAISES `numeric
    # field overflow` at COMMIT. ``generation.cost.fit_cost_to_column`` is
    # what reconciles both before a value is ever assigned: it rounds to
    # scale explicitly (so the in-memory value equals the stored one) and
    # caps at the precision ceiling, marking a capped amount incomplete.
    # #VERIFY: test_cost_usd_round_trips_as_decimal pins that the value comes
    # back as Decimal rather than float, since the driver's type mapping is
    # what makes the column choice effective. Widening this column means
    # widening ``_MAX_COST_USD``/``_COST_SCALE`` in generation/cost.py in the
    # same change.
    cost_usd: Mapped[Decimal | None] = mapped_column(Numeric(12, 6), default=None)
    # #ASSUME: payment/financial: ``cost_complete`` is NOT derivable from the
    # other columns. A run can report every token and still be un-costable
    # because a model has no entry in ``core/pricing.py``, so this records what
    # the price table knew at the time the job ran, which a later reader cannot
    # reconstruct from a price table that has since been filled in.
    # #VERIFY: False means ``cost_usd`` is a LOWER BOUND; no caller may present
    # it as a total or compare it against a budget without saying so.
    cost_complete: Mapped[bool | None] = mapped_column(default=None)


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


class DeviceDownload(UUIDPrimaryKeyMixin, CreatedAtMixin, UpdatedAtMixin, Base):
    """One (device, child profile, storybook) offline-download record (G15).

    Reports client-side IndexedDB cache state (``frontend/src/offline/db.ts``'s
    ``storybooks`` store) so a guardian can see which books are downloaded on
    which device, closing the one remaining G15 gap (device list/revoke was
    already delivered via ``DeviceGrant``). ``device_id`` is a NEW, separate
    identity from ``DeviceGrant.jti``: it is a plain client-generated UUID
    persisted in ``localStorage`` (``frontend/src/offline/deviceId.ts``), not
    the kid-mode device-authorization token id. The two concepts do not
    coincide: a guardian's own browser previewing the kid shelf downloads
    books too, and has no ``DeviceGrant`` of its own, so keying this table on
    the auth token id would silently miss it.

    ``family_id`` is denormalized from the owning profile (same reasoning as
    ``Character.family_id``: this table carries the ADR-022 Tier 1
    ``family_scoped`` RLS policy, which needs the family on the row itself)
    and kept honest by the same composite FK pattern.

    This is a best-effort snapshot, not a strict inventory: a device that
    goes permanently offline right after downloading, or is wiped without
    ever coming back online, leaves a stale row behind forever (nothing ever
    reports its removal). ``updated_at`` (inherited, "last confirmed") is the
    guardian-visible staleness signal; nothing purges a row on a timer.

    Attributes:
        id: Surrogate primary key.
        family_id: The owning profile's family, denormalized for RLS.
        child_profile_id: The profile the book was downloaded for.
        device_id: The reporting device's client-generated persistent id.
        storybook_id: The downloaded book. Tracked at the book level, not
            per-version: ``deleteStorybooksById`` (the client eviction path)
            removes every cached version of an id at once, so a per-version
            row would just always agree with the book-level one while adding
            nothing.
        created_at: When this device first reported downloading this book.
        updated_at: When this device most recently confirmed still having it
            (a fresh download of an already-reported book updates this
            rather than inserting a second row; see the unique constraint).
    """

    __tablename__ = "device_download"
    __table_args__ = (
        ForeignKeyConstraint(
            ["child_profile_id", "family_id"],
            [_FK_CHILD_PROFILE, _FK_CHILD_PROFILE_FAMILY_ID],
            ondelete="CASCADE",
            name="fk_device_download_profile_family",
        ),
        UniqueConstraint(
            "device_id",
            "child_profile_id",
            "storybook_id",
            name="uq_device_download_device_profile_book",
        ),
        Index("ix_device_download_family_id", "family_id"),
        # Both referencing FK sides are indexed; Postgres indexes only the
        # referenced side automatically, so an unindexed one turns each
        # cascading parent delete into a sequential scan of this table.
        Index("ix_device_download_storybook_id", "storybook_id"),
    )

    family_id: Mapped[uuid.UUID] = mapped_column()
    child_profile_id: Mapped[uuid.UUID] = mapped_column()
    device_id: Mapped[str] = mapped_column(String(64))
    # #CRITICAL: data-integrity: CASCADE (Phase 3a): a download record is
    # child- and story-linked data, purged with either side.
    # #VERIFY: tests/integration/test_deletion_drill.py.
    storybook_id: Mapped[str] = mapped_column(
        ForeignKey(_FK_STORYBOOK, ondelete="CASCADE")
    )


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


class KwsVerification(Base):
    """One KWS parent-verification attempt, from send to resolution (ADR-018).

    The row is written by ``consent/service.py::start_parent_verification``
    BEFORE the outbound send-email call, and resolved later by
    ``consent/service.py::record_parent_verified`` when the authenticated
    ``parent-verified`` webhook quotes our ``externalPayload`` back.

    Scope, since the class name invites a wrong reading: KWS establishes that
    an adult is an adult. A ``verified`` row here is corroborating evidence
    beside the 16 CFR 312.5 consent record on ``User.consent_*``, never a
    replacement for it (see ``consent/__init__.py``).

    #CRITICAL: security: there is deliberately NO ``parent_email`` column, and
    none may be added under any name. Avoiding the parent's address as a join
    key is the entire reason the opaque per-attempt correlation exists
    (``consent/external_payload.py``); a column here would reintroduce the most
    sensitive field in the delivery as this table's natural key, and it would
    not survive a guardian changing their address either.
    #VERIFY: tests/unit/test_kws_verification_model.py::
    test_the_table_has_no_email_column.

    Attributes:
        id: The minted attempt id, which IS the correlation. Not a separate
            surrogate key: the value we hand KWS in ``externalPayload`` and the
            value we look a delivery up by must be the same value, or the
            lookup needs a second index and a second chance to disagree.
        user_id: The guardian this attempt attributes to.
        kws_environment: Which KWS environment produced it, ``test`` or
            ``production``.
        status: ``sent`` until a delivery resolves it to ``verified`` or
            ``failed``, or until the outbound send itself gives up and leaves
            it ``send_failed``. Only the first two are facts about the parent.
        requested_at: When the send was attempted (UTC, TIMESTAMPTZ).
        resolved_at: When the attempt stopped being open, or ``None`` while
            ``sent``. For ``verified`` and ``failed`` that is when the delivery
            landed; for ``send_failed`` it is when we gave up sending. The
            pairing CHECK forces the column to carry both, so a reader that
            means "a delivery arrived" must filter on status as well.
        transaction_id: KWS's opaque id for the verification, ``None`` until a
            delivery reports one.
        enabled_methods: ``settings.kws_enabled_methods`` as it stood at send
            time.
        location: The location sent to KWS for this attempt, which selected
            which methods the parent was offered. ``None`` on rows written
            before the column existed.
    """

    __tablename__ = "kws_verification"
    # #CRITICAL: data integrity: both vocabularies are constrained AT REST, not
    # just at the writer. kws_environment in particular is the only thing that
    # distinguishes a sandbox verification from evidence about a real parent
    # (the KWS API reports nothing that identifies which environment answered),
    # so an unmodeled value here would be an unreadable record rather than a
    # cosmetic defect. The pairing CHECK is the same shape as
    # ck_kid_flag_resolved_pairing: it keeps a "still waiting" filter
    # (status = 'sent') from ever disagreeing with resolved_at IS NULL.
    # #VERIFY: tests/unit/test_kws_verification_model.py::
    # test_status_and_environment_are_constrained_at_rest and
    # ::test_resolution_pairing_is_constrained_at_rest.
    __table_args__ = (
        CheckConstraint(
            f"status IN ({_KWS_VERIFICATION_STATUS_VALUES})",
            name="ck_kws_verification_status",
        ),
        CheckConstraint(
            f"kws_environment IN ({_KWS_ENVIRONMENT_VALUES})",
            name="ck_kws_verification_environment",
        ),
        CheckConstraint(
            "(status = 'sent') = (resolved_at IS NULL)",
            name="ck_kws_verification_resolution_pairing",
        ),
        # ADR-018 D1 names the location a compliance input, because it is what
        # selects the methods KWS offers the parent; a FORMAT check only, in
        # the same spirit as ck_user_residence_country_format. It accepts an
        # ISO 3166-1 alpha-2 country ("US") or an ISO 3166-2 subdivision
        # ("US-CA"), and does not test membership: real membership is enforced
        # at the API boundary, and KWS itself rejects a code it does not know.
        # NULL stays legal, since rows written before this column existed
        # carry no location and inventing one for them would be a lie.
        CheckConstraint(
            "location IS NULL OR location ~ '^[A-Z]{2}(-[A-Z0-9]{1,3})?$'",
            name="ck_kws_verification_location_format",
        ),
        # #ASSUME: external resources: the delivery-health aggregate
        # (consent/service.py::verification_delivery_health) filters this whole
        # table on kws_environment and aggregates over requested_at and
        # resolved_at, and it is reached from the PUBLIC, UNAUTHENTICATED
        # readiness endpoint (api/health.py::check_kws_verification). Rows here
        # are never deleted, so without this index the scan grows without a
        # ceiling; the only other index on the table is the user_id one, which
        # has kws_environment nowhere in it and cannot serve the predicate at
        # all. Its job is to bound the scan to one environment, NOT to cover
        # the query: the aggregate's FILTER also reads status, so an index-only
        # scan would need a four-column index, which is not worth the write
        # cost on a table that gains one row per verification email.
        # #VERIFY: keep in step with supabase/migrations/
        # 20260810180000_add_kws_verification_delivery_health_index.sql;
        # tests/integration/test_schema_parity.py compares the two databases the
        # two paths build, so dropping either half fails there.
        Index(
            "ix_kws_verification_environment_requested_at",
            "kws_environment",
            "requested_at",
        ),
    )

    # No ``UUIDPrimaryKeyMixin``, and no default: the mixin's ``uuid.uuid4``
    # default would silently mint a SECOND id for a caller that forgot to pass
    # the one it gave KWS, and that row could never be matched to a delivery.
    # Requiring the value makes the omission a NOT NULL failure instead.
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True)
    # #CRITICAL: data-integrity: CASCADE (Phase 3a, GDPR/COPPA erasure): a
    # verification attempt is personal data about the guardian who started it,
    # so it goes when their user row does.
    # #VERIFY: tests/integration/test_deletion_drill.py::
    # test_delete_my_family_removes_the_kws_verification_rows. Name that test,
    # not the file: it is the only one in there that seeds a kws_verification
    # row, so it is the only one this CASCADE can be observed by.
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey(_FK_USER, ondelete="CASCADE"), index=True
    )
    kws_environment: Mapped[str] = mapped_column(String(16))
    status: Mapped[str] = mapped_column(
        String(16), default=KWS_VERIFICATION_STATUS_SENT
    )
    requested_at: Mapped[datetime] = mapped_column(_TS, server_default=func.now())
    resolved_at: Mapped[datetime | None] = mapped_column(_TS, default=None)
    transaction_id: Mapped[str | None] = mapped_column(String(128), default=None)
    # #CRITICAL: data integrity: a SNAPSHOT, never a live read. The
    # parent-verified event reports no verification method at all, so the set
    # enabled at send time is the only bound that will ever exist on how this
    # parent was verified, and the vendor cannot supply one afterwards. Read
    # live instead of copied, that bound would evaporate retroactively for
    # every row the instant anyone toggled a row in the Control Panel.
    # #VERIFY: tests/unit/test_kws_verification_service.py::
    # test_the_enabled_methods_snapshot_is_copied_not_referenced.
    enabled_methods: Mapped[list[str]] = mapped_column(JSONB)
    # #CRITICAL: data integrity: a SNAPSHOT for the same reason
    # enabled_methods is one. The location decides which methods KWS offers
    # this parent, so it bounds how they could have been verified just as
    # directly as the method list does, and the parent-verified event reports
    # neither. Nullable because rows predating this column have no location
    # and no way to recover one.
    # #VERIFY: tests/unit/test_kws_verification_service.py::
    # test_the_location_is_recorded_on_the_attempt.
    location: Mapped[str | None] = mapped_column(String(16), default=None)
