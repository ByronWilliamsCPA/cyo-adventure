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
| UW-A03 | **Production cutover**: provision `cyo_api` / `cyo_worker` role passwords in staging and prod, retire `postgres`-role traffic. Until this lands, RLS is enabled but disarmed. The ADR names M4.1 as its review gate; M4.1 carries no ADR-021 content. | 021 | M4.1 | unscheduled |
| UW-A04 | `worker_database_url` + `get_worker_session()` + the three worker entrypoints | 021 | 5 | unscheduled |
| UW-A05 | `worker` service in docker-compose; uncomment the dev Redis leg | 021 | 5 | unscheduled |
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
| UW-C01 | **`AL-014` blocking**: no hand-authored skeleton can pass `check_promotion_bundle`, because the lineage sidecar is unconditional. Called blocking inside `A11` while sitting in the post-launch backlog. | now | unscheduled |
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

## Cluster D: untracked GitHub issues

roadmap.md lines 197-199 assert that open issues "remain accurately tracked" in the debt register.
That claim is false: the register cites 9 issue numbers, 6 still open, against 33 open issues. The
19 below appear in no planning document by number or description.

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
| UW-G14 | 23 filled stories committed to `main` are never imported or published; 3 legacy-shaped fills need normalization at import | draft-stories-manifest | content | unscheduled |
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

## Cluster M: external and owner-gated

Work this repository cannot complete on its own.

| ID | Item | Owner | Status |
|----|------|-------|--------|
| UW-M01 | Rebuild and redeploy the `:staging` backend and worker from at least `b29aa6b`, then re-run `e2e-staging.yml`. Per the now-deleted `handoff-staging-stale-backend-image-2026-07-21.md` (untracked local handoff, removed once its one ask was verified; see the "Deletion and archive candidates" table). Verified 2026-07-28, not satisfied: `e2e-staging.yml` run [30364118803](https://github.com/ByronWilliamsCPA/cyo-adventure/actions/runs/30364118803) (same-day, scheduled) still shows the identical 4-passed/2-failed split as the 2026-07-21 handoff, same two specs (`guardian-admin-smoke.spec.ts:34`, `kid-library-smoke.spec.ts:75`), same guardian-console-not-rendering symptom. Every run since 2026-07-18 has failed the same way; the redeploy has not landed or did not resolve it. | homelab-infra | unscheduled |
| UW-M02 | Naive-user session with real children. Gates UW-I01, UW-I02, and 15 unrun Track B scenarios. | project owner | blocked |
| UW-M03 | Counsel engagement: ADR-018 D1-D4, ADR-016 ring-2 granularity, ADR-023 OD-1 and OD-5. Long lead time; the roadmap already flags that this should start now. | project owner | decision |
| UW-M04 | OpenRouter DPA execution (privacy-model Blocker 1a) | project owner | decision |
| UW-M05 | **Wyrmreach provenance conflict**: the series design and report live only on unmerged branch `claude/dnd-story-game-series-mqr9zy` with unsigned commits, and no `data/series/wyrmreach/` exists on `main`, yet the series is recorded as live in production. Resolve how published content reached production without a main merge before doing more Wyrmreach work. | project owner | decision |
| UW-M06 | Owner decisions from the authoring handoff: book 2 shape, Wyrmreach doc placement, the reader-path four, and whether PL-17's floor applies to gamebooks. Standing alternative: retire the `brass-lantern` series. | project owner | decision |
| UW-M07 | **R2 cover bucket is publicly served, contradicting the code's own invariant.** `covers/storage.py` asserts as `#CRITICAL: security` that the bucket must have no public custom domain or r2.dev access bound to it, because covers are served only as short-lived presigned GET URLs. It does. Verified 2026-07-28: `GET https://cyo-bucket.williamshome.family/sk_ashfall_expedition/1.webp` returns 200 `image/webp`, 86,732 bytes, with no credentials. Because `cover_object_key` is deterministic (`{storybook_id}/{version}.webp`), anyone who can guess a storybook id reads any cover, including one still at `pending_review` under the H2 approval gate shipped in PR #469, so that gate binds the API read paths only. Fix is unbinding the public domain in the Cloudflare dashboard, outside this repository. Until then, treat the H2 cover gate as an API-surface control, not an image-reachability control. | project owner | unscheduled |

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
