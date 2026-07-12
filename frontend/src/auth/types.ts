export type Role = 'guardian' | 'child' | 'admin'

const ROLES: readonly Role[] = ['guardian', 'child', 'admin']

/**
 * Runtime guard for the closed {@link Role} set. The backend `/v1/me` `role`
 * field is a trust-boundary string; validate it rather than casting blindly so
 * an unexpected value fails closed (treated as not-a-role) instead of producing
 * a Principal with an unauthorized role.
 */
export function isRole(value: unknown): value is Role {
  return typeof value === 'string' && (ROLES as readonly string[]).includes(value)
}

export interface Principal {
  subject: string
  /**
   * The base persona from `/v1/me` (`role`). One adult can be a guardian, an
   * admin, or both: `role` stays the persona ('guardian' for anyone with
   * family guardianship, 'admin' for an admin-only adult) and the orthogonal
   * {@link isAdmin} capability decides admin-console access, mirroring the
   * backend's `Principal.is_admin` (api/deps.py).
   */
  role: Role
  /** The global admin capability (`/v1/me` `is_admin`), orthogonal to role. */
  isAdmin: boolean
  familyId: string
  profileIds: string[]
}
