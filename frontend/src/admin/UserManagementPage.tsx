import { useEffect, useMemo, useState } from 'react'

import { LoadingStatus } from '@ds/components/LoadingStatus'
import { classifyApiError } from '../hooks/classifyApiError'
import { useApi } from '../hooks/useApi'
import { ConnectionsTab } from './ConnectionsTab'
import { FamiliesTab } from './FamiliesTab'
import { KidsTab } from './KidsTab'
import { UsersTab } from './UsersTab'
import { makeUserManagementApi } from './userManagementApi'
import type {
  AdminProfileView,
  FamilyConnectionView,
  FamilyView,
  UserView,
} from '../client/types.gen'

const TABS = ['users', 'kids', 'families', 'connections'] as const
type TabKey = (typeof TABS)[number]

const TAB_LABELS: Record<TabKey, string> = {
  users: 'Guardians & admins',
  kids: 'Kids',
  families: 'Families',
  connections: 'Family connections',
}

interface Loaded {
  users: UserView[]
  profiles: AdminProfileView[]
  families: FamilyView[]
  connections: FamilyConnectionView[]
}

type LoadState =
  { kind: 'loading' } | { kind: 'error'; message: string } | { kind: 'ready'; data: Loaded }

/**
 * Admin console page for managing every account type in the app: guardians,
 * admins, kid profiles, families, and the directional family-connection
 * allowlist that a future recommendation feature will read (WS-J). Four
 * tabs share one initial load; each tab mutates through
 * `userManagementApi.ts` and reports back here to refresh all four lists,
 * since a family rename/create affects the dropdowns on every other tab.
 */
export function UserManagementPage() {
  const api = useApi()
  const userManagementApi = useMemo(() => makeUserManagementApi(api), [api])

  const [tab, setTab] = useState<TabKey>('users')
  const [state, setState] = useState<LoadState>({ kind: 'loading' })

  async function loadAll(): Promise<Loaded> {
    const [users, profiles, families, connections] = await Promise.all([
      userManagementApi.listUsers(),
      userManagementApi.listProfiles(),
      userManagementApi.listFamilies(),
      userManagementApi.listConnections(),
    ])
    return { users, profiles, families, connections }
  }

  // Mount-time load, matching ModerationThresholdsPage's cancelled-guard
  // idiom so an unmount before the request resolves never calls setState on
  // a gone component.
  useEffect(() => {
    let cancelled = false
    async function load() {
      try {
        const data = await loadAll()
        if (!cancelled) setState({ kind: 'ready', data })
      } catch (err) {
        console.error('user management load failed:', err instanceof Error ? err.message : err)
        if (!cancelled) {
          setState({
            kind: 'error',
            message: classifyApiError(err, {
              transient: 'We could not load the user management console. Please reload.',
            }).message,
          })
        }
      }
    }
    void load()
    return () => {
      cancelled = true
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps -- userManagementApi is memoized on api
  }, [userManagementApi])

  // Re-fetches every list after a mutation on any tab. A refresh failure
  // here must NOT replace the ready tables with the top-level error state:
  // the admin's edit already went through (or was already reported as
  // failed by the tab itself), only the on-screen lists are stale.
  async function refreshAll() {
    try {
      const data = await loadAll()
      setState({ kind: 'ready', data })
    } catch (err) {
      console.error('user management refresh failed:', err instanceof Error ? err.message : err)
      // Keep showing the previous ready data rather than blanking the page;
      // the next successful mutation's refresh will recover it.
    }
  }

  if (state.kind === 'loading') {
    return (
      <LoadingStatus />
    )
  }
  if (state.kind === 'error') {
    return (
      <p role="alert" className="console__error cyo-text-error">
        {state.message}
      </p>
    )
  }

  const { data } = state

  return (
    <main>
      <h1>User management</h1>
      <nav aria-label="User management sections">
        {TABS.map((key) => (
          <button
            key={key}
            type="button"
            aria-current={tab === key ? 'page' : undefined}
            onClick={() => setTab(key)}
          >
            {TAB_LABELS[key]}
          </button>
        ))}
      </nav>
      {tab === 'users' ? (
        <UsersTab
          api={userManagementApi}
          families={data.families}
          users={data.users}
          onChanged={refreshAll}
        />
      ) : null}
      {tab === 'kids' ? (
        <KidsTab
          api={userManagementApi}
          families={data.families}
          profiles={data.profiles}
          onChanged={refreshAll}
        />
      ) : null}
      {tab === 'families' ? (
        <FamiliesTab api={userManagementApi} families={data.families} onChanged={refreshAll} />
      ) : null}
      {tab === 'connections' ? (
        <ConnectionsTab
          api={userManagementApi}
          families={data.families}
          connections={data.connections}
          onChanged={refreshAll}
        />
      ) : null}
    </main>
  )
}
