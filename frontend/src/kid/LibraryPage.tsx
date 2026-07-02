import { useParams } from 'react-router-dom'

/**
 * Placeholder for the per-child library home screen (C4a-3). Reached from the
 * Profile Picker; the profileId param scopes which child's shelf renders.
 * Wireframe:
 * docs/superpowers/specs/2026-06-30-phase-4a-mobile-ui-wireframes-design.md#42.
 */
export function LibraryPage() {
  const { profileId } = useParams()
  return (
    <div className="kid-stub">
      <h1>My Books</h1>
      <p>
        Library for profile {profileId} is coming in C4a-3.
      </p>
    </div>
  )
}
