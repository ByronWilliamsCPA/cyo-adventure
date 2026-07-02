export type Role = 'guardian' | 'child' | 'admin'

export interface Principal {
  subject: string
  role: Role
  familyId: string
  profileIds: string[]
}
