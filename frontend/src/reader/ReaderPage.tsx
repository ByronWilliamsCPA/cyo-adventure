/**
 * The reader page: loads a story (cache-first, then network), resumes saved
 * progress, plays it, persists each step, and reconciles multi-device conflicts.
 *
 * The engine owns no server revision (its ReadingState.state_revision is always
 * 0), so this page tracks the last known server revision and stamps each save
 * with it; that is what makes sequential saves and 409 detection work.
 */

import { useCallback, useEffect, useRef, useState } from 'react'

import { cacheStorybook, getCachedStorybook, getReadingState } from '../offline/db'
import { type SyncApi, resolveConflict, saveProgress } from '../offline/sync'
import type { ReadingState, Storybook } from '../player/types'
import { ConflictDialog } from './ConflictDialog'
import { DownloadNeeded } from './DownloadNeeded'
import { Reader } from './Reader'

export interface ReaderPageProps {
  api: SyncApi
  fetchStory: (storybookId: string, version: number) => Promise<Storybook>
  profileId: string
  storybookId: string
  version: number
  deviceId?: string
}

type Phase = 'loading' | 'reading' | 'download-needed'

interface ConflictState {
  local: ReadingState
  server: ReadingState
}

export function ReaderPage({
  api,
  fetchStory,
  profileId,
  storybookId,
  version,
  deviceId,
}: ReaderPageProps) {
  const [story, setStory] = useState<Storybook | null>(null)
  const [initialReading, setInitialReading] = useState<ReadingState | undefined>(undefined)
  const [phase, setPhase] = useState<Phase>('loading')
  const [conflict, setConflict] = useState<ConflictState | null>(null)
  // Bumped to remount the Reader (and re-seed its machine) when we adopt the
  // server's state; the machine reads its input only at creation.
  const [readerKey, setReaderKey] = useState(0)
  const revisionRef = useRef(0)

  const load = useCallback(async () => {
    let cached = await getCachedStorybook(storybookId, version)
    if (!cached) {
      try {
        cached = await fetchStory(storybookId, version)
        await cacheStorybook(cached)
      } catch {
        setPhase('download-needed')
        return
      }
    }
    const saved = await getReadingState(profileId, storybookId)
    revisionRef.current = saved?.state_revision ?? 0
    setStory(cached)
    setInitialReading(saved)
    setPhase('reading')
  }, [fetchStory, profileId, storybookId, version])

  // Load on mount and whenever the load inputs change. The body is inlined here
  // (rather than calling load()) and every setState runs after an await, so
  // react-hooks/set-state-in-effect sees no synchronous state update. The
  // cancelled guard prevents a state update if the inputs change mid-load.
  useEffect(() => {
    let cancelled = false
    void (async () => {
      let cached = await getCachedStorybook(storybookId, version)
      if (cancelled) return
      if (!cached) {
        try {
          cached = await fetchStory(storybookId, version)
          await cacheStorybook(cached)
        } catch {
          if (!cancelled) setPhase('download-needed')
          return
        }
      }
      const saved = await getReadingState(profileId, storybookId)
      if (cancelled) return
      revisionRef.current = saved?.state_revision ?? 0
      setStory(cached)
      setInitialReading(saved)
      setPhase('reading')
    })()
    return () => {
      cancelled = true
    }
  }, [fetchStory, profileId, storybookId, version])

  const persist = useCallback(
    async (reading: ReadingState) => {
      const stamped: ReadingState = {
        ...reading,
        state_revision: revisionRef.current,
      }
      const result = await saveProgress(api, profileId, storybookId, stamped, {
        deviceId,
      })
      if (result.kind === 'saved') {
        revisionRef.current = result.row.state_revision
      } else if (result.kind === 'conflict') {
        setConflict({ local: stamped, server: result.currentRow })
      }
    },
    [api, profileId, storybookId, deviceId]
  )

  // Stable handler so the Reader's progress effect does not re-fire (and re-save
  // unchanged state) on every ReaderPage re-render.
  const handleProgress = useCallback((reading: ReadingState) => void persist(reading), [persist])

  const keepThisDevice = useCallback(async () => {
    if (!conflict) return
    const result = await resolveConflict(
      api,
      profileId,
      storybookId,
      conflict.local,
      conflict.server,
      'continue_from_this_device',
      { deviceId }
    )
    if (result.kind === 'saved') {
      revisionRef.current = result.row.state_revision
    }
    setConflict(null)
  }, [api, conflict, deviceId, profileId, storybookId])

  const adoptNewest = useCallback(async () => {
    if (!conflict) return
    await resolveConflict(
      api,
      profileId,
      storybookId,
      conflict.local,
      conflict.server,
      'use_newer_progress',
      { deviceId }
    )
    revisionRef.current = conflict.server.state_revision
    setInitialReading(conflict.server)
    // Remount the Reader so its machine re-initialises from the adopted server
    // state; without this the reader keeps playing from the local position.
    setReaderKey((key) => key + 1)
    setConflict(null)
  }, [api, conflict, deviceId, profileId, storybookId])

  if (phase === 'loading') {
    return <p data-testid="loading">Loading...</p>
  }
  if (phase === 'download-needed' || !story) {
    return (
      <DownloadNeeded
        onRetry={() => {
          setPhase('loading')
          void load()
        }}
      />
    )
  }
  return (
    <>
      <Reader
        key={readerKey}
        story={story}
        initialReading={initialReading}
        onProgress={handleProgress}
      />
      {conflict ? (
        <ConflictDialog
          onKeepThisDevice={() => void keepThisDevice()}
          onUseNewest={() => void adoptNewest()}
        />
      ) : null}
    </>
  )
}
