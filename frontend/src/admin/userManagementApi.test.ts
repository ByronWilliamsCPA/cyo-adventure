import { describe, expect, it, vi } from 'vitest'

import { makeUserManagementApi } from './userManagementApi'

function fakeAxios() {
  return {
    get: vi.fn(),
    post: vi.fn(),
    patch: vi.fn(),
    delete: vi.fn(),
  }
}

describe('makeUserManagementApi', () => {
  describe('users', () => {
    it('lists users with no family filter', async () => {
      const api = fakeAxios()
      api.get.mockResolvedValue({ data: { users: [{ id: 'u1' }] } })
      const result = await makeUserManagementApi(api as never).listUsers()
      expect(api.get).toHaveBeenCalledWith('/v1/admin/users', { params: undefined })
      expect(result).toEqual([{ id: 'u1' }])
    })

    it('lists users scoped to a family', async () => {
      const api = fakeAxios()
      api.get.mockResolvedValue({ data: { users: [] } })
      await makeUserManagementApi(api as never).listUsers('fam-a')
      expect(api.get).toHaveBeenCalledWith('/v1/admin/users', {
        params: { family_id: 'fam-a' },
      })
    })

    it('creates a user invite', async () => {
      const api = fakeAxios()
      api.post.mockResolvedValue({ data: { id: 'u2' } })
      const body = { email: 'a@example.com', family_id: 'fam-a', role: 'guardian' as const }
      const result = await makeUserManagementApi(api as never).createUser(body)
      expect(api.post).toHaveBeenCalledWith('/v1/admin/users', body)
      expect(result.id).toBe('u2')
    })

    it('updates a user', async () => {
      const api = fakeAxios()
      api.patch.mockResolvedValue({ data: { id: 'u1', status: 'deactivated' } })
      const result = await makeUserManagementApi(api as never).updateUser('u1', {
        status: 'deactivated',
      })
      expect(api.patch).toHaveBeenCalledWith('/v1/admin/users/u1', { status: 'deactivated' })
      expect(result.status).toBe('deactivated')
    })
  })

  describe('profiles', () => {
    it('lists profiles with no family filter', async () => {
      const api = fakeAxios()
      api.get.mockResolvedValue({ data: { profiles: [{ id: 'p1' }] } })
      const result = await makeUserManagementApi(api as never).listProfiles()
      expect(api.get).toHaveBeenCalledWith('/v1/admin/profiles', { params: undefined })
      expect(result).toEqual([{ id: 'p1' }])
    })

    it('lists profiles scoped to a family', async () => {
      const api = fakeAxios()
      api.get.mockResolvedValue({ data: { profiles: [] } })
      await makeUserManagementApi(api as never).listProfiles('fam-a')
      expect(api.get).toHaveBeenCalledWith('/v1/admin/profiles', {
        params: { family_id: 'fam-a' },
      })
    })

    it('creates a profile', async () => {
      const api = fakeAxios()
      api.post.mockResolvedValue({ data: { id: 'p2' } })
      const body = { family_id: 'fam-a', display_name: 'Kid', age_band: '5-8' as const }
      const result = await makeUserManagementApi(api as never).createProfile(body)
      expect(api.post).toHaveBeenCalledWith('/v1/admin/profiles', body)
      expect(result.id).toBe('p2')
    })

    it('updates a profile', async () => {
      const api = fakeAxios()
      api.patch.mockResolvedValue({ data: { id: 'p1', status: 'active' } })
      const result = await makeUserManagementApi(api as never).updateProfile('p1', {
        status: 'active',
      })
      expect(api.patch).toHaveBeenCalledWith('/v1/admin/profiles/p1', { status: 'active' })
      expect(result.status).toBe('active')
    })
  })

  describe('families', () => {
    it('lists families', async () => {
      const api = fakeAxios()
      api.get.mockResolvedValue({ data: { families: [{ id: 'fam-a' }] } })
      const result = await makeUserManagementApi(api as never).listFamilies()
      expect(api.get).toHaveBeenCalledWith('/v1/admin/families')
      expect(result).toEqual([{ id: 'fam-a' }])
    })

    it('creates a family', async () => {
      const api = fakeAxios()
      api.post.mockResolvedValue({ data: { id: 'fam-b', name: 'New' } })
      const result = await makeUserManagementApi(api as never).createFamily({ name: 'New' })
      expect(api.post).toHaveBeenCalledWith('/v1/admin/families', { name: 'New' })
      expect(result.name).toBe('New')
    })

    it('updates a family', async () => {
      const api = fakeAxios()
      api.patch.mockResolvedValue({ data: { id: 'fam-a', status: 'deactivated' } })
      const result = await makeUserManagementApi(api as never).updateFamily('fam-a', {
        status: 'deactivated',
      })
      expect(api.patch).toHaveBeenCalledWith('/v1/admin/families/fam-a', {
        status: 'deactivated',
      })
      expect(result.status).toBe('deactivated')
    })
  })

  describe('family connections', () => {
    it('lists connections', async () => {
      const api = fakeAxios()
      api.get.mockResolvedValue({ data: { connections: [{ id: 'c1' }] } })
      const result = await makeUserManagementApi(api as never).listConnections()
      expect(api.get).toHaveBeenCalledWith('/v1/admin/family-connections')
      expect(result).toEqual([{ id: 'c1' }])
    })

    it('creates a connection', async () => {
      const api = fakeAxios()
      api.post.mockResolvedValue({ data: { id: 'c2' } })
      const body = { family_id: 'fam-a', connected_family_id: 'fam-b' }
      const result = await makeUserManagementApi(api as never).createConnection(body)
      expect(api.post).toHaveBeenCalledWith('/v1/admin/family-connections', body)
      expect(result.id).toBe('c2')
    })

    it('deletes a connection', async () => {
      const api = fakeAxios()
      api.delete.mockResolvedValue({ data: undefined })
      await makeUserManagementApi(api as never).deleteConnection('c1')
      expect(api.delete).toHaveBeenCalledWith('/v1/admin/family-connections/c1')
    })
  })
})
