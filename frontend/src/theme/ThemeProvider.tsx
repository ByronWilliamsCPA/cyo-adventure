import { useCallback, useEffect, useLayoutEffect, useMemo, useState } from 'react'
import type { ReactNode } from 'react'

import { ThemeContext, type ThemeContextValue } from './themeContext'
import {
  applyResolvedTheme,
  getSystemTheme,
  readStoredMode,
  THEME_STORAGE_KEY,
  writeStoredMode,
  type ResolvedTheme,
  type ThemeMode,
} from './theme'

/**
 * Global theme provider, mounted once at the app root (App.tsx) alongside
 * ToastProvider. Owns the light/dark/system preference and keeps
 * <html data-theme> (tokens.css's `[data-theme="dark"]` hook) in sync with
 * it.
 *
 * index.html carries a small inline script that stamps the same resolved
 * value onto <html> synchronously, before this component (or any stylesheet
 * paint) runs, so there is no flash of the wrong theme on load; the effect
 * below re-applies it after mount so React and the DOM never disagree once
 * rendering settles.
 *
 * `resolvedTheme` is deliberately DERIVED from `mode` and `systemPrefersDark`
 * on every render, not held as its own state variable: setting state
 * synchronously in an effect body (as an earlier version of this file did,
 * to keep a separate resolvedTheme state in sync with mode) trips
 * react-hooks/set-state-in-effect and risks a cascading extra render.
 * Deriving it removes the need for that effect entirely; the two effects
 * that remain only call setState from inside an event-listener callback
 * (matchMedia's 'change', window's 'storage'), the pattern this codebase
 * already uses elsewhere (NotificationBell.tsx, LandingPage.tsx).
 */
export function ThemeProvider({ children }: { children: ReactNode }) {
  const [mode, setModeState] = useState<ThemeMode>(() => readStoredMode())
  // Tracked independently of `mode` (and always, not just while mode is
  // 'system'): resolvedTheme's derivation below only USES this when mode is
  // 'system', but listening unconditionally means toggling in and out of
  // 'system' never has to tear down/re-attach the matchMedia listener.
  const [systemPrefersDark, setSystemPrefersDark] = useState<boolean>(
    () => getSystemTheme() === 'dark'
  )

  const resolvedTheme: ResolvedTheme =
    mode === 'system' ? (systemPrefersDark ? 'dark' : 'light') : mode

  const setMode = useCallback((next: ThemeMode) => {
    setModeState(next)
    writeStoredMode(next)
  }, [])

  // Syncs the DOM (an external system) with the resolved theme; no React
  // state is set here, only <html data-theme>. useLayoutEffect (not useEffect)
  // so the attribute is written BEFORE the browser paints the committed
  // render: on a toggle, a post-paint useEffect would let one frame paint with
  // the outgoing theme's tokens before data-theme flips, a visible flash. The
  // no-flash path on first load is index.html's inline script, not this; this
  // just keeps toggles and OS-preference changes flash-free after mount.
  useLayoutEffect(() => {
    applyResolvedTheme(resolvedTheme)
  }, [resolvedTheme])

  useEffect(() => {
    // #EDGE: browser-compat: matchMedia is absent in jsdom and a
    // MediaQueryList predating 2020 (Safari < 14) exposes only the deprecated
    // addListener, not addEventListener. Feature-detect both so a missing API
    // degrades to "no live OS-change tracking" (initial resolution still
    // works) instead of throwing at mount, where this provider sits OUTSIDE
    // AppErrorBoundary (App.tsx) and a throw would blank the whole app.
    // #VERIFY: ThemeProvider.test.tsx system-change and matchMedia-absent cases.
    if (typeof window.matchMedia !== 'function') return undefined
    const query = window.matchMedia('(prefers-color-scheme: dark)')
    function onChange(event: MediaQueryListEvent) {
      setSystemPrefersDark(event.matches)
    }
    if (typeof query.addEventListener !== 'function') return undefined
    query.addEventListener('change', onChange)
    return () => query.removeEventListener('change', onChange)
  }, [])

  // Cross-tab sync, the same 'storage' pattern LandingPage's device-grant
  // door uses: another tab changing the preference (or clearing it) is
  // picked up here without a reload.
  useEffect(() => {
    function onStorage(event: StorageEvent) {
      if (event.key !== null && event.key !== THEME_STORAGE_KEY) return
      setModeState(readStoredMode())
    }
    window.addEventListener('storage', onStorage)
    return () => window.removeEventListener('storage', onStorage)
  }, [])

  const value = useMemo<ThemeContextValue>(
    () => ({ mode, resolvedTheme, setMode }),
    [mode, resolvedTheme, setMode]
  )

  return <ThemeContext.Provider value={value}>{children}</ThemeContext.Provider>
}
