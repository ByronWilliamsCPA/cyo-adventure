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
  role: Role
  familyId: string
  profileIds: string[]
}
