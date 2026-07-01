import { Button } from '@cyo/design-system'

export function Variants() {
  return (
    <div style={{ display: 'flex', gap: '12px', alignItems: 'center', padding: '24px' }}>
      <Button variant="primary">Begin Adventure</Button>
      <Button variant="ghost">Skip Chapter</Button>
      <Button variant="danger">Abandon Quest</Button>
    </div>
  )
}

export function Sizes() {
  return (
    <div style={{ display: 'flex', gap: '12px', alignItems: 'center', padding: '24px' }}>
      <Button size="sm">Small</Button>
      <Button size="md">Medium</Button>
      <Button size="lg">Start Reading</Button>
    </div>
  )
}

export function Disabled() {
  return (
    <div style={{ display: 'flex', gap: '12px', alignItems: 'center', padding: '24px' }}>
      <Button variant="primary" disabled>Loading…</Button>
      <Button variant="ghost" disabled>Skip</Button>
      <Button variant="danger" disabled>Delete</Button>
    </div>
  )
}
