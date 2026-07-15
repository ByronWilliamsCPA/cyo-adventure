import { render, screen } from '@testing-library/react'
import { createElement, Suspense } from 'react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { importWithReload, lazyWithReload } from './lazyWithReload'

const FLAG = 'chunk-reload:Widget'

// A no-op scheduler: the watchdog timer is never fired, so the reload path's
// promise stays pending exactly as it does in production when a real reload
// tears the page down. Keeps the un-awaited recovery promise from arming a real
// 10s timeout during these synchronous side-effect assertions.
const noopTimer = () => {}

function goodFactory() {
  return Promise.resolve({ default: 'the-module' })
}

function badFactory() {
  return Promise.reject(new Error('Failed to fetch dynamically imported module'))
}

describe('importWithReload', () => {
  beforeEach(() => {
    sessionStorage.clear()
  })

  afterEach(() => {
    vi.restoreAllMocks()
  })

  it('returns the module and clears the reload flag on success', async () => {
    sessionStorage.setItem(FLAG, '1')
    const reload = vi.fn()

    const mod = await importWithReload('Widget', goodFactory, { reload })

    expect(mod).toEqual({ default: 'the-module' })
    expect(reload).not.toHaveBeenCalled()
    expect(sessionStorage.getItem(FLAG)).toBeNull()
  })

  it('force-reloads once, warns, and sets the flag on the first import failure', async () => {
    const reload = vi.fn()
    const warn = vi.spyOn(console, 'warn').mockImplementation(() => {})

    // The recovery path returns a promise that never settles (the reload
    // replaces the document), so we do NOT await the call; we let the rejected
    // factory microtask run, then assert the side effects.
    void importWithReload('Widget', badFactory, { reload, setTimer: noopTimer })
    await new Promise((resolve) => setTimeout(resolve, 0))

    expect(reload).toHaveBeenCalledTimes(1)
    expect(sessionStorage.getItem(FLAG)).toBe('1')
    // Observability: the recovery is announced before the reload discards the
    // console, so a stale-deploy event leaves a trace in prod telemetry.
    expect(warn).toHaveBeenCalledWith(expect.stringContaining('recover stale chunk "Widget"'))
  })

  it('rethrows instead of reloading when the flag is already set (no loop)', async () => {
    sessionStorage.setItem(FLAG, '1')
    const reload = vi.fn()

    await expect(importWithReload('Widget', badFactory, { reload })).rejects.toThrow(
      /dynamically imported module/
    )
    expect(reload).not.toHaveBeenCalled()
  })

  it('does not reload when storage is unavailable (cannot record the attempt)', async () => {
    const reload = vi.fn()
    const throwingStorage = {
      getItem: () => {
        throw new Error('storage disabled')
      },
      setItem: () => {
        throw new Error('storage disabled')
      },
      removeItem: () => {
        throw new Error('storage disabled')
      },
    } as unknown as Storage

    await expect(
      importWithReload('Widget', badFactory, { reload, storage: throwingStorage })
    ).rejects.toThrow(/dynamically imported module/)
    expect(reload).not.toHaveBeenCalled()
  })

  it('does not reload when the flag write fails partway (getItem ok, setItem throws)', async () => {
    // A storage that can be read but not written (quota full, partial lockdown)
    // must be treated the same as fully unavailable: we could not record the
    // one-shot attempt, so reloading risks an unbounded loop. Fall through.
    const reload = vi.fn()
    const readOnlyStorage = {
      getItem: () => null,
      setItem: () => {
        throw new Error('QuotaExceededError')
      },
      removeItem: () => {},
    } as unknown as Storage

    await expect(
      importWithReload('Widget', badFactory, { reload, storage: readOnlyStorage })
    ).rejects.toThrow(/dynamically imported module/)
    expect(reload).not.toHaveBeenCalled()
  })

  it('does not reload on a non-chunk error and rethrows it immediately', async () => {
    // A module-level throw or a transient error is not a stale-deploy signature;
    // a hard reload cannot fix it and would only discard unsaved in-page state.
    const reload = vi.fn()
    const appError = new Error('component threw during evaluation')

    await expect(
      importWithReload('Widget', () => Promise.reject(appError), { reload })
    ).rejects.toBe(appError)
    expect(reload).not.toHaveBeenCalled()
    expect(sessionStorage.getItem(FLAG)).toBeNull()
  })

  it('rejects via the watchdog when the reload does not replace the document', async () => {
    // A no-op reload (blocked or suppressed navigation) must not hang the
    // Suspense fallback forever: the watchdog surfaces the original error.
    const reload = vi.fn()
    const error = vi.spyOn(console, 'error').mockImplementation(() => {})
    let fireWatchdog!: () => void
    const setTimer = (callback: () => void) => {
      fireWatchdog = callback
    }

    const pending = importWithReload('Widget', badFactory, { reload, setTimer })
    await new Promise((resolve) => setTimeout(resolve, 0))
    expect(reload).toHaveBeenCalledTimes(1)

    // Simulate the grace period elapsing with the page still intact.
    fireWatchdog()

    await expect(pending).rejects.toThrow(/dynamically imported module/)
    expect(error).toHaveBeenCalledWith(expect.stringContaining('did not recover chunk "Widget"'))
  })

  it('re-arms recovery: reloads again after an intervening success cleared the flag', async () => {
    const reload = vi.fn()
    vi.spyOn(console, 'warn').mockImplementation(() => {})

    // First failure reloads and sets the flag.
    void importWithReload('Widget', badFactory, { reload, setTimer: noopTimer })
    await new Promise((resolve) => setTimeout(resolve, 0))
    expect(reload).toHaveBeenCalledTimes(1)

    // A later success clears the flag.
    await importWithReload('Widget', goodFactory, { reload })
    expect(sessionStorage.getItem(FLAG)).toBeNull()

    // A subsequent failure is treated as fresh and reloads once more.
    void importWithReload('Widget', badFactory, { reload, setTimer: noopTimer })
    await new Promise((resolve) => setTimeout(resolve, 0))
    expect(reload).toHaveBeenCalledTimes(2)
  })
})

describe('lazyWithReload (React.lazy wrapper)', () => {
  it('shows the Suspense fallback, then renders the resolved component', async () => {
    const Lazy = lazyWithReload('HappyWidget', () =>
      Promise.resolve({ default: () => createElement('p', null, 'loaded content') })
    )

    render(
      createElement(
        Suspense,
        { fallback: createElement('span', null, 'loading fallback') },
        createElement(Lazy)
      )
    )

    expect(screen.getByText('loading fallback')).toBeInTheDocument()
    expect(await screen.findByText('loaded content')).toBeInTheDocument()
  })
})
