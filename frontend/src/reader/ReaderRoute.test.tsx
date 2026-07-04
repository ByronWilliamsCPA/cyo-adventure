import { render, screen } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { describe, expect, it } from 'vitest'
import { ReaderRoute } from './ReaderRoute'

function renderAt(path: string) {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <Routes>
        <Route path="/read/:profileId/:storybookId/:version" element={<ReaderRoute />} />
      </Routes>
    </MemoryRouter>
  )
}

// A route pattern missing a param the component expects, exercising the same
// "params are missing" guard a routing config mismatch would trigger for real.
function renderAtIncompleteRoute(path: string) {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <Routes>
        <Route path="/read/:profileId" element={<ReaderRoute />} />
      </Routes>
    </MemoryRouter>
  )
}

describe('ReaderRoute guards', () => {
  it('shows a styled, exitable message for a non-integer version', () => {
    renderAt('/read/p1/s/abc')
    expect(screen.getByText('That story link looks wrong')).toBeTruthy()
    expect(screen.getByRole('button', { name: 'Back to my books' })).toBeTruthy()
  })

  it('shows a styled, exitable message when route params are missing', () => {
    renderAtIncompleteRoute('/read/p1')
    expect(screen.getByText("We couldn't tell which story to open")).toBeTruthy()
    expect(screen.getByRole('button', { name: 'Back to start' })).toBeTruthy()
  })
})
