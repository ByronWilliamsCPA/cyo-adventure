# Sentinel re-insertion prototype report

Strip-all-then-reinsert clean rate: **10.0%** (3/30)

Round-trip integrity-check pass rate (bound-skeleton-relative: proves a clean reinsertion restores the exact token multiset the ORIGINAL pre-fill skeleton declared; a fill-quality signal, legitimately below 100% on an ordinary not_found token): **10.0%** (3/30)

Verify-manifest pass rate (ADR-023 G1-R gate metric: proves the reinserted document is self-consistent with its own derived manifest; a transform-correctness signal, distinct from the round-trip rate above, required at 100%): **100.0%** (30/30)

Sentence-start capitalization widening matches: **94**

Plural occurrences seen but left unwrapped: **0**

## Per-provider variance

| Provider | Clean | Total | Clean rate |
| --- | --- | --- | --- |
| openrouter | 3 | 30 | 10.0% |

## Per-slot coverage

| Slot | Reinsertable | Total | Coverage |
| --- | --- | --- | --- |
| CHAPERONE | 11 | 36 | 30.6% |
| COMPANION | 456 | 510 | 89.4% |
| COMPANION_KIND | 25 | 36 | 69.4% |
| ENTRANCE | 53 | 60 | 88.3% |
| FOUNDER | 132 | 168 | 78.6% |
| HERO | 391 | 1458 | 26.8% |
| HUB | 53 | 60 | 88.3% |
| KIN | 56 | 84 | 66.7% |
| LISTENER | 210 | 210 | 100.0% |
| OCCASION | 12 | 12 | 100.0% |
| OPENING_MOMENT | 5 | 6 | 83.3% |
| OPERATOR | 233 | 234 | 99.6% |
| THRESHOLD | 32 | 60 | 53.3% |

## Per-(node, token) outcome histogram

| Outcome | Count |
| --- | --- |
| not_found | 1265 |
| reinsertable | 1669 |

## Occurrence-multiplicity distribution (reinsertable tokens only)

| Occurrences | Count |
| --- | --- |
| 1 | 1408 |
| 2-3 | 249 |
| 4+ | 12 |
