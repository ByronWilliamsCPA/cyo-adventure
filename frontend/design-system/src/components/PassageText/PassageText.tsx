import type { ReactNode } from 'react'
import './PassageText.css'

export interface PassageTextRange {
  /** Inclusive start offset, in UTF-16 code units, into `text`. */
  start: number
  /** Exclusive end offset. */
  end: number
}

export interface PassageTextProps {
  text: string
  className?: string
  /**
   * A character range within `text` to visually highlight, e.g. the word
   * currently being read aloud (P-5: pre-reader read-along support, see
   * useReadAloud's `spokenWordRange`). Omitted or null renders plain prose;
   * every other caller (admin review screens, this component's own tests)
   * is unaffected.
   */
  highlightRange?: PassageTextRange | null
}

interface ParagraphOffset {
  text: string
  /** Offset of this paragraph's first character within the original `text`. */
  start: number
}

const PARAGRAPH_SEPARATOR = /\r\n\r\n+|\n\n+/g

/**
 * Splits `text` into non-empty paragraphs the same way the original
 * `text.split(regex).filter(Boolean)` did, but keeps each paragraph's start
 * offset into the source string so a global highlight range can be mapped
 * back onto the right paragraph and local offset.
 */
function splitParagraphsWithOffsets(text: string): ParagraphOffset[] {
  const result: ParagraphOffset[] = []
  let lastIndex = 0
  PARAGRAPH_SEPARATOR.lastIndex = 0
  let matched = PARAGRAPH_SEPARATOR.exec(text)
  while (matched !== null) {
    const para = text.slice(lastIndex, matched.index)
    if (para.length > 0) {
      result.push({ text: para, start: lastIndex })
    }
    lastIndex = matched.index + matched[0].length
    matched = PARAGRAPH_SEPARATOR.exec(text)
  }
  const rest = text.slice(lastIndex)
  if (rest.length > 0) {
    result.push({ text: rest, start: lastIndex })
  }
  return result
}

function renderParagraph(
  paragraph: ParagraphOffset,
  highlightRange: PassageTextRange | null | undefined
): ReactNode {
  if (!highlightRange) return paragraph.text
  const localStart = highlightRange.start - paragraph.start
  const localEnd = highlightRange.end - paragraph.start
  if (localEnd <= 0 || localStart >= paragraph.text.length || localStart >= localEnd) {
    // The range does not fall within this paragraph at all.
    return paragraph.text
  }
  const clampedStart = Math.max(0, localStart)
  const clampedEnd = Math.min(paragraph.text.length, localEnd)
  return (
    <>
      {paragraph.text.slice(0, clampedStart)}
      <mark className="cyo-passage__highlight">
        {paragraph.text.slice(clampedStart, clampedEnd)}
      </mark>
      {paragraph.text.slice(clampedEnd)}
    </>
  )
}

export function PassageText({ text, className = '', highlightRange = null }: PassageTextProps) {
  const paragraphs = splitParagraphsWithOffsets(text)

  if (paragraphs.length <= 1) {
    const [only] = paragraphs
    return (
      <p className={`cyo-passage ${className}`.trim()}>
        {only ? renderParagraph(only, highlightRange) : text}
      </p>
    )
  }

  return (
    <div className={`cyo-passage cyo-passage--multi ${className}`.trim()}>
      {paragraphs.map((para, i) => (
        // Index key is stable here: paragraph content is static per render.
        // This previously carried an `eslint-disable-next-line
        // react/no-array-index-key`, which was dead: eslint-plugin-react is
        // not a dependency of this repo, so the rule never ran and ESLint
        // reported the directive itself as referencing an unknown rule once
        // design-system entered lint scope. The reasoning is kept, the
        // suppression dropped.
        <p key={i}>{renderParagraph(para, highlightRange)}</p>
      ))}
    </div>
  )
}
