import { act, renderHook } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

import type { ReviewSurface } from '../guardian/reviewApi'
import type { PassageEditApi } from './passageEditApi'
import { usePassageEdit } from './usePassageEdit'

const SURFACE: ReviewSurface = {
  storybook_id: 's1',
  version: 1,
  status: 'in_review',
  screened: true,
  summary: null,
  blob: {
    nodes: [
      {
        id: 'n1',
        body: 'A dark cave yawned ahead.',
        choices: [{ id: 'c1', label: 'Step inside', target: 'n2' }],
      },
    ],
  },
  flagged_passages: [],
  story_level_findings: [],
}

function makePassageEditApi(overrides: Partial<PassageEditApi> = {}): PassageEditApi {
  return {
    editNode: vi.fn(),
    ...overrides,
  }
}

describe('usePassageEdit', () => {
  it('reports editingDisabled when the surface has not loaded yet', () => {
    const { result } = renderHook(() =>
      usePassageEdit({
        storybookId: 's1',
        surface: null,
        passageEditApi: makePassageEditApi(),
        onSurfaceRefreshed: vi.fn(),
      })
    )
    expect(result.current.editingDisabled).toBe(true)
  })

  it('reports editingDisabled for a published surface, enabled for in_review/needs_revision', () => {
    const { result, rerender } = renderHook(
      ({ surface }: { surface: ReviewSurface }) =>
        usePassageEdit({
          storybookId: 's1',
          surface,
          passageEditApi: makePassageEditApi(),
          onSurfaceRefreshed: vi.fn(),
        }),
      { initialProps: { surface: { ...SURFACE, status: 'published' } } }
    )
    expect(result.current.editingDisabled).toBe(true)
    rerender({ surface: { ...SURFACE, status: 'needs_revision' } })
    expect(result.current.editingDisabled).toBe(false)
  })

  it('does nothing when opening an edit dialog before the surface has loaded', () => {
    const { result } = renderHook(() =>
      usePassageEdit({
        storybookId: 's1',
        surface: null,
        passageEditApi: makePassageEditApi(),
        onSurfaceRefreshed: vi.fn(),
      })
    )
    act(() => result.current.openEditDialog('n1'))
    expect(result.current.editNodeId).toBeNull()
  })

  it('does nothing when opening an edit dialog for a node id not in the blob', () => {
    const { result } = renderHook(() =>
      usePassageEdit({
        storybookId: 's1',
        surface: SURFACE,
        passageEditApi: makePassageEditApi(),
        onSurfaceRefreshed: vi.fn(),
      })
    )
    act(() => result.current.openEditDialog('does-not-exist'))
    expect(result.current.editNodeId).toBeNull()
  })

  it('opens the dialog prefilled with the node body and choices', () => {
    const { result } = renderHook(() =>
      usePassageEdit({
        storybookId: 's1',
        surface: SURFACE,
        passageEditApi: makePassageEditApi(),
        onSurfaceRefreshed: vi.fn(),
      })
    )
    act(() => result.current.openEditDialog('n1'))
    expect(result.current.editNodeId).toBe('n1')
    expect(result.current.editBody).toBe('A dark cave yawned ahead.')
    expect(result.current.editChoices).toEqual([{ id: 'c1', label: 'Step inside', target: 'n2' }])
  })

  it('updates only the matching choice label, leaving others untouched', () => {
    const surfaceWithTwoChoices: ReviewSurface = {
      ...SURFACE,
      blob: {
        nodes: [
          {
            id: 'n1',
            body: 'Body.',
            choices: [
              { id: 'c1', label: 'First', target: 'n2' },
              { id: 'c2', label: 'Second', target: 'n3' },
            ],
          },
        ],
      },
    }
    const { result } = renderHook(() =>
      usePassageEdit({
        storybookId: 's1',
        surface: surfaceWithTwoChoices,
        passageEditApi: makePassageEditApi(),
        onSurfaceRefreshed: vi.fn(),
      })
    )
    act(() => result.current.openEditDialog('n1'))
    act(() => result.current.setEditChoiceLabel('c2', 'Second (edited)'))
    expect(result.current.editChoices).toEqual([
      { id: 'c1', label: 'First', target: 'n2' },
      { id: 'c2', label: 'Second (edited)', target: 'n3' },
    ])
  })

  it('does nothing on save when no edit dialog is open', async () => {
    const editNode = vi.fn()
    const { result } = renderHook(() =>
      usePassageEdit({
        storybookId: 's1',
        surface: SURFACE,
        passageEditApi: makePassageEditApi({ editNode }),
        onSurfaceRefreshed: vi.fn(),
      })
    )
    await act(async () => {
      await result.current.saveEdit()
    })
    expect(editNode).not.toHaveBeenCalled()
  })

  it('does nothing on save if the surface becomes unavailable after the dialog opened', async () => {
    const editNode = vi.fn()
    const initialProps: { surface: ReviewSurface | null } = { surface: SURFACE }
    const { result, rerender } = renderHook(
      ({ surface }: { surface: ReviewSurface | null }) =>
        usePassageEdit({
          storybookId: 's1',
          surface,
          passageEditApi: makePassageEditApi({ editNode }),
          onSurfaceRefreshed: vi.fn(),
        }),
      { initialProps }
    )
    act(() => result.current.openEditDialog('n1'))
    expect(result.current.editNodeId).toBe('n1')
    rerender({ surface: null })
    await act(async () => {
      await result.current.saveEdit()
    })
    expect(editNode).not.toHaveBeenCalled()
  })

  it('saves an edit, feeds the refreshed surface up, and closes the dialog', async () => {
    const refreshed: ReviewSurface = { ...SURFACE, blob: { nodes: [] } }
    const editNode = vi.fn().mockResolvedValue(refreshed)
    const onSurfaceRefreshed = vi.fn()
    const { result } = renderHook(() =>
      usePassageEdit({
        storybookId: 's1',
        surface: SURFACE,
        passageEditApi: makePassageEditApi({ editNode }),
        onSurfaceRefreshed,
      })
    )
    act(() => result.current.openEditDialog('n1'))
    act(() => result.current.setEditBody('New body.'))
    await act(async () => {
      await result.current.saveEdit()
    })
    expect(editNode).toHaveBeenCalledWith('s1', 1, 'n1', {
      body: 'New body.',
      choice_labels: { c1: 'Step inside' },
    })
    expect(onSurfaceRefreshed).toHaveBeenCalledWith(refreshed)
    expect(result.current.editNodeId).toBeNull()
  })

  it('surfaces gate findings on a 422 gate failure without closing the dialog', async () => {
    const editNode = vi.fn().mockRejectedValue({
      isAxiosError: true,
      response: {
        status: 422,
        data: {
          message: 'edited passage failed the validation gate',
          details: { findings: [{ rule_id: 'L1-7', message: 'node/word budget exceeded' }] },
        },
      },
    })
    const errorSpy = vi.spyOn(console, 'error').mockImplementation(() => undefined)
    const { result } = renderHook(() =>
      usePassageEdit({
        storybookId: 's1',
        surface: SURFACE,
        passageEditApi: makePassageEditApi({ editNode }),
        onSurfaceRefreshed: vi.fn(),
      })
    )
    act(() => result.current.openEditDialog('n1'))
    await act(async () => {
      await result.current.saveEdit()
    })
    expect(result.current.editNodeId).toBe('n1')
    expect(result.current.editGateFindings).toEqual([
      { rule_id: 'L1-7', message: 'node/word budget exceeded' },
    ])
    expect(result.current.editSubmitting).toBe(false)
    errorSpy.mockRestore()
  })

  it('surfaces a generic error for a non-gate failure', async () => {
    const editNode = vi.fn().mockRejectedValue({ isAxiosError: true, response: { status: 500 } })
    const errorSpy = vi.spyOn(console, 'error').mockImplementation(() => undefined)
    const { result } = renderHook(() =>
      usePassageEdit({
        storybookId: 's1',
        surface: SURFACE,
        passageEditApi: makePassageEditApi({ editNode }),
        onSurfaceRefreshed: vi.fn(),
      })
    )
    act(() => result.current.openEditDialog('n1'))
    await act(async () => {
      await result.current.saveEdit()
    })
    expect(result.current.editError).toBe('We could not save this edit. Please try again.')
    expect(result.current.editGateFindings).toBeNull()
    errorSpy.mockRestore()
  })

  it('resets error/gate-finding state on close', async () => {
    const editNode = vi.fn().mockRejectedValue({ isAxiosError: true, response: { status: 500 } })
    const errorSpy = vi.spyOn(console, 'error').mockImplementation(() => undefined)
    const { result } = renderHook(() =>
      usePassageEdit({
        storybookId: 's1',
        surface: SURFACE,
        passageEditApi: makePassageEditApi({ editNode }),
        onSurfaceRefreshed: vi.fn(),
      })
    )
    act(() => result.current.openEditDialog('n1'))
    await act(async () => {
      await result.current.saveEdit()
    })
    expect(result.current.editError).not.toBeNull()
    act(() => result.current.closeEditDialog())
    expect(result.current.editNodeId).toBeNull()
    expect(result.current.editError).toBeNull()
    errorSpy.mockRestore()
  })
})
