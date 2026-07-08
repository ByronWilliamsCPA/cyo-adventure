import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { RequestStoryForm } from './RequestStoryForm'

const mockGet = vi.fn()
const mockPost = vi.fn()
const fakeApi = { get: mockGet, post: mockPost }
vi.mock('../hooks/useApi', () => ({
  useApi: () => fakeApi,
}))

const CHILD_A = {
  id: 'child-a',
  display_name: 'Rae',
  age_band: '8-11',
  reading_level_cap: 99,
  avatar: null,
  tts_enabled: false,
  created_at: '2026-07-04T10:00:00Z',
}
const CHILD_TEEN = {
  id: 'child-b',
  display_name: 'Sam',
  age_band: '13-16',
  reading_level_cap: 99,
  avatar: null,
  tts_enabled: false,
  created_at: '2026-07-04T10:00:00Z',
}
const FAMILY_A = { id: 'fam-a', name: 'The Ambers' }

function mockGuardianLoad(profiles: unknown[] = [CHILD_A, CHILD_TEEN]) {
  mockGet.mockImplementation((url: string) =>
    url === '/v1/profiles'
      ? Promise.resolve({ data: { profiles } })
      : Promise.reject(new Error(`unexpected GET ${url}`))
  )
}

function mockAdminLoad(families: unknown[] = [FAMILY_A]) {
  mockGet.mockImplementation((url: string) =>
    url === '/v1/admin/families'
      ? Promise.resolve({ data: { families } })
      : Promise.reject(new Error(`unexpected GET ${url}`))
  )
}

beforeEach(() => {
  mockGet.mockReset()
  mockPost.mockReset()
})

describe('RequestStoryForm', () => {
  describe('guardian mode', () => {
    it('renders a child select from listProfiles with a "No specific child" option, and no family select', async () => {
      mockGuardianLoad()
      render(<RequestStoryForm mode="guardian" />)
      const childSelect = await screen.findByLabelText(/child/i)
      expect(childSelect).toBeInTheDocument()
      expect(screen.getByRole('option', { name: 'No specific child' })).toBeInTheDocument()
      expect(screen.getByRole('option', { name: 'Rae' })).toBeInTheDocument()
      expect(screen.queryByLabelText(/family/i)).not.toBeInTheDocument()
    })

    it('caps the request text textarea at 500 characters', async () => {
      mockGuardianLoad()
      render(<RequestStoryForm mode="guardian" />)
      const textarea = await screen.findByLabelText(/what should the story be about/i)
      expect(textarea).toHaveAttribute('maxLength', '500')
    })

    it('shows a reload notice when the child list fails to load', async () => {
      mockGet.mockRejectedValue(new Error('network down'))
      render(<RequestStoryForm mode="guardian" />)
      expect(await screen.findByRole('alert')).toHaveTextContent(/could not load your children/i)
    })

    it('prefills the band select from the chosen child and keeps it editable', async () => {
      mockGuardianLoad()
      render(<RequestStoryForm mode="guardian" />)
      const childSelect = await screen.findByLabelText(/child/i)
      fireEvent.change(childSelect, { target: { value: 'child-a' } })
      const bandSelect = screen.getByLabelText<HTMLSelectElement>('Age band')
      expect(bandSelect.value).toBe('8-11')
      fireEvent.change(bandSelect, { target: { value: '5-8' } })
      expect(bandSelect.value).toBe('5-8')
    })

    it('shows the style select only for teen bands and resets it to prose when leaving one', async () => {
      mockGuardianLoad()
      render(<RequestStoryForm mode="guardian" />)
      const bandSelect = await screen.findByLabelText('Age band')
      expect(screen.queryByLabelText('Story style')).not.toBeInTheDocument()

      fireEvent.change(bandSelect, { target: { value: '13-16' } })
      const styleSelect = screen.getByLabelText<HTMLSelectElement>('Story style')
      fireEvent.change(styleSelect, { target: { value: 'gamebook' } })
      expect(styleSelect.value).toBe('gamebook')

      fireEvent.change(bandSelect, { target: { value: '8-11' } })
      expect(screen.queryByLabelText('Story style')).not.toBeInTheDocument()

      fireEvent.change(bandSelect, { target: { value: '13-16' } })
      expect(screen.getByLabelText<HTMLSelectElement>('Story style').value).toBe('prose')
    })

    it('resets the story style to prose when selecting a child moves the band out of the teen set', async () => {
      mockGuardianLoad()
      render(<RequestStoryForm mode="guardian" />)
      const childSelect = await screen.findByLabelText(/child/i)
      const bandSelect = screen.getByLabelText<HTMLSelectElement>('Age band')

      fireEvent.change(bandSelect, { target: { value: '13-16' } })
      fireEvent.change(screen.getByLabelText<HTMLSelectElement>('Story style'), {
        target: { value: 'gamebook' },
      })

      fireEvent.change(childSelect, { target: { value: 'child-a' } })
      expect(bandSelect.value).toBe('8-11')
      expect(screen.queryByLabelText('Story style')).not.toBeInTheDocument()

      fireEvent.change(bandSelect, { target: { value: '13-16' } })
      expect(screen.getByLabelText<HTMLSelectElement>('Story style').value).toBe('prose')
    })

    it('disables submit until text, band and length are set, then posts the expected body and shows the success notice', async () => {
      mockGuardianLoad()
      mockPost.mockResolvedValue({
        data: { id: 'req-1', status: 'approved', concept_id: 'concept-1' },
      })
      render(<RequestStoryForm mode="guardian" />)
      const childSelect = await screen.findByLabelText(/child/i)
      const submitButton = screen.getByRole('button', { name: /send request/i })
      expect(submitButton).toBeDisabled()

      fireEvent.change(childSelect, { target: { value: 'child-a' } })
      fireEvent.change(screen.getByLabelText(/what should the story be about/i), {
        target: { value: 'A story about a brave fox' },
      })
      expect(submitButton).toBeDisabled()
      fireEvent.change(screen.getByLabelText('Story length'), { target: { value: 'medium' } })
      expect(submitButton).toBeEnabled()

      fireEvent.click(submitButton)
      await waitFor(() =>
        expect(mockPost).toHaveBeenCalledWith('/v1/story-requests/authored', {
          request_text: 'A story about a brave fox',
          age_band: '8-11',
          length: 'medium',
          narrative_style: 'prose',
          profile_id: 'child-a',
        })
      )
      expect(await screen.findByRole('status')).toHaveTextContent(
        /approved and sent for authoring/i
      )
    })

    it('double-clicking Send request results in exactly one POST call', async () => {
      mockGuardianLoad()
      let resolvePost: (value: { data: unknown }) => void = () => {}
      mockPost.mockImplementation(
        () =>
          new Promise((resolve) => {
            resolvePost = resolve
          })
      )
      render(<RequestStoryForm mode="guardian" />)
      await screen.findByLabelText(/child/i)
      fireEvent.change(screen.getByLabelText(/what should the story be about/i), {
        target: { value: 'A story about a brave fox' },
      })
      fireEvent.change(screen.getByLabelText('Age band'), { target: { value: '8-11' } })
      fireEvent.change(screen.getByLabelText('Story length'), { target: { value: 'medium' } })

      const submitButton = screen.getByRole('button', { name: /send request/i })
      fireEvent.click(submitButton)
      fireEvent.click(submitButton)
      expect(mockPost).toHaveBeenCalledTimes(1)
      resolvePost({
        data: { id: 'req-1', status: 'approved', concept_id: 'concept-1' },
      })
      expect(await screen.findByRole('status')).toHaveTextContent(
        /approved and sent for authoring/i
      )
    })

    it('shows the blocked notice instead of the success notice when the response status is blocked', async () => {
      mockGuardianLoad()
      mockPost.mockResolvedValue({ data: { id: 'req-1', status: 'blocked', concept_id: null } })
      render(<RequestStoryForm mode="guardian" />)
      await screen.findByLabelText(/child/i)
      fireEvent.change(screen.getByLabelText(/what should the story be about/i), {
        target: { value: 'A scary story' },
      })
      fireEvent.change(screen.getByLabelText('Age band'), { target: { value: '8-11' } })
      fireEvent.change(screen.getByLabelText('Story length'), { target: { value: 'medium' } })
      fireEvent.click(screen.getByRole('button', { name: /send request/i }))
      expect(await screen.findByRole('alert')).toHaveTextContent(/did not pass/i)
      expect(screen.queryByText(/approved and sent for authoring/i)).not.toBeInTheDocument()
    })

    it('shows a transient error alert and re-enables submit when the create call rejects', async () => {
      mockGuardianLoad()
      mockPost.mockRejectedValueOnce(new Error('network down'))
      render(<RequestStoryForm mode="guardian" />)
      await screen.findByLabelText(/child/i)
      fireEvent.change(screen.getByLabelText(/what should the story be about/i), {
        target: { value: 'A story about a brave fox' },
      })
      fireEvent.change(screen.getByLabelText('Age band'), { target: { value: '8-11' } })
      fireEvent.change(screen.getByLabelText('Story length'), { target: { value: 'medium' } })

      const submitButton = screen.getByRole('button', { name: /send request/i })
      fireEvent.click(submitButton)

      expect(await screen.findByRole('alert')).toHaveTextContent(
        'We could not send this request. Please try again.'
      )
      expect(submitButton).toBeEnabled()
    })
  })

  describe('admin mode', () => {
    it('renders a required family select from listFamilies, no child select, and keeps submit disabled until a family is chosen', async () => {
      mockAdminLoad()
      mockPost.mockResolvedValue({
        data: { id: 'req-2', status: 'approved', concept_id: 'concept-2' },
      })
      render(<RequestStoryForm mode="admin" />)
      const familySelect = await screen.findByLabelText<HTMLSelectElement>(/family/i)
      expect(familySelect).toBeRequired()
      expect(screen.getByRole('option', { name: 'The Ambers' })).toBeInTheDocument()
      expect(screen.queryByLabelText(/child/i)).not.toBeInTheDocument()

      const submitButton = screen.getByRole('button', { name: /send request/i })
      fireEvent.change(screen.getByLabelText(/what should the story be about/i), {
        target: { value: 'A story about a brave fox' },
      })
      fireEvent.change(screen.getByLabelText('Age band'), { target: { value: '8-11' } })
      fireEvent.change(screen.getByLabelText('Story length'), { target: { value: 'medium' } })
      expect(submitButton).toBeDisabled()

      fireEvent.change(familySelect, { target: { value: 'fam-a' } })
      expect(submitButton).toBeEnabled()

      fireEvent.click(submitButton)
      await waitFor(() =>
        expect(mockPost).toHaveBeenCalledWith('/v1/story-requests/authored', {
          request_text: 'A story about a brave fox',
          age_band: '8-11',
          length: 'medium',
          narrative_style: 'prose',
          family_id: 'fam-a',
        })
      )
    })
  })
})
