/**
 * Adapter from the axios instance to the guardian self-service co-parent
 * invite endpoint (G14). Hand-typed like `userManagementApi.ts`: calls go
 * directly on `useApi()`'s axios instance rather than through the generated
 * SDK (`src/client/sdk.gen.ts`), so this page inherits the same
 * baseURL/auth/401-recovery every other guardian page gets from `useApi()`.
 * Only the generated *types* are reused, so the OpenAPI drift gate keeps
 * them honest.
 *
 * Complements `../admin/userManagementApi.ts`'s `createUser` (admin-mediated,
 * any family): this adapter is the guardian-initiated counterpart, hard-
 * scoped server-side to the caller's own family (api/me.py::invite_guardian).
 */

import { type AxiosInstance } from 'axios'

import type { GuardianInviteBody, UserView } from '../client/types.gen'

const INVITE_PATH = '/v1/me/family/invite-guardian'

export interface InviteGuardianApi {
  inviteGuardian(body: GuardianInviteBody): Promise<UserView>
}

export function makeInviteGuardianApi(api: AxiosInstance): InviteGuardianApi {
  return {
    async inviteGuardian(body: GuardianInviteBody): Promise<UserView> {
      const res = await api.post<UserView>(INVITE_PATH, body)
      return res.data
    },
  }
}
