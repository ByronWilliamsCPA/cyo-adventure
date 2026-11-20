import type { ReactNode } from 'react'

import { Button } from '@ds/components/Button'

import { BookCover } from './BookCover'

export interface TitlePageProps {
  /** The kid-facing title, already resolved through resolvePersonalization. */
  title: string
  gradientSeed: string
  coverUrl: string | null
  onStart: () => void
  /** The reader's slim top bar (Leave, text size), rendered by Reader. */
  chrome: ReactNode
}

/**
 * The opening beat of a fresh read (design review 2026-08-01, recommendation
 * 12): the cover the child picked on the shelf, the title, and one "Start".
 * Never shown when resuming mid-book; Reader decides that (isOpeningRead).
 *
 * The title is the page's h1: it is the only heading here, and the reader's
 * other screens start at h2 under the kid shell, so the outline stays ordered.
 */
export function TitlePage({ title, gradientSeed, coverUrl, onStart, chrome }: TitlePageProps) {
  return (
    <>
      {chrome}
      <section
        className="reader-title-page"
        data-testid="title-page"
        aria-labelledby="reader-title-page-heading"
      >
        <BookCover coverUrl={coverUrl} title={title} gradientSeed={gradientSeed} size="lg" />
        <h1 id="reader-title-page-heading" className="reader-title-page__title">
          {title}
        </h1>
        <Button variant="primary" size="lg" data-testid="start-reading" onClick={onStart}>
          Start
        </Button>
      </section>
    </>
  )
}
