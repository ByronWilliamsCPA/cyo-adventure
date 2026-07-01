import './PassageText.css'

export interface PassageTextProps {
  text: string
  className?: string
}

export function PassageText({ text, className = '' }: PassageTextProps) {
  const paragraphs = text.split(/\n\n+/).filter(Boolean)

  if (paragraphs.length <= 1) {
    return <p className={`cyo-passage ${className}`.trim()}>{text}</p>
  }

  return (
    <div className={`cyo-passage cyo-passage--multi ${className}`.trim()}>
      {paragraphs.map((para, i) => (
        // Index key is stable here — paragraph content is static per render
        // eslint-disable-next-line react/no-array-index-key
        <p key={i}>{para}</p>
      ))}
    </div>
  )
}
