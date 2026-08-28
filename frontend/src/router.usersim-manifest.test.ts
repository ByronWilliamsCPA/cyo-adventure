import type { ReactNode } from 'react'
import { describe, expect, it } from 'vitest'

import { ROUTE_MANIFEST } from '../e2e-usersim/support/route-manifest'
import { routes } from './router'

/**
 * Sync test between the usersim tier's checked-in route-manifest.ts and the
 * real route tree in router.tsx.
 *
 * Copies router.test.tsx's approach rather than inventing a new one: walk
 * the exported route config STRUCTURALLY (never scrape source text),
 * joining paths exactly as router.tsx's own path segments combine, and
 * carry a positive control so a broken traversal cannot pass by finding
 * nothing to compare.
 *
 * This only needs the URL shape of the tree, not which components gate each
 * leaf (router.test.tsx already owns that), so it is a plain path walk with
 * no Suspense-unwrapping step.
 */

type RouteLike = {
  path?: string
  index?: boolean
  element?: ReactNode
  children?: RouteLike[]
}

function joinPath(parentPath: string, segment: string | undefined): string {
  if (segment === undefined) return parentPath
  if (segment.startsWith('/')) return segment
  return parentPath === '/' ? `/${segment}` : `${parentPath}/${segment}`
}

/** Every leaf path in the route tree, recursively, including the catch-all. */
function leafPaths(
  nodes: readonly RouteLike[],
  parentPath = '',
  out = new Set<string>()
): Set<string> {
  for (const node of nodes) {
    const here = joinPath(parentPath, node.path)
    if (node.children && node.children.length > 0) {
      leafPaths(node.children, here, out)
    } else {
      out.add(here)
    }
  }
  return out
}

const ALL_LEAF_PATHS = leafPaths(routes)

// The catch-all 404 route (`path: '*'` in router.tsx) joins to '/*'. It is
// not a concrete, navigable URL any UI element ever links to, so it is
// excluded from the "reachable" set the manifest is checked against; a walk
// has nothing to substitute for '*' and nowhere real to point it at.
const EXCLUDED_PATHS = new Set<string>(['/*'])

const REACHABLE_LEAF_PATHS = new Set(
  [...ALL_LEAF_PATHS].filter((path) => !EXCLUDED_PATHS.has(path))
)

const MANIFEST_PATHS = new Set(ROUTE_MANIFEST.map((entry) => entry.path))

describe('usersim route manifest sync', () => {
  // Positive control, and the reason the two assertions below mean
  // anything. If the recursive leaf-path walk silently stopped descending
  // into a pathless layout's children (the same risk router.test.tsx's own
  // positive control guards against for gate detection), REACHABLE_LEAF_PATHS
  // would come back small or empty, and the bidirectional checks below could
  // pass vacuously by both sides being wrong in the same way. This fails
  // first in that world, by pinning specific paths that are only reachable
  // by descending through at least two pathless wrapper layers (KidShell ->
  // DeviceAuthorizedRoute -> leaf, or AdultGate -> GUARDIAN_CONSOLE_PATH ->
  // GuardianShell -> leaf).
  //
  // The exact count is a cross-check, not an invariant: this repo's own
  // recon before this test counted 30 leaf routes across four surfaces
  // (landing 3, kid 3, guardian 16, admin 10 = 32), one short of the 33 a
  // structural walk of the current tree actually produces (32 real leaves
  // plus the '/*' catch-all). The count below is asserted against the real
  // tree, not the earlier estimate; see the task report for the discrepancy.
  it('derives a non-vacuous, correctly-nested reachable path set (positive control)', () => {
    expect(ALL_LEAF_PATHS.size).toBe(33)
    expect(REACHABLE_LEAF_PATHS.size).toBe(32)
    expect(REACHABLE_LEAF_PATHS.has('/guardian/profiles')).toBe(true)
    expect(REACHABLE_LEAF_PATHS.has('/admin/moderation-dashboard')).toBe(true)
    expect(REACHABLE_LEAF_PATHS.has('/library/:profileId')).toBe(true)
  })

  it('has a manifest entry for every reachable leaf route', () => {
    const missing = [...REACHABLE_LEAF_PATHS].filter((path) => !MANIFEST_PATHS.has(path))
    expect(missing).toEqual([])
  })

  it('has no manifest entry for a route that does not exist in the tree', () => {
    const extra = [...MANIFEST_PATHS].filter((path) => !REACHABLE_LEAF_PATHS.has(path))
    expect(extra).toEqual([])
  })
})
