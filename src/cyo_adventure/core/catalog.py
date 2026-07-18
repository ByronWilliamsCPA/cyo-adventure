"""Canonical catalog-ownership constants.

The base story inventory, admin-authored stories that every family's guardians
can browse and assign, is owned by a single reserved "Library" family rather
than any real family. This module names that family's canonical id so the
import CLI (and any future admin surface) reference it by name, never a magic
UUID.

The Library family is seeded by
``supabase/migrations/20260718000000_library_family.sql``. It holds no users or
child profiles: admins manage its stories through the global ``is_admin``
review/approval capability, and a Library-owned story reaches a child only
after an admin publishes it at ``visibility='catalog'`` (WS-E,
``publishing/state_machine.py``) and a guardian assigns it
(``StorybookAssignment``), exactly like any other catalog book.
"""

from __future__ import annotations

import uuid

# #CRITICAL: security: this id is the ownership boundary for the shared base
# inventory. It is a reserved, deterministic sentinel (all-zero except the
# final octet) so every environment's migration seeds the same row; changing
# it would orphan every Library-owned story. Library ownership does NOT by
# itself widen visibility: a Library-owned story stays family-private until an
# admin sets visibility='catalog' at release approval, and the
# StorybookAssignment read-gate is unchanged.
# #VERIFY: tests/unit/test_catalog.py pins this value; the migration inserts
# exactly this id, and import_cli --library imports under it.
LIBRARY_FAMILY_ID = uuid.UUID("00000000-0000-0000-0000-000000000001")

# Human-readable name for the reserved family row (kept in sync with the
# migration's INSERT and the Family.name column).
LIBRARY_FAMILY_NAME = "Library"
