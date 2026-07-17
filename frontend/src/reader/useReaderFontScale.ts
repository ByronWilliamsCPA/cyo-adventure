import { useCallback, useState } from 'react'

/**
 * Reader text-size control (UX-K2).
 *
 * Three discrete steps so a young reader (or a grown-up beside them) can make
 * the prose bigger without a fiddly slider. The choice is a preference, not a
 * security boundary, so it lives in localStorage keyed per profile; a read
 * failure (private mode) degrades silently to the default.
 */
export const READER_FONT_LEVELS = [0, 1, 2] as const
export type ReaderFontLevel = (typeof READER_FONT_LEVELS)[number]

const SCALE_BY_LEVEL: Record<ReaderFontLevel, number> = {
  0: 1,
  1: 1.15,
  2: 1.3,
}

const LABEL_BY_LEVEL: Record<ReaderFontLevel, string> = {
  0: 'A',
  1: 'A+',
  2: 'A++',
}

function storageKey(profileId: string): string {
  return `cyo-reader-font-scale-${profileId}`
}

function readLevel(profileId: string): ReaderFontLevel {
  try {
    const raw = localStorage.getItem(storageKey(profileId))
    const parsed = Number(raw)
    if (parsed === 1 || parsed === 2) return parsed
  } catch {
    // Storage unavailable: fall back to the default size.
  }
  return 0
}

export interface ReaderFontScale {
  level: ReaderFontLevel
  scale: number
  label: string
  setLevel: (level: ReaderFontLevel) => void
  levels: readonly ReaderFontLevel[]
  labelFor: (level: ReaderFontLevel) => string
}

export function useReaderFontScale(profileId: string): ReaderFontScale {
  const [level, setLevelState] = useState<ReaderFontLevel>(() => readLevel(profileId))

  const setLevel = useCallback(
    (next: ReaderFontLevel) => {
      setLevelState(next)
      try {
        localStorage.setItem(storageKey(profileId), String(next))
      } catch {
        // Best-effort persistence; the in-memory choice still applies this session.
      }
    },
    [profileId]
  )

  return {
    level,
    scale: SCALE_BY_LEVEL[level],
    label: LABEL_BY_LEVEL[level],
    setLevel,
    levels: READER_FONT_LEVELS,
    labelFor: (l) => LABEL_BY_LEVEL[l],
  }
}
