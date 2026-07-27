import { test } from '@playwright/test'

/**
 * F-6c (BLOCKED-ON-SEED): go-back replay of a VARIABLE-GATED choice, proven
 * against the real backend, has no seeded fixture to run against today.
 *
 * kid-go-back-real.spec.ts already proves go-back persistence to the real
 * backend, but on "The Tide Pool Mystery" (s_tide_pools), which has zero
 * variables: every choice in that story is always visible, so that spec
 * cannot show a gated choice re-appearing correctly after a go-back + reload.
 * reader-go-back.spec.ts (mocked tier) already proves faithful gated-var
 * replay (the `has_lantern` gate in the Lantern Cave fixture), but only
 * against a mocked PUT, not a real persisted round trip.
 *
 * Every seeded story with an in-story variable gate is unusable for this
 * specific case:
 *
 *   - "The Clockwork Garden" (s_clockwork_garden, has_key/courage gates) is
 *     explicitly reserved, in offline-conflict-real.spec.ts's own file
 *     header, as the SOLE owner of that story's reading_state across the
 *     real-backend suite (no file-ordering guarantee across specs; see
 *     real-stack.ts's header). Reading it here would race that file's own
 *     conflict assertions.
 *   - "The Bridge Builder" (s_bridge_builder, planks/has_rope gates) is
 *     approval-gated and is approval-flow.spec.ts's own serial fixture
 *     (pending -> approved -> published), with no defensive per-file
 *     resetRealState() call of its own. Reading it here would race that
 *     file's approval lifecycle in the same no-file-ordering-guarantee tier.
 *   - The Ember Trail series' only gated choice (`c_n_e2_carried`, proven by
 *     series-continue-real.spec.ts) is reachable ONLY through a continuation
 *     read (startContinuation, not start): player/engine.ts's back() and
 *     replayRecordedPath() explicitly, permanently fail closed for any
 *     continuation-state read (an #EDGE-tagged, intentional architectural
 *     limit, not a bug: replaying from start(story) can never reproduce
 *     carried-in variable values that differ from the story's own declared
 *     initial values). Go-back is simply unavailable on this book by design,
 *     so it cannot stand in for this case either.
 *   - "The Tide Pool Mystery" (s_tide_pools), used by kid-go-back-real.spec.ts
 *     itself, has no variables at all (see this file's header above).
 *
 * No seeded, kid-reachable, non-exclusively-owned, non-continuation story
 * with an in-story variable gate exists today. Fabricating a "passing" test
 * against one of the stories above would either race a sibling spec's fixture
 * ownership or silently prove nothing (a gate that can never re-close).
 *
 * TODO(seed): add a small, dedicated, non-exclusive, non-continuation story
 * fixture with a single in-story variable gate (mirroring the Lantern Cave's
 * `has_lantern` shape) to scripts/seed_dev_data.py, assigned to the seeded
 * Dev Reader profile and not claimed by any other real-backend spec's file
 * header. Once seeded, this spec should mirror kid-go-back-real.spec.ts's
 * structure: take the gated choice, go back, reload, and assert (a) the
 * gated choice's button reappears in the DOM, and (b) a direct
 * dev-guardian-authorized GET of the real reading-state row shows the
 * reverted `var_state` and `current_node`, exactly as kid-go-back-real.spec.ts
 * confirms cross-device via a direct fetch today.
 */
test.skip(
  'going back past a variable-gated choice replays the gate correctly against the real backend',
  () => {
    // Intentionally not implemented; see the TODO(seed) above.
  }
)
