import { Button } from '@ds/components/Button'
import { useNavigate } from 'react-router-dom'

export interface BackToLibraryProps {
  /** Profile whose library to return to. */
  profileId: string
}

/** A "Back to my books" action that returns to the kid library for a profile. */
export function BackToLibrary({ profileId }: BackToLibraryProps) {
  const navigate = useNavigate()
  return (
    <Button variant="ghost" onClick={() => navigate(`/library/${profileId}`)}>
      Back to my books
    </Button>
  )
}
