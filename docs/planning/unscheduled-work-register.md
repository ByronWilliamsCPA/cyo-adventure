---
schema_type: planning
title: "Unscheduled Work Register"
description: "Every piece of directed work found in ADRs, handoff docs, design specs, review reports,
  registers, code comments, and GitHub issues that had no phase home in PROJECT-PLAN.md or roadmap.md
  as of the 2026-07-28 sweep, each given a stable UW-* ID and a proposed phase."
tags:
  - planning
  - scope
  - technical-debt
status: active
owner: core-maintainer
authors:
  - name: "Byron Williams"
purpose: "Give every directed-but-unscheduled item a durable ID and a phase home, so work that was
  decided somewhere in the document tree cannot be lost between plan refreshes. This register is the
  placeholder mechanism referenced by the 2026-07-28 plan audit in roadmap.md and PROJECT-PLAN.md."
component: Strategy
source: "Six-agent documentation and code sweep, 2026-07-28 (ADRs, handoff/remediation docs, workstream
  design docs, code markers, GitHub issues + registers, architecture/misc docs)"
---

# Unscheduled Work Register

> **Status**: Active | **Version**: 1.0 | **Created**: 2026-07-28
>
> Companion to the [capability register](./capability-register.md) (what the product must do) and the
> [R1 deferred-debt register](./r1-deferred-debt-register.md) (what R1 knowingly deferred). This
> register holds the third category: work that was **directed in some document but never scheduled
> anywhere**.

## Why this register exists

The 2026-07-28 sweep found a structural gap rather than an oversight. This project maintains four
independent ID namespaces:

| Namespace | Lives in | Mapped into roadmap phases? |
|-----------|----------|------------------------------|
| `K*` / `G*` / `A*` / `S*` | [capability-register.md](./capability-register.md) | 🟡 Mostly, via roadmap.md's "Where every open register item lands" table. Written here as ✅ on 2026-07-28; the linkage check then proved 11 open capabilities (K1, K9, K10, K11, K20, G14, G18, A2, A3, A16, S8) appeared in no row of it. They are now mapped, as unratified proposals |
| `C*` / `GS*` / `U*` / `T*` / `P*` / `SL*` | [r1-deferred-debt-register.md](./r1-deferred-debt-register.md) | ❌ No: zero debt IDs are cited in either master document |
| `AL-*` | [authoring-lessons-log.md](./authoring-lessons-log.md) | ❌ No: zero `AL-` hits in either master document |
| GitHub issues | the tracker | ❌ Partially: 19 of 33 open issues appear in no planning document |

Only the first namespace has phase linkage. This register closes that gap by assigning a phase to
every unmapped item, and by giving items that had no ID at all (ADR follow-ons, design-doc open
questions, code-level deferrals) their first stable identifier.

## How to use it

- **Adding work**: if you defer something, add a `UW-*` row here in the same change, or cite an
  existing register ID. A deferral with no ID and no row is how items got lost before.
- **Doing work**: move the row's Status to `done` and cite the PR. Do not delete rows; the audit
  trail is the point.
- **Dedup discipline**: several docs describe the same findings under different ID schemes. Where a
  row says "canonical", that is the ID to use; the alternatives are cross-referenced, not duplicated.
- **Phase column**: proposed home, not a commitment. `blocked` and `decision` are real states, not
  a scheduling failure; recording that something cannot be scheduled yet is the point.

**Status values**: `unscheduled` (needs a phase commitment) | `blocked` (a named prerequisite is
open) | `decision` (waits on an owner ruling) | `verify` (may already be done; confirm then close) |
`done` (closed, with a PR reference).

---

## The linkage contract

This section is the enforced contract, not advice. `scripts/check_work_linkage.py` reads it as the
specification and fails the build on a violation. Changing the rules means changing that script and
its tests, deliberately, in the same change.

### The invariant

Every row in every register must resolve to exactly one **disposition**:

| Disposition | Means | Required evidence |
|-------------|-------|-------------------|
| scheduled | has a home in the plan | `Phase` holds a value from the vocabulary below |
| `blocked` | cannot be scheduled yet | the row names the open prerequisite |
| `decision` | waits on a human ruling | the row names the owner who must rule |
| `verify` | may already be done | the row names what to check |
| `done` | closed | the row cites a PR, commit, or issue |

A row with a status but no evidence, or with a `Phase` value outside the vocabulary, is an
**orphan**. Orphan count is the health metric for this whole system: it goes to zero and a check
keeps it there. Everything else here is plumbing in service of that one number.

This generalizes the rule `scripts/check_lessons_log.py` already enforces on the lessons log: a
status asserts something happened, so it must cite what proves it.

### Phase vocabulary (closed set)

| Group | Allowed values | Source of truth |
|-------|----------------|-----------------|
| Product phases | `0` `1` `2` `2b` `3` `4a` `4b` `4c` `4d` `5` | `roadmap.md` `## Phase` headings |
| Track 2 phases | `6` `7` `8` `9` | `PROJECT-PLAN.md` Track 2 |
| Milestones | `M0`..`M7`, and dotted sub-milestones such as `M4.1` | `roadmap.md` Milestones |
| Release rungs | `R1` `R2` `R3` | `roadmap.md` release ladder |
| Named workstreams | `content` | `roadmap.md` Content workstream |
| Queue | `now` | `roadmap.md` Now queue |

### Non-phase dispositions (closed set)

Not every piece of directed work belongs to a product phase. These sentinels are legitimate, and
being a closed set is what stops them becoming a junk drawer:

| Sentinel | For |
|----------|-----|
| `CI hygiene` | repo tooling and gates; no product phase |
| `doc` | a documentation correction with no code change |
| `recurring` | an ongoing practice, not a one-time deliverable |
| `post-launch` | deliberately deferred past R3 |
| `external:<repo>` | owned by another repository, for example `external:homelab-infra` |
| `issue:<number>` | a live defect tracked in the issue tracker rather than the phase plan, for example `issue:460` |

### Not allowed

- A cross-reference in the `Phase` column (`see G`, `see H`). Point at a real phase, or set the
  status to `blocked` and name the blocker. "See another cluster" is not a disposition.
- An empty `Phase` on a row whose status is `unscheduled`.
- The same ID in two namespaces.
- More than one value in the `Phase` column. Work that spans phases takes the **earliest** phase,
  where it starts, and says so in the Item text. A comma-list hides which phase owns the commitment,
  which is the failure this register exists to prevent.
- The `Phase` column repeating the `Status` value. `decision` and `blocked` are statuses; a row in
  either state still needs the phase it will land in once resolved.

### How the other three registers link in

They keep their own schemas, because they track different things and flattening them would lose
information. This register is the **join table** that gives their rows a phase:

| Register | Linkage obligation |
|----------|--------------------|
| [capability-register.md](./capability-register.md) | a row not marked ✅ must appear in `roadmap.md`'s "Where every open register item lands" mapping |
| [r1-deferred-debt-register.md](./r1-deferred-debt-register.md) | a row not marked `[Closed]` or `[Resolved]` must be cited by a `UW-B*` row here. That register uses both markers interchangeably (3 and 7 rows respectively as of 2026-07-28); the validator honours both, because treating `[Resolved]` rows as open would report closed work as a gap and train readers to ignore the check |
| [authoring-lessons-log.md](./authoring-lessons-log.md) | a lesson whose status is not `applied`, `rejected`, or `superseded` must be cited by a `UW-C*` row here |

That is why clusters B and C exist. They are not commentary; they are the linkage layer, and the
validator treats a missing entry there as a build failure.

### Validate

```bash
uv run python scripts/check_work_linkage.py
```

---

## Cluster A: ADR follow-ons

Decisions that were accepted or proposed, whose consequent work was never scheduled. Sourced from
`docs/planning/adr/`.

| ID | Item | ADR | Phase | Status |
|----|------|-----|-------|--------|
| UW-A01 | **Tiered RLS scoping in its entirety**: Tier-1 scoped policies, `set_config` per request, the spike, and the integration suite run as `cyo_api`. Zero references in any planning document. | 022 | 5 | unscheduled |
| UW-A02 | Demote any Tier-1 table lacking a flat `family_id`; author the denormalization migration | 022 | 5 | unscheduled |
| UW-A03 | **Production cutover** (issue #559): retire `postgres`-role traffic. **Closed 2026-08-04, verified live against production** (`cvrnaydpzijtszfbsraq`): `pg_authid` shows `cyo_api`/`cyo_worker` both `LOGIN`, password set, `rolbypassrls=f`; `pg_stat_activity` shows 5 active app connections as `cyo_api` and **zero** as `postgres`, so the switch is observed in traffic, not just provisioned. Sequenced safely: PR #560 (`eb96f687`, sets Tier 1 RLS context before the device-grant lookup) was merged and re-verified green on `e2e-staging.yml` (multiple 2026-08-03 runs) before the homelab team rotated the production passwords, so the cutover did not reproduce the device-grant 401 that first surfaced on staging. One leg unconfirmed by direct observation: `cyo_worker` has login+password provisioned but showed 0 active connections in this snapshot (workers connect on demand, not continuously); recommend confirming with a real generation job. The ADR names M4.1 as its review gate; M4.1 carries no ADR-021 content. | 021 | M4.1 | done |
| UW-A04 | `worker_database_url` + `get_worker_session()` + the three worker entrypoints. Delivered in `c393baba` (PR #334): `core/config.py` `worker_database_url`, `core/database.py::get_worker_session`, pinned against regression by `tests/unit/test_worker.py:1045`. | 021 | 5 | done |
| UW-A05 | `worker` service in docker-compose; uncomment the dev Redis leg. Delivered in `d4afda05` (PR #333): the `worker:` service in `docker-compose.yml`. | 021 | 5 | done |
| UW-A06 | Stale-`GenerationJob` observability check | 021 | 5 | unscheduled |
| UW-A07 | Per-role privilege tightening (19 tables deferred at migration time, `20260720170000_create_service_roles.sql:26`) | 021 | 5 | unscheduled |
| UW-A08 | **Personalization feature in its entirety**: slot kind, sentinel preservation, post-fill integrity check, toggles, consent events, values payload, client resolver, kid indicator. The ADR states nothing in it exists in code today. | 023 | 4b | blocked |
| UW-A09 | `display_name` is under-validated for render use; re-check at set-time and render-time | 023 | 4b | unscheduled |
| UW-A10 | Per-skeleton pronoun audit across the catalog | 023 | 4b | unscheduled |
| UW-A11 | **Bounded one-hop backtracking**: the accepted rules plus the `runtime-semantics.md` §6 rewrite to v1.2. Zero references in any planning document. | 024 | 4b | unscheduled |
| UW-A12 | Forward-binding constraint: any future enable of continuation backtracking must land the replay origin as **server-validated** state | 024 | 4b | unscheduled |
| UW-A13 | "Read again" on a continuation resets to `start_node` and discards carried variables. The ADR defers this "as its own defect". Canonical duplicate of debt `SL10` and diversity `B4`; tracked as UW-L01 / [#460](https://github.com/ByronWilliamsCPA/cyo-adventure/issues/460). | 024 | issue:460 | unscheduled |
| UW-A14 | **#CRITICAL**: decide and enforce whether the direct-Anthropic leg is production-selectable. PROJECT-PLAN still describes the adapter as "deferred" while the ADR says it is built and admin-selectable. | 003 | 5 | decision |
| UW-A15 | Processor rows for Modal / Bedrock / Azure / Vertex before enabling them. P7-12 gates App Store submission on a complete processor record; three counterparties are missing. | 003, 018 | 7 | unscheduled |
| UW-A16 | BYOK versus live ZDR toggle test; confirm Anthropic commercial terms | 003 | 7 | unscheduled |
| UW-A17 | Trial OpenRouter prompt-injection detection (currently off) | 003 | 5 | unscheduled |
| UW-A18 | Review rule: adding `plugins` or `tools` to `openrouter.py` voids the ZDR carve-out. No review checklist exists to hold this. | 003 | 5 | unscheduled |
| UW-A19 | Ring-2 granularity divergence from B6 awaits counsel (2026-07-26 amendment) | 016 | 7 | decision |
| UW-A20 | Verify connection and recommendation payloads are in the erasure set | 016 | 4d | verify |
| UW-A21 | Enable and verify `X25519MLKEM768` on Pangolin / nginx | 013 | 5 | unscheduled |
| UW-A22 | Header-size capacity test for ML-DSA tokens (gates the signature migration) | 013 | 5 | unscheduled |
| UW-A23 | **Quarterly gate review** of the deferred signature migration. The ADR says tracking is "operator discipline, not automation"; no recurring-ops list exists to hold it. | 013 | recurring | unscheduled |
| UW-A24 | Maintain `docs/security/crypto-inventory.md` | 013 | recurring | unscheduled |
| UW-A25 | Read-time upcaster chain plus a golden fixture per schema version. Conditional: trigger is the second live schema version. | 001 | post-launch | unscheduled |
| UW-A26 | Re-verify PWA behavior on each iOS Safari major release | 002 | recurring | unscheduled |
| UW-A27 | Reconcile nginx versus Pangolin-direct ingress into one documented topology | 004 | 5 | unscheduled |
| UW-A28 | AdultGate OAuth-bypass passes an adult with no re-auth challenge. Server-side approval freshness is deferred and "needs its own attestation design" (CHANGELOG). | 014 | 5 | unscheduled |
| UW-A29 | Migrate the catalog to parameterized skeletons: 14 of 61 skeletons and 4,305 `<<FILL>>` nodes still contract-less. Canonical for handoff "A20" and the parameterize-at-promotion runbook. | 019 | content | unscheduled |
| UW-A30 | Standing obligation: contracts must be **maintained**, with per-wave human quality review | 019 | recurring | unscheduled |
| UW-A31 | Slot-value "packs" deferred to a later increment | 019 | post-launch | unscheduled |
| UW-A32 | WS-6 fresh-generation feed inherits the promotion bar (unbuilt) | 020 | content | unscheduled |
| UW-A33 | Cross-cell derivation as a future amendment, with evidence | 020 | post-launch | unscheduled |
| UW-A34 | Judge-model tree-pair distinctness revisit (floor gaming) | 020 | post-launch | unscheduled |
| UW-A35 | In-app admin promotion surface, deferred to WS-8 | 020 | content | unscheduled |
| UW-A36 | Catalog bloat flattens selection weights; contract-maintenance surface grows with the catalog | 020 | content | unscheduled |
| UW-A37 | Consolidate cover storage into Supabase Storage if blobs externalize (conditional on UW-A38) | 017 | 9 | unscheduled |
| UW-A38 | `blob_ref` object-storage externalization, and the MinIO leg. Named in PROJECT-PLAN prose only; absent from the roadmap Phase 5 checklist. | 001, 004 | 9 | unscheduled |
| UW-A39 | ADR-018 Blocker 1 narrowed to the classifier leg, not closed | 018 | 7 | unscheduled |
| UW-A40 | **Doc hygiene**: ADR-007 is still `proposed` though its purge shipped 2026-07-17; ADR-021 is still `proposed` though its implementation shipped in PR #333 and PR #334 (PR #323 was docs-only and did not flip the status itself). Flip both. | 007, 021 | now | done |
| UW-A41 | **Doc hygiene**: PROJECT-PLAN.md section 3's ADR table and the ADR status list omit ADR-020 through ADR-024. Corrected by the 2026-07-28 audit in commit `bcfc9ab`; keep them in sync going forward. | all | now | done |
| UW-A42 | **Doc hygiene**: backfill a **Follow-on work** section into all 24 ADRs that predate the [`adr/README.md`](./adr/README.md#follow-on-work-is-part-of-the-adr-required-for-new-and-amended-adrs) rule requiring one, so the register can be reconciled against ADR-declared consequences rather than only against this cluster's own manual sourcing. | all | post-launch | unscheduled |
| UW-A43 | **Bind a child session to its minting device grant.** Revoking a device grant stops the DEVICE token but not a child session already minted from it: `api/deps.py::_child_principal` does no database round-trip and the token carries no grant reference, so a child keeps reading online for the rest of `child_session_ttl_seconds` (12 hours). Fix: carry the grant `jti` in the child-session claims and check it on the read path, accepting a database read there. Disclosed in ADR-014 "Negative / risks"; current behavior pinned by `tests/integration/test_child_sessions.py::test_known_limitation_revoked_device_grant_does_not_invalidate_minted_child_session`. | 014 | 5 | unscheduled |

## Cluster B: debt-register phase linkage

The [R1 deferred-debt register](./r1-deferred-debt-register.md) is accurate but orphaned: not one of
its IDs is cited in either master document. Rather than restate 35 rows, this cluster assigns phases
to the register wholesale. **The debt register remains the source of truth for item detail.**

| ID | Item | Phase | Status |
|----|------|-------|--------|
| UW-B01 | `C1`, `C3`, `C4`, `C5` (offline replay loss, retry cap bypass, untested approval lock, `choice_path` replay). `C5` is canonical for security-plan `L1` and lesson `AL-023`. | 5 | unscheduled |
| UW-B02 | `GS1` Tier-2 generation yield weak at 3/7 | 2b | unscheduled |
| UW-B03 | `GS3` Perspective sunsets 2026-12-31 with no date gate; 18 of 29 versions mock-moderated. Hard external deadline. | 5 | unscheduled |
| UW-B04 | `U2`, `U3`, `U4`, `U6`, `U9b` guardian-console UX debt | 4b | unscheduled |
| UW-B05 | `U5` no guardian reading tracker: superseded by G9's shipped `ReadingPage.tsx`. Verified 2026-07-29: `GET /families/me/reading-summary` (`api/reading_history.py`) and `frontend/src/guardian/ReadingPage.tsx` shipped 2026-07-17 in PR #270; capability G9 records it delivered. | 4b | done |
| UW-B06 | `U7` threshold-change audit feed cannot show who changed it | 5 | unscheduled |
| UW-B07 | `U9` push channel (delivery is poll-only). The S9/G10 gap is named in prose but has no phase. | 4c | unscheduled |
| UW-B08 | `T1`, `T4`, `T5`, `T6` test-ladder hygiene | 5 | unscheduled |
| UW-B09 | `T3` kid RequestStory error-clear only implicitly tested. Verified 2026-07-29 done: explicit `T3` regression tests at `frontend/src/library/RequestStory.test.tsx:411` and `:433`; debt register's own `U1` row already notes it was pinned by a T3 regression test. | 4b | done |
| UW-B10 | `T8` no Renovate rule pinning esbuild to Vite's range | CI hygiene | unscheduled |
| UW-B11 | `T9` whole-repo markdownlint debt. Canonical with issue #248. | CI hygiene | unscheduled |
| UW-B12 | `P1` app-wide rate-limit **policy** never decided (P9-05 covers the deliverable, not the ruling) | 9 | decision |
| UW-B13 | `P2` `get_generation_job` returns raw report to guardians, against ADR-007. Canonical with issues #72 and #88, and traceability §3.1. | 7 | decision |
| UW-B14 | `P3` `useApi` does not redirect on 401 (decide alongside `P1`) | 4b | unscheduled |
| UW-B15 | `P4` skeleton-scale deferrals. Canonical with issues #77, #78, #79. | 2b | unscheduled |
| UW-B16 | `SL1` through `SL10`, the ten story-lifecycle deferrals. The register calls them "R2-planning inputs"; R2/M6 has no line for any of them. `SL10` is canonical for the continuation carried-state defect (UW-L01, [#460](https://github.com/ByronWilliamsCPA/cyo-adventure/issues/460)). | 6 | unscheduled |
| UW-B17 | `GS2` the adversarial safety gate's "flag and route to human review" claim is unverified for the model-dependent classes: no live-model adversarial run has been executed. **Re-triaged 2026-07-29: the "blocked on credential availability" reason is stale.** `.env` in this environment holds non-placeholder OpenRouter/OpenAI/Anthropic/Gemini keys (verified by prefix/length, not by value). The real blocker is that running the live adversarial suite spends real money against those keys, an owner-authorized action, not a missing-credential block. The roadmap already schedules an "adversarial live-model run" at Phase 5 but cites no register ID, which is why the debt row read as uncited. | 5 | decision |
| UW-B18 | `T7` the real smoke tier is local-only because the per-IP rate limiter trips above one worker. The debt row calls this "not a defect" and says to revisit "if a staging environment appears". One has: `.github/workflows/e2e-staging.yml`. Re-test the multi-worker assumption against staging and close or re-scope the row. | CI hygiene | verify |

## Cluster C: authoring-lessons phase linkage

The [authoring lessons log](./authoring-lessons-log.md) is mandated by CLAUDE.md and has 24 open
lessons, none referenced by either master document. Its only plan linkage is one sentence inside
capability-register row `A11`, which the roadmap files under "Post-launch backlog". That is the wrong
home for at least two blocking items.

**`AL-*` is the canonical namespace** for the authoring, ceiling-scale-review, and series-stress-test
findings; `reviews/ceiling-scale-review-2026-07-25.md` and `series-stress-test-findings.md` describe
substantially the same work under different headings. Do not triple-book.

| ID | Item | Phase | Status |
|----|------|-------|--------|
| UW-C01 | **`AL-014` blocking**: no hand-authored skeleton could pass `check_promotion_bundle`, because the lineage sidecar was unconditional. **Partially closed 2026-08-01** (PR #532, commit `4b6fe922`): `prove_shell` now runs `check_skeleton` (gate/cell/envelope) and `check_theme_contract` for a lineage-less shell and skips only the two parent-relative legs, logging that it did; the `skeleton-promotion.yml` filter that had been dropping such shells out of the prover's argv entirely is gone. **Still open**: `AL-014`'s proposal also asked for an origin sidecar and for the WS-5 anti-clone floor to still apply to a hand-authored original. The floor is parent-relative and cannot run without a lineage parent, so proving an original against its in-cell siblings (the `UW-C06` `check_incell_clones` path) is the remaining work. | now | unscheduled |
| UW-C02 | **`AL-036` blocking**: the review surface cannot deliver the human approval ADR-005 requires at 746 nodes (no pagination, virtualization, or per-node state). This undercuts the `A6` safety gate, so ADR-005 attests less than it claims. | 5 | unscheduled |
| UW-C03 | `AL-034` one import is ~2,986 provider round trips in a single Postgres transaction holding `FOR UPDATE`, 40 to 100 minutes. Bound concurrency; split import out of the long transaction. | 5 | unscheduled |
| UW-C04 | `AL-039` repair and the Stage-1 fidelity gate are structurally impossible at scale and both fail open; fidelity lacks an `<untrusted_passage>` fence (`#CRITICAL: security`) | 5 | unscheduled |
| UW-C05 | `AL-040` `/admin/rescreen` sweeps synchronously in one request; enqueue on RQ or require scoped IDs | 5 | unscheduled |
| UW-C06 | `AL-044` in-cell duplication check on changed `skeletons/**` shells; book 2 fails `check_incell_clones` at 0.0139 against a 0.05 floor | content | decision |
| UW-C07 | `AL-046` fill orchestrator is one-shot against a 32k output cap and the matcher has no feasibility predicate; 13 books are unfillable today | content | unscheduled |
| UW-C08 | `AL-013`, `AL-024`, `AL-027`, `AL-044` validator and tooling accuracy work | post-launch | unscheduled |
| UW-C09 | `AL-028`, `AL-029`, `AL-030`, `AL-032` reader-surface defects (endings denominator inverts at large M, corpus-relative progress bar, 300ms+ BACK freeze, reconnect teleport) | 4b | unscheduled |
| UW-C10 | `AL-019`, `AL-020` reader-path retention and de-identified engagement rollup. Four owner decisions precede any table. | post-launch | decision |
| UW-C11 | `AL-022` add `estimated_minutes_whole_world`, surface both clocks | 4b | decision |
| UW-C12 | `AL-037` `embed_series_block` silently rewrites authored series metadata | content | unscheduled |
| UW-C13 | `AL-049` flywheel parent-selection headroom skip plus an operator config budget | content | unscheduled |
| UW-C14 | `AL-050` migrate 3 legacy fills to schema v2 and delete `_LEGACY_PRE_V2`. Paired with the strict-xfail at `tests/unit/test_filled_story_corpus.py:63`, which carries the instruction in code. | content | unscheduled |
| UW-C15 | `AL-052` triage 13 read-time drifts and 6 ending-mix outliers | content | unscheduled |
| UW-C16 | `AL-056` `--preflight` mode for paid-provider instruments | CI hygiene | unscheduled |
| UW-C17 | `AL-031` and `AL-038` are marked `applied` but each carries an explicitly open half (listing-path denormalization; read-time carry audit plus gating the continuation offer on a satisfying ending). Split into new IDs per the log's own status discipline. | now | unscheduled |
| UW-C18 | `AL-011` document that L2-13 past 460 nodes is correct, so it is not "fixed" later | doc | unscheduled |
| UW-C19 | `AL-023` the shipped client never sends `choice_path`, so the server-side engine replay that exists to reject a forged `current_node`/`var_state`/`path` is dormant (`api/reading.py` carries the `#ASSUME` admitting it). Any analytics derived from the client-supplied `path` inherits the same trust problem. | 5 | unscheduled |
| UW-C20 | `AL-068` `CLOSED_VOCABULARIES` drift guard: a test that fails when a slot type exists in the personalization taxonomy with neither a vocabulary entry nor an explicit free-text exemption, mirroring how the DB CHECK lists are pinned to `PERSONALIZATION_FIELDS`. The immediate instance (`dedication` accepting free text) was fixed fail-closed in Stage C commit `f03c7fdc`. Shipped 2026-07-30 (ADR-023 Task D6, branch `feat/personalization-d6-closed-vocabularies`) in commit `bee0c678`: `tests/unit/test_personalization_vocab_drift.py` gained `test_every_personalization_field_has_a_vocabulary_or_an_exemption`, `test_closed_vocabularies_keys_are_a_subset_of_personalization_fields`, `test_every_closed_vocabulary_is_non_empty`, and `test_exempt_fields_carry_no_vocabulary_entry`. | 5 | done |
| UW-C21 | `AL-072` pre-push or CI check that a branch's new Supabase migration timestamp prefix is strictly greater than the newest prefix on `origin/main`, so a same-day collision between two concurrent branches (D6's `20260730000000_` colliding with PR #494's migration of the same prefix) fails before merge rather than after. | CI hygiene | unscheduled |
| UW-C22 | `AL-073` resolve `OLLAMA_CA_BUNDLE` and sibling file-path settings repo-root-relative in `core/config.py` (or build the `--preflight` mode `AL-056` already proposed), so a script run from a git worktree does not fail on a cwd-relative CA-bundle path. Second occurrence of the same defect `UW-C16` already tracks; recorded separately per the linkage contract because it is a distinct lesson row, but the fix is the same work item. | CI hygiene | unscheduled |
| UW-C23 | ADR-011 section 10's flowed-band choiceless rule ("1, prefer 0" at 8-11, "0-1" above) counts STOPS and is unimplemented. `validator/choice_grammar.py`'s CG-1 caps consecutive single-choice NODES at 6 for those bands, which is a derived words-per-stop backstop, not the ADR rule, and its `#ASSUME` now says so. Implementing the real rule needs stop-level adjacency (ADR-026 `compose_stop` boundaries), which nothing in the validator computes today. Surfaced by the PR #532 review (I8). | 4b | unscheduled |
| UW-C24 | Every `CG-1`..`CG-4` choice-grammar rule is inert in production: `validator/gate.py::run_gate` defaults `enforce_grammar=False` and no production caller passes `True` (only `tests/unit/test_choice_grammar.py` does). The D3/D11 grandfathering rationale is sound, but the flip condition was recorded nowhere. It is now stated in the module docstring: the flag flips when the D11 `deprecated` per-skeleton marker lands (W2.4), at which point the gate can enforce for unmarked (new) skeletons and skip marked ones, and the default can become `True`. Until then the rules produce no finding on any real story. Surfaced by the PR #532 review (I9). | 4b | decision |
| UW-C25 | `AL-079` fold the verified JHM 2019 citation (Adams, Beckelhymer and Marr 2019, DOI 10.5642/jhummath.201902.05), the derived-vs-stated label on the decisions-per-playthrough constant, and the designer-prior labels on words/node and total-words into the `UW-G17` ADR-011 amendment; the rebuilt research base itself is committed at `docs/planning/research/` (2026-08-02). | doc | unscheduled |

## Cluster D: untracked GitHub issues

roadmap.md lines 197-199 assert that open issues "remain accurately tracked" in the debt register.
That claim is false: the debt register cites 9 issue numbers, 6 still open, against 48 open issues
as of 2026-08-03. The 34 issues below appear in no other planning document by number or by
description, so this cluster is their only phase home.

Adding a row here is now a judgement call rather than a gate. `scripts/check_work_linkage.py`
once carried a `--check-issue-orphans` flag requiring every open GitHub issue to be cited under
`docs/planning/` or labelled `unplanned`, plus a `--check-issues` flag resolving each cited
number against the API. Both were retired: they ran only in CI, because they needed network
access and `gh` auth that the pre-commit hook deliberately does not have, so the two gates
enforced different contracts and a green local run proved nothing about the stricter one. The
recurring cost also outgrew the return, most visibly when the workflow's own drift-alert issue
became an uncited open issue and failed the gate that filed it. What remains is the offline
linkage contract, which every row in this table is still bound by.

| ID | Issues | Theme | Phase | Status |
|----|--------|-------|-------|--------|
| UW-D01 | #249, #250, #251, #253, #254 | Device-auth and principal hardening (existence oracle, type invariants, token audiences, double-revoke, shared secret helper) | 5 | unscheduled |
| UW-D02 | #252 | `expires_at` on `device_grant` so active-devices excludes ghosts | 4b | unscheduled |
| UW-D03 | #255 | Device-auth doc-diagram refresh and test hygiene | CI hygiene | unscheduled |
| UW-D04 | #137 | All error conditions render one generic retryable error (naive-UX F1) | 4b | unscheduled |
| UW-D05 | #144 | Stage-0 classifiers handle NaN and Infinity asymmetrically | 5 | unscheduled |
| UW-D06 | #347 | Catalog import: pre-upload quality gating and `verdict_parse_failed` under mock | 5 | unscheduled |
| UW-D07 | #63 | `storybook_version` lacks a provider column, so provenance is unrecoverable | 5 | unscheduled |
| UW-D08 | #138 | Pin the homelab backend-net subnet, narrow `FORWARDED_ALLOW_IPS` | 9 | unscheduled |
| UW-D09 | #302, #383, #382, #364, #248 | CI and release hygiene (mutation run failing, Codecov carryforward race, `cast()` narrowing, release re-verification, markdownlint debt) | CI hygiene | unscheduled |
| UW-D10 | #67 | coverage.py zero hits for async handlers under CPython 3.12; probably obsolete after the 3.14 move | CI hygiene | verify |
| UW-D11 | #290 | The scheduled real-backend nightly E2E is failing. Phase 5 tracks the *capability*; the failing run is uncited. | 5 | unscheduled |
| UW-D12 | #295 | Python 3.14 residual: `target-version = "py311"`, plus rollout steps 1, 2, 5, 6, 7 from the upgrade evaluation (Renovate lockstep, 3.14 in `python-compatibility.yml`, flip `ci.yml` to required, staged homelab deploy, post-flip cleanup) | 5 | unscheduled |
| UW-D13 | #221 | A wrong or defaulted R2 bucket passes the covers-configured guard | 7 | unscheduled |
| UW-D14 | #187, #172 | Promote api-tests to a required gate; Codecov Bundle Analysis blocked on Vite 8. Named in the capability register only. | CI hygiene | unscheduled |
| UW-D15 | #453 | Family-scoped `ADMIN_ACTOR_ROLE` hardcodes audit dual-role owners as cross-family admins | 5 | unscheduled |
| UW-D16 | #74 | Guardian console "Still processing" is inert for admins. Canonical with debt `U2`. | 4b | unscheduled |
| UW-D17 | #71 | App-wide rate-limit **policy** for polling endpoints. The mechanism already exists: `middleware/security.py::RateLimitMiddleware` applies one Redis-backed per-client-IP limit across every route. Check whether polling routes (reading state, generation status, notifications) need their own tier rather than sharing the global bucket, and close the issue if the single tier is the intended policy. | 5 | verify |
| UW-D18 | #535 | 3 linux-libc-dev kernel-header CVEs in the production base image, 2 of them fixable by a base-image refresh. Also needs a `docs/known-vulnerabilities.md` entry per the unfixed-CVE rule; no entry may age past 60 days without reassessment. | 5 | unscheduled |
| UW-D19 | #505 | 7 unfixed linux-libc-dev kernel-header CVEs with no Debian trixie fix published. Blocked on an upstream trixie kernel-header release; nothing in this repo can close it. Re-triage quarterly, because the OpenSSF release gate blocks a release on any vulnerability older than 60 days regardless of reassessment status. | 5 | blocked |
| UW-D20 | #542 | Stage-1 reviewer passes prompt-injection corpus items E2/E3 at **every** batch size, so the injection gap is not a batch-tuning artifact and the PR #541 batch-size default cannot close it. From the moderation review redesign track. | 5 | unscheduled |
| UW-D21 | #552 | `renovate.json` package rules that never fire. Another silent-gate failure: a rule matching nothing is indistinguishable from a rule with nothing to match, so the config looks configured while the dependency class it names goes ungoverned. | CI hygiene | unscheduled |
| UW-D22 | #571 | `e2e-staging` is green **by retry, not clean**: the last spec's device-grant revoke fails its first attempt in every observed run and passes on `retries: 1`. The console's own banner proves the backend rejected the `DELETE`, and an identical helper call earlier in the tier passes first time, so it is position-dependent rather than a helper bug. Starts as CI hygiene because the first deliverable is diagnostic: the banner text cannot discriminate 429 from 401, 5xx, or a dropped connection, so the actual status must be captured before a cause can be named. If the 60 rpm/IP hypothesis confirms, the fix converges with UW-D17 (#71) in phase 5 and this row moves there. Green-with-retry does not close it. | CI hygiene | unscheduled |
| UW-D23 | #573 | The weekly whole-corpus link check found at least one dead link in `docs/`, `README.md`, or `CONTRIBUTING.md`. Filed by `link-check-full.yml`, which scans ~100 third-party hosts, so confirm a link is actually dead before editing: a host that refuses `HEAD` or rate-limits the runner reads identically to rot. Related to UW-D26's standing problem, and to the reason that check was split out of the PR gate in the first place (#563). | CI hygiene | unscheduled |
| UW-D24 | #574 | The weekly dependency-provenance report. It currently reports **zero** actionable transitive vulnerabilities and self-describes as a sticky marker that is updated rather than reopened, so it is a dashboard, not a defect: it stays open by design and closing it would only cause the next run to file a new one. The obligation is to read it each week and act when the count stops being zero, which is a practice rather than a deliverable. | recurring | unscheduled |
| UW-D25 | #575 | The scheduled Planning Linkage check failed and filed this alert. Its cause was the #571 orphan, which UW-D22 above resolves, so this is very likely already fixed. **To check:** dispatch or wait for a scheduled `planning-linkage.yml` run after UW-D22 merges, confirm it is green, then close the issue. Nothing closes it automatically; the workflow's own text asks a human to. | CI hygiene | verify |
| UW-D26 | (no issue) | **Standing problem, not a defect in any one run**, and the reason the three rows above exist at all. Scheduled workflows file `ci-failure` issues that are deduplicated by title but never auto-closed, and an open uncited issue is an orphan, so every bot alert fails the very gate that files it. #575 is the pure case: the linkage check filed an issue that then made the linkage check fail. The considered fixes were to label bot issues `unplanned` at filing time, to exempt `ci-failure` in `--check-issue-orphans`, or to close the issue from the workflow on a green run. **Decided instead to remove both issue-facing checks** (`--check-issues` and `--check-issue-orphans`): tying every open issue to the phase plan was a good idea that cost more than it returned, and an offline checker is also one that the pre-commit hook and CI can run identically. Removal landed in PR #576; the checker now makes no network call and the intro to this cluster records why. | CI hygiene | done |
| UW-D27 | [#558](https://github.com/ByronWilliamsCPA/cyo-adventure/issues/558) | Automated database backup and a tested restore drill. `docs/operations/runbook.md` section 6 stated plainly none existed in this repository. `scripts/backup_database.py` + `.github/workflows/supabase-backup.yml` close the backup half (daily `supabase db dump`, AES-256-GCM encryption, tiered R2 upload with GFS lifecycle rules, and failure alerting); the restore procedure is documented but **not yet drilled** against a live project, so this stays open until that drill runs. Canonical with the roadmap's Phase 5 "backups and a tested restore" line. | 5 | unscheduled |

## Cluster E: security and safety hardening

From [security-hardening-plan-2026-07.md](./security-hardening-plan-2026-07.md). `H1` and `H2` are
already on the Phase 5 checklist; the Medium and Low tiers are not, and they include gate bypasses.

| ID | Item | Phase | Status |
|----|------|-------|--------|
| UW-E01 | `M1` reading and completion routes bypass the assignment gate. Closed 2026-07-29: `api/reading.py`'s `get_reading_state`/`put_reading_state`/`record_completion` now gate on a `_require_assignment` check for non-admin callers, plus a `_require_current_published_approved` check on the create path (commit `72175c8`, branch `fix/child-safety-band-and-read-gate`) | 5 | done |
| UW-E02 | `M2` guardian blob-fetch skips the gate. Closed 2026-07-29: `api/library.py`'s `get_storybook_version` now gates on assignment for all non-admin callers, not just `role == CHILD` (commit `72175c8`, branch `fix/child-safety-band-and-read-gate`) | 5 | done |
| UW-E03 | `M3` repair skips the validator. Verified 2026-07-29 stale: `moderation/repair.py:7-12` documents that `moderation/pipeline.py` schema-validates and re-runs `validator.gate.run_gate` on repaired output before it may replace the pre-repair blob, matching capability S4's 2026-07-16 ruling. Distinct from `UW-C04` (`AL-039` fidelity-gate fence gap), which still stands. | 5 | done |
| UW-E04 | `M4` review-model allowlist | 5 | unscheduled |
| UW-E05 | `M5` real PII detector | 5 | unscheduled |
| UW-E06 | `M7` family cost cap on the authoring-plan path | 5 | unscheduled |
| UW-E07 | `M8` production Postgres host port exposure and password default | 5 | unscheduled |
| UW-E08 | `L3` `allowed_content_flags` is inert; `L4` `reading_level_cap` is unenforced; `L5` health-endpoint version disclosure | 5 | unscheduled |
| UW-E09 | `H4` mock-reviewer fail-fast. Canonical with debt `GS3`. | 5 | unscheduled |
| UW-E10 | `R-1` homoglyph folding and `R-2` OIDC clock skew, both open decisions | 5 | decision |
| UW-E11 | `G11` moderation fail-open. Covered by the roadmap's umbrella "moderation review-model redesign" line, but a fail-open safety path deserves its own row. | 5 | unscheduled |
| UW-E12 | Class-C aggregate-harm: no whole-story or per-path safety pass exists | 5 | unscheduled |
| UW-E13 | Confine production generation to the guarded route; the direct-Anthropic leg bypasses it. Related to UW-A14. | 5 | unscheduled |
| UW-E14 | Privacy-model **Blocker 1b** remains open: Stage-0 classifier and LLM-review retention terms unconfirmed | 7 | blocked |
| UW-E15 | **Doc hygiene**: the security plan still marks `H3` (ADR-007 purge) "needs re-triage" while the roadmap marks it delivered | now | unscheduled |
| UW-E16 | `_extract_subject()` dev/test auth stub is still live in `api/deps.py:234`, guarded only by unset OIDC env vars | 5 | unscheduled |

## Cluster F: test and quality hardening

From [testing-review-2026-07-22.md](./testing-review-2026-07-22.md),
[test-coverage-audit-2026-07-09.md](./test-coverage-audit-2026-07-09.md), and
[test-traceability-matrix.md](./test-traceability-matrix.md). Phase 5's generic "test ladder" line
needs to become these named actions.

| ID | Item | Phase | Status |
|----|------|-------|--------|
| UW-F01 | `C1` no behavioral safety evaluation: mocks only, a 13-item corpus, zero `llm_eval` tests in CI. Debt `GS2` tracks the live adversarial *run*, not the *suite*. | 5 | unscheduled |
| UW-F02 | `H1` foreign-key `ON DELETE` parity gap; the migration header falsely claims coverage | 5 | unscheduled |
| UW-F03 | `H2` frontend hand-mirrored adapters bypass the generated client, with no OpenAPI-pinned test | 5 | unscheduled |
| UW-F04 | `H3` mutmut enforces no kill-floor on PRs | CI hygiene | unscheduled |
| UW-F05 | `H4` zero performance and load testing before Phase 9; perf markers are dead. Phase 5's "performance pass" needs teeth. | 5 | unscheduled |
| UW-F06 | `M1` full-stack E2E never drives the RQ worker | 5 | unscheduled |
| UW-F07 | `M2` schema parity omits policies, triggers, and functions | 5 | unscheduled |
| UW-F08 | `M3` player-parity corpus is 3 traces | 5 | unscheduled |
| UW-F09 | `M4` interrogate and pydoclint never run in CI | CI hygiene | unscheduled |
| UW-F10 | `M5` coverage-combine verified on a subset only | CI hygiene | unscheduled |
| UW-F11 | `M6` no rate-limit or CORS negative tests | 5 | unscheduled |
| UW-F12 | `L1` through `L6` (node_edit integration, a dead `or True` assertion, SimpleNamespace casts, index-predicate parity, 70 versus 80% thresholds, no `@example` seeds) | CI hygiene | unscheduled |
| UW-F13 | Coverage-audit batches A, B, C (backend floors, standards conformance, frontend Vitest). A branch `test/coverage-gap-closure` exists with no plan row. | 5 | unscheduled |
| UW-F14 | Deferred coverage work: Tier-3 LLM eval suite (needs a budget decision), MSW adoption, fakeredis plus a genai seam | 5 | decision |
| UW-F15 | Traceability matrix: extend staging past smoke to GJ2/GJ3/GJ5 (named "the single highest-value gap"), promote GJ1/GJ4 in prod to full journeys, alert on every scheduled run, close the K5 and K8/A16 shipped-but-untested rows, and normalize the 2026-07-17 addendum rows | 5 | unscheduled |
| UW-F16 | `A16` cover generation is ❌ across all four test tiers | 5 | unscheduled |
| UW-F17 | Execute [r1-live-e2e-checklist.md](./r1-live-e2e-checklist.md): all 39 manual steps are unchecked | M4.1 | unscheduled |
| UW-F18 | 15 of 17 naive-user Track B scenarios never run; only K1 and K2 are logged, both blocked by #196. Track B to A promotion never exercised. | 5 | blocked |
| UW-F19 | Weak skips that pass on a construction failure: `tests/unit/test_gate.py:469,496` and `test_notifications_registry.py:262`. Corpus-availability skips silently pass when the catalog is thin. | CI hygiene | unscheduled |
| UW-F20 | 0 of 21 skeletons proven end-to-end per [skeleton-corpus-story-generation-test-plan.md](./skeleton-corpus-story-generation-test-plan.md), plus 3 open decisions (coverage depth, triage owner, tracking location) | 5 | unscheduled |
| UW-F21 | Three `continue-on-error: true` steps in `ci.yml` (lines 268, 421, 649); `supabase-ci.yml` and `ci.yml:731` both defer promotion to `ci-gate` | CI hygiene | unscheduled |
| UW-F22 | Six symbols with no reader anywhere in the codebase, confirmed by the 2026-07-31 vulture calibration. Vulture is right that all six are unreferenced; the consequence differs per symbol, so each needs its own call between wire-it-up and delete-it. (a) `flywheel/strategy.py:81` `OPEN_PR_PER_CELL = 1` is documented as the per-cell open-PR cap, but `cadence.py:194` implements the bound as `if cell in open_pr_cells`, a set-membership test that hardcodes "at most 1". Behaviour matches the constant TODAY, so nothing is broken; changing the constant would silently do nothing. Latent trap, not a live defect. (b) `flywheel/strategy.py:105` `TEMPLATE_SET_VERSION = 1` has zero references, and `ledger.py`'s `AttemptRecord` (lines 105-158) carries no version field, so the ledger genuinely does not record the template-set version its own comment says it should. (c) `core/token_audience.py:42` `TokenAudience.GUARDIAN_OIDC = "authenticated"` is documentation of `Settings.oidc_audience`'s default rather than dead code, but `config.py:592` repeats the literal `"authenticated"` instead of referencing the member, so two copies of one value can drift with nothing asserting they agree. Fix is `default=TokenAudience.GUARDIAN_OIDC.value`. (d) `generation/authoring_metadata.py:44` `SkeletonAuthoringMetadata` is a TypedDict referenced only from a docstring cross-reference at `import_story.py:235`, never used as an annotation. (e) `scripts/check_quality_gate.py:85` `get_measures` is a dead method; the script is invoked by no nox session, workflow, or hook. (f) `story_requests/service.py:149` `profile_monthly_spend` is a public wrapper with no caller; its siblings `family_monthly_spend` and `profile_monthly_spend_by_family` both have callers, and the ADR-015 G3 envelope it wraps IS enforced at `can_auto_approve` (`service.py:343-346`) via the private `_approved_count_since`. Dead wrapper only, no control gap. **Closed 2026-07-31** on branch `fix/uw-f22-unreferenced-symbols`, one commit per symbol. (a) Constant deleted and its explanatory comment moved onto the `cell in open_pr_cells` membership test in `cadence.py::_blocking_bound`; the flywheel design does not want a tunable here, so the constant was the trap and not the bound (`ca105f78`). (b) Owner ruled retrofit: `AttemptRecord` gained a required `template_set_version` field, `to_json`/`_coerce_record` carry it, and rows written before the field read back as a frozen `_UNVERSIONED_TEMPLATE_SET = 1` (a historical fact, deliberately not an import of the live constant). No ledger migration was needed; `_coerce_record` already ignores unknown keys and defaults missing ones (`ca105f78`). (c) `config.py` now uses `default=TokenAudience.GUARDIAN_OIDC.value`; the member stays out of the distinctness validator by design (issue #251) (`6ca818d9`). (d) **The brief's characterization understated this one.** Applying the TypedDict as the annotation on the writer immediately proved it had DRIFTED from the dict it claimed to describe: the four A6/A7 differentiation keys were written by the producer but never added to the shape, and four scalars declared `str` are in fact written `str \| None`. The shape was widened to match the producer, and the divergence is recorded in the class docstring (`83b4c58a`). (e) Owner ruled delete, and the whole script went rather than just the dead method: nothing invoked it, and the org reusable `python-sonarcloud.yml` already enforces the same gate. Its Ruff per-file-ignore and two doc references went with it (`20dba651`). (f) `can_auto_approve` now calls `profile_monthly_spend` and `family_monthly_spend` instead of reaching past them to `_approved_count_since`. The brief's characterization held exactly: dead wrapper, no control gap. The resolved `now` is threaded into both calls, and `test_can_auto_approve_uses_one_instant_for_both_spend_counts` fails if either is dropped. Four stale `#VERIFY` pointers in the same module, all naming a `TestBudget` class that does not exist, were repaired in the same commit (`2755ae26`); an earlier draft of this row said five. Every hash cited above was re-pointed after the branch was rebased onto `main` (post-#518 squash-merge), which rewrote all eight; the pre-rebase hashes resolve only on `backup/uw-f22-prerebase`. Cite subjects rather than hashes in future rows, since a squash-merge will retire these too. | 5 | done |
| UW-F23 | Generate the vulture `--make-whitelist` baseline, but only AFTER UW-F22 is closed, otherwise the baseline freezes the six true positives as accepted. Regenerate at commit time: whitelist entries are line-anchored and drift on any edit above them. Residual finding count after the 2026-07-31 calibration is 77 (from 346 raw), all adjudicated false-positive or test-only. **Closed 2026-07-31** by `vulture_whitelist.py`, added on branch `fix/uw-f22-unreferenced-symbols` in the commit immediately after `9045e52f` (a self-citing hash is not available: the row is part of the commit it would name). Final count is 72 entries, not the 71 the closure order implied, and the arithmetic is 77 - 7 + 2. Only 71 of those 72 are adjudicated false positives: `forwarded_allow_ips` is a deferred TRUE positive, suppressed solely to keep the baseline at exit 0 and tagged inline in `vulture_whitelist.py` so the deferral stays greppable. It remains scheduled as UW-F25, and the ordering rule at the top of this row is therefore satisfied by the register rather than by the baseline. Two further corrections fall out of the count. First, the 77 was NOT all false-positive or test-only: it also held `config.py`'s `rate_limit_redis_cooldown_seconds`, the issue #516 symptom, so seven true positives cleared rather than six. Second, widening `SkeletonAuthoringMetadata` to match its producer (UW-F22 (d)) ADDED two findings, `differentiation_level` and `variation_axis`, because those TypedDict keys are written through the `*_KEY` constants and so the identifiers themselves appear nowhere else; the sibling keys escape only because other code happens to reuse their names as local variables. Both are structural false positives of the same kind the baseline exists to absorb. The baseline is wired in through `paths` in `[tool.vulture]`, since a whitelist that is not scanned does nothing, and `vulture_whitelist.py` is excluded from Ruff and BasedPyright because its undefined bare names are the mechanism. `uv run vulture` now exits 0, so the next finding is a signal. One trap the wiring creates, recorded in the file's own docstring: regeneration must pass `src/ scripts/` positionally (`uv run vulture src/ scripts/ --make-whitelist`), because plain `--make-whitelist` scans the whitelist alongside the source, finds nothing left to report, and writes an EMPTY file that silently un-suppresses all 72 entries. Hit once while writing this row. | CI hygiene | done |
| UW-F24 | `setup_logging()` is never called by the served application, so three settings that exist, are documented, and have tests are inert in production. Found 2026-07-31 by the issue #516 generalisation sweep (an AST scan for every attribute read of `settings` across `src/` and `scripts/`, after a naive name grep produced a false all-clear). Verified: `structlog.is_configured()` returns False after `create_app()`, and the only caller anywhere is `scripts/backfill_covers_r2.py`, a one-off backfill that passes hardcoded arguments rather than settings. Neither RQ worker entrypoint calls it either. Consequences: `Settings.log_level`, `json_logs`, and `include_timestamp` change nothing at runtime; the deployed service renders through structlog's default ConsoleRenderer rather than the JSON handler `json_logs=True` selects; and `add_correlation_id` is never installed as a processor, so log lines carry no `correlation_id` key even though `CorrelationMiddleware` populates the contextvar and CLAUDE.md's "Example JSON Log Output" shows one. Explicit `get_correlation_id()` reads still work; only the automatic injection into every log line is missing. Fix is to call `setup_logging()` from `create_app()` and both worker entrypoints with the settings values, which will change the log format that container stdout consumers see, so it is a deployment-visible change and not a pure code fix. | 5 | unscheduled |
| UW-F25 | `Settings.forwarded_allow_ips` is never read in Python. Found by the same 2026-07-31 sweep. The value that actually takes effect is uvicorn's `--forwarded-allow-ips` CLI flag: hardcoded to `172.16.0.0/12` in the Dockerfile CMD and overridden per stack in `docker-compose.yml` (`${FORWARDED_ALLOW_IPS:-172.25.0.0/16}`) and `docker-compose.prod.yml`. Setting `CYO_ADVENTURE_FORWARDED_ALLOW_IPS` in an environment therefore does nothing, while the field's docstring reads as though it governs the behaviour. Security-adjacent: this is the list of proxies trusted to set `X-Forwarded-*`, so the resolution is either to have the entrypoint derive the flag from the setting (one source of truth) or to delete the field and repoint its rationale at the Dockerfile and compose files. Do not simply drop it without recording where the real value lives; the docstring is currently the only prose explanation of the choice. Note that vulture no longer reports this: the UW-F23 baseline suppresses it (tagged `UW-F25` inline in `vulture_whitelist.py`), so this row is now the only signal keeping it visible. Delete that whitelist entry as part of the fix. | 5 | unscheduled |

## Cluster G: content diversity and catalog workstream

roadmap.md and PROJECT-PLAN.md both **state outright** that this workstream has no line item
anywhere. This cluster is that line item. Live specs are
[story-diversity-plan-v2.md](./story-diversity-plan-v2.md),
[story-diversity-implementation-plan.md](./story-diversity-implementation-plan.md), and
[story-diversity-review-errata.md](./story-diversity-review-errata.md); the remediation plan,
execution plan, and original analysis are superseded and must not be tracked from.

**Phase label `G`** in this register means the "Content workstream: diversity and catalog growth"
section of [roadmap.md](./roadmap.md), created 2026-07-28 to give this work its first phase home.

| ID | Item | Source | Phase | Status |
|----|------|--------|-------|--------|
| UW-G01 | **`A20`**: 14 of 16 skeletons and 4,305 `<<FILL>>` nodes unslotted; needs a family-based plan generator first. Largest single item in the workstream. Canonical with UW-A29. | plan-v2, s4 handoff | content | unscheduled |
| UW-G02 | `OQ-4`: 11 stateful Tier-2 skeletons unmigrated, plus the series-level binding design | ws2 | content | unscheduled |
| UW-G03 | `A9` item 2: restructure `the-sunken-temple` (5 variables, 20 conditions, 75 effects, plus a 35-ending remix to 0.0710) | s4 handoff | content | unscheduled |
| UW-G04 | Per-band ATG calibration: `_BAND_THRESHOLDS` is still `{}`, so the anti-template guard stays advisory | ws0, ws1 | content | unscheduled |
| UW-G05 | WS-0 Phase 3 judge-model calibration run; sentence-shape correlation as a gating signal; persisted theme signatures on `StorybookVersion`; leaf-cluster ECS partition | ws0 | content | unscheduled |
| UW-G06 | ECS and RAR dashboard surfacing; served-window ECS DB loader; young-band panel growth; same-theme cross-tree pairs; weekly non-required judge workflow | ws0 phase2 | content | unscheduled |
| UW-G07 | Series and `carries_state` partner exclusion; ATG wiring into `api/node_edit.py` re-screen; threading briefs into ATG | ws1 | content | unscheduled |
| UW-G08 | Grammar-based composer (§7, explicitly deferred); §5.5 deferred-within-M5 items (tier promotion, variable add/remove, stateful grafts, restart-on-fail rewiring); `OQ-8` PL-23 rule family | ws5 | content | unscheduled |
| UW-G09 | WS-6 fresh-generated trees as the flywheel feed; lift the lineage-depth cap (`OQ-5`); in-app promotion-review surface; `flywheel-reports/` cycle reports | ws8 | content | unscheduled |
| UW-G10 | Binding cache (`OQ-3`); `story-skeletons.md` contract column | ws2 | content | unscheduled |
| UW-G11 | `A10` teen short-cell zero candidates returning 422; `A15` retire-for-quality; `A17` tombstone card | plan-v2 | content | unscheduled |
| UW-G12 | Eight items behind prerequisites: reading telemetry, PL-25 fail-depth floor, outcome-mix floor, challenge mode and permadeath, alternate beat phrasings, per-`profile_id` ATG scoping, guardian visibility ceiling, growing small cells | plan-v2 §5 | post-launch | blocked |
| UW-G13 | **Wave 5**: 36 new skeletons, 2 per production cell; the dagger-cell 460-node ceiling experiment; the Tier-2 stateful pilot | story-inventory | content | unscheduled |
| UW-G14 | 23 filled stories committed to `main` are unpublished; 3 legacy-shaped fills need normalization at import. Mechanism corrected 2026-08-03: issue #347 records a production import run on 2026-07-21 landing 25 stories at `in_review`, so the open step is the separate admin promotion to `visibility='catalog'` (`publishing/catalog_publish.py::promote_catalog_story`), not the import. Live database state is unverified; checking it is step 1 of the SQ-01 runbook | draft-stories-manifest | content | unscheduled |
| UW-G15 | `F1` `--series-id` on import; `F2` auto-repair silently replaces imported content; `F3` carried variables invert acquisition branches. Restated in the ceiling-scale review; track via `AL-*`. | series-stress-test | content | unscheduled |
| UW-G16 | Story-quality residuals A, B, C (skeleton promotion gate, RL-13 noise, rule-catalog drift); B and C are product decisions | story-quality-lessons | content | decision |
| UW-G17 | Five research reconciliation actions (exposure ratio, per-band fail-state, reconvergence targets, an independent FK/Lexile gate, edition-family anchoring) plus four open calibration conflicts. Needs an ADR-011 amendment. | research | post-launch | decision |
| UW-G18 | `SR-8` is reserved and claimed by PR #416; `L2-8` emits no ID; `validator-rules.md` contradicts itself on whether SR-8 is implemented | validator-rules | doc | unscheduled |

## Cluster H: story personalization (ADR-023)

The feature has an ADR, two large planning documents, and a merged Stage A. Neither master document
references any of it. **Stage A's G1 gate fired STOP at 3.3% sentinel survival, so Stages B, C, and D
are void pending a re-plan on post-fill re-insertion.** This cluster is therefore recorded as blocked,
not scheduled: that is its accurate state.

| ID | Item | Phase | Status |
|----|------|-------|--------|
| UW-H01 | Re-plan Stage B onward on post-fill re-insertion, after the G1 STOP verdict | 4b | blocked |
| UW-H02 | `P3` through `P11` of the implementation plan, entirely | 4b | blocked |
| UW-H03 | `G2` counsel gate on `OD-1` and `OD-5`. This is what keeps ADR-023 at `proposed`. | 7 | decision |
| UW-H04 | `K19` Route A copy rewrite is a hard **precondition** on the G18 flag, paired with PR #415's A11. Register-only today. | 4b | unscheduled |
| UW-H05 | `R8` they/them handling deferred; ring-3 aggregate rendering; free-text dedications out of scope | 4b | unscheduled |
| UW-H06 | Capability rows `G18` and `K20` have no phase home, which is why `S10` and `S11`'s ADR-023 extensions have none either | 4b | unscheduled |
| UW-H07 | Ring-3 exclusion must land as a test in the S12 work | post-launch | unscheduled |
| UW-H08 | Task R3's open half: `storybook_version.sentinel_manifest` is written once at persist time and never refreshed when a later in-place blob rewrite changes what the blob carries (`moderation/pipeline.py` adopting a repair, `api/node_edit.py` applying an edit). Both sites now re-derive the sibling `personalization_eligible` boolean from the rewritten blob, so the flag is correct; the manifest can still describe the pre-rewrite blob, which is what `verify_manifest` compares against at rest. `db/models.py` records the gap on the column itself. | 4b | unscheduled |

## Cluster I: reader UX and player

| ID | Item | Source | Phase | Status |
|----|------|--------|-------|--------|
| UW-I01 | `A11` request-page reshape, gated on a naive-user session with real children that only the owner can run. Note the ID collision with capability-register `A11`. | s5 handoff | 4b | blocked |
| UW-I02 | `A13b` "Try a different way" three-hop ending-screen rewind; `A18` differentiate the two back-chevrons. Both implement ADR-024. | s5 handoff | 4b | blocked |
| UW-I03 | `A12` deferred pending an owner decision citing ADR-024 Decision 6 (needs durable replay-origin state) | s5 handoff | 4b | decision |
| UW-I04 | Slice `S5` (reader UX) of the diversity implementation plan is undelivered | diversity impl | 4b | unscheduled |
| UW-I05 | Half-built two-device conflict-resolution UI awaiting a product decision | frontend review | 4b | decision |
| UW-I06 | Non-resting accessibility states unscanned; a focused a11y hardening pass is recommended. `P14` jsx-a11y plugin deferred on the eslint 10 peer range. | frontend review, remediation | 5 | unscheduled |
| UW-I07 | Kid-shell and guardian-console rendering of interpretation fields; feeding interpretation into prompts; LLM-authored kid prose (`OQ-5`) | ws7 | 4b | unscheduled |
| UW-I08 | `Mascot.tsx` ships placeholder vector glyphs pending the curated illustrated set | code | 4b | unscheduled |
| UW-I09 | Sibling-visibility wireframe 4.1 deferred: a child principal cannot read sibling profiles | code | 4b | unscheduled |
| UW-I10 | `apiContractParity.ts:125`: backend `status` gained `awaiting_manual_fill`, absent from the frontend `JobStatus` union, "left for a maintainer decision" | code | 4b | decision |

## Cluster J: remediation-plan and console gaps

| ID | Item | Source | Phase | Status |
|----|------|--------|-------|--------|
| UW-J01 | `P7` auto-assign-on-publish, blocked on a `requested_by_profile_id` migration. Raised independently by the persona audit. | remediation, persona audit | 4b | blocked |
| UW-J02 | `P9` PKCE recovery flow deferred (needs live Supabase) | remediation | 5 | unscheduled |
| UW-J03 | `P10` cover-staleness escape, blocked on `StorybookVersion` timestamps | remediation | 4b | blocked |
| UW-J04 | `P12` `schema_version` reader gate not started | remediation | 4b | unscheduled |
| UW-J05 | `P13` durable conflicts store: 409-conflicted writes are currently deleted | remediation | 5 | unscheduled |
| UW-J06 | Admin archive and un-publish button: the endpoint exists with no UI | persona audit | 4b | unscheduled |
| UW-J07 | Admin resubmit-for-review button; guardian profile-delete button | persona audit | 4b | unscheduled |
| UW-J08 | Link request to storybook so "being written" flips; ship the `K19` reflect-back or downgrade its DELIVERED status | persona audit | 4b | unscheduled |
| UW-J09 | Audit-stamp consistency so self-review is detectable | persona audit | 5 | unscheduled |
| UW-J10 | Guardian per-child unassign: merged as PR #428. Verified 2026-07-29: `DELETE /storybooks/{storybook_id}/assignments/{profile_id}` implemented at `api/assignments.py:348-351`; capability G8 (`capability-register.md`) records it delivered 2026-07-27 with the `AssignChildrenDialog.tsx` Remove control. | persona audit | 4b | done |
| UW-J11 | Guardian-defined book groups by age or topic; catalog-trunk-branch admin notification (unresolved); prompt-adjustment suggestions in the dashboard | lifecycle redesign | 4c | unscheduled |
| UW-J12 | ADR-015 consent-time budget semantics (quota debit, per-child pre-auth envelopes); the two-step approve-then-publish audit split; `family_connections` has no consumer widening child visibility | authorization matrix | 4c | unscheduled |
| UW-J13 | Authorization matrix missing rows for families, provider-allowlist, moderation-thresholds, and cover-generate | traceability | doc | unscheduled |
| UW-J14 | `U-5` JIT onboarding admin-seeding footgun is unrecorded in ADR-009 | traceability | doc | unscheduled |
| UW-J15 | **Plan overclaim**: roadmap Phase 4b marks `G2` controls delivered, but the intake UI hardcodes empty arrays and the profile form lacks a banned-theme field | traceability §3.4 | now | unscheduled |
| UW-J16 | Track 2 items with no home: web direct billing and the education channel (Android and i18n are already parked) | traceability | post-launch | unscheduled |
| UW-J17 | External health check `check_external_service` is a shipped placeholder that always returns `status=True` and is not wired into readiness | code | 5 | unscheduled |
| UW-J18 | `notifications/service.py:25`: backfill migration adding `pipeline_event.family_id` is named as future work | code | 4c | unscheduled |
| UW-J19 | `covers/storage.py:173`: upload cancellation cannot reach a background thread; "tracked as a follow-up, not fixed here" | code | 5 | unscheduled |
| UW-J20 | `story_requests/service.py:109`: a real ledger table is a `G13` follow-up once spend needs finer accounting | code | 8 | unscheduled |
| UW-J21 | `merge_graft_contract` and `prune_contract` are implemented and unit-tested but not wired into the acceptance harness (`D7`) | code | content | unscheduled |
| UW-J22 | `review_provider="modal"` ships in the config enum but hard-fails at build time; the default `"mock"` runs no real moderation review | code | 2b | unscheduled |

## Cluster K: documentation accuracy and compliance

Stale documentation is directed work: each item below either misleads a reader or misstates the
project's own inventory.

| ID | Item | Phase | Status |
|----|------|-------|--------|
| UW-K01 | **Release blocker**: `docs/known-vulnerabilities.md` entries PYSEC-2022-42969 (`py`, via `interrogate` 1.7.0) and PYSEC-2026-89 (`markdown`, CVSS 7.5) are 68 days old with reassessment due 2026-07-20, now 8 days overdue. The OpenSSF release gate blocks releases for any vulnerability older than 60 days regardless of reassessment status. Closed by PR #464 (`757ff8e`): PYSEC-2022-42969 was withdrawn upstream and PYSEC-2026-89 does not affect the pinned `markdown` 3.10.2, so neither needed a dependency change. That PR also resolved the release-gate contradiction the entries carried. | now | done |
| UW-K02 | `docs/known-vulnerabilities.md`: libuuid1 and gawk entries name base image `dhi-python:3.12-debian13`; the project runs `3.14-debian13`. The Review History row is a `2026-MM-DD` placeholder and the Resolved Entries table is header-only. | doc | unscheduled |
| UW-K03 | 2 fixable linux-libc-dev CVEs due 2026-08-24, blocked on a Renovate digest bump to a base carrying `linux-libc-dev` 6.12.96-1 | 5 | blocked |
| UW-K04 | `docs/index.md` publishes `pip install cyo-adventure` on the docs home page. This is a deployed app; `publish-pypi.yml` was deleted. It also claims "Python 3.12+" against `>=3.11` and a 3.14 target. | now | unscheduled |
| UW-K05 | `TECHNICAL_BASELINE.md` "Planned additions" sections list 10 packages as not-yet-added; all 10 shipped long ago. The document reads as a live backlog. | now | unscheduled |
| UW-K06 | `TECHNICAL_BASELINE.md`: the nginx image is tagged `alpine` with a note to pin a digest before release. Real supply-chain gap. | 5 | unscheduled |
| UW-K07 | `docs/snyk-implementation-findings.md` recommendations A through F, including a `docs/security/snyk.md` that was never written and a decision on Snyk's role against osv-scanner, pip-audit, trivy, bandit, and semgrep. Zero `Snyk` hits in either master document. | 5 | decision |
| UW-K08 | `docs/snyk-implementation-findings.md` claims the `py` transitive dependency "is gone"; `uv.lock` still carries it via `interrogate`. Contradicts UW-K01. | now | unscheduled |
| UW-K09 | `docs/development/architecture.md` lists **Authentik** as the auth component; auth is Supabase per ADR-009 | doc | unscheduled |
| UW-K10 | `docs/architecture/README.md` claims "all 21 ADRs"; there are 24. `CLAUDE.md` says 18. Both understate the decision inventory. | now | unscheduled |
| UW-K11 | `docs/api/README.md`: the rating upsert update path is not re-exercised in the Postman suite | CI hygiene | unscheduled |
| UW-K12 | `data-model.md:380` `pipeline_event` "will subsume" the current minimal table; `data-model.md:446` `display_name` reserved for a future admin UI | doc | unscheduled |
| UW-K13 | `CHANGELOG.md:2727` carries a `## [0.1.0] - TBD` placeholder in shipped history | doc | unscheduled |
| UW-K14 | `CLAUDE.md`'s warning about a stale `ending.type` in `cyo-author/reference/skeleton-format.md` is itself now stale: the skill doc was corrected | now | unscheduled |
| UW-K15 | Stale frontmatter on delivered work: `ws5`, `ws7`, `ws8-floor-recalibration`, `ws-g-pr3` (25 unchecked boxes despite PR #194), `admin-guardian-dual-roles-plan`, `spec-principal-unresolved-interstitial` (shipped as PR #455). `condition-evaluator-spec.md` is still "Draft" though fully implemented. | doc | unscheduled |
| UW-K16 | The 2026-07-20 roadmap audit calls `admin-guardian-dual-roles-plan.md` unstarted; the work shipped. Only 3 open decisions remain (admin-only `family_id`, dual-role guardian widening, `role='admin'` to `'adult'` rename). | now | decision |
| UW-K17 | `catalog-first-inventory-gap.md` is marked SUPERSEDED 2026-07-28, but Gap B (kid-initiated title requests of existing catalog titles) may not be covered elsewhere | doc | verify |
| UW-K18 | 98 RAD markers carry no paired `#VERIFY`, 82 of them outside `tests/`. Highest-value: the `generation/worker.py` concurrency pair, the `db/models.py` cascade CRITICAL, the `classifiers.py` API-key placement CRITICAL, and four deploy-ordering CRITICALs in `supabase/migrations/`. | 5 | unscheduled |
| UW-K19 | `tests/CLAUDE.md:22` requires a linked issue on every `pytest.mark.skip`; only 2 of the declarative marks reference tracked work | CI hygiene | unscheduled |
| UW-K20 | `docs/planning/` is the only directory in `docs/` exempt from front-matter validation, excluded twice over: the hook's `files: ^docs/(?!planning/).*\.md$` regex and a hardcoded skip at `tools/validate_front_matter.py:311-322`. The cause is that the validator has no `schema_type` concept and so applies the user-facing-docs schema to everything. Measured 2026-07-28: of 72 planning docs, 2 pass and 241 issues are raised, dominated by three systematic mismatches (planning docs carry an H1 the schema forbids, use `status: active` against an allowed set of draft/in-review/published, and use tags it does not know). The fix is a `planning` schema in the validator, not conforming 70 documents to a schema written for a different audience. Until then, `scripts/check_work_linkage.py` is the only automated gate over `docs/planning/`. | CI hygiene | unscheduled |

## Cluster L: live defects

These are not plan gaps. They are bugs found during the sweep, recorded here only so the register is
complete; each is filed as a GitHub issue.

| ID | Item | Issue | Status |
|----|------|-------|--------|
| UW-L01 | `machine.ts:108` wires `RESTART` to `start(story)`, the new-reader entry point, so a restart on a continuation read reseeds `var_state` from the book's declared initials and returns to `story.start_node`, discarding both carried series state and the continuation entry node. Root cause: the machine context keeps only `{story, reading, error}`, dropping the `entryNode`/`varState` pair that `ReaderPage.tsx:246` passed to `startContinuation`, so `reset` cannot reproduce a continuation even in principle. Canonical across ADR-024's deferred defect, debt `SL10`, diversity `B4`, and s5-handoff `B4`. | [#460](https://github.com/ByronWilliamsCPA/cyo-adventure/issues/460) | unscheduled |
| UW-L02 | `api/deps.py:208-228` commits in the teardown half of a yield-dependency, which FastAPI runs after the response is sent. Documented at `docs/api/README.md:88-95` as follow-up work; mitigated only by an 1100 ms newman delay that also serves as rate-limit spacing, so it cannot be tuned for the race alone. | [#461](https://github.com/ByronWilliamsCPA/cyo-adventure/issues/461) | unscheduled |
| UW-L03 | `Settings.rate_limit_redis_cooldown_seconds` (`core/config.py:342`, carries a `#CRITICAL: timing` tag and has unit-test coverage) was never threaded into `RateLimitMiddleware`, so the middleware fell back to a hardcoded `5.0` and `CYO_ADVENTURE_RATE_LIMIT_REDIS_COOLDOWN_SECONDS` had zero effect in any deployed environment. Found by the 2026-07-31 vulture calibration. Fixed 2026-07-31 in commit `bb42b308` (PR #520, "wire the rate-limit Redis knobs and close the UW-F22 dead-symbol findings"): `middleware/security.py:933` now passes `_settings.rate_limit_redis_cooldown_seconds` into the middleware config, alongside the sibling `rate_limit_redis_timeout_seconds` wiring that was already correct. | [#516](https://github.com/ByronWilliamsCPA/cyo-adventure/issues/516) | done |

## Cluster M: external and owner-gated

Work this repository cannot complete on its own.

| ID | Item | Owner | Status |
|----|------|-------|--------|
| UW-M01 | Deploy the device-grant RLS fix to `:staging` once it merges, then re-run `e2e-staging.yml` to confirm the tier is green. **Fully re-diagnosed 2026-08-02; the original "rebuild the stale `:staging` image from `b29aa6b`" ask is refuted.** That premise fails two ways: every migration since `b29aa6b` is purely additive (no `DROP`/`RENAME COLUMN`), so a forward-migrated database cannot break older ORM code, and `trigger-image-build.yml` has succeeded on every merge through 2026-08-02. The tier's redness was **two independent faults**. (1) Three deterministic 500s (`/v1/notifications`, `/v1/review-queue`, `/v1/guardian/books`, the only three routes issuing a full-ORM `select(Storybook)`/`select(StorybookVersion)`) caused by the 07-30 migration stall, i.e. the database being BEHIND a current backend, the exact inverse of the original diagnosis. **Fixed** by repair run [30754078625](https://github.com/ByronWilliamsCPA/cyo-adventure/actions/runs/30754078625), confirmed in run [30757075720](https://github.com/ByronWilliamsCPA/cyo-adventure/actions/runs/30757075720). (2) The device-grant 401: `api/deps.py::_device_principal` reads `select(DeviceGrant).where(jti == ...)` to learn the grant's `family_id`, but `device_grant` is an ADR-022 Tier 1 `family_scoped` table and `apply_family_rls_context` only runs AFTER the principal is built, so the lookup runs with `app.family_id` unset, matches zero rows fail-closed exactly as `20260724120000_scoped_rls_tier1_family_scoping.sql` documents, and is reported as "device grant token failed verification". Not a secret, not a deployment fact: `docker logs` proves the SAME container minted (201) and rejected (401) in the same second. The comment at `deps.py:571` claims there is no chicken-and-egg, which holds for guardian/admin (the `user` table has a Tier 2 blanket policy) and for child (no DB read at all) but was never extended to the device branch, the only pre-principal read of a Tier 1 table. Latent since the 2026-07-18 Tier 1 cutover and invisible to every other tier because local and `e2e-real-*` connect as the owner, which bypasses RLS. **Code fix is in this repo** on `fix/device-grant-rls-lookup`: `_device_principal` now applies the RLS context itself, from the token's already-verified `family_id` claim, before the lookup. A `SECURITY DEFINER` bypass function was drafted first and discarded: it would have made app code depend on a migration-only database object (absent from the ORM `create_all` test fixtures) and could not deploy until that migration landed, reintroducing the very migrate-before-deploy ordering hazard that caused fault (1) above. Setting context from the claim needs no migration, deploys as pure code, and additionally binds the grant row to the family the token claims, which the `jti`-only lookup never checked. This row covers only the owner-side deploy and re-run that follows. | homelab-infra | unscheduled |
| UW-M02 | Naive-user session with real children. Gates UW-I01, UW-I02, and 15 unrun Track B scenarios. | project owner | blocked |
| UW-M03 | Counsel engagement: ADR-018 D1-D4, ADR-016 ring-2 granularity, ADR-023 OD-1 and OD-5. Long lead time; the roadmap already flags that this should start now. | project owner | decision |
| UW-M04 | OpenRouter DPA execution (privacy-model Blocker 1a) | project owner | decision |
| UW-M05 | **Wyrmreach provenance conflict**: the series design and report live only on unmerged branch `claude/dnd-story-game-series-mqr9zy` with unsigned commits, and no `data/series/wyrmreach/` exists on `main`, yet the series is recorded as live in production. Resolve how published content reached production without a main merge before doing more Wyrmreach work. | project owner | decision |
| UW-M06 | Owner decisions from the authoring handoff: book 2 shape, Wyrmreach doc placement, the reader-path four, and whether PL-17's floor applies to gamebooks. Standing alternative: retire the `brass-lantern` series. | project owner | decision |
| UW-M07 | **R2 cover bucket is publicly served, contradicting the code's own invariant.** `covers/storage.py` asserts as `#CRITICAL: security` that the bucket must have no public custom domain or r2.dev access bound to it, because covers are served only as short-lived presigned GET URLs. It did. Verified 2026-07-28: `GET https://cyo-bucket.williamshome.family/sk_ashfall_expedition/1.webp` returned 200 `image/webp`, 86,732 bytes, with no credentials. Because `cover_object_key` is deterministic (`{storybook_id}/{version}.webp`), anyone who could guess a storybook id could read any cover, including one still at `pending_review` under the H2 approval gate shipped in PR #469, so that gate bound the API read paths only. Fix was unbinding the public custom domain in the Cloudflare dashboard, outside this repository. Resolved 2026-07-30: the project owner disconnected the custom domain and cleared the DNS record; re-verified this session with `dig cyo-bucket.williamshome.family` failing to resolve (`Could not resolve host`) against a working general-egress sanity check (`curl https://example.com` returned 200 from the same environment), so the negative is genuine, not a local network gap. The bucket is no longer reachable at that hostname at all; the H2 cover gate is again a real reachability control, not only an API-surface one. | project owner | done |
| UW-M08 | **ADR-022 Tier 1 RLS is inert on production.** The prod backend connects as `postgres.cvrnaydpzijtszfbsraq`, and the `postgres` role has `rolbypassrls = true` (verified against the prod database 2026-08-02), so every `family_scoped` policy created by `20260724120000_scoped_rls_tier1_family_scoping.sql` is bypassed and the family-isolation backstop enforces nothing in production. The least-privilege roles the migration was written for (`cyo_api`, `cyo_worker`, both `rolbypassrls = false`) already EXIST on the prod project but are unused by the API. Staging is correctly cut over to `cyo_api`, which is the only reason UW-M01's device-grant defect surfaced at all: prod cannot fail that way because it enforces no policy. Remedy is the ADR-021 least-privilege cutover on prod, pointing the backend at `cyo_api` and the worker at `cyo_worker`. Do NOT cut over until UW-M01's code fix has merged and been verified on staging, or the same device-grant 401 will land on production the moment the role changes. **Resolved 2026-08-04, closed by the same cutover as `UW-A03`**: the precondition (PR #560 merged and green on staging) was satisfied before the production role switch, so the family-isolation backstop is now enforced live, not just present in migrations. | homelab-infra | done |

---

## Deletion and archive candidates

Documents whose directed work is complete or fully absorbed. Listed so a later cleanup pass does not
have to re-derive them.

| Document | Disposition |
|----------|-------------|
| `handoff-homelab-infra-dev-environment-2026-07-16.md` | Delete. All three asks confirmed done by its own successor handoff. |
| `handoff-authoring-lessons-and-story-quality-2026-07-27.md` | Trim, do not delete. Sections 3 and 4 are obsolete after PR #416; 5, 7, and 9 are live. |
| `handoff-s4-catalog-remaining-2026-07-26.md`, `handoff-s5-reader-ux-remaining-2026-07-26.md` | Keep until their contents land in a phase. They are the only written specs for that work. |
| `story-diversity-remediation-plan.md`, `story-diversity-execution-plan.md` | Superseded by plan-v2, already banner-marked. Do not track from them; `D*` and `M*` IDs are dead. |
| `story-diversity-analysis.md` | Corrected, not superseded, by the errata. Measurements hold; recommendations do not. |
| `ws0-label-fingerprint-finding.md` | Superseded by the evaluation; option 2 shipped. |
| `ws8-floor-recalibration-proposal.md` | Absorbed into ADR-020 Amendment 1; its "awaiting sign-off" banner is stale. |
| `ws-g-pr3-implementation-plan.md` | Closed by PR #194; only a trivial v2 declared-export block remains. |
| `admin-guardian-dual-roles-plan.md` | Retire after UW-K16's three decisions are made. |
| `reviews/ceiling-scale-review-2026-07-25.md` | Keep as evidence, track via `AL-*` only. |

## Related documents

- [PROJECT-PLAN.md](./PROJECT-PLAN.md) - phases and gates; section 1 carries the 2026-07-28 audit note
- [roadmap.md](./roadmap.md) - phase detail; carries the 2026-07-28 audit section
- [capability-register.md](./capability-register.md) - persona capability contract (`K`/`G`/`A`/`S`)
- [r1-deferred-debt-register.md](./r1-deferred-debt-register.md) - R1 deferrals (`C`/`GS`/`U`/`T`/`P`/`SL`)
- [authoring-lessons-log.md](./authoring-lessons-log.md) - authoring and validator lessons (`AL-*`)
