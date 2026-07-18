---
title: "Catalog-first inventory: admin-only Library family as storage owner"
schema_type: planning
status: delivered
owner: core-maintainer
purpose: "Record the delivered ownership model for the admin-authored base story
  inventory: a single reserved Library family owns catalog-origin stories, and
  import_cli --library imports under it, so a base-inventory story needs no real
  family's UUID."
tags:
  - planning
  - architecture
  - catalog
  - authorization
---

# Catalog-first inventory: admin-only Library family

> **Status**: Delivered (2026-07-18). Surfaced during the initial
> story-inventory authoring run, whose import step required `--family <uuid>`,
> which is wrong for a base inventory that no real family owns.

## The gap, as stated

1. Stories should not require a real family's UUID; admins should author a base
   inventory that exists independent of any family.
2. Guardians should browse that inventory and decide which titles to authorize
   for their family.
3. Kids should be able to request a title from the main library, prompting
   their guardian to review it for inclusion. (Deferred to a follow-up PR; see
   below.)

## Delivered design (this PR): admin-only Library family

The base inventory is owned by a single reserved **Library** family rather than
any real family, and rather than making `Storybook.family_id` nullable. This
keeps the NOT NULL ownership invariant and every existing family-scoped access
check unchanged, while giving admin-authored stories a stable, real owner.

- **`core/catalog.py::LIBRARY_FAMILY_ID`** names the reserved family's
  deterministic id (`00000000-0000-0000-0000-000000000001`).
- **`supabase/migrations/20260718000000_library_family.sql`** seeds that family
  idempotently (`ON CONFLICT DO NOTHING`) in every environment. It holds no
  users or child profiles.
- **`import_cli --library`** imports a filled story under the Library family
  (mutually exclusive with `--family`), so no real family's UUID is needed.

Ownership by the Library family grants **no** child access on its own. The
import still runs the validation gate and the moderation pipeline and lands the
story `in_review` (ADR-005: mandatory human approval is preserved). An admin
then approves, publishes, and sets `visibility='catalog'` through the normal
WS-E flow; only then can guardians browse the story and assign it to a child
via `StorybookAssignment` (the unchanged read-gate). `api/library.py` already
reads `visibility='catalog'` books cross-family, so a Library-owned catalog book
is browsable and assignable by every family with no further change.

## Why not nullable `family_id`

An earlier assessment proposed widening `Storybook.family_id` to nullable
(NULL = library-owned). The admin-only Library family reaches the same outcome
without a schema/RLS change or an audit of every `family_id ==` filter: those
filters keep working because the Library family is a real row. Requirement 2
(guardian authorization) needs no change; it is the existing catalog browse +
`StorybookAssignment` flow.

## Operator steps: import the base inventory to Supabase

After this migration is applied to the target (Supabase) database, an admin
imports each approved filled story under the Library family:

```bash
# once per approved story (filled JSON produced by the authoring run)
uv run python -m cyo_adventure.generation.import_cli \
    out/<slug>.filled.json --library --model <model-id>
```

Each import lands the story `in_review` under the Library family; the admin then
approves + publishes + sets `visibility='catalog'` in the admin console. Every
family's guardians can then browse and assign the title.

Requires the migration applied and DB credentials for the target environment;
it is an operator action in the authenticated environment, not part of CI.

## Follow-up (not in this PR)

- **Kid title requests (gap requirement 3)**: a kid-facing catalog browse
  (age-band filtered, title/cover only) plus a `title_request` row and a
  guardian "requested by your reader" queue whose approval creates the
  `StorybookAssignment`. Touches the OpenAPI contract (regenerate the frontend
  client). Related: issue #173 (nullable `StoryRequest.family_id` for
  catalog-origin generation requests).
