<!--
SPDX-FileCopyrightText: 2026 Byron Williams <byronawilliams@gmail.com>
SPDX-License-Identifier: MIT
-->

# WS-8 D6 Runbook: Parameterize an Already-Promoted Contract-Less Tree

> **Status: operational runbook.** This documents the OPTIONAL, manual-first
> parameterize-at-promotion path (WS-8 D6). It implements
> `docs/planning/ws8-catalog-flywheel-design.md` section 7.3 and OQ-6, and it
> reuses the WS-2 recipe (`docs/planning/ws2-parameterized-catalog-design.md`
> section 8.1) verbatim.

## When (and when not) to run this

This runbook applies to a tree that was **already promoted contract-less**: a
Tier-2-parity WS-5 mutant today, or a future WS-6 fresh tree. Its purpose is to
add a theme contract so the tree can be re-themed like the rest of the
parameterized catalog.

**This is optional and does not block the first promotion.** Per design section
7.3 and OQ-6, promotion does NOT block on parameterization: a contract-less
promoted tree is exactly as safe as its contract-less parent (same free-text
fill path, same gate, ADR-020 decision 6). Parameterization is a follow-up you
run **as a separate, second PR** when convenient. The scheduled home for closing
the contract gap in bulk is the WS-2 Tier-2 migration wave; run this per-tree
path only when a specific tree needs its contract sooner.

Do **not** run it against a tree that is already parameterized (one that already
carries a `<slug>.contract.json` sidecar or already exposes `{SLOT}` tokens):
the glue refuses those inputs, because re-slotting an already-slotted tree would
corrupt it.

## What stays manual

The glue is deliberately manual-first. The operator authors, by hand, both of
these per the WS-2 recipe; there is **no LLM in this path** and the glue drafts
neither:

1. the slotting **plan** (`plan.json`), and
2. the theme **contract** (`contract.json`).

The glue only chains the existing, unchanged transform and acceptance checks and
prepares the second draft PR. It adds no bypass of any check.

## Prerequisites

- You are on a dedicated feature branch, **never** `main` / `master` (the glue
  refuses the protected branches, matching D4's posture).
- The already-promoted contract-less skeleton is on disk (for example
  `skeletons/8-11/<slug>.json`), or you have its promotion bundle directory.
- `gh` is authenticated if you intend to actually open the PR (`--create`);
  otherwise the default dry run needs nothing.

## Step 1: author the slotting plan (`plan.json`)

Follow the WS-2 recipe (`ws2-parameterized-catalog-design.md` section 8.1). The
plan is a JSON object with exactly three maps:

```json
{
  "beats":  { "<node_id>": "<slotted beats text with {SLOT} tokens>" },
  "titles": { "<ending_node_id>": "<slotted ending title>" },
  "labels": { "<node_id>": { "<choice_id>": "<slotted choice label>" } }
}
```

- Every FILL node needs a `beats` entry, and every ending node needs a `titles`
  entry (the transform requires exhaustive coverage of those two surfaces).
- `labels` is not exhaustive: slot only the choice labels that carry a
  theme-specific noun (recipe section 8.1 step 3).
- Only edit the slotted surfaces. The transform byte-preserves each FILL
  directive's `role=` and `words=`, so do not touch them.
- Every `{TOKEN}` must be a bare all-caps slot id (`{HERO}`, `{A1_GATE}`);
  `{lower}` or `{1BAD}` fail the slot-token grammar check.

## Step 2: author the theme contract (`contract.json`)

Author the contract per the WS-2 recipe and the `ThemeContract` schema
(`src/cyo_adventure/storybook/theme_contract.py`). Its declared slot ids must
**exactly match** the `{SLOT}` token set the plan introduces (no missing, no
extra), and its `default_binding` must name every slot with values that pass the
contract's own constraints and the band-mandatory denylist floor. Use
`scripts/bind_theme.py` to sanity-check a candidate binding renders cleanly
before you commit the contract.

## Step 3: run the chained checks (dry run by default)

```bash
uv run python scripts/parameterize_promotion.py \
    skeletons/8-11/<slug>.json \
    --plan plan.json \
    --contract contract.json
```

The glue runs, in order and honoring each exit code (it writes nothing further
on any failure):

1. **`parameterize_skeleton.py`** applies the plan under its **six fail-closed
   checks**: coverage; dangling references; `role=`/`words=` byte-preservation;
   structural-fingerprint equality; `run_gate` not blocked; slot-token grammar.
   The slotted skeleton is written to the working directory (default
   `out/parameterize/<slug>/`) only when all six pass.
2. The authored contract is placed as the slotted skeleton's
   `<slug>.contract.json` sidecar.
3. **`check_theme_contract.py`** runs the WS-2 acceptance checks against that
   sidecar.

If either check fails, fix the plan or contract and re-run. On success, the glue
prints the exact `gh pr create --draft` command and the composed PR body, but
opens nothing (the dry run has no side effect, matching D4).

A bundle directory works in place of the skeleton path:

```bash
uv run python scripts/parameterize_promotion.py out/mutations/<slug> \
    --plan plan.json --contract contract.json
```

## Step 4: open the second draft PR

When the dry run is clean, re-run with `--create` to stage the files into a
dedicated worktree and open the draft PR:

```bash
uv run python scripts/parameterize_promotion.py \
    skeletons/8-11/<slug>.json \
    --plan plan.json \
    --contract contract.json \
    --create
```

This reuses D4's posture exactly:

- writes **only** inside a dedicated `.worktrees/parameterize-<slug>` checkout of
  a fresh `flywheel/parameterize-<slug>` branch (never the real `skeletons/` on
  `main`);
- copies the slotted skeleton and its contract sidecar into
  `skeletons/<band>/`, regenerates the catalog doc region and the skeleton
  diagram;
- opens a **draft** PR labeled `skeleton-promotion`;
- **never** merges, approves, or enables auto-merge (ADR-020 decision 4). The
  `skeleton-promotion` label excludes the PR from auto-merge tooling, and the
  promotion CI job independently re-proves the gate, contract, anti-clone floor,
  and lineage/hash on the PR's files.

## Step 5: human review and merge

A human reviews the second PR (the diff is: the in-place re-slotting of
`skeletons/<band>/<slug>.json` plus the new `<slug>.contract.json`) and merges
it. As with every promotion, structure approval is the PR review; there is no
auto-merge. Once merged, the tree is an ordinary parameterized catalog skeleton,
and every story filled from it continues to run the unchanged
fill -> gate -> moderation -> ADR-005 chain.

## Safety property

The transform's six fail-closed checks and the contract-acceptance checks are
the gatekeepers. The glue only sequences them and honors their exit codes; it
adds no bypass and weakens no check. It refuses to run on a protected branch,
refuses an already-parameterized input, and writes files destined for
`skeletons/` only inside its own worktree.
