import { act, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { ThemeProvider } from './ThemeProvider'
import { ThemeToggle } from './ThemeToggle'
import { THEME_STORAGE_KEY } from './theme'
import { useTheme } from './useTheme'

type ChangeListener = (event: MediaQueryListEvent) => void

interface StubMediaQuery {
  matches: boolean
  listeners: Set<ChangeListener>
  /** Flips `matches` and fires every registered 'change' listener with it. */
  setMatches(next: boolean): void
}

function stubMatchMedia(prefersDark: boolean): StubMediaQuery {
  const stub: StubMediaQuery = {
    matches: prefersDark,
    listeners: new Set(),
    setMatches(next) {
      stub.matches = next
      stub.listeners.forEach((listener) => listener({ matches: next } as MediaQueryListEvent))
    },
  }
  vi.stubGlobal(
    'matchMedia',
    vi.fn(
      (query: string) =>
        ({
          get matches() {
            return query === '(prefers-color-scheme: dark)' && stub.matches
          },
          addEventListener: (_event: string, listener: ChangeListener) =>
            stub.listeners.add(listener),
          removeEventListener: (_event: string, listener: ChangeListener) =>
            stub.listeners.delete(listener),
        }) as unknown as MediaQueryList
    )
  )
  return stub
}

function ThemeStateProbe() {
  const { mode, resolvedTheme } = useTheme()
  return (
    <span data-testid="theme-state">
      {mode}:{resolvedTheme}
    </span>
  )
}

afterEach(() => {
  localStorage.clear()
  document.documentElement.removeAttribute('data-theme')
  vi.unstubAllGlobals()
})

describe('useTheme outside a ThemeProvider', () => {
  it('throws a helpful error', () => {
    // Swallow the expected React error-boundary console.error noise.
    const spy = vi.spyOn(console, 'error').mockImplementation(() => {})
    expect(() => render(<ThemeStateProbe />)).toThrow(
      'useTheme must be used within a ThemeProvider'
    )
    spy.mockRestore()
  })
})

describe('ThemeProvider', () => {
  it('defaults to system, resolved from the OS preference, and stamps <html data-theme>', () => {
    stubMatchMedia(true)
    render(
      <ThemeProvider>
        <ThemeStateProbe />
      </ThemeProvider>
    )
    expect(screen.getByTestId('theme-state')).toHaveTextContent('system:dark')
    expect(document.documentElement.getAttribute('data-theme')).toBe('dark')
  })

  it('reads a previously stored explicit mode instead of the OS preference', () => {
    stubMatchMedia(true)
    localStorage.setItem(THEME_STORAGE_KEY, 'light')
    render(
      <ThemeProvider>
        <ThemeStateProbe />
      </ThemeProvider>
    )
    expect(screen.getByTestId('theme-state')).toHaveTextContent('light:light')
    expect(document.documentElement.getAttribute('data-theme')).toBe('light')
  })

  it('re-resolves and re-stamps <html> when the OS preference changes while in system mode', () => {
    const media = stubMatchMedia(false)
    render(
      <ThemeProvider>
        <ThemeStateProbe />
      </ThemeProvider>
    )
    expect(screen.getByTestId('theme-state')).toHaveTextContent('system:light')

    act(() => {
      media.setMatches(true)
    })

    expect(screen.getByTestId('theme-state')).toHaveTextContent('system:dark')
    expect(document.documentElement.getAttribute('data-theme')).toBe('dark')
  })

  it('ThemeToggle cycles system -> light -> dark -> system, persisting each choice', () => {
    stubMatchMedia(false)
    render(
      <ThemeProvider>
        <ThemeToggle />
        <ThemeStateProbe />
      </ThemeProvider>
    )
    const button = screen.getByRole('button')

    expect(screen.getByTestId('theme-state')).toHaveTextContent('system:light')

    act(() => button.click())
    expect(screen.getByTestId('theme-state')).toHaveTextContent('light:light')
    expect(localStorage.getItem(THEME_STORAGE_KEY)).toBe('light')

    act(() => button.click())
    expect(screen.getByTestId('theme-state')).toHaveTextContent('dark:dark')
    expect(localStorage.getItem(THEME_STORAGE_KEY)).toBe('dark')
    expect(document.documentElement.getAttribute('data-theme')).toBe('dark')

    act(() => button.click())
    expect(screen.getByTestId('theme-state')).toHaveTextContent('system:light')
    expect(localStorage.getItem(THEME_STORAGE_KEY)).toBe('system')
  })

  it('exposes a per-mode accessible label naming the current mode and the next one', () => {
    // The only ThemeToggle behavior the cycle test above does not assert: the
    // aria-label is the sole affordance a screen-reader user has (the icon is
    // aria-hidden), so it must name the CURRENT mode, not just the target.
    stubMatchMedia(false)
    render(
      <ThemeProvider>
        <ThemeToggle />
      </ThemeProvider>
    )
    const button = screen.getByRole('button')

    expect(button).toHaveAttribute('aria-label', 'Theme: Match device. Switch to Light.')

    act(() => button.click())
    expect(button).toHaveAttribute('aria-label', 'Theme: Light. Switch to Dark.')

    act(() => button.click())
    expect(button).toHaveAttribute('aria-label', 'Theme: Dark. Switch to Match device.')
  })

  it('picks up a theme change made in another tab via the storage event', () => {
    stubMatchMedia(false)
    render(
      <ThemeProvider>
        <ThemeStateProbe />
      </ThemeProvider>
    )
    expect(screen.getByTestId('theme-state')).toHaveTextContent('system:light')

    localStorage.setItem(THEME_STORAGE_KEY, 'dark')
    act(() => {
      window.dispatchEvent(
        new StorageEvent('storage', { key: THEME_STORAGE_KEY, newValue: 'dark' })
      )
    })

    expect(screen.getByTestId('theme-state')).toHaveTextContent('dark:dark')
  })
})
