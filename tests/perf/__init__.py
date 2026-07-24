# SPDX-FileCopyrightText: 2026 Byron Williams <byronawilliams@gmail.com>
#
# SPDX-License-Identifier: MIT
"""Performance regression tests (the ``perf`` marker).

Opt-in and off the PR path (each module gates on ``CYO_RUN_PERF=1``). These are
in-process algorithmic regression guards that pin a hot path's complexity class,
NOT a load test. The deployment-level capacity baseline is P9-13
(docs/planning/PROJECT-PLAN.md): it measures API, DB-connection, and
generation-worker throughput under simulated multi-family load against hosted
infra, and records the result in docs/planning/capacity-baseline.md. This tier
does not replace it.
"""
