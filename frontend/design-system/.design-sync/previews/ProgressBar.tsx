import { ProgressBar } from '@cyo/design-system'

export function InProgress() {
  return (
    <div style={{ padding: '24px', maxWidth: '400px' }}>
      <ProgressBar value={60} label="Chapter 3 of 5" showLabel />
    </div>
  )
}

export function Complete() {
  return (
    <div style={{ padding: '24px', maxWidth: '400px' }}>
      <ProgressBar value={100} label="Adventure complete!" showLabel />
    </div>
  )
}

export function AllStates() {
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '16px', padding: '24px', maxWidth: '400px' }}>
      <ProgressBar value={0} label="Not started" showLabel />
      <ProgressBar value={25} label="Just beginning" showLabel />
      <ProgressBar value={60} label="More than halfway" showLabel />
      <ProgressBar value={100} label="Finished!" showLabel />
    </div>
  )
}
