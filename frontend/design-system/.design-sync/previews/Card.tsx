import { Card } from '@cyo/design-system'

export function Default() {
  return (
    <div style={{ padding: '24px', maxWidth: '480px', background: 'var(--color-parchment)' }}>
      <Card>
        <div style={{ padding: '16px' }}>A quiet, non-interactive card row.</div>
      </Card>
    </div>
  )
}

export function Interactive() {
  return (
    <div style={{ padding: '24px', maxWidth: '480px', background: 'var(--color-parchment)' }}>
      <Card interactive>
        <div style={{ padding: '16px' }}>Hover me: a clickable whole-row card.</div>
      </Card>
    </div>
  )
}

export function CardList() {
  return (
    <div
      style={{
        display: 'flex',
        flexDirection: 'column',
        gap: '12px',
        padding: '24px',
        maxWidth: '480px',
        background: 'var(--color-parchment)',
      }}
    >
      <Card interactive>
        <div style={{ padding: '16px' }}>The Whispering Wood</div>
      </Card>
      <Card interactive>
        <div style={{ padding: '16px' }}>Riverbend Mystery</div>
      </Card>
    </div>
  )
}
