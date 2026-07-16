import { render, screen } from '@testing-library/react'
import { MemoryRouter, RouterProvider, createMemoryRouter } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import type { MockInstance } from 'vitest'

import { NotFoundPage, RouteError, RouteFallback } from './routeElements'
import { routes } from './router'

describe('NotFoundPage', () => {
  it('renders friendly 404 copy with a way home for both audiences', () => {
    // NotFoundPage renders outside every shell, so it must carry its own
    // framing and exits: the landing page and the kid profile picker.
    render(
      <MemoryRouter>
        <NotFoundPage />
      </MemoryRouter>
    )
    expect(
      screen.getByRole('heading', { level: 1, name: /we can't find that page/i })
    ).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Go to the start' })).toHaveAttribute('href', '/')
    expect(screen.getByRole('link', { name: "Who's reading?" })).toHaveAttribute('href', '/kids')
  })
})

describe('RouteFallback', () => {
  it('announces itself as a status region with kid-neutral copy', () => {
    // The Suspense fallback renders on every surface (kid tablets included),
    // so the copy stays friendly and the region is announced politely.
    render(<RouteFallback />)
    const status = screen.getByRole('status')
    expect(status).toHaveTextContent('Just a sec...')
    expect(status).toHaveAttribute('aria-live', 'polite')
  })
})

describe('RouteError', () => {
  let consoleErrorSpy: MockInstance

  beforeEach(() => {
    consoleErrorSpy = vi.spyOn(console, 'error').mockImplementation(() => {})
  })

  afterEach(() => {
    vi.restoreAllMocks()
  })

  it('renders an app-consistent fallback and logs the underlying error', async () => {
    // Drive RouteError the way it is actually reached in production: as a
    // route's errorElement, so useRouteError() resolves a real thrown error
    // from that route's loader.
    const router = createMemoryRouter(
      [
        {
          path: '/boom',
          loader: () => {
            throw new Error('lazy chunk failed to load')
          },
          errorElement: <RouteError />,
          element: <div>never rendered</div>,
        },
      ],
      { initialEntries: ['/boom'] }
    )
    render(<RouterProvider router={router} />)

    const alert = await screen.findByRole('alert')
    expect(alert).toHaveTextContent('Something went wrong')
    expect(alert).toHaveTextContent('Please reload the page')
    expect(consoleErrorSpy).toHaveBeenCalledWith(
      'Route error:',
      expect.objectContaining({ message: 'lazy chunk failed to load' })
    )
  })

  it('renders the fallback without logging when there is no route error to report', () => {
    // Rendered as a plain element (no errorElement context) useRouteError()
    // resolves undefined; the component must still render its fallback and
    // must not log a spurious "Route error: undefined" line.
    const router = createMemoryRouter([{ path: '/', element: <RouteError /> }], {
      initialEntries: ['/'],
    })
    render(<RouterProvider router={router} />)

    expect(screen.getByRole('alert')).toHaveTextContent('Something went wrong')
    expect(consoleErrorSpy).not.toHaveBeenCalledWith('Route error:', expect.anything())
  })
})

describe('router catch-all (router.tsx)', () => {
  it('renders the styled 404 for an unmatched URL', async () => {
    const router = createMemoryRouter(routes, {
      initialEntries: ['/definitely/not/a/page'],
    })
    render(<RouterProvider router={router} />)

    expect(
      await screen.findByRole('heading', { level: 1, name: /we can't find that page/i })
    ).toBeInTheDocument()
    expect(screen.getByRole('link', { name: "Who's reading?" })).toHaveAttribute('href', '/kids')
  })

  it('declares an errorElement on the catch-all route', () => {
    // A throw on the unmatched-URL path must degrade to the styled RouteError
    // boundary, same as the two main route trees.
    const catchAll = routes.find((route) => 'path' in route && route.path === '*')
    expect(catchAll).toBeDefined()
    expect(catchAll && 'errorElement' in catchAll && catchAll.errorElement).toBeTruthy()
  })
})
