import { StatusBadge } from '@cyo/design-system'

export function Connected() {
  return (
    <div style={{ padding: '24px' }}>
      <StatusBadge status="connected" />
    </div>
  )
}

export function Offline() {
  return (
    <div style={{ padding: '24px' }}>
      <StatusBadge status="offline" />
    </div>
  )
}

export function Loading() {
  return (
    <div style={{ padding: '24px' }}>
      <StatusBadge status="loading" />
    </div>
  )
}

export function AllStatuses() {
  return (
    <div style={{ display: 'flex', gap: '16px', flexWrap: 'wrap', alignItems: 'center', padding: '24px' }}>
      <StatusBadge status="connected" />
      <StatusBadge status="offline" />
      <StatusBadge status="loading" />
      <StatusBadge status="error" />
    </div>
  )
}
