import { useMemo } from 'react'

import './App.css'
import { makeFetchStory, makeSyncApi } from './api/readerApi'
import { useApi } from './hooks/useApi'
import { ReaderPage } from './reader/ReaderPage'

interface DemoConfig {
  profileId: string
  storybookId: string
  version: number
}

/**
 * Reader target. Profile/story selection is the Phase 4a library flow; for the
 * Phase 1 reader these come from build-time env with sensible demo defaults.
 */
function demoConfig(): DemoConfig {
  const env = import.meta.env
  return {
    profileId: env.VITE_DEMO_PROFILE_ID ?? 'demo-profile',
    storybookId: env.VITE_DEMO_STORYBOOK_ID ?? 's_lantern_cave',
    version: Number(env.VITE_DEMO_VERSION ?? '1'),
  }
}

function App() {
  const api = useApi()
  const syncApi = useMemo(() => makeSyncApi(api), [api])
  const fetchStory = useMemo(() => makeFetchStory(api), [api])
  const cfg = demoConfig()

  return (
    <div className="app">
      <header className="app-header">
        <h1>CYO Adventure</h1>
      </header>
      <main className="app-main">
        <ReaderPage
          api={syncApi}
          fetchStory={fetchStory}
          profileId={cfg.profileId}
          storybookId={cfg.storybookId}
          version={cfg.version}
        />
      </main>
    </div>
  )
}

export default App
