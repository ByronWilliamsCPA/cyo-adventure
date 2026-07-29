# Sentinel re-insertion prototype report

Strip-all-then-reinsert clean rate: **13.3%** (4/30)

Round-trip integrity-check pass rate (bound-skeleton-relative: proves a clean reinsertion restores the exact token multiset the ORIGINAL pre-fill skeleton declared; a fill-quality signal, legitimately below 100% on an ordinary not_found token): **13.3%** (4/30)

Verify-manifest pass rate (ADR-023 G1-R gate metric: proves the reinserted document is self-consistent with its own derived manifest; a transform-correctness signal, distinct from the round-trip rate above, required at 100%): **100.0%** (30/30)

Sentence-start capitalization widening matches: **120**

Plural occurrences seen but left unwrapped: **0**

## Per-provider variance

| Provider | Clean | Total | Clean rate |
| --- | --- | --- | --- |
| openrouter | 4 | 30 | 13.3% |

## Per-slot coverage

| Slot | Reinsertable | Total | Coverage |
| --- | --- | --- | --- |
| CHAPERONE | 23 | 36 | 63.9% |
| COMPANION | 502 | 510 | 98.4% |
| COMPANION_KIND | 27 | 36 | 75.0% |
| ENTRANCE | 48 | 60 | 80.0% |
| FOUNDER | 159 | 168 | 94.6% |
| HERO | 618 | 1458 | 42.4% |
| HUB | 58 | 60 | 96.7% |
| KIN | 49 | 84 | 58.3% |
| LISTENER | 208 | 210 | 99.0% |
| OCCASION | 12 | 12 | 100.0% |
| OPENING_MOMENT | 5 | 6 | 83.3% |
| OPERATOR | 232 | 234 | 99.1% |
| THRESHOLD | 42 | 60 | 70.0% |

## Per-(node, token) outcome histogram

| Outcome | Count |
| --- | --- |
| not_found | 951 |
| reinsertable | 1983 |

## Occurrence-multiplicity distribution (reinsertable tokens only)

| Occurrences | Count |
| --- | --- |
| 1 | 1652 |
| 2-3 | 321 |
| 4+ | 10 |
