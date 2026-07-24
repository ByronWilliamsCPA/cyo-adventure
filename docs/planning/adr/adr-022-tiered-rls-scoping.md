---
title: "ADR-022: Tiered RLS scoping (flat per-family enforcement on the high-sensitivity tables)"
schema_type: planning
status: proposed
owner: core-maintainer
purpose: "Record the decision to make Row Level Security a real, fail-closed defense-in-depth
  boundary on the never-cross-family children's-PII tables (a deliberately flat per-family
  predicate for the cyo_api role), while keeping the FastAPI Principal layer the primary
  authorization authority and leaving the three-ring sharing graph and admin cross-family
  logic exclusively in the application layer."
tags:
  - planning
  - architecture
  - decisions
  - security
---

# ADR-022: Tiered RLS scoping (flat per-family enforcement on the high-sensitivity tables)

> **Status**: Proposed
> **Date**: 2026-07-24
> **Amends**: [ADR-009](./adr-009-supabase-platform.md) (Decision point 7: "Row Level
> Security is optional defense-in-depth later, never the primary model." The "never the
> primary model" clause stands; the implicit "blanket `USING(true)` indefinitely" posture
> does not) and [ADR-021](./adr-021-service-account-rls-and-worker-deployment.md) (Decision
> point 2 and Implementation item 2, which specify blanket `USING(true)` policies for both
> service roles; the high-sensitivity tables get a scoped `cyo_api` policy instead)

## TL;DR

Once the ADR-021 least-privilege cutover lands (the app connects as the non-owner `cyo_api`
role instead of the `BYPASSRLS` `postgres` owner), attach a deliberately flat per-family
`USING` predicate to the RLS policies on the small set of tables that hold children's PII
and must never legitimately cross a family boundary (Tier 1). Every other table, and every
`cyo_worker` policy, keeps the blanket `USING(true)` shape (Tier 2). The predicate reads a
request-scoped `set_config('app.family_id', ..., is_local => true)` set from the resolved
`Principal` inside `get_session()`'s transaction, and is fail-closed: an unset context
returns zero rows (an outage, not a cross-family leak). The three-ring sharing graph
(ADR-016) and admin cross-family reach stay entirely in the FastAPI layer; RLS is a
second, dumb backstop, not a re-implementation of the authorization rules. The policies are
verified as a live control by running the integration/IDOR suite against a `cyo_api`
connection in CI, so they cannot silently rot into untested scaffolding.

## Context

### Problem

The RLS audit of 2026-07-24 established four facts about the live system (prod
`cvrnaydpzijtszfbsraq` and staging):

1. The application connects to Postgres as `postgres` (table owner, `BYPASSRLS`) via the
   Supavisor session-mode pooler (`:5432`), so RLS never affects backend queries today.
2. All 22 public tables have RLS enabled with a single `service_rw FOR ALL TO
   {cyo_api, cyo_worker} USING (true) WITH CHECK (true)` policy each (per ADR-021's plan).
3. `anon`/`authenticated` have no grants and no policies (default-deny); there is no
   PostgREST path anywhere, and the frontend uses supabase-js for auth only.
4. All cross-family isolation is therefore enforced solely by the FastAPI `Principal`
   layer (`authorize_family()` in `api/deps.py`, per-query `family_id` scoping), backed by
   the IDOR suite. It is the only control: a single missed `WHERE family_id ==` clause is
   an immediate cross-family exposure of another family's children's data, with nothing
   underneath it.

ADR-009 point 7 made the app layer the sole authority deliberately, and ADR-021 (Proposed)
plans to keep RLS as a blanket `USING(true)` placeholder even after the role cutover. This
ADR revisits that specific posture for the highest-sensitivity subset of tables, on the
grounds that the app being solo-maintained with heavy AI-assisted PR throughput makes "one
person's per-query discipline is the only thing standing between a routine defect and a
COPPA-covered breach of kids' data" the exact single-point-of-failure that a cheap,
fail-closed database backstop exists to remove.

The decision was reached through a structured adversarial debate (two advocates arguing to
keep vs. revise ADR-009 point 7, two rebuttal rounds, and a senior-architecture review that
verified the pooling mode against the repo). Its material conclusions are recorded in the
Rationale below.

### Constraints

- **Technical**: RLS is inert until the ADR-021 cutover makes the app connect as a
  non-owner role, so this ADR is strictly downstream of ADR-021 and cannot ship before it.
  Supabase CLI migrations are forward-only (ADR-012); policy changes must be additive.
  The predicate mechanism (`set_config`) must be transaction-scoped so it resets on
  `COMMIT`/`ROLLBACK` and cannot leak across pooled requests.
- **Business**: solo operator (ADR-009). This must not become a second authorization
  system to maintain. The scoped tier is deliberately kept flat and small so there is
  almost nothing to co-evolve with the application rules.
- **Regulatory**: children's PII under COPPA/GDPR-K/AADC (ADR-018). "The database enforces
  per-family isolation of children's data, exercised on every CI run" is a materially
  stronger incident and disclosure posture than "we have tests," and RLS enabled but
  disarmed (`USING(true)`) is a worse artifact to explain post-incident than a real policy.

### Significance

This decision is cheap to make now (it rides the ADR-021 migration that is happening
regardless) and more expensive to retrofit after a cross-family incident. It does not
change the primary authorization model; it adds a bounded structural backstop where the
data is most sensitive.

## Decision

**On the tables that hold children's PII and never legitimately cross a family boundary,
the RLS policy for the `cyo_api` role will carry a flat, fail-closed per-family predicate
instead of `USING(true)`. Everything else stays blanket. The FastAPI `Principal` layer
remains the primary authorization authority; RLS is a second, deliberately dumb backstop,
never a re-implementation of the sharing or admin rules.**

1. **Tier 1 (scoped, `cyo_api` only).** Candidate tables: `child_profile`, `reading_state`,
   `completion`, `story_request`, `rating`, `device_grant` (the tables an IDOR bug would
   leak and that carry, or can cheaply carry, a `family_id`). Policy shape:

   ```sql
   CREATE POLICY family_scoped ON public.<table>
     FOR ALL TO cyo_api
     USING (
       family_id::text = current_setting('app.family_id', true)
       OR current_setting('app.is_admin', true) = 'true'
     )
     WITH CHECK (
       family_id::text = current_setting('app.family_id', true)
       OR current_setting('app.is_admin', true) = 'true'
     );
   ```

   The `current_setting(..., true)` form returns `NULL` when the GUC is unset, so a request
   that never set context matches no row: **fail-closed** (a zero-row outage, not a leak).
   The `app.is_admin` clause is the explicit escape hatch for the legitimately cross-family
   admin/moderation path (see point 4); without it, admin review would break on day one.

2. **Tier 2 (blanket `USING(true)`).** Every other table keeps the ADR-021 blanket policy.
   This explicitly includes `family_connection` and any recommendation-adjacent tables,
   which cross families *by design* (ADR-016) and must not carry a single-family predicate,
   and all low-sensitivity catalog/reference tables (`series`, `concept`,
   `provider_model_allowlist`, etc.).

3. **The `cyo_worker` role keeps blanket `USING(true)` on all tables.** The worker operates
   across the pipeline without a single-family request context and never needs to set one.
   This role split is what keeps the mechanism cheap: only the FastAPI request path (one
   code path, `get_session()`) carries the context-setting obligation; the worker path
   (`generation/worker.py`, `covers/worker.py`) is untouched.

4. **Mechanism.** In `get_session()`'s request-scoped transaction, issue
   `SELECT set_config('app.family_id', <principal.family_id>, true)` and
   `SELECT set_config('app.is_admin', <'true'|'false'>, true)` from the resolved
   `Principal` before handing the session to the route. `is_local => true` scopes both GUCs
   to the current transaction. No session-level `SET` is used anywhere.

5. **Scope boundary (what stays in the app layer).** The three-ring sharing graph
   (directional, revocable, dual-consent `family_connection` edges, ADR-016) and the full
   admin authorization logic remain in FastAPI. RLS never encodes graph traversal or
   revocation state. Offline reading (IndexedDB) is out of RLS's reach by construction and
   is unchanged; RLS protects the server query that populates the device, nothing after.

6. **Verification is part of the decision, not an afterthought.** The integration/IDOR
   suite runs against a connection authenticated as `cyo_api` (not the bypassing owner), so
   every test exercises the live policies and a too-tight policy fails closed and loudly in
   CI. A dedicated negative test asserts that a session with no `app.family_id` set returns
   zero rows from every Tier 1 table.

## Rationale

The debate turned on six points; the review's weighting:

- **Threat model (decisive).** The relevant adversary is not an external SQL client (there
  is none) but the maintainer's own future code: a new endpoint with a forgotten filter, an
  ORM refactor that drops a `.filter()`, an AI-assisted PR. The IDOR suite tests known
  endpoints; a new endpoint ships with no test for its own missing filter. RLS fails closed
  when that discipline lapses once.
- **Verification defeats the "untested policy = false confidence" objection.** Pointing the
  suite at the `cyo_api` role converts the policies from assumed-correct scaffolding into a
  control proven on every commit, for the cost of a test-fixture role swap.
- **The pooling footgun is defused by construction.** The deployment uses session-mode
  pooling (`:5432`), and transaction-scoped `set_config(..., true)` resets at commit under
  both pooling modes, so the stale-session-variable leak that would make scoped RLS
  *introduce* the risk it removes is avoidable, not inherent. This must still be proven by a
  spike before committing (see Validation).
- **Drift is bounded because Tier 1 is deliberately dumb.** A flat `family_id =` predicate
  encodes none of the evolving three-ring/admin rules, so there is almost nothing to
  co-evolve, and any drift fails closed (a broken cross-family read is an empty result in
  CI, not a leak). The drift hazard the "keep it blanket" side raised is real for *rich*
  RLS and does not apply to this tier.
- **Marginal cost rides a cutover already scheduled.** ADR-021 already creates the roles,
  grants, and per-table policies; this changes the predicate on ~5-6 of them and adds two
  `set_config` calls on one code path.
- **Compliance asymmetry is a tiebreaker, not a driver.** COPPA does not mandate RLS, but a
  DB-enforced isolation story is materially stronger, and a disarmed RLS layer is worse to
  explain than a real one.

## Options Considered

### Option 1: Tiered scoping (flat per-family on high-sensitivity tables) ✓

**Pros**:

- ✅ Converts "one app-layer bug = cross-family breach of kids' PII" into "one bug + one
  policy hole = breach," where the data is most sensitive.
- ✅ Fail-closed: a context-propagation bug is an outage, not a leak.
- ✅ Near-zero marginal cost on top of the ADR-021 cutover; verified live in CI.

**Cons**:

- ❌ Adds a per-request context-setting obligation on the API path (one code path).
- ❌ Requires proving the `set_config`/pooler semantics before commit.

### Option 2: Keep blanket `USING(true)` on all tables (ADR-021 as written) ✗

**Pros**:

- ✅ Zero new mechanism; one authorization layer to reason about.

**Cons**:

- ❌ Leaves the FastAPI layer as the sole control over children's PII with no backstop.
- ❌ Ships RLS enabled-but-disarmed, the weakest post-incident posture.

### Option 3: Full scoped RLS on all tables, including the three-ring graph and admin logic in SQL ✗

**Pros**:

- ✅ Maximal database-enforced isolation.

**Cons**:

- ❌ Re-implements directional/revocable/consent-gated sharing and admin cross-family reach
  in SQL predicates, a second copy of complex, evolving logic that will drift silently at
  exactly the edge cases that matter.
- ❌ Unaffordable maintenance surface for a solo operator; the review explicitly rejected it.

## Consequences

### Positive

- ✅ Children's-PII tables gain a fail-closed, DB-enforced per-family boundary behind the
  app layer, verified on every CI run.
- ✅ The primary authorization model (ADR-009 point 7's core) is unchanged; no logic is
  duplicated for the hard cases.
- ✅ Stronger, defensible COPPA/incident narrative.

### Trade-offs

- ⚠️ The API request path must reliably set `app.family_id`/`app.is_admin` per request.
  Mitigation: single choke point (`get_session()`), fail-closed on omission, negative test.
- ⚠️ Admin cross-family reads depend on the `app.is_admin` escape hatch being set correctly
  from the verified `Principal`. Mitigation: set it in the same place as `app.family_id`;
  test both the admin-allowed and non-admin-denied paths.

### Technical Debt

- Tables scoped in the ORM by `child_profile_id` rather than a direct `family_id` column
  need either a denormalized `family_id` (preferred, keeps the predicate flat) or a
  join-based predicate (reintroduces per-row cost and is discouraged). Confirm each Tier 1
  candidate's column during implementation; demote any table that cannot carry a flat
  `family_id` to Tier 2 pending a denormalization migration rather than adding a subquery
  predicate.
- Per-role grant tightening remains deferred to ADR-021's existing debt item.

## Implementation

### Components Affected

1. **`supabase/migrations/<ts>_scoped_rls_tier1.sql`**: replace the Tier 1 tables'
   `cyo_api` policy with the `family_scoped` shape above (additive: `DROP POLICY IF EXISTS`
   then `CREATE POLICY`, per the existing `add_service_role_policies.sql` idempotent
   pattern). `cyo_worker` policies unchanged.
2. **`core/database.py` / `api/deps.py`**: set `app.family_id` and `app.is_admin` via
   `set_config(..., true)` in the request-scoped session from the resolved `Principal`.
   Preserve the existing transaction-pooler / prepared-cache branch untouched.
3. **`tests/integration/conftest.py`**: add a `cyo_api`-role connection fixture (see
   deliverable C) so the IDOR/integration suite exercises the policies.
4. **`tests/integration/test_rls_service_roles.py`** (or a new module): the unset-context
   zero-rows negative test, plus admin-escape-hatch allow/deny tests.
5. **`docs/operations/runbook.md`**: the future-table checklist gains a "decide Tier 1 vs
   Tier 2" step for every new table.

### Testing Strategy

- Unit: `set_config` values are derived correctly from `Principal` (including the
  no-family / admin cases).
- Integration (the load-bearing guard): suite runs as `cyo_api`; cross-family fixtures must
  return zero rows; unset context returns zero rows; admin context reads across families.
- Spike (prerequisite, deliverable B): prove `set_config(..., is_local => true)` through
  asyncpg + the session-mode pooler + `pool_pre_ping` resets across sequential requests on a
  reused connection, including the rollback path, with no cross-request bleed.

## Validation

### Success Criteria

- [ ] ADR-021 cutover complete (app connects as `cyo_api`), the hard prerequisite.
- [ ] Spike proves per-request `set_config` isolation under the deployed pooler (no bleed).
- [ ] Tier 1 tables enforce per-family isolation for `cyo_api`; cross-family reads return
      zero rows; unset context returns zero rows; admin context reads across families.
- [ ] The integration/IDOR suite runs as `cyo_api` in CI and is green.
- [ ] `family_connection`/recommendation tables confirmed still blanket (Tier 2).

### Review Schedule

- Initial: alongside the ADR-021 cutover review (M4.1/M5 hardening).
- Ongoing: revisit if a Tier 1 table's cross-family semantics change, or if a second,
  less-trusted DB consumer (analytics replica, support tool, Data API) is ever introduced.

## Related

- [ADR-009](./adr-009-supabase-platform.md): the authorization-model decision this amends
  (point 7; the "never the primary model" clause stands).
- [ADR-021](./adr-021-service-account-rls-and-worker-deployment.md): the least-privilege
  role cutover this decision rides on and is downstream of; its blanket-policy clause is
  narrowed here for the Tier 1 tables.
- [ADR-016](./adr-016-recommendation-sharing-social-boundary.md): the three-ring sharing
  boundary that stays in the app layer and keeps `family_connection` at Tier 2.
- [ADR-014](./adr-014-device-authorized-kid-access.md): device grants and child sessions,
  Tier 1 candidates scoped by `family_id`.
- [ADR-018](./adr-018-childrens-privacy-compliance.md): the children's-privacy posture that
  raises the value of a DB-enforced backstop.
- [ADR-012](./adr-012-supabase-cli-migrations.md): forward-only migration mechanics the new
  policy migration follows.
