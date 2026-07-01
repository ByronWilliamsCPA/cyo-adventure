import { Dialog, Button } from '@cyo/design-system'

export function ConflictDialog() {
  return (
    <div style={{ position: 'relative', height: '420px', overflow: 'hidden' }}>
      <Dialog
        title="Your adventure was saved on another device"
        actions={
          <>
            <Button variant="ghost">Keep that save</Button>
            <Button variant="primary">Use this device</Button>
          </>
        }
      >
        <p style={{ margin: 0 }}>
          You were reading <strong>The Enchanted Forest</strong> on your tablet. Which version
          would you like to continue from?
        </p>
      </Dialog>
    </div>
  )
}

export function ClosableDialog() {
  return (
    <div style={{ position: 'relative', height: '420px', overflow: 'hidden' }}>
      <Dialog
        title="Chapter complete!"
        onClose={() => undefined}
        actions={<Button variant="primary">Continue to next chapter</Button>}
      >
        <p style={{ margin: 0 }}>
          You chose wisely — the river path led you to the hidden village. Your adventure
          score: <strong>3 out of 5 stars</strong>.
        </p>
      </Dialog>
    </div>
  )
}
