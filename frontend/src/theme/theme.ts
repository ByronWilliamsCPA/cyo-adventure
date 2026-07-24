/**
 * Theme resolution shared by ThemeProvider, the no-flash inline script
 * (index.html), and any test that needs to seed/read the stored preference.
 *
 * Three-state preference ('system' | 'light' | 'dark') collapses to a
 * two-state resolved theme ('light' | 'dark') that tokens.css keys off via
 * `[data-theme]` on the root element; 'system' never reaches the DOM, only
 * its resolved value does, so tokens.css never has to know a third state
 * exists.
 */
export type ThemeMode = 'system' | 'light' | 'dark'
export type ResolvedTheme = 'light' | 'dark'

export const THEME_STORAGE_KEY = 'cyo-theme'

const VALID_MODES: ReadonlySet<string> = new Set(['system', 'light', 'dark'])

export function isThemeMode(value: string | null): value is ThemeMode {
  return value !== null && VALID_MODES.has(value)
}

// #ASSUME: external-resources: localStorage can throw (private-mode Safari,
// storage quota, a disabled-storage policy). Every read/write here is
// wrapped so a blocked storage API degrades to session-only 'system'
// behavior instead of crashing theme resolution.
// #VERIFY: ThemeProvider.test.tsx "falls back to system when localStorage throws".
export function readStoredMode(): ThemeMode {
  try {
    const stored = localStorage.getItem(THEME_STORAGE_KEY)
    return isThemeMode(stored) ? stored : 'system'
  } catch {
    return 'system'
  }
}

export function writeStoredMode(mode: ThemeMode): void {
  try {
    localStorage.setItem(THEME_STORAGE_KEY, mode)
  } catch {
    // Preference just won't survive a reload; the in-memory state still applies.
  }
}

export function getSystemTheme(): ResolvedTheme {
  return typeof window !== 'undefined' && typeof window.matchMedia === 'function'
    ? window.matchMedia('(prefers-color-scheme: dark)').matches
      ? 'dark'
      : 'light'
    : 'light'
}

export function resolveTheme(mode: ThemeMode): ResolvedTheme {
  return mode === 'system' ? getSystemTheme() : mode
}

/** Stamps the resolved theme onto <html data-theme>, the hook tokens.css's `[data-theme="dark"]` block matches on. */
export function applyResolvedTheme(resolved: ResolvedTheme): void {
  document.documentElement.setAttribute('data-theme', resolved)
}
