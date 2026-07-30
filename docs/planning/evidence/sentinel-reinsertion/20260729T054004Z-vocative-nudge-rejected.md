# Sentinel re-insertion prototype report

Strip-all-then-reinsert clean rate: **3.3%** (1/30)

Round-trip integrity-check pass rate (bound-skeleton-relative: proves a clean reinsertion restores the exact token multiset the ORIGINAL pre-fill skeleton declared; a fill-quality signal, legitimately below 100% on an ordinary not_found token): **3.3%** (1/30)

Verify-manifest pass rate (ADR-023 G1-R gate metric: proves the reinserted document is self-consistent with its own derived manifest; a transform-correctness signal, distinct from the round-trip rate above, required at 100%): **100.0%** (30/30)

Sentence-start capitalization widening matches: **147**

Plural occurrences seen but left unwrapped: **0**

## Per-provider variance

| Provider | Clean | Total | Clean rate |
| --- | --- | --- | --- |
| openrouter | 1 | 30 | 3.3% |

## Per-slot coverage

| Slot | Reinsertable | Total | Coverage |
| --- | --- | --- | --- |
| CHAPERONE | 24 | 36 | 66.7% |
| COMPANION | 504 | 510 | 98.8% |
| COMPANION_KIND | 22 | 36 | 61.1% |
| ENTRANCE | 48 | 60 | 80.0% |
| FOUNDER | 159 | 168 | 94.6% |
| HERO | 72 | 1458 | 4.9% |
| HUB | 56 | 60 | 93.3% |
| KIN | 63 | 84 | 75.0% |
| LISTENER | 206 | 210 | 98.1% |
| OCCASION | 12 | 12 | 100.0% |
| OPENING_MOMENT | 6 | 6 | 100.0% |
| OPERATOR | 227 | 234 | 97.0% |
| THRESHOLD | 47 | 60 | 78.3% |

## Per-(node, token) outcome histogram

| Outcome | Count |
| --- | --- |
| not_found | 1488 |
| reinsertable | 1446 |

## Occurrence-multiplicity distribution (reinsertable tokens only)

| Occurrences | Count |
| --- | --- |
| 1 | 1210 |
| 2-3 | 225 |
| 4+ | 11 |
