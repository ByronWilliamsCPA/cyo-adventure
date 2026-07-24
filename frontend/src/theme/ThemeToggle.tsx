import type { ReactElement } from 'react'

import { useTheme } from './useTheme'
import type { ThemeMode } from './theme'
import './theme.css'

const NEXT_MODE: Record<ThemeMode, ThemeMode> = {
  system: 'light',
  light: 'dark',
  dark: 'system',
}

const MODE_LABEL: Record<ThemeMode, string> = {
  system: 'Match device',
  light: 'Light',
  dark: 'Dark',
}

function SunIcon() {
  return (
    <svg width="18" height="18" viewBox="0 0 24 24" aria-hidden="true" focusable="false">
      <circle cx="12" cy="12" r="4.5" fill="none" stroke="currentColor" strokeWidth="2" />
      <path
        fill="none"
        stroke="currentColor"
        strokeWidth="2"
        strokeLinecap="round"
        d="M12 2.5v2.5M12 19v2.5M21.5 12H19M5 12H2.5M18.5 5.5 16.8 7.2M7.2 16.8 5.5 18.5M18.5 18.5 16.8 16.8M7.2 7.2 5.5 5.5"
      />
    </svg>
  )
}

function MoonIcon() {
  return (
    <svg width="18" height="18" viewBox="0 0 24 24" aria-hidden="true" focusable="false">
      <path
        fill="currentColor"
        d="M20.5 14.7A8.5 8.5 0 0 1 9.3 3.5a8.5 8.5 0 1 0 11.2 11.2Z"
      />
    </svg>
  )
}

function SystemIcon() {
  return (
    <svg width="18" height="18" viewBox="0 0 24 24" aria-hidden="true" focusable="false">
      <rect x="3" y="4" width="18" height="12" rx="1.5" fill="none" stroke="currentColor" strokeWidth="2" />
      <path fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" d="M8 20h8M12 16v4" />
    </svg>
  )
}

const MODE_ICON: Record<ThemeMode, () => ReactElement> = {
  system: SystemIcon,
  light: SunIcon,
  dark: MoonIcon,
}

/**
 * Three-way theme toggle (system -> light -> dark -> system), mounted in
 * every top-level surface's chrome (landing, kid, guardian, admin) so the
 * preference is reachable no matter which door a reader/guardian/admin came
 * in through. A single tap advances to the next mode; the icon reflects the
 * CURRENT mode (not the mode a tap would switch to), matching NotificationBell
 * and KidNav's convention of the visible glyph describing present state.
 */
export function ThemeToggle({ className = '' }: { className?: string }) {
  const { mode, setMode } = useTheme()
  const Icon = MODE_ICON[mode]
  const next = NEXT_MODE[mode]

  return (
    <button
      type="button"
      className={['theme-toggle', className].filter(Boolean).join(' ')}
      onClick={() => setMode(next)}
      aria-label={`Theme: ${MODE_LABEL[mode]}. Switch to ${MODE_LABEL[next]}.`}
      title={`Theme: ${MODE_LABEL[mode]}`}
    >
      <Icon />
    </button>
  )
}
