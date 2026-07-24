import { createContext } from 'react'

import type { ResolvedTheme, ThemeMode } from './theme'

export interface ThemeContextValue {
  /** The stored preference: 'system' follows the OS, 'light'/'dark' pin it. */
  mode: ThemeMode
  /** What's actually applied right now (mode with 'system' resolved). */
  resolvedTheme: ResolvedTheme
  setMode: (mode: ThemeMode) => void
}

export const ThemeContext = createContext<ThemeContextValue | undefined>(undefined)
