/**
 * The multi-device save-conflict dialog (offline-conflict-ux.md section 1).
 *
 * Shown when a reading-state save returns 409 because another device advanced the
 * same story. Modal and blocking: the reader must choose, so no progress is lost
 * without a decision. The two actions map to the server-contract options
 * `continue_from_this_device` and `use_newer_progress`.
 */

export interface ConflictDialogProps {
  onKeepThisDevice: () => void
  onUseNewest: () => void
}

export function ConflictDialog({ onKeepThisDevice, onUseNewest }: ConflictDialogProps) {
  return (
    <div
      data-testid="conflict-dialog"
      role="dialog"
      aria-modal="true"
      aria-labelledby="conflict-title"
      className="conflict-dialog"
    >
      <h2 id="conflict-title">You were reading on another device</h2>
      <p>
        Your place in this story is different here than on your other device. Which one do you want
        to keep?
      </p>
      <div className="conflict-actions">
        <button type="button" data-testid="conflict-keep" onClick={onKeepThisDevice}>
          Keep this device
        </button>
        <button type="button" data-testid="conflict-use-newest" onClick={onUseNewest}>
          Use the newest place
        </button>
      </div>
    </div>
  )
}
