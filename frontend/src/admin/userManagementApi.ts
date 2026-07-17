/**
 * Adapter from the axios instance to the WS-J admin user-management API
 * (guardians/admins, kid profiles, families, family connections). Hand-typed
 * like `moderationThresholdsApi.ts`: calls go directly on `useApi()`'s axios
 * instance rather than through the generated SDK (`src/client/sdk.gen.ts`),
 * so this page inherits the same baseURL/auth/401-recovery every other admin
 * page gets from `useApi()`. Only the generated *types* are reused, so the
 * OpenAPI drift gate keeps them honest.
 */

import { type AxiosInstance } from 'axios'

import type {
  AdminProfileCreateBody,
  AdminProfileListView,
  AdminProfileUpdateBody,
  AdminProfileView,
  FamilyConnectionCreateBody,
  FamilyConnectionListView,
  FamilyConnectionView,
  FamilyCreateBody,
  FamilyListView,
  FamilyUpdateBody,
  FamilyView,
  UserCreateBody,
  UserListView,
  UserUpdateBody,
  UserView,
} from '../client/types.gen'

const USERS_PATH = '/v1/admin/users'
const PROFILES_PATH = '/v1/admin/profiles'
const FAMILIES_PATH = '/v1/admin/families'
const CONNECTIONS_PATH = '/v1/admin/family-connections'

export interface UserManagementApi {
  listUsers(familyId?: string): Promise<UserView[]>
  createUser(body: UserCreateBody): Promise<UserView>
  updateUser(id: string, body: UserUpdateBody): Promise<UserView>

  listProfiles(familyId?: string): Promise<AdminProfileView[]>
  createProfile(body: AdminProfileCreateBody): Promise<AdminProfileView>
  updateProfile(id: string, body: AdminProfileUpdateBody): Promise<AdminProfileView>

  listFamilies(): Promise<FamilyView[]>
  createFamily(body: FamilyCreateBody): Promise<FamilyView>
  updateFamily(id: string, body: FamilyUpdateBody): Promise<FamilyView>

  listConnections(): Promise<FamilyConnectionView[]>
  createConnection(body: FamilyConnectionCreateBody): Promise<FamilyConnectionView>
  deleteConnection(id: string): Promise<void>
}

export function makeUserManagementApi(api: AxiosInstance): UserManagementApi {
  return {
    async listUsers(familyId?: string): Promise<UserView[]> {
      const res = await api.get<UserListView>(USERS_PATH, {
        params: familyId ? { family_id: familyId } : undefined,
      })
      return res.data.users
    },
    async createUser(body: UserCreateBody): Promise<UserView> {
      const res = await api.post<UserView>(USERS_PATH, body)
      return res.data
    },
    async updateUser(id: string, body: UserUpdateBody): Promise<UserView> {
      const res = await api.patch<UserView>(`${USERS_PATH}/${id}`, body)
      return res.data
    },

    async listProfiles(familyId?: string): Promise<AdminProfileView[]> {
      const res = await api.get<AdminProfileListView>(PROFILES_PATH, {
        params: familyId ? { family_id: familyId } : undefined,
      })
      return res.data.profiles
    },
    async createProfile(body: AdminProfileCreateBody): Promise<AdminProfileView> {
      const res = await api.post<AdminProfileView>(PROFILES_PATH, body)
      return res.data
    },
    async updateProfile(id: string, body: AdminProfileUpdateBody): Promise<AdminProfileView> {
      const res = await api.patch<AdminProfileView>(`${PROFILES_PATH}/${id}`, body)
      return res.data
    },

    async listFamilies(): Promise<FamilyView[]> {
      const res = await api.get<FamilyListView>(FAMILIES_PATH)
      return res.data.families
    },
    async createFamily(body: FamilyCreateBody): Promise<FamilyView> {
      const res = await api.post<FamilyView>(FAMILIES_PATH, body)
      return res.data
    },
    async updateFamily(id: string, body: FamilyUpdateBody): Promise<FamilyView> {
      const res = await api.patch<FamilyView>(`${FAMILIES_PATH}/${id}`, body)
      return res.data
    },

    async listConnections(): Promise<FamilyConnectionView[]> {
      const res = await api.get<FamilyConnectionListView>(CONNECTIONS_PATH)
      return res.data.connections
    },
    async createConnection(body: FamilyConnectionCreateBody): Promise<FamilyConnectionView> {
      const res = await api.post<FamilyConnectionView>(CONNECTIONS_PATH, body)
      return res.data
    },
    async deleteConnection(id: string): Promise<void> {
      await api.delete(`${CONNECTIONS_PATH}/${id}`)
    },
  }
}
