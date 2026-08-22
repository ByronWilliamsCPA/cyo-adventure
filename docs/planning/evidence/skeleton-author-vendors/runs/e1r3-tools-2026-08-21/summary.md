# Skeleton-author comparison summary

Primary endpoint (S-1): VOID for this run. The between-leg statistic 0.000 / p = 1.0000 below-the-
fold in `summary.json` is computed over an all-zeros repair-round vector, an artifact of the drivers
scoring only each point's final draft; it discriminates nothing. The decision-bearing output of this
tool-assisted run is the strict-pass column; per-point checker-invocation counts are in `tools-
meta.json`. The same artifact makes `errors`, `first-pass clean`, `mean repair rounds`, and `output
tokens` non-measurements here.

| leg | shells | errors | strict pass | first-pass clean | mean repair rounds | output tokens | min catalog distance |
| --- | --- | --- | --- | --- | --- | --- | --- |
| claude-fable-subagent | 6 | 0 | 6 | 6 | 0.00 | 0 | 0.066 |
| claude-haiku-subagent | 6 | 0 | 3 | 3 | 0.00 | 0 | 0.138 |
| claude-opus-subagent | 6 | 0 | 6 | 6 | 0.00 | 0 | 0.051 |
| claude-sonnet-subagent | 6 | 0 | 4 | 4 | 0.00 | 0 | 0.083 |
| deepseek-v4-flash | 6 | 0 | 3 | 3 | 0.00 | 0 | 0.150 |
| deepseek-v4-pro | 6 | 0 | 0 | 0 | 0.00 | 0 | 0.172 |
| moonshot-kimi-k3-modal | 6 | 0 | 5 | 5 | 0.00 | 0 | 0.063 |
