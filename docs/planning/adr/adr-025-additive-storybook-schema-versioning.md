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
> (question F1). The frontmatter `status: accepted` refers to the decision, which is settled;
> implementation is tracked separately and is not a frontmatter state in this repo.
> First implemented (2026-08-06) by the ADR-025 implementation plan in PR
> [#636](https://github.com/ByronWilliamsCPA/cyo-adventure/pull/636) (branch
> `feat/persistent-characters`), **which had not merged when this line was written**; treat
> "Implementation notes" below as describing that branch until #636 lands on `main`.
> **Cross-sign**: `storybook/models.py`, `storybook/schema_export.py`, `schema/storybook.schema.json`,
> both player engines, and the conformance corpus. No database migration; published blobs are not
> rewritten.
> **Scope**: this ADR was a design record only when accepted. As of the commit that accepted it,
> `_check_schema_version` still required exact equality with `SCHEMA_VERSION = "2.0"`, there was no
> `SCHEMA_MINOR` constant, and no range check existed anywhere. The decision text below was written
> in the present tense as a specification of the target state, in the same voice as
> [ADR-027](./adr-027-in-story-illustration.md), which carries a similar disclaimer.
> Implementation was separately scheduled work at that time; see "Implementation notes" below for
> what is actually true in the tree now.

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

## Alternatives Considered

### Alternative 1: keep exact-equality versioning and migrate published blobs on each bump

Bump `SCHEMA_VERSION` to `2.1` as today, keep the exact string comparison, and rewrite every stored
blob to the new version as part of the release.

Rejected. A published blob is not just a document, it is the artifact a reading state pins by
`(storybook_id, version)`, and the offline cache holds copies this server cannot reach at all. A
rewrite would either invalidate live reading states or leave device caches disagreeing with the
server about what version `2.1` contains. It also converts every additive field into a data
migration with a rollback story, which is the cost this ADR exists to remove.

### Alternative 2: an extension bag (`extra="allow"`, or a single `extensions` dict)

Relax `extra="forbid"` and `additionalProperties: false`, or add one open `extensions: dict` field
that new features write into without a version bump at all.

Rejected, and it is the option this ADR most deliberately refuses. Strict field enumeration is
not incidental strictness; it is the gate that catches malformed LLM output before a human
reviewer ever sees it, and an open bag is exactly the hole a generator hallucinating a plausible
field key would fall through undetected. It also gives up the one property the range check buys:
a parser can still say precisely which fields it does and does not understand.

### Alternative 3: major-version-per-addition

Treat every schema change as a major bump with its own ADR, accepting that each one is a breaking
change and scheduling it as such.

Rejected as honest but unaffordable. Four features already queued behind the format wall (ending
rarity, per-node media, sound cues, band presentation hints) would each become a breaking change
with a deploy sequence and a compatibility window, for additions that by construction change
nothing about how an existing story reads. The decision keeps the major-bump discipline for
changes that genuinely are breaking; it only declines to treat "one new optional field" as one of
them.

## Implementation notes (2026-08-06, first implementation)

Two enforcement points carry the decision, backed by one constant convention:

1. `Storybook._check_schema_version` (`storybook/models.py`) delegates to
   `is_supported_schema_version`, which accepts any `SCHEMA_MAJOR.x` with `x <= SCHEMA_MINOR` and
   returns `False`, never raises, for a version outside that range, a malformed string, or a
   non-string value. `parse_schema_version` is the one function that parses a raw `MAJOR.MINOR`
   string and the one that raises `ValueError` when it is malformed; `is_supported_schema_version`
   takes `object`, catches that, and turns both the malformed and the wrong-type case into a
   `False` result rather than propagating an exception out of a trust boundary.
2. `import_catalog._needs_legacy_normalization` asks a narrower question than the parser does: "is
   this the legacy shape I should rewrite", via `parse_schema_version` directly, not
   `is_supported_schema_version`. Because "legacy" means "rewrite it", the predicate returns `True`
   for exactly two inputs, and the three paths are distinct:
   - **Legacy (rewritten).** The `schema_version` key is absent entirely (the pre-versioning
     shape, where no claim was ever made so stamping one on is a repair), or it names a major
     below `SCHEMA_MAJOR`.
   - **Supported (topology decides).** Any same-major version at or below `SCHEMA_MINOR`, not
     merely one at exactly the current minor, falls through to the `metadata.topology` check and
     is legacy only if that key is missing.
   - **Refused (never rewritten, returns before the topology check).** A higher major, a
     same-major future minor such as `2.1`, an unparseable string such as `3.0.0` or `v3.0`, and
     a present-but-non-string value. Each reaches `run_gate` unmodified to be rejected loudly by
     `_check_schema_version`. This is decided by the version bound alone, so the outcome does not
     depend on whether `metadata.topology` happens to be present.

   The asymmetry between an absent key and a present-but-wrong one is the whole point: overwriting
   a wrong claim destroys the evidence the refusal rests on. The importer's job is detecting the
   legacy pre-versioning shape, not deciding what this build can parse; those are different
   questions on purpose, and collapsing them into one call would let a same-major, unsupported
   document masquerade as `2.0`.

Backing both: `SCHEMA_MINOR` in `storybook/models.py` is the single place a minor is bumped, and
`SCHEMA_VERSION` is derived from it so the two cannot drift.
`LEGACY_NORMALIZED_SCHEMA_VERSION = "2.0"` in `import_catalog.py` is a separate, deliberately fixed
constant pinning the stamp the legacy normalizer writes; it must never be changed to track
`SCHEMA_MINOR`, or a future minor bump would start rewriting legacy blobs to a version this build
never actually normalized them for.

**The exported JSON Schema is deliberately not a third enforcement point.**
`schema/storybook.schema.json` constrains `schema_version` to `{"type": "string"}` with no
`pattern`, `enum`, or `const`, so L1-1 (schema conformance) accepts `"3.0"` and `"banana"` alike.
The range check is a `model_validator(mode="after")`, which has no JSON Schema representation, so
it can only run at the Pydantic boundary. A document with an unsupported version therefore passes
L1-1 and is refused in `validator/gate.py::_parse_storybook`, which reports it as a normal L1-1
finding carrying Pydantic's own message. That path is reachable by design, not a schema-drift
anomaly, and no amount of keeping `schema_export.build_schema()` in sync with `models.py` would
change it.

This is the same accepted-range mechanism decision 2 describes; the importer's legacy-detection
question is implementation detail decision 2's text did not need to anticipate.

**Known gap: decision 2's stamping clause and decision 3's converse are not enforced.** Neither
enforcement point above ties the emitted `schema_version` stamp to `SCHEMA_VERSION`.
`Storybook.schema_version` defaults to `SCHEMA_VERSION` only when the field is absent from the
input, and every real producer supplies it explicitly. The full inventory, which is more varied
than "hardcoded at `2.0`":

| Producer | How the value is chosen |
| --- | --- |
| The 61 committed skeleton documents under `skeletons/` | Literal `"2.0"` in each. (`skeletons/*/*.json` matches 124 files; the other 63 are `.contract.json` and `.lineage.json` sidecars carrying their own `contract_version`/`lineage_version`, not the Storybook schema.) |
| `scripts/seed_dev_data.py:167`, `scripts/seed_series_catalog.py:145` | Literal `"2.0"`. |
| `scripts/build_series_book.py:315` | `str(spec.get("schema_version", "2.0"))`: spec-driven, with `"2.0"` only as a fallback, so a series spec can already declare any string. |
| `generation/templates/structure.md:27` (Stage-A prompt) | **Unpinned.** The prompt lists `schema_version` among the required top-level fields but states no value, so an LLM-generated skeleton carries whatever the model emitted. |
| `import_catalog._normalize_legacy_fill` | `LEGACY_NORMALIZED_SCHEMA_VERSION`, pinned at `"2.0"` on purpose (see above). |

The Stage-A prompt is the significant omission: it is the primary production path, not a script,
and it is the one producer with no pinned value at all. Note also that the scan behind this
inventory is narrower than it first appears: outside `_normalize_legacy_fill`, no Python in `src/`
assigns `blob["schema_version"]`, but that is a statement about Python assignment only, and the
prompt template above determines an emitted version without ever performing one. (Unrelated
namespace, listed so nobody "fixes" it: `diversity/panel.py` and
`scripts/capture_stage0_baseline.py` each carry their own integer `schema_version` for
diversity-panel and safety-baseline artifacts. Neither is the Storybook schema.)

So decision 2's "It stamps newly-published blobs with the current version" and decision 3's
converse ("A story only carries a new field if it was published... at the minor that defines it")
are both unenforced today; they hold only because no minor beyond `0` has ever existed. The
concrete open question for the next minor bump: after `SCHEMA_MINOR = 1`, what stamps a document
`2.1`, given 61 skeletons hardcode `"2.0"`, the Stage-A prompt pins nothing, and nothing in `src/`
rewrites the field? Recorded rather than fixed here, since fixing every producer was out of scope
for this branch; see `UW-A45` in `unscheduled-work-register.md`.

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

## Follow-on work

Per the [ADR follow-on rule](./README.md), every consequent item cites a phase, a `UW-*` row, or an
issue. This ADR was accepted 2026-08-01, after the 2026-07-28 cutoff, so the rule applies to it.

| Item | Home |
| --- | --- |
| Enforce decision 2's stamping clause and decision 3's converse. Per the owner ruling of 2026-08-06 this ships as a validator rule ("a document's declared minor must cover the fields it actually uses"), not a publish-path stamper, and lands alongside the first `SCHEMA_MINOR` bump to `1`. Includes pinning a value in the Stage-A prompt (`generation/templates/structure.md`), the one producer that pins none. | `UW-A45`, Phase 5 |
| Reconcile `import_catalog._needs_legacy_normalization` with `_check_schema_version` so the two acceptance rules cannot disagree, and keep them documented as deliberately separate questions. | `UW-C34` / `AL-101`, delivered by PR [#636](https://github.com/ByronWilliamsCPA/cyo-adventure/pull/636) |

Two clauses of this ADR create no schedulable item, and are recorded here so their absence from the
table is a stated conclusion rather than an oversight:

- **Decision 4 (corpus gating)** and **decision 5 (rolling-deploy sequencing)** are preconditions on
  each future minor bump, not standalone work. There is nothing to schedule until a minor is
  actually proposed, at which point both become acceptance criteria of that minor's own change.
  They are restated in "Consequences" as the standing per-minor discipline.

## Related

- [ADR-001](./adr-001-story-format-json-storybook.md) chose the JSON Storybook format and recorded
  "exactly one accepted version" as technical debt. This ADR supersedes that clause; ADR-001's
  Technical Debt section is annotated accordingly.
- [ADR-027](./adr-027-in-story-illustration.md) is one of the additions this ADR unblocks, and
  shares the "design record written in the present tense" disclaimer in the status block above.
