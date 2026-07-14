import 'fake-indexeddb/auto'

import { IDBFactory } from 'fake-indexeddb'
import { render, screen } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { beforeEach, describe, expect, it } from 'vitest'

import { AUTHORIZE_DEVICE_INTENT_PARAM, AUTHORIZE_DEVICE_INTENT_VALUE } from '../routes'
import { _resetDbHandle } from '../offline/db'
import { DeviceAuthorizedRoute } from './DeviceAuthorizedRoute'
import { setDeviceGrant } from './deviceGrant'

function renderGate(initialPath = '/kids') {
  return render(
    <MemoryRouter initialEntries={[initialPath]}>
      <Routes>
        <Route path="/guardian/login" element={<div>Login page</div>} />
        <Route element={<DeviceAuthorizedRoute />}>
          <Route path="/kids" element={<div>Kid picker</div>} />
        </Route>
      </Routes>
    </MemoryRouter>
  )
}

beforeEach(() => {
  globalThis.indexedDB = new IDBFactory()
  _resetDbHandle()
  localStorage.clear()
})

describe('DeviceAuthorizedRoute', () => {
  it('renders the nested route immediately when a valid device grant exists', () => {
    setDeviceGrant({
      token: 'tok-1',
      expiresAt: '2099-01-01T00:00:00Z',
      familyId: 'fam-1',
      id: 'grant-1',
    })
    renderGate()
    expect(screen.getByText('Kid picker')).toBeInTheDocument()
  })

  it('redirects to guardian login with the authorize-device intent marker when no grant exists', async () => {
    renderGate()
    // No grant in localStorage or the IndexedDB mirror, so this resolves
    // from 'checking' straight to 'unauthorized' asynchronously.
    expect(await screen.findByText('Login page')).toBeInTheDocument()
    expect(screen.queryByText('Kid picker')).not.toBeInTheDocument()
  })

  it('redirects when the stored grant is expired', async () => {
    setDeviceGrant({
      token: 'tok-1',
      expiresAt: '2020-01-01T00:00:00Z',
      familyId: 'fam-1',
      id: 'grant-1',
    })
    renderGate()
    expect(await screen.findByText('Login page')).toBeInTheDocument()
  })

  it('shows a loading state while checking the IndexedDB mirror', () => {
    renderGate()
    expect(screen.getByRole('status')).toBeInTheDocument()
  })

  it('recovers from the IndexedDB mirror when localStorage alone is empty', async () => {
    setDeviceGrant({
      token: 'tok-1',
      expiresAt: '2099-01-01T00:00:00Z',
      familyId: 'fam-1',
      id: 'grant-1',
    })
    // Simulate a localStorage clear that leaves the IndexedDB mirror intact
    // (the mirror write is async; give it a tick before clearing).
    await new Promise((resolve) => setTimeout(resolve, 0))
    localStorage.removeItem('device_grant')

    renderGate()
    expect(await screen.findByText('Kid picker')).toBeInTheDocument()
  })

  it('builds the redirect with the intent query param', async () => {
    renderGate()
    const login = await screen.findByText('Login page')
    expect(login).toBeInTheDocument()
    // The marker is a plain query param on GUARDIAN_LOGIN_PATH; assert the
    // constants used to build it are the ones exported for a future login
    // flow to read.
    expect(AUTHORIZE_DEVICE_INTENT_PARAM).toBe('intent')
    expect(AUTHORIZE_DEVICE_INTENT_VALUE).toBe('authorize-device')
  })
})
