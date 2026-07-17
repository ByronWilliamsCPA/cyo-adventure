import type { ReaderFontScale } from './useReaderFontScale'

export interface TextSizeControlProps {
  fontScale: ReaderFontScale
}

/**
 * A / A+ / A++ text-size picker for the reader top bar (UX-K2).
 *
 * A radiogroup so assistive tech announces it as one control with a current
 * choice; each option meets the 44px tap floor for young readers.
 */
export function TextSizeControl({ fontScale }: TextSizeControlProps) {
  const { level, levels, labelFor, setLevel } = fontScale
  return (
    <div className="reader-textsize" role="radiogroup" aria-label="Text size">
      {levels.map((option) => (
        <button
          key={option}
          type="button"
          role="radio"
          aria-checked={option === level}
          aria-label={`Text size ${labelFor(option)}`}
          className={
            option === level
              ? 'reader-textsize__button reader-textsize__button--active'
              : 'reader-textsize__button'
          }
          onClick={() => setLevel(option)}
        >
          {labelFor(option)}
        </button>
      ))}
    </div>
  )
}
