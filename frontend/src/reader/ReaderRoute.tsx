import { useMemo } from 'react'
import { useNavigate, useParams } from 'react-router-dom'

import { EmptyState } from '@ds/components/EmptyState'
import { Button } from '@ds/components/Button'
import {
  makeFetchServerState,
  makeFetchStory,
  makeRecordCompletion,
  makeSyncApi,
} from '../api/readerApi'
import { useApi } from '../hooks/useApi'
import { BackToLibrary } from './BackToLibrary'
import { ReaderPage } from './ReaderPage'

/**
 * Router-driven entry point for the reader, migrated off App.tsx's former
 * hard-coded demo config onto real route params: /read/:profileId/:storybookId/:version.
 *
 * Kid auth (which profile/story a session may open) is C4a-2's job, not
 * this route's; this stays unauthenticated for now, matching the pre-router
 * behavior it replaces.
 */
export function ReaderRoute() {
  const { profileId, storybookId, version } = useParams<{
    profileId: string
    storybookId: string
    version: string
  }>()
  const api = useApi()
  const syncApi = useMemo(() => makeSyncApi(api), [api])
  const fetchStory = useMemo(() => makeFetchStory(api), [api])
  // Memoized like syncApi/fetchStory above, keyed on the same stable `api`
  // instance: ReaderPage's load() useCallback depends on fetchServerState by
  // identity, so a non-memoized factory call here would mint a fresh function
  // every render and re-fire the mount effect in an unbounded loop (see the
  // NO_SERVER_STATE/NO_RECORD_COMPLETION comment in ReaderPage.tsx for the
  // regression this pattern guards against).
  const fetchServerState = useMemo(() => makeFetchServerState(api), [api])
  const recordCompletion = useMemo(() => makeRecordCompletion(api), [api])
  const navigate = useNavigate()

  if (!profileId || !storybookId || !version) {
    return (
      <EmptyState
        title="We couldn't tell which story to open"
        description="This link is missing some information. Let's go back to the start."
        actions={
          <Button variant="ghost" onClick={() => navigate('/')}>
            Back to start
          </Button>
        }
      />
    )
  }
  const parsedVersion = Number(version)
  if (!Number.isInteger(parsedVersion) || parsedVersion < 1) {
    return (
      <EmptyState
        title="That story link looks wrong"
        description="This story link isn't valid. Let's go back to your books."
        actions={<BackToLibrary profileId={profileId} />}
      />
    )
  }

  return (
    // Keyed by the route params so navigating to a different story (or a
    // different version/profile) fully remounts ReaderPage instead of reusing
    // the same instance; a stale in-flight load from the old story can then
    // never resolve into the new one's state.
    <ReaderPage
      key={`${profileId}:${storybookId}:${parsedVersion}`}
      api={syncApi}
      fetchStory={fetchStory}
      fetchServerState={fetchServerState}
      recordCompletion={recordCompletion}
      profileId={profileId}
      storybookId={storybookId}
      version={parsedVersion}
    />
  )
}
