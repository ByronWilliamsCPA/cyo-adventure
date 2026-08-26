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
source: "Live production data queried via the read-only Supabase MCP 2026-08-25 and 2026-08-26; moderation pipeline at src/cyo_adventure/moderation/ as of bfd47f54. Section 6 (root cause and corrections) rests on the 2026-08-26 queries and on review_provider.py/config.py read at that commit."
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

The twelve are the twelve *largest* books in the backlog, with one
exception in each direction (see section 6: the size reading does not
survive measurement):

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
`sk_clover_butterfly` (20, 2) hold real verdicts.

**Four of the five are not clean, however.** Section 6.2 breaks out the
fail-safe findings they also carry: 24 of 148 nodes on `sk_hollow_lighthouse`
and 22 of 25 on `sk_clocktower_cipher` have no readability verdict at all.
Those two belong in the sweep, not in this bucket. Their 122 actionable findings
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
3. **Size ordering is a cost choice, not a diagnosis.** This section
   originally read the size ranking as evidence of a size-dependent failure
   (batching, truncation, timeout). Section 6 refutes that: `sk_hollow_lighthouse`
   (148 nodes) holds real verdicts while five smaller books do not, and the root
   cause is a mock reviewer, which is size-independent. Re-moderating the two
   550-node books last remains the cheap ordering, on cost grounds alone.

## 5. Measurement provenance

> Sections 1 to 4 are the 2026-08-25 measurement as first written. Section 6
> corrects three of their claims; where the two disagree, section 6 is the
> later measurement and wins.

Queried 2026-08-25 through the read-only Supabase MCP against the production
project, over `storybook`, `storybook_version`, and the JSONB
`moderation_report->'findings'` array. Counts in section 2 are single queries
grouped on `source`, `verdict`, and an exact match of the fail-safe message
string, not sampled. Node counts come from `jsonb_array_length(blob->'nodes')`.

## 6. Correction and root cause, 2026-08-26

Section 2.1 said the cause was "not determinable from the stored report". That
remains true of the report. It was determinable from the code in about twenty
minutes, and it did not need the canary.

### 6.1 The mock reviewer is the cause

`moderation/review_provider.py:119-120`, unchanged by PR #764:

```python
if backend == "mock":
    return MockProvider(responses=["{}"] * _MOCK_RESPONSE_BUDGET), True
```

The mock answers every call with the literal `"{}"`. That is valid JSON and a
`dict`, so it clears both parse guards in `moderation/stages.py::_parse_verdict`;
`payload.get("verdict", "")` then yields `""`, `mapping.get("")` yields `None`,
and the function emits `unknown verdict; defaulted to fail-safe`. Every stage,
every node, which is exactly the shape of all 2,916 findings. `core/config.py:594`
defaults `review_provider` to `"mock"`.

Two consequences the earlier analyses missed:

1. **The mock stamps itself independent.** The `True` in the tuple above is the
   `independent` flag. That is why all seventeen books carry
   `summary.reviewer_independent: true`, and why the 2026-07-28 analysis's
   `reviewer_independent: false` selector matched none of them. The
   `summary.reviewer_independent is False` arm of PR #764's
   `moderation_report_unusable`, and the stamp arm of
   `scripts/remoderate_books.py --mock-moderated`, are both dead against a real
   mock run. Only the fail-safe-message substring arm reaches these books.
2. **The mock guard cannot fire in the failure mode it exists for.**
   `core/config.py:1787` refuses mock only when `review_provider == "mock"` AND
   `environment != "local"` AND not `allow_mock_review`. Both inputs are read
   from the process environment by the same `Settings` object, which declares
   no `env_file` (`core/config.py:218`) and therefore reads nothing but
   exported variables. A process started without them exported takes both
   defaults, `review_provider="mock"` and `environment="local"`, from one
   absence, and the guard is off. Reproduced from the repo root on 2026-08-26:
   resolved settings were `environment=local`, `db host=localhost`,
   `review_provider=mock`, `openai key set=False`, even though `.env` names
   both `CYO_ADVENTURE_REVIEW_PROVIDER` and `OPENAI_API_KEY`. The `.env` file
   is not the mechanism; it is never read by the app at all, which is why
   naming those keys in it changed nothing.

**Operational consequence.** Any sweep must print the resolved `environment`,
database host, and `review_provider` before executing. Run from a shell that
has not exported them, `scripts/remoderate_books.py --execute` would
re-moderate with the mock, write the same `{}`-derived findings, and exit
successfully. Exporting the variables (for example by sourcing `.env` into the
shell) is what makes a real reviewer available; the file's presence alone does
nothing.

### 6.2 The twelve-versus-five split is not clean

Measured 2026-08-26 over `moderation_report->'findings'`, splitting on the
fail-safe substring per book rather than per class:

| Book | Nodes | Fail-safe findings | Stage affected |
|---|---:|---:|---|
| `sk_clocktower_cipher` | 25 | 22 | `llm_readability` |
| `sk_hollow_lighthouse` | 148 | 24 | `llm_readability` |
| `sk_backyard_treasure_map` | 61 | 1 | `llm_readability` |
| `sk_teddy_bears_picnic` | 29 | 1 | `llm_readability` |
| `sk_clover_butterfly` | 20 | 0 | none |

These are stored with `verdict: "pass"`, because `_parse_verdict` takes
`fail_safe=PASS` for soft stages while Stage 1 takes `FLAG`. So an identical
reviewer failure is a flag on safety and a **pass** on readability.

That defeats both halves of PR #764 for these books:
`moderation_report_unusable` returns "usable" as soon as one genuine finding
exists, and `api/review_surface.py::build_review_surface` filters
`verdict is PASS` before rendering, so the unreviewed nodes are invisible to the
reviewer rather than merely unlabelled.

Bounded, not fatal: `llm_safety` returned real verdicts for every node of all
five books, so content safety was genuinely reviewed. The missing dimension is
readability.

### 6.3 The time reading, and why it is wrong

An intermediate hypothesis held that the split was a two-hour outage window
(everything from 19:54 on 2026-07-21 fail-safe, everything before it clean).
Published catalog books refute it by interleaving at 8-second spacing:

| Time | Book | Status | Result |
|---|---|---|---|
| 19:54:48 | `sk_midnight_museum` | published | 56 real findings |
| 19:55:04 | `sk_ashfall_expedition` | published | 76 real findings |
| 19:55:12 | `sk_sunken_signal` | in_review | 100% fail-safe |
| 19:55:14 | `sk_cave_of_echoes__dino-dig` | in_review | 100% fail-safe |

There was no outage window. Whatever selected the twelve was per-job
configuration. The stored `summary` carries no provider or model field, so the
July run's configuration is not recoverable from the data; the mechanism in 6.1
is established, the specific job that triggered it is not, and further
archaeology on it is not worth the cost.

## 7. Remediation, 2026-08-26

Three fixes follow from section 6. All three are on branch
`fix/mock-reviewer-self-identification`, which is not merged; nothing below is
live yet.

### 7.1 The mock reviewer now identifies itself in every environment

The gap-G1 stamp in `moderation/pipeline.py` and
`core/config.py::_require_real_reviewer_outside_local` were both gated on
`environment != "local"`, and both read `review_provider` and `environment`
from the process environment through the same `Settings` object, which
declares no `env_file` and reads nothing but exported variables. That made
them one defense wearing two coats: a process started without those variables
exported takes `review_provider="mock"` (the config default) and
`environment="local"` from one absence, so the config guard does not raise and
the stamp does not apply. The result is a report claiming
`reviewer_independent: true` over nodes no reviewer judged, which is the exact
shape of all twelve.

The stamp is now unconditional. A mock review is not an independent review in
local either, and the stamp is verdict-neutral (`ADVISORY` never gates). This
also revives two code paths that were dead against a real mock run: the
`summary.reviewer_independent is False` arm of
`moderation_report_unusable` (#764) and the stamp arm of
`scripts/remoderate_books.py --mock-moderated`.

### 7.2 A partly-unjudged report now says so

`moderation_report_unusable` returns `False` at the first genuine finding, so
the five books in section 2.2 read as usable and fully reviewed even though
four of them carry a fail-safe `llm_readability` result on up to 88% of their
nodes. Those rows persist with `verdict: "pass"`, because a soft stage fails
safe to PASS, and `api/review_surface.py` drops PASS before rendering. They are
invisible, not merely unlabelled.

`moderation/report.py::hidden_fail_safe_node_counts` counts that hidden
remainder per source and per distinct node; the surface renders one story-level
structural finding from it, matching the shape #764 chose for a wholly unusable
report. Stage 1 safety fail-safes are deliberately excluded: they fail safe to
FLAG, so they gate and already render as flagged passages, and counting them
would describe one outage twice.

This changes rendering only. The approval gate reads the stored report through
`moderation_report_unusable`, not through the surface, so whether a
partly-unjudged story should also be *unapprovable* remains an open decision.

### 7.3 The sweep refuses to run without a reviewer

`scripts/remoderate_books.py` now refuses `--execute` when the resolved
`review_provider` is the mock, as a preflight before the sweep is awaited, and
prints the `environment`, database target, and provider it actually resolved
before every executed run. Credentials in the database URL are never printed.

This is why the `sk_sunken_signal` canary was not run on 2026-08-25. Resolved
settings on the workstation were `environment=local`, `db host=localhost`,
`review_provider=mock`, `openai key set=False`, despite a `.env` naming a real
provider and a remote database. The canary would have re-moderated with the
mock, against the wrong database, and exited successfully.

**Still required to run the sweep:** a production `CYO_ADVENTURE_DATABASE_URL`,
a real `CYO_ADVENTURE_REVIEW_PROVIDER` with its API key, and confirmation of
which environment is being targeted. The preflight now prints all three before
doing anything.
