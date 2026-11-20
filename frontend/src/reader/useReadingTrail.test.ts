import { renderHook } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'

import type { ReadingTrailBatchBody } from '../client/types.gen'
import type { ReadingTrailApi } from '../offline/sync'
import { emitReaderTransition } from '../player/transitions'
import type { ReadingState, Storybook } from '../player/types'
import { TRAIL_FLUSH_INTERVAL_MS, useReadingTrail } from './useReadingTrail'

const STORY: Storybook = {
  schema_version: '1',
  id: 's',
  version: 1,
  title: 'T',
  metadata: {},
  start_node: 'a',
  nodes: [
    {
      id: 'a',
      body: '',
      is_ending: false,
      choices: [
        { id: 'c1', label: 'one', target: 'b' },
        { id: 'c2', label: 'two', target: 'b' },
      ],
    },
    { id: 'b', body: '', is_ending: false, choices: [] },
  ],
}

const AT_B: ReadingState = {
  current_node: 'b',
  var_state: {},
  path: ['a', 'b'],
  visit_set: ['a', 'b'],
  version: 1,
  state_revision: 0,
  save_slots: {},
}

function makeApi() {
  const calls: Array<{ body: ReadingTrailBatchBody; keepalive?: boolean }> = []
  const api: ReadingTrailApi = {
    postBatch: vi.fn(
      (_p: string, _s: string, body: ReadingTrailBatchBody, options?: { keepalive?: boolean }) => {
        calls.push({ body, keepalive: options?.keepalive })
        return Promise.resolve({ recorded: true, stored_steps: body.steps.length })
      }
    ),
  }
  return { api, calls }
}

afterEach(() => {
  vi.useRealTimers()
  vi.restoreAllMocks()
})

describe('useReadingTrail', () => {
  it('records machine transitions for its own story and flushes on leave', () => {
    const { api, calls } = makeApi()
    const { result } = renderHook(() =>
      useReadingTrail({ api, profileId: 'p1', storybookId: 's', version: 1 })
    )
    result.current.begin(STORY, undefined)
    emitReaderTransition(STORY, { type: 'choose', from: 'a', choiceId: 'c2', to: AT_B })
    // Another reader's story is ignored.
    emitReaderTransition({ ...STORY }, { type: 'choose', from: 'a', choiceId: 'c1', to: AT_B })
    result.current.observe(AT_B)
    result.current.leave()
    expect(calls).toHaveLength(1)
    expect(calls[0].keepalive).toBe(true)
    expect(calls[0].body.steps.map((s) => [s.kind, s.node_id, s.choice_id])).toEqual([
      ['start', 'a', null],
      ['choice', 'a', 'c2'],
      ['leave', 'b', null],
    ])
  })

  it('keeps one handle identity across renders', () => {
    const { api } = makeApi()
    const { result, rerender } = renderHook(() =>
      useReadingTrail({ api, profileId: 'p1', storybookId: 's', version: 1 })
    )
    const first = result.current
    rerender()
    expect(result.current).toBe(first)
  })

  it('records nothing and sends nothing without an api', () => {
    const { result, unmount } = renderHook(() =>
      useReadingTrail({ profileId: 'p1', storybookId: 's', version: 1 })
    )
    result.current.begin(STORY, undefined)
    expect(() => {
      emitReaderTransition(STORY, { type: 'back', to: AT_B })
      result.current.observe(AT_B)
      result.current.leave()
    }).not.toThrow()
    unmount()
  })

  it('flushes with keepalive when the page is hidden, without a leave marker', () => {
    const { api, calls } = makeApi()
    const { result } = renderHook(() =>
      useReadingTrail({ api, profileId: 'p1', storybookId: 's', version: 1 })
    )
    result.current.begin(STORY, undefined)
    const visibility = vi.spyOn(document, 'visibilityState', 'get').mockReturnValue('hidden')
    document.dispatchEvent(new Event('visibilitychange'))
    visibility.mockRestore()
    expect(calls).toHaveLength(1)
    expect(calls[0].keepalive).toBe(true)
    expect(calls[0].body.steps.map((s) => s.kind)).toEqual(['start'])
  })

  it('flushes on an interval and leaves on unmount', () => {
    vi.useFakeTimers()
    const { api, calls } = makeApi()
    const { result, unmount } = renderHook(() =>
      useReadingTrail({ api, profileId: 'p1', storybookId: 's', version: 1 })
    )
    result.current.begin(STORY, undefined)
    vi.advanceTimersByTime(TRAIL_FLUSH_INTERVAL_MS)
    expect(calls).toHaveLength(1)
    unmount()
    expect(calls).toHaveLength(2)
    expect(calls[1].body.steps.map((s) => s.kind)).toEqual(['leave'])
  })

  it('keeps reading when the recorder cannot start', () => {
    const { api } = makeApi()
    const warn = vi.spyOn(console, 'warn').mockImplementation(() => {})
    const { result } = renderHook(() =>
      useReadingTrail({ api, profileId: 'p1', storybookId: 's', version: 1 })
    )
    const broken = { ...STORY, nodes: null } as unknown as Storybook
    expect(() => result.current.begin(broken, undefined)).not.toThrow()
    expect(() => result.current.observe(AT_B)).not.toThrow()
    expect(warn).toHaveBeenCalled()
  })
})
