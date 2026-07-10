import { render, screen } from '@testing-library/react'
import { RouterProvider, createMemoryRouter } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import type { MockInstance } from 'vitest'

import { NotFoundPage, RouteError } from './routeElements'

describe('NotFoundPage', () => {
  it('renders a 404 message for an unmatched route', () => {
    render(<NotFoundPage />)
    const alert = screen.getByRole('alert')
    expect(alert).toHaveTextContent('Page not found')
    expect(alert).toHaveTextContent('does not exist')
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
