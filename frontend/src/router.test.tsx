import { isValidElement } from 'react'
import type { ReactElement, ReactNode } from 'react'
import { describe, expect, it } from 'vitest'

import { DeviceAuthorizedRoute } from './auth/DeviceAuthorizedRoute'
import { ProtectedRoute } from './auth/ProtectedRoute'
import { AdultGate, GuardianAuthLayout } from './routeElements'
import { routes } from './router'
import { GUARDIAN_CONSOLE_PATH, PRIVACY_PATH, SUPPORT_PATH } from './routes'

/**
 * Structural assertions over the exported route CONFIG, deliberately without
 * rendering anything.
 *
 * The paired page tests (legal/PrivacyPolicyPage.test.tsx,
 * legal/SupportPage.test.tsx) render each page with no auth provider mounted,
 * which proves the COMPONENT needs no session. That is a weaker claim than the
 * one routes.ts makes: those tests would keep passing if someone moved the
 * route itself under ProtectedRoute, because the component would still render
 * fine in isolation. Placement in the tree is a property of this config, so it
 * has to be asserted against this config.
 *
 * Nothing here mounts a component, so the lazy chunks in routeElements.tsx are
 * never resolved and no mock scaffolding is needed; the imported components are
 * used only for reference-identity comparison.
 */

/** The four components that gate a subtree. Anything below one requires auth. */
const GATE_COMPONENTS: readonly unknown[] = [
  ProtectedRoute,
  DeviceAuthorizedRoute,
  AdultGate,
  GuardianAuthLayout,
]

type RouteLike = {
  path?: string
  index?: boolean
  element?: ReactNode
  children?: RouteLike[]
}

/**
 * Every component type reachable from a route's `element`, unwrapping the
 * Suspense boundaries `router.tsx` wraps lazy elements in. Without descending
 * through children, `suspended(<AdultGate />)` would read as Suspense alone and
 * every gate in the tree would go undetected, which is what the positive
 * control below exists to catch.
 */
function componentTypesIn(node: ReactNode): unknown[] {
  if (!isValidElement(node)) return []
  const element = node as ReactElement<{ children?: ReactNode }>
  return [element.type, ...componentTypesIn(element.props.children)]
}

function joinPath(parentPath: string, segment: string | undefined): string {
  if (segment === undefined) return parentPath
  if (segment.startsWith('/')) return segment
  return parentPath === '/' ? `/${segment}` : `${parentPath}/${segment}`
}

/**
 * Map each leaf route's resolved URL to the component types standing between
 * the tree root and that leaf. Pathless layout routes contribute their element
 * to the chain without contributing a URL segment, which is exactly how the
 * gates are expressed in this config.
 */
function leafGateChains(
  nodes: readonly RouteLike[],
  parentPath = '',
  inherited: readonly unknown[] = [],
  out = new Map<string, unknown[]>()
): Map<string, unknown[]> {
  for (const node of nodes) {
    const here = joinPath(parentPath, node.path)
    const chain = [...inherited, ...componentTypesIn(node.element)]
    if (node.children) {
      leafGateChains(node.children, here, chain, out)
    } else {
      out.set(here, chain)
    }
  }
  return out
}

const CHAINS = leafGateChains(routes)

function gatesOn(path: string): unknown[] {
  const chain = CHAINS.get(path)
  expect(chain, `no route resolves to ${path}`).toBeDefined()
  return (chain ?? []).filter((type) => GATE_COMPONENTS.includes(type))
}

describe('route config', () => {
  // Positive control, and the reason the two assertions below mean anything.
  // If gate detection silently stopped working (a refactor that stops wrapping
  // in Suspense, a component swapped for a differently-imported copy, an
  // element shape componentTypesIn cannot see through), every path would look
  // ungated and the public-route assertions would pass vacuously. This case
  // fails first in that world.
  it('detects the gates on a known gated guardian route', () => {
    const gates = gatesOn(`${GUARDIAN_CONSOLE_PATH}/profiles`)
    expect(gates).toContain(GuardianAuthLayout)
    expect(gates).toContain(AdultGate)
    expect(gates).toContain(ProtectedRoute)
  })

  it('detects the device gate on the kid surface', () => {
    expect(gatesOn('/library/:profileId')).toContain(DeviceAuthorizedRoute)
  })

  it.each([
    ['privacy policy', PRIVACY_PATH],
    ['support', SUPPORT_PATH],
  ])('leaves the public %s route outside every gate', (_label, path) => {
    // routes.ts #CRITICAL: both URLs are registered with Epic's Kids Web
    // Services and are followed by a parent mid-verification with no session.
    // A gate here would bounce that parent to a login page from a third-party
    // consent flow, which reads as a phishing redirect.
    expect(gatesOn(path)).toEqual([])
  })
})
