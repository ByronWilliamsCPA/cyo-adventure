import { useMemo } from 'react'
import { useNavigate, useParams } from 'react-router-dom'

import { EmptyState } from '@ds/components/EmptyState'
import { Button } from '@ds/components/Button'
import { makeFetchStory, makeSyncApi } from '../api/readerApi'
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
  const navigate = useNavigate()

  if (!profileId || !storybookId || !version) {
    return (
      <EmptyState
        title="That story link looks wrong"
        description="We couldn't tell which story to open. Let's go back to the start."
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
    <ReaderPage
      api={syncApi}
      fetchStory={fetchStory}
      profileId={profileId}
      storybookId={storybookId}
      version={parsedVersion}
    />
  )
}
