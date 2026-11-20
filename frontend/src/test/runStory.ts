/**
 * Shared test fixture for the ending-screen rewind ("Try a different choice")
 * tests: a fork, then a single-choice run with effects, then a negative ending.
 * Test-only; nothing in the app imports it.
 */

import type { Storybook } from '../player/types'

// fork (2 choices) -> a1 (1 choice) -> a2 (1 choice) -> setback ending; the
// other branch goes straight to a win. The single-choice run before the
// ending is the case "Go back a page" handles badly: one step back lands on
// a2, which has no decision on it.
export const runStory: Storybook = {
  schema_version: '2.0',
  id: 's_run',
  version: 1,
  title: 'The Long Hall',
  metadata: {},
  variables: [{ name: 'steps', type: 'int', initial: 0, min: 0, max: 10 }],
  start_node: 'n_intro',
  nodes: [
    {
      id: 'n_intro',
      body: 'You step into the hall.',
      is_ending: false,
      choices: [{ id: 'c_go', label: 'Walk in', target: 'n_fork' }],
    },
    {
      id: 'n_fork',
      body: 'Two doors.',
      is_ending: false,
      choices: [
        { id: 'c_left', label: 'The red door', target: 'n_a1' },
        { id: 'c_right', label: 'The blue door', target: 'n_win' },
      ],
    },
    {
      id: 'n_a1',
      body: 'A long corridor.',
      is_ending: false,
      on_enter: [{ op: 'inc', var: 'steps', value: 1 }],
      choices: [{ id: 'c_a1', label: 'Keep going', target: 'n_a2' }],
    },
    {
      id: 'n_a2',
      body: 'It gets darker.',
      is_ending: false,
      on_enter: [{ op: 'inc', var: 'steps', value: 1 }],
      choices: [{ id: 'c_a2', label: 'Keep going', target: 'n_trap' }],
    },
    {
      id: 'n_trap',
      body: 'A net drops from the ceiling.',
      is_ending: true,
      choices: [],
      ending: { id: 'e_trap', kind: 'capture', valence: 'negative', title: 'Caught in a Net' },
    },
    {
      id: 'n_win',
      body: 'Sunlight and cake.',
      is_ending: true,
      choices: [],
      ending: { id: 'e_win', kind: 'success', valence: 'positive', title: 'Cake Day' },
    },
  ],
}
