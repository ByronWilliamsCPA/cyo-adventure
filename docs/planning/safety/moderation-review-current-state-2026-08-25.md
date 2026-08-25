---
title: "Moderation Review: Backlog Census, 2026-08-25"
schema_type: planning
status: draft
owner: core-maintainer
purpose: "Re-measure the seventeen books waiting at the human review gate before the Stage D sweep runs, so the sweep is planned against what the reports actually contain rather than against their finding counts."
tags:
  - planning
  - safety
  - moderation
component: Safety-Pipeline
source: "Live production data queried via the read-only Supabase MCP 2026-08-25; moderation pipeline at src/cyo_adventure/moderation/ as of bfd47f54"
---

# Moderation Review: Backlog Census, 2026-08-25

> **Status**: Draft. Successor measurement to
> [moderation-review-current-state-2026-07-28.md](./moderation-review-current-state-2026-07-28.md),
> which measured 29 versions across the whole catalog. This one measures only the
> seventeen books at the human review gate, because those are what
> [`UW-C364`](../unscheduled-work-register.md)'s sweep targets and what
> [`UW-G14`](../unscheduled-work-register.md) must promote.

## 1. Why re-measure

The Stage D sweep (`scripts/remoderate_books.py --in-review`) is built and
unrun. Sizing it from finding counts alone would misread the job: the counts are
dominated by a degradation, not by content. This census separates the two so the
sweep starts from a canary rather than from seventeen books.

## 2. The backlog, as at 2026-08-25

Nothing has moved since the 2026-07-21 import. The newest `storybook_version`
row in production is dated 2026-07-28, so no code merged since then has touched
stored review state.

| Class | Books | Nodes | Findings | Of which actionable |
|---|---:|---:|---:|---:|
| Every node took the fail-safe path | 12 | 2,916 | 5,856 | 0 |
| Reviewer returned real verdicts | 5 | 283 | 675 | 122 |
| **Total** | **17** | **3,199** | **6,531** | **122** |

"Actionable" counts findings that are neither a fail-safe placeholder nor a
`pass` verdict: 99 third-party `openai` advisories, 13 `llm_readability` flags,
8 real `llm_safety` flags, 2 `llm_engagement` advisories.

Findings track node count almost exactly at two per node (550 nodes to 1,102
findings; 20 nodes to 42), because stages 1 and 2 each emit one finding per node
whatever the verdict. Stage A's structural collapse and the review surface's
`PASS` filter both post-date these stored reports.

### 2.1 The twelve

Every finding in these books carries the message
`unknown verdict; defaulted to fail-safe`, emitted at exactly one place
(`moderation/stages.py::_parse_verdict`, the `verdict is None` branch). That
branch is reached when the reviewer's response parsed as JSON but carried no
recognisable `verdict` value; it is distinct from the two
`verdict parse failed` exits above it, which no stored finding uses.

The twelve are the twelve largest books in the backlog:

| Book | Nodes | Findings |
|---|---:|---:|
| `sk_sunken_temple`, `sk_harrowstone_keep` | 550 each | 1,102 each |
| `sk_thornwood_trial` | 375 | 752 |
| `sk_drowned_court` | 314 | 630 |
| `sk_sunspire_ascent` | 252 | 506 |
| `sk_salt_archive` | 225 | 452 |
| `sk_mapmakers_island` | 224 | 450 |
| `sk_last_train_north` | 143 | 288 |
| `sk_signal_in_the_static` | 123 | 248 |
| `sk_cave_of_echoes__space-station`, `sk_cave_of_echoes__dino-dig` | 64 each | 130 each |
| `sk_sunken_signal` | 32 | 66 |

**These books have no review result.** A `soft_flag: true` report with zero real
verdicts is not a lenient review, it is an absent one; the gate held, which is
the fail-safe working, but a human approving from this report would be approving
on no evidence.

**The mock-reviewer stamp does not explain it.** All seventeen carry
`summary.reviewer_independent: true`, so the 2026-07-28 analysis's mock-moderated
classification (`reviewer_independent: false`) does not select any of them. What
produced the unrecognisable verdicts is **not determinable from the stored
report**: a mock or stub reviewer whose stamp was written differently, a
misconfigured provider, and a prompt/vocabulary mismatch all land on the same
branch. Determining which is step 1 of the sweep, not an afterthought to it.

`scripts/remoderate_books.py` still reaches them, via `--in-review` and via
`--mock-moderated`'s fail-safe-substring arm, so no selector change is needed.

### 2.2 The five

`sk_hollow_lighthouse` (148 nodes, 88 actionable), `sk_teddy_bears_picnic` (29,
14), `sk_clocktower_cipher` (25, 14), `sk_backyard_treasure_map` (61, 4) and
`sk_clover_butterfly` (20, 2) hold real verdicts. Their 122 actionable findings
are a tractable human review today, through the surface the redesign already
shipped. They are the only part of the backlog a reviewer can act on before the
sweep runs.

## 3. Covers

No book in production has an approved cover. One published catalog book carries
a `pending_review` cover image; the other 13 published books and all 17 in-review
books have `cover_status = 'none'`. Cover generation is therefore unexercised
against the catalog, not merely incomplete.

| Status / visibility | Books | Cover image | Cover approved |
|---|---:|---:|---:|
| `in_review` / family | 17 | 0 | 0 |
| `published` / catalog | 10 | 1 (`pending_review`) | 0 |
| `published` / family | 4 | 0 | 0 |

## 4. What this changes about the sweep

1. **Canary first.** Re-moderate `sk_sunken_signal` (32 nodes, the cheapest
   fail-safe book) alone via `--book-id`, and read the resulting verdicts. If
   they are real, the degradation was environmental and the sweep is safe. If
   they are fail-safe again, the reviewer is still broken and a seventeen-book
   sweep would spend on 2,916 nodes to reproduce the same non-result.
2. **The five are independent.** Their review needs no sweep and no spend.
3. **Size ordering is not neutral.** The fail-safe class is exactly the large
   half of the backlog, which is consistent with a size-dependent failure
   (batching, truncation, timeout) but does not establish one. Whatever the
   canary shows, re-moderating the two 550-node books last is the cheap
   ordering.

## 5. Measurement provenance

Queried 2026-08-25 through the read-only Supabase MCP against the production
project, over `storybook`, `storybook_version`, and the JSONB
`moderation_report->'findings'` array. Counts in section 2 are single queries
grouped on `source`, `verdict`, and an exact match of the fail-safe message
string, not sampled. Node counts come from `jsonb_array_length(blob->'nodes')`.
