import { EmptyState, Button } from '@cyo/design-system'

export function Default() {
  return (
    <div style={{ padding: '32px' }}>
      <EmptyState
        icon={<span style={{ fontSize: '2.5rem' }}>📚</span>}
        title="Your library is empty"
        description="Ask a parent or teacher to add stories to your reading list."
        actions={<Button variant="ghost">Browse featured stories</Button>}
      />
    </div>
  )
}

export function Loading() {
  return (
    <div style={{ padding: '32px' }}>
      <EmptyState
        icon={<span style={{ fontSize: '2.5rem' }}>⏳</span>}
        title="Loading your adventure…"
        description="Hang tight while we fetch the next chapter."
      />
    </div>
  )
}

export function Offline() {
  return (
    <div style={{ padding: '32px' }}>
      <EmptyState
        icon={<span style={{ fontSize: '2.5rem' }}>📵</span>}
        title="No connection"
        description="This story needs to be downloaded before you can read it offline. Connect to Wi-Fi and try again."
        actions={
          <>
            <Button variant="primary">Download story</Button>
            <Button variant="ghost">Browse offline stories</Button>
          </>
        }
      />
    </div>
  )
}
