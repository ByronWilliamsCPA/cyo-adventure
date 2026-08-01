---
title: "ADR-025: Additive minor versioning for the Storybook schema"
schema_type: planning
status: accepted
owner: core-maintainer
purpose: "Define how the Storybook JSON schema evolves without invalidating published blobs or offline
  caches: minor versions are strictly additive-optional, the server accepts a declared compatibility
  range instead of one exact version string, and runtime-visible additions are gated on conformance
  corpus coverage in both player engines."
tags:
  - planning
  - architecture
  - decisions
  - storybook
---

# ADR-025: Additive minor versioning for the Storybook schema

> **Status**: Accepted (2026-08-01), on owner direction recorded in
> [design-review-kid-appeal-2026-08-01.md](../design-review-kid-appeal-2026-08-01.md) section 8
> (question F1).
> **Cross-sign**: `storybook/models.py`, `storybook/schema_export.py`, `schema/storybook.schema.json`,
> both player engines, and the conformance corpus. No database migration; published blobs are not
> rewritten.

## TL;DR

The Storybook schema moves from "exactly `2.0` or reject" to a declared **accepted range** of minor
versions, where a minor version may only **add optional fields with safe defaults**. Anything else
(renames, semantic changes, new required fields) is a major version and a separate decision.
Published blobs keep the version they were published with, forever; nothing is backfilled. A new
field that changes what a reader sees or does may not be used by content until both player engines
implement it and the conformance corpus covers it.

## Context

Every model in `storybook/models.py` sets `extra="forbid"`, `schema/storybook.schema.json` sets
`additionalProperties: false` throughout, and `Storybook._check_schema_version` requires exact
string equality with `SCHEMA_VERSION = "2.0"`. The consequence, documented in the kid-appeal design
review (section 5.1): adding any per-node or per-ending field (illustration URL, sound cue, ending
rarity) either rejects every already-published blob (bump with exact equality) or hard-fails older
parsers (add without bump). There is no additive rule, no extension bag, and no blob migration path.

Mitigating facts that shape the decision:

- The frontend `Storybook`/`StoryNode` types are plain TS interfaces, structurally tolerant of
  unknown fields; cached offline blobs and old clients do not break on additions. The strictness is
  entirely server-side.
- Content is only ever produced server-side behind the generation and approval gates, so the writer
  and its validator deploy together; forward tolerance (old server reading newer blob) is only an
  issue during a rolling deploy window.
- Reading state pins `(storybook_id, version)` already, so a published blob is immutable and its
  schema version is a stable property of that artifact.

## Decision

1. **Version grammar.** `schema_version` is `MAJOR.MINOR`. A **minor** bump may only add optional
   fields with defaults that reproduce current behavior when absent (absent = today's semantics,
   byte-for-byte). Prohibited in a minor: removing or renaming fields, changing the meaning or type
   of existing fields, adding required fields, tightening validation on existing content. Any of
   those is a **major** bump and requires its own ADR.
2. **Accepted range, not exact match.** The parser accepts any `2.x` with `x <=` the deployed
   `SCHEMA_MINOR`. It stamps newly-published blobs with the current version. `extra="forbid"`
   stays: each minor enumerates its fields explicitly, so strict parsing still catches junk while
   the range check provides backward compatibility. `schema_export.py` emits the JSON schema for
   the current minor; the schema for each historical minor is reproducible from the tagged release
   that introduced it.
3. **No backfill.** Published `2.0` blobs remain `2.0` indefinitely. A story only carries a new
   field if it was published (or republished through the normal approval gate) at the minor that
   defines it.
4. **Runtime-visible additions are corpus-gated.** If a new field changes anything a reader sees or
   does (an image, a sound cue, ending rarity in the celebration), then before any production
   content uses it: both `player/engine.py` and `frontend/src/player/engine.ts` (or the relevant
   renderer) implement it, and `schema/conformance/` gains cases exercising it. A minor that adds a
   purely descriptive field (metadata no renderer reads yet) may ship without corpus entries but
   must say so in its changelog entry.
5. **Operational caveat.** During a rolling deploy, an old replica must never be asked to parse a
   newer minor. Sequence: deploy the code that understands `2.(x+1)` everywhere first; only then
   allow content at `2.(x+1)` to be authored or imported. With a single-operator deployment this is
   a release-notes rule, not tooling.

## Consequences

- Unblocks, without further format debate: ending `rarity`/`is_secret` metadata (design review
  3.4), optional per-node media fields (5.2, gated on its own ADR for art scope per ADR-017),
  sound-cue fields (owner decision, 2026-08-01), and future band-specific presentation hints.
- Each such feature still needs its own product decision; this ADR only removes the format wall.
- The validator gains a small version-range check and loses nothing: strict field enumeration per
  minor keeps the LLM-output gate as tight as today.
- Cost accepted: two engines plus corpus per runtime-visible field (already the standing tax,
  design review 5.3), and a per-minor discipline that additions land in `models.py`,
  `schema_export.py`, the JSON schema, and the changelog together.
