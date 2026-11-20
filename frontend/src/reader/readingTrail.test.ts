import { describe, expect, it, vi } from 'vitest'

import type { ReadingTrailBatchBody } from '../client/types.gen'
import type { ReadingState, Storybook } from '../player/types'
import { MAX_ELAPSED_SECONDS, MAX_STEPS_PER_READ, ReadingTrailRecorder } from './readingTrail'

// n_open (one choice) -> n_entrance (two choices, SAME target) -> n_fork
// (two choices) -> one of two endings.
const STORY: Storybook = {
  schema_version: '1',
  id: 's_trail',
  version: 3,
  title: 'Trail',
  metadata: {},
  start_node: 'n_open',
  nodes: [
    {
      id: 'n_open',
      body: '',
      is_ending: false,
      choices: [{ id: 'c_go', label: 'Go', target: 'n_entrance' }],
    },
    {
      id: 'n_entrance',
      body: '',
      is_ending: false,
      choices: [
        { id: 'c_take', label: 'Take', target: 'n_fork' },
        { id: 'c_leave', label: 'Leave', target: 'n_fork' },
      ],
    },
    {
      id: 'n_fork',
      body: '',
      is_ending: false,
      choices: [
        { id: 'c_dark', label: 'Dark', target: 'n_gold' },
        { id: 'c_light', label: 'Light', target: 'n_exit' },
      ],
    },
    {
      id: 'n_gold',
      body: '',
      is_ending: true,
      ending: { id: 'e_gold', kind: 'success', valence: 'positive', title: 'Gold' },
    },
    {
      id: 'n_exit',
      body: '',
      is_ending: true,
      ending: { id: 'e_exit', kind: 'completion', valence: 'neutral', title: 'Out' },
    },
  ],
}

function state(path: string[]): ReadingState {
  return {
    current_node: path[path.length - 1],
    var_state: {},
    path,
    visit_set: [...new Set(path)],
    version: 3,
    state_revision: 0,
    save_slots: {},
  }
}

function setup(baseline?: ReadingState) {
  let clock = 1_000_000
  let ids = 0
  const sent: Array<{ body: ReadingTrailBatchBody; keepalive: boolean }> = []
  const send = vi.fn((body: ReadingTrailBatchBody, options: { keepalive: boolean }) => {
    sent.push({ body, keepalive: options.keepalive })
    return Promise.resolve('recorded' as const)
  })
  const recorder = new ReadingTrailRecorder({
    story: STORY,
    baseline,
    version: 3,
    send,
    now: () => clock,
    newId: () => `read-${String(++ids)}`,
  })
  const tick = (seconds: number) => {
    clock += seconds * 1000
  }
  const steps = () => sent.flatMap((batch) => batch.body.steps)
  return { recorder, send, sent, tick, steps }
}

function choose(from: string, choiceId: string, path: string[]) {
  return { type: 'choose' as const, from, choiceId, to: state(path) }
}

describe('ReadingTrailRecorder', () => {
  it('records a fresh read: start, auto step, real choices, then the ending', () => {
    const { recorder, sent, tick } = setup()
    tick(4)
    recorder.onTransition(choose('n_open', 'c_go', ['n_open', 'n_entrance']))
    tick(20)
    recorder.onTransition(choose('n_entrance', 'c_leave', ['n_open', 'n_entrance', 'n_fork']))
    tick(10)
    recorder.onTransition(choose('n_fork', 'c_dark', ['n_open', 'n_entrance', 'n_fork', 'n_gold']))
    // Reaching an ending flushes on its own.
    expect(sent).toHaveLength(1)
    expect(sent[0].body.read_id).toBe('read-1')
    expect(sent[0].body.version).toBe(3)
    expect(sent[0].body.steps).toEqual([
      { seq: 0, kind: 'start', node_id: 'n_open', choice_id: null, elapsed_s: 0 },
      { seq: 1, kind: 'auto', node_id: 'n_open', choice_id: 'c_go', elapsed_s: 4 },
      // Same-target choices are told apart by the machine's own choice id.
      { seq: 2, kind: 'choice', node_id: 'n_entrance', choice_id: 'c_leave', elapsed_s: 24 },
      { seq: 3, kind: 'choice', node_id: 'n_fork', choice_id: 'c_dark', elapsed_s: 34 },
      { seq: 4, kind: 'end', node_id: 'n_gold', choice_id: null, elapsed_s: 34 },
    ])
  })

  it('records a saved read past its first node as a resume', () => {
    const { recorder, steps } = setup(state(['n_open', 'n_entrance', 'n_fork']))
    recorder.leave()
    expect(steps().map((s) => [s.kind, s.node_id])).toEqual([
      ['resume', 'n_fork'],
      ['leave', 'n_fork'],
    ])
  })

  it('records each BACK of a rewind, and a later different choice', () => {
    const { recorder, steps } = setup()
    recorder.onTransition(choose('n_open', 'c_go', ['n_open', 'n_entrance']))
    recorder.onTransition(choose('n_entrance', 'c_take', ['n_open', 'n_entrance', 'n_fork']))
    recorder.onTransition({ type: 'back', to: state(['n_open', 'n_entrance']) })
    recorder.onTransition({ type: 'back', to: state(['n_open']) })
    recorder.onTransition(choose('n_open', 'c_go', ['n_open', 'n_entrance']))
    recorder.onTransition(choose('n_entrance', 'c_leave', ['n_open', 'n_entrance', 'n_fork']))
    recorder.leave()
    expect(steps().map((s) => s.kind)).toEqual([
      'start',
      'auto',
      'choice',
      'back',
      'back',
      'auto',
      'choice',
      'leave',
    ])
    expect(steps()[4].node_id).toBe('n_open')
    expect(steps()[7].node_id).toBe('n_fork')
  })

  it('closes the read on restart and opens a new read id with fresh seq', () => {
    const { recorder, sent, tick } = setup()
    recorder.onTransition(choose('n_open', 'c_go', ['n_open', 'n_entrance']))
    tick(5)
    recorder.onTransition({ type: 'restart', to: state(['n_open']) })
    recorder.leave()
    expect(sent.map((b) => b.body.read_id)).toEqual(['read-1', 'read-2'])
    expect(sent[0].body.steps[sent[0].body.steps.length - 1]).toMatchObject({
      kind: 'restart',
      node_id: 'n_entrance',
    })
    expect(sent[1].body.steps[0]).toMatchObject({ seq: 0, kind: 'start', elapsed_s: 0 })
    expect(sent[1].body.steps[1]).toMatchObject({ seq: 1, kind: 'leave', node_id: 'n_open' })
  })

  it('records an unexplained position change as a jump, and ignores a duplicate state', () => {
    const { recorder, steps } = setup()
    recorder.observe(state(['n_open']))
    recorder.onTransition({ type: 'jump', to: state(['n_open', 'n_entrance']) })
    recorder.observe(state(['n_open', 'n_entrance', 'n_fork']))
    recorder.observe(state(['n_open', 'n_entrance', 'n_fork']))
    recorder.observe(state(['n_not_in_story']))
    recorder.leave()
    expect(steps().map((s) => [s.kind, s.node_id])).toEqual([
      ['start', 'n_open'],
      ['jump', 'n_entrance'],
      ['jump', 'n_fork'],
      ['leave', 'n_fork'],
    ])
  })

  it('leave is idempotent and closes the recorder', () => {
    const { recorder, sent } = setup()
    recorder.leave()
    recorder.leave()
    recorder.onTransition(choose('n_open', 'c_go', ['n_open', 'n_entrance']))
    recorder.flush()
    expect(sent).toHaveLength(1)
    expect(sent[0].keepalive).toBe(true)
  })

  it('stops sending for the mount once the server says recording is off', async () => {
    const send = vi.fn(() => Promise.resolve('disabled' as const))
    const recorder = new ReadingTrailRecorder({
      story: STORY,
      baseline: undefined,
      version: 3,
      send,
    })
    recorder.flush()
    await Promise.resolve()
    await Promise.resolve()
    recorder.onTransition(choose('n_open', 'c_go', ['n_open', 'n_entrance']))
    recorder.leave()
    expect(send).toHaveBeenCalledTimes(1)
  })

  it('tolerates a send that rejects', async () => {
    const send = vi.fn(() => Promise.reject(new Error('boom')))
    const recorder = new ReadingTrailRecorder({
      story: STORY,
      baseline: undefined,
      version: 3,
      send,
    })
    expect(() => recorder.leave()).not.toThrow()
    await Promise.resolve()
    expect(send).toHaveBeenCalledTimes(1)
  })

  it('flushes in bounded batches, caps steps per read, and clamps elapsed time', () => {
    const { recorder, sent, tick, steps } = setup()
    tick(MAX_ELAPSED_SECONDS * 2)
    for (let i = 0; i < MAX_STEPS_PER_READ + 50; i += 1) {
      recorder.onTransition({ type: 'back', to: state(['n_open']) })
    }
    recorder.flush()
    expect(Math.max(...sent.map((b) => b.body.steps.length))).toBeLessThanOrEqual(20)
    expect(steps()).toHaveLength(MAX_STEPS_PER_READ)
    const last = steps()[steps().length - 1]
    expect(last.seq).toBe(MAX_STEPS_PER_READ - 1)
    expect(last.elapsed_s).toBe(MAX_ELAPSED_SECONDS)
  })
})
