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

  describe('highlightRange (P-5 read-aloud word highlight)', () => {
    it('renders no <mark> when highlightRange is omitted', () => {
      render(<PassageText text="Once upon a time." />)
      expect(document.querySelector('mark')).not.toBeInTheDocument()
    })

    it('renders no <mark> when highlightRange is null', () => {
      render(<PassageText text="Once upon a time." highlightRange={null} />)
      expect(document.querySelector('mark')).not.toBeInTheDocument()
    })

    it('wraps only the given range in a <mark> within a single-paragraph passage', () => {
      render(<PassageText text="Once upon a time." highlightRange={{ start: 5, end: 9 }} />)
      const mark = document.querySelector('mark')
      expect(mark).toHaveClass('cyo-passage__highlight')
      expect(mark).toHaveTextContent('upon')
      // Full sentence is still readable end to end via the paragraph container.
      expect(document.querySelector('.cyo-passage')).toHaveTextContent('Once upon a time.')
    })

    it('maps a global offset into the correct paragraph of a multi-paragraph passage', () => {
      const text = 'First paragraph.\n\nSecond paragraph.'
      const start = text.indexOf('Second')
      render(<PassageText text={text} highlightRange={{ start, end: start + 'Second'.length }} />)
      const mark = document.querySelector('mark')
      expect(mark).toHaveTextContent('Second')
      // The first paragraph is untouched.
      expect(screen.getByText('First paragraph.')).toBeInTheDocument()
    })

    it('renders plain text when the range falls outside the passage entirely', () => {
      render(<PassageText text="Once upon a time." highlightRange={{ start: 100, end: 105 }} />)
      expect(document.querySelector('mark')).not.toBeInTheDocument()
      expect(screen.getByText('Once upon a time.')).toBeInTheDocument()
    })
  })
})
