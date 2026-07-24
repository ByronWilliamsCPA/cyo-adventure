import { afterEach, describe, expect, it, vi } from 'vitest'

import {
  getSystemTheme,
  isThemeMode,
  readStoredMode,
  resolveTheme,
  THEME_STORAGE_KEY,
  writeStoredMode,
} from './theme'

function stubMatchMedia(prefersDark: boolean) {
  vi.stubGlobal(
    'matchMedia',
    vi.fn(
      (query: string) =>
        ({
          matches: query === '(prefers-color-scheme: dark)' && prefersDark,
          addEventListener: vi.fn(),
          removeEventListener: vi.fn(),
        }) as unknown as MediaQueryList
    )
  )
}

afterEach(() => {
  localStorage.clear()
  vi.unstubAllGlobals()
})

describe('isThemeMode', () => {
  it('accepts the three known modes and rejects everything else', () => {
    expect(isThemeMode('system')).toBe(true)
    expect(isThemeMode('light')).toBe(true)
    expect(isThemeMode('dark')).toBe(true)
    expect(isThemeMode(null)).toBe(false)
    expect(isThemeMode('auto')).toBe(false)
    expect(isThemeMode('')).toBe(false)
  })
})

describe('readStoredMode / writeStoredMode', () => {
  it('defaults to system with nothing stored', () => {
    expect(readStoredMode()).toBe('system')
  })

  it('round-trips a written mode', () => {
    writeStoredMode('dark')
    expect(localStorage.getItem(THEME_STORAGE_KEY)).toBe('dark')
    expect(readStoredMode()).toBe('dark')
  })

  it('falls back to system for a corrupt stored value', () => {
    localStorage.setItem(THEME_STORAGE_KEY, 'not-a-real-mode')
    expect(readStoredMode()).toBe('system')
  })

  // #ASSUME: external-resources: localStorage can throw (private-mode Safari,
  // quota, disabled storage). readStoredMode must degrade to 'system' rather
  // than crash theme resolution on mount.
  it('falls back to system when localStorage.getItem throws', () => {
    const spy = vi.spyOn(Storage.prototype, 'getItem').mockImplementation(() => {
      throw new Error('storage disabled')
    })
    expect(readStoredMode()).toBe('system')
    spy.mockRestore()
  })

  it('does not throw when localStorage.setItem throws', () => {
    const spy = vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => {
      throw new Error('storage disabled')
    })
    expect(() => writeStoredMode('light')).not.toThrow()
    spy.mockRestore()
  })
})

describe('getSystemTheme / resolveTheme', () => {
  it('reads the OS preference via matchMedia', () => {
    stubMatchMedia(true)
    expect(getSystemTheme()).toBe('dark')
    stubMatchMedia(false)
    expect(getSystemTheme()).toBe('light')
  })

  it('defaults to light when matchMedia is unavailable (jsdom, older browsers)', () => {
    vi.stubGlobal('matchMedia', undefined)
    expect(getSystemTheme()).toBe('light')
  })

  it('resolves system to the OS preference and pins light/dark as-is', () => {
    stubMatchMedia(true)
    expect(resolveTheme('system')).toBe('dark')
    expect(resolveTheme('light')).toBe('light')
    expect(resolveTheme('dark')).toBe('dark')
  })
})
