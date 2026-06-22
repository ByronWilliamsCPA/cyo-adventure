/**
 * The iOS post-eviction "download needed" state (offline-conflict-ux.md section 2).
 *
 * Shown when a story's cached blob is gone (iOS cleared it under storage pressure)
 * and the network is unavailable, instead of a broken passage. "Try again"
 * re-fetches and re-caches the story.
 */

export interface DownloadNeededProps {
  onRetry: () => void
  onBackToLibrary?: () => void
}

export function DownloadNeeded({ onRetry, onBackToLibrary }: DownloadNeededProps) {
  return (
    <section data-testid="download-needed" className="download-needed">
      <h2>This story needs to download again</h2>
      <p>
        Your device cleared this story to save space. Connect to the internet to download it again.
      </p>
      <div className="download-actions">
        <button type="button" data-testid="download-retry" onClick={onRetry}>
          Try again
        </button>
        {onBackToLibrary ? (
          <button type="button" data-testid="download-back" onClick={onBackToLibrary}>
            Back to library
          </button>
        ) : null}
      </div>
    </section>
  )
}
