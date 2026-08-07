import { type AxiosInstance } from 'axios'

import type {
  CharacterCreateBody,
  CharacterListView,
  CharacterUpdateBody,
  CharacterView,
} from '../client/types.gen'

const CHARACTERS_PATH = '/v1/characters'

/**
 * The archetype roster (backend source of truth:
 * storybook/character_vocabulary.py::ARCHETYPE_ROSTER), in wire order.
 *
 * #CRITICAL: data integrity: this order is the backend's stored numeric code
 * for every character (position 1-6, ARCHETYPE_CODES). This list must keep
 * the same six names in the same order as the backend constant; the backend
 * assigns the code, so a mismatch here would not corrupt storage, but it
 * WOULD silently show the wrong label for whatever code an existing
 * character already carries.
 * #VERIFY: characterApi.test.ts pins this literal six-item order.
 */
export const ARCHETYPE_ROSTER = [
  'scout',
  'guardian',
  'trickster',
  'scholar',
  'healer',
  'wildheart',
] as const

export type CharacterArchetype = (typeof ARCHETYPE_ROSTER)[number]

/**
 * The `look` catalog (backend: api/schemas.py::CharacterLook,
 * `^avatar_(0[1-9]|1[0-2])$`): twelve ids, avatar_01 through avatar_12. This
 * is a distinct catalog from the profile-level named avatar ids in
 * profiles/avatars.ts (fox, owl, dragon, ...); the two must never be confused.
 */
export const CHARACTER_LOOKS: readonly string[] = Array.from(
  { length: 12 },
  (_, index) => `avatar_${String(index + 1).padStart(2, '0')}`
)

/**
 * Backend bound on CharacterName (api/schemas.py): 1-32 characters,
 * NFC-normalized server-side. This constant exists so the creator's
 * client-side length check and its message can never drift from the number
 * the server actually enforces.
 */
export const CHARACTER_NAME_MAX_LENGTH = 32

export interface CharactersApi {
  list(profileId: string): Promise<CharacterView[]>
  create(body: CharacterCreateBody): Promise<CharacterView>
  update(characterId: string, body: CharacterUpdateBody): Promise<CharacterView>
  activate(characterId: string): Promise<CharacterView>
  retire(characterId: string): Promise<CharacterView>
  remove(characterId: string): Promise<void>
}

/**
 * Adapter from the axios instance to `/v1/characters` (Task 2's six routes).
 * Hand-typed like inviteGuardianApi.ts: calls go directly on `useApi()`'s
 * axios instance rather than through the generated SDK
 * (`src/client/sdk.gen.ts`), so this page inherits the same
 * baseURL/auth/401-recovery every other kid/guardian adapter gets from
 * `useApi()`. Only the generated *types* are reused, so the OpenAPI drift
 * gate keeps them honest; there is no hand-written request/response shape
 * here beyond this thin routing.
 *
 * #ASSUME: data integrity: `list()` returns `res.data.characters` (the
 * `CharacterListView` envelope), documented active-first by the backend, but
 * callers must not rely on array order to find the active one; they should
 * check `is_active` explicitly (see useActiveCharacter.ts).
 * #VERIFY: characterApi.test.ts asserts the request shape for every method.
 */
export function makeCharactersApi(api: AxiosInstance): CharactersApi {
  return {
    async list(profileId: string): Promise<CharacterView[]> {
      const res = await api.get<CharacterListView>(CHARACTERS_PATH, {
        params: { profile_id: profileId },
      })
      return res.data.characters
    },
    async create(body: CharacterCreateBody): Promise<CharacterView> {
      const res = await api.post<CharacterView>(CHARACTERS_PATH, body)
      return res.data
    },
    async update(characterId: string, body: CharacterUpdateBody): Promise<CharacterView> {
      const res = await api.patch<CharacterView>(`${CHARACTERS_PATH}/${characterId}`, body)
      return res.data
    },
    async activate(characterId: string): Promise<CharacterView> {
      const res = await api.post<CharacterView>(`${CHARACTERS_PATH}/${characterId}/activate`)
      return res.data
    },
    async retire(characterId: string): Promise<CharacterView> {
      const res = await api.post<CharacterView>(`${CHARACTERS_PATH}/${characterId}/retire`)
      return res.data
    },
    async remove(characterId: string): Promise<void> {
      await api.delete(`${CHARACTERS_PATH}/${characterId}`)
    },
  }
}
