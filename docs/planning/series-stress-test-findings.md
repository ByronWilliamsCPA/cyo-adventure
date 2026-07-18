# Series Stress Test Findings: Two-Book 13-16 Gamebook at the Node Ceiling

**Date**: 2026-07-18
**Branch**: `claude/fable-dnd-series-testing-1eqkom`
**Scope**: Exercise the story pipeline at the largest configured scale cell and verify the series
feature end to end with two skill-authored books.

## 1. Objective

Per the test brief: author a classic Dungeons and Dragons style adventure for the 13-16 band in
gamebook style at the largest length for the band, near the node ceiling, as a two-book
state-carrying series. Write book 1, verify it, write book 2, and confirm all series functionality
works, including a full local import, linkage, approval, and publish cycle.

## 2. What was built

Both books occupy the ADR-011 scale cell **(13-16, long, gamebook)**: node budget 370-585,
max depth 80, words/node mean 65 (hard cap 145), PL-17 breadth floors (0.25 endings fraction,
0.08 decision fraction), PL-20 min complete arc 32 nodes. Both are **Tier 2** (stateful) and
share series id `brass-lantern` with `carries_state=true`.

| Metric | Book 1: The Harrowstone Keep | Book 2: The Sunken Temple |
| --- | --- | --- |
| Skeleton | `skeletons/13-16/the-harrowstone-keep.json` | `skeletons/13-16/the-sunken-temple.json` |
| Filled | `out/the-harrowstone-keep.filled.json` | `out/the-sunken-temple.filled.json` |
| Nodes | 550 | 550 |
| Endings | 152 (1 completion + 3 success wins) | 152 (1 completion + 3 success wins) |
| Words | 39,935 | 35,920 |
| Longest path | 79 (budget 80) | 79 (same topology) |
| Variables | vigor, has_lantern, scout_ally, has_sigil | vigor, has_lantern (carried true), marsh_guide, choir_key |
| L2 walk | 7,280 reachable configs, uncapped | passes (smaller: carried var is constant) |
| Gate result | blocked=false, 0 errors, **0 warnings** | blocked=false, 0 errors, **0 warnings** |

Book 2 reuses book 1's proven 550-node topology verbatim (renamed node ids, renamed book-local
variables, all beats, labels, and ending titles reauthored) via
a derivation transform. Story: book 1 forms the Company of the Brass Lantern and shuts the first
seal under Harrowstone Keep; book 2 follows the burnt-notes hook south into the Greymarsh to stop
the Coil raising the second seal, and its win endings plant the book 3 hook (the third seal,
under the mountains).

## 3. Verification results

All checks ran locally on this branch; the end-to-end flow is reproducible via
`scripts/series_e2e_local.py` (see section 5).

1. **Single-story gate** (`run_gate`): both filled books pass with zero errors and zero warnings.
   RL-13 reading level is clean across all 1,100 filled nodes (FK grade held to roughly 5-9
   per node against the 7.0 +/- 2.0 band target).
2. **Cross-book series validator** (`validate_series`, SR-1..SR-7): 0 findings over the pair.
3. **Import**: `import_filled_story` persisted both books (gate + persist + moderation) against a
   local PostgreSQL 16 with all 18 Supabase CLI migrations applied to vanilla Postgres.
4. **Series linkage**: `assign_book_index` + `embed_series_block` linked book 1 as index 1 and
   book 2 as index 2 and stamped the embedded series blocks (entry `n_start`, carries true,
   final false), mirroring the worker path (see F1).
5. **Approve and publish**: `publishing.service.approve` published book 1, then published book 2
   with the series chain gate active (`_series_chain_docs` loaded published book 1 and ran
   SR-1..SR-7 over the chain).
6. **Player smoke test**: `StoryEngine` on published book 2 starts with the carried state
   (`has_lantern=true`), the carried-state-gated choice at `g0_hedda` is visible and playable,
   and an 18-node read reached Act 1.

## 4. Findings

### F2 (High, data integrity): moderation auto-repair can silently replace imported content

With the default all-mock providers, the Stage 1 review returns `{}` per unit; the fail-safe maps
an unknown verdict to FLAG, so any large import soft-flags. The soft-flag path then calls
`attempt_repair` with the **generation** provider. The mock generation provider returns its stub
story (`s_mock_generated`), which is schema-valid and passes the gate, so it **replaced the
550-node imported blob wholesale**. Observed consequences:

- `storybook.id` (`sk_harrowstone_keep`) no longer matched `version.blob.id`
  (`s_mock_generated`), the exact unreachable-version hazard warned about in
  `import_story.py`.
- The later series approve failed with SR-6, because the stub is a Tier-1 story sitting inside a
  `carries_state=true` chain.

**Suggested fix**: `attempt_repair` acceptance should require identity preservation (same
`id`, same tier, plausibly same node count) before swapping the blob, and the mock provider
should echo the input story for repair prompts. Until then, local imports of real content with
mock settings are lossy whenever anything soft-flags.

### F1 (Medium): the import path performs no series linkage

`import_filled_story` (and thus `import_cli`) never calls `link_series_position` or
`embed_series_block`; those run only in the generation worker via a `StoryRequest`. A
skill-authored series book therefore imports as a standalone story and must be linked manually
(as `scripts/series_e2e_local.py` does). Suggest an `--series-id` option on the import CLI that
runs `assign_book_index` + `embed_series_block` in the same transaction.

### F3 (Medium, authoring guidance): carried variables invert acquisition branches

With `carries_state=true`, a variable acquired in book 1 (`has_lantern` set in Act 0, plus a
"gift it if missing" branch conditioned on `has_lantern == false`) initializes true in book 2.
The unmodified branch becomes unsatisfiable and is a hard **L2-11 dead-branch error**. Book 2
flips that condition into an always-satisfiable carried-state gate and drops the redundant set
effects. Any future continuation tooling (or the cyo-author skill docs) should call this out:
acquisition branches of carried variables must be redesigned, not copied.

### F4 (Low, environment): migrations run cleanly on vanilla PostgreSQL

Docker was unavailable in the test environment; PostgreSQL 16 via `initdb`/`pg_ctl` worked. All
18 `supabase/migrations/*.sql` apply to vanilla Postgres with no Supabase-specific roles or
schemas required (the auth/PostgREST references are comments only). Good portability signal for
local development without the Supabase CLI.

### F5 (Info): the ceiling cell is practical end to end

550 nodes per book is comfortably workable: the full gate (including the Layer 2 config walk at
7,280 configs) completes in seconds, import plus moderation of a ~40k-word book completes locally
in under a minute, and approve with the chain gate re-parses the full sibling chain without
noticeable cost. Nothing suggests 585 (the hard max) would behave differently.

## 5. Reproduction

```bash
# One-time local database (no Docker needed)
/usr/lib/postgresql/16/bin/initdb -D /var/lib/pg-cyo
pg_ctl -D /var/lib/pg-cyo start
createdb cyo_adventure
for f in supabase/migrations/*.sql; do psql -v ON_ERROR_STOP=1 -d cyo_adventure -f "$f"; done

# Full series flow: seed, import x2, link x2, approve x2, verify
export CYO_ADVENTURE_DATABASE_URL="postgresql+asyncpg://postgres@localhost/cyo_adventure"
uv run python scripts/series_e2e_local.py
```

The script disables the auto-repair hook for the reason in F2 (documented inline); everything
else is the production code path.
