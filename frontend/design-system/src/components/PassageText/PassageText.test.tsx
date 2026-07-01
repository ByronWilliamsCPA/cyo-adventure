import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { PassageText } from './PassageText'

describe('PassageText', () => {
  it('splits LF-separated text into multiple paragraphs', () => {
    render(<PassageText text={'First paragraph.\n\nSecond paragraph.'} />)
    expect(screen.getByText('First paragraph.')).toBeInTheDocument()
    expect(screen.getByText('Second paragraph.')).toBeInTheDocument()
  })

  it('splits CRLF-separated text into multiple paragraphs', () => {
    render(<PassageText text={'First paragraph.\r\n\r\nSecond paragraph.'} />)
    expect(screen.getByText('First paragraph.')).toBeInTheDocument()
    expect(screen.getByText('Second paragraph.')).toBeInTheDocument()
  })

  it('renders single-paragraph text without the multi-paragraph wrapper', () => {
    render(<PassageText text="Only one paragraph here." />)
    const paragraph = screen.getByText('Only one paragraph here.')
    expect(paragraph.className).not.toContain('cyo-passage--multi')
  })
})
