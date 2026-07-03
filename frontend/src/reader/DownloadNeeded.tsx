/**
 * The iOS post-eviction / offline "download needed" state
 * (offline-conflict-ux.md section 2). Shown only when the device is genuinely
 * offline and the story is not cached, so the copy about reconnecting is accurate.
 */

import { Button } from '@ds/components/Button'
import { EmptyState } from '@ds/components/EmptyState'

export interface DownloadNeededProps {
  onRetry: () => void
  onBackToLibrary?: () => void
}

export function DownloadNeeded({ onRetry, onBackToLibrary }: DownloadNeededProps) {
  return (
    <div data-testid="download-needed">
      <EmptyState
        title="This story needs to download again"
        description="Your device cleared this story to save space. Connect to the internet to download it again."
        actions={
          <>
            <Button variant="primary" data-testid="download-retry" onClick={onRetry}>
              Try again
            </Button>
            {onBackToLibrary ? (
              <Button variant="ghost" data-testid="download-back" onClick={onBackToLibrary}>
                Back to library
              </Button>
            ) : null}
          </>
        }
      />
    </div>
  )
}
