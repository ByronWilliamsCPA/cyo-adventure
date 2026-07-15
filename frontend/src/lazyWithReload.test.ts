import { beforeEach, describe, expect, it, vi } from 'vitest'

import { importWithReload } from './lazyWithReload'

const FLAG = 'chunk-reload:Widget'

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

  it('returns the module and clears the reload flag on success', async () => {
    sessionStorage.setItem(FLAG, '1')
    const reload = vi.fn()

    const mod = await importWithReload('Widget', goodFactory, { reload })

    expect(mod).toEqual({ default: 'the-module' })
    expect(reload).not.toHaveBeenCalled()
    expect(sessionStorage.getItem(FLAG)).toBeNull()
  })

  it('force-reloads once and sets the flag on the first import failure', async () => {
    const reload = vi.fn()

    // The recovery path returns a promise that never settles (the reload
    // replaces the document), so we do NOT await the call; we let the rejected
    // factory microtask run, then assert the side effects.
    void importWithReload('Widget', badFactory, { reload })
    await new Promise((resolve) => setTimeout(resolve, 0))

    expect(reload).toHaveBeenCalledTimes(1)
    expect(sessionStorage.getItem(FLAG)).toBe('1')
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

  it('re-arms recovery: reloads again after an intervening success cleared the flag', async () => {
    const reload = vi.fn()

    // First failure reloads and sets the flag.
    void importWithReload('Widget', badFactory, { reload })
    await new Promise((resolve) => setTimeout(resolve, 0))
    expect(reload).toHaveBeenCalledTimes(1)

    // A later success clears the flag.
    await importWithReload('Widget', goodFactory, { reload })
    expect(sessionStorage.getItem(FLAG)).toBeNull()

    // A subsequent failure is treated as fresh and reloads once more.
    void importWithReload('Widget', badFactory, { reload })
    await new Promise((resolve) => setTimeout(resolve, 0))
    expect(reload).toHaveBeenCalledTimes(2)
  })
})
