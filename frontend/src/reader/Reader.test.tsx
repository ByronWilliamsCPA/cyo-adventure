import { readFileSync } from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, describe, expect, it } from 'vitest'

import type { Storybook } from '../player/types'
import { Reader } from './Reader'

const here = path.dirname(fileURLToPath(import.meta.url))
const tracesPath = path.resolve(here, '../../../schema/conformance/player_traces.json')
const lantern = (
  JSON.parse(readFileSync(tracesPath, 'utf-8')) as {
    traces: { story: Storybook }[]
  }
).traces[0].story

afterEach(cleanup)

describe('Reader', () => {
  it('renders the start passage and its visible choices', () => {
    render(
      <MemoryRouter>
        <Reader story={lantern} profileId="p1" />
      </MemoryRouter>
    )
    expect(screen.getByTestId('passage-body').textContent).toContain('lantern')
    expect(screen.getByTestId('choice-c_take_lantern')).toBeTruthy()
    expect(screen.getByTestId('choice-c_ignore_lantern')).toBeTruthy()
    expect(screen.getByTestId('choice-c_take_lantern').textContent).toContain('›')
  })

  it('hides a choice whose condition is false', () => {
    render(
      <MemoryRouter>
        <Reader story={lantern} profileId="p1" />
      </MemoryRouter>
    )
    fireEvent.click(screen.getByTestId('choice-c_ignore_lantern'))
    // Without the lantern, the dark passage choice is not rendered.
    expect(screen.queryByTestId('choice-c_dark_passage')).toBeNull()
    expect(screen.getByTestId('choice-c_bright_tunnel')).toBeTruthy()
  })

  it('reveals the conditional choice once the lantern is taken', () => {
    render(
      <MemoryRouter>
        <Reader story={lantern} profileId="p1" />
      </MemoryRouter>
    )
    fireEvent.click(screen.getByTestId('choice-c_take_lantern'))
    expect(screen.getByTestId('choice-c_dark_passage')).toBeTruthy()
  })

  it('shows the ending screen on reaching an ending', () => {
    render(
      <MemoryRouter>
        <Reader story={lantern} profileId="p1" />
      </MemoryRouter>
    )
    fireEvent.click(screen.getByTestId('choice-c_take_lantern'))
    fireEvent.click(screen.getByTestId('choice-c_dark_passage'))
    expect(screen.getByTestId('ending-screen')).toBeTruthy()
    expect(screen.getByTestId('ending-id').textContent).toBe('e_treasure_found')
  })

  it('reports progress to onProgress', () => {
    const seen: string[] = []
    render(
      <MemoryRouter>
        <Reader story={lantern} onProgress={(r) => seen.push(r.current_node)} profileId="p1" />
      </MemoryRouter>
    )
    fireEvent.click(screen.getByTestId('choice-c_take_lantern'))
    expect(seen).toContain('n_cave_fork')
  })

  it('reports the reached ending to onComplete exactly once', () => {
    const completed: string[] = []
    render(
      <MemoryRouter>
        <Reader story={lantern} onComplete={(id) => completed.push(id)} profileId="p1" />
      </MemoryRouter>
    )
    fireEvent.click(screen.getByTestId('choice-c_take_lantern'))
    fireEvent.click(screen.getByTestId('choice-c_dark_passage'))
    expect(completed).toEqual(['e_treasure_found'])
  })

  it('does not re-post the same ending after Read again', () => {
    const completed: string[] = []
    render(
      <MemoryRouter>
        <Reader story={lantern} onComplete={(id) => completed.push(id)} profileId="p1" />
      </MemoryRouter>
    )
    fireEvent.click(screen.getByTestId('choice-c_take_lantern'))
    fireEvent.click(screen.getByTestId('choice-c_dark_passage'))
    fireEvent.click(screen.getByTestId('restart'))
    fireEvent.click(screen.getByTestId('choice-c_take_lantern'))
    fireEvent.click(screen.getByTestId('choice-c_dark_passage'))
    expect(completed).toEqual(['e_treasure_found'])
  })
})
