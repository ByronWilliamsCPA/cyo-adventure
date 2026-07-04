import { fireEvent, render, screen } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { describe, expect, it } from 'vitest'
import { BackToLibrary } from './BackToLibrary'

describe('BackToLibrary', () => {
  it('navigates to the profile library on click', () => {
    render(
      <MemoryRouter initialEntries={['/read/p1/s/1']}>
        <Routes>
          <Route path="/read/:profileId/:storybookId/:version" element={<BackToLibrary profileId="p1" />} />
          <Route path="/library/:profileId" element={<div>Library Page</div>} />
        </Routes>
      </MemoryRouter>
    )
    fireEvent.click(screen.getByRole('button', { name: 'Back to my books' }))
    expect(screen.getByText('Library Page')).toBeTruthy()
  })
})
