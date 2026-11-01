/**
 * Adapter from the axios instance to the guardian self-service family
 * deletion endpoint (GDPR Article 17 / COPPA 312.10, PROJECT-PLAN Phase 7).
 * Hand-typed like `inviteGuardianApi.ts`: the call goes straight through
 * `useApi()`'s axios instance so it inherits the same baseURL, auth, and
 * 401-recovery as every other guardian page. The endpoint answers 204 with no
 * body, so there is no response type to reuse from the generated client.
 *
 * Server side: `api/me.py::delete_my_family` erases every family-owned row by
 * cascade and queues the R2 cover and Supabase Auth identity purge for after
 * the commit (`erasure.py`).
 */

import { type AxiosInstance } from 'axios'

const FAMILY_PATH = '/v1/me/family'

export interface FamilyDeletionApi {
  deleteMyFamily(): Promise<void>
}

export function makeFamilyDeletionApi(api: AxiosInstance): FamilyDeletionApi {
  return {
    async deleteMyFamily(): Promise<void> {
      await api.delete(FAMILY_PATH)
    },
  }
}
