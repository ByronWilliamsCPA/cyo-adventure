import { useMemo } from 'react'
import { useParams } from 'react-router-dom'

import { makeFetchStory, makeSyncApi } from '../api/readerApi'
import { useApi } from '../hooks/useApi'
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

  if (!profileId || !storybookId || !version) {
    return <p role="alert">Missing story reference in the URL.</p>
  }
  const parsedVersion = Number(version)
  if (!Number.isInteger(parsedVersion) || parsedVersion < 1) {
    return <p role="alert">Invalid story version in the URL.</p>
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
