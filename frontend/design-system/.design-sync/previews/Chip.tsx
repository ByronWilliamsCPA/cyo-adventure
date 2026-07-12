import { Chip } from '@cyo/design-system'

export function Default() {
  return (
    <div style={{ padding: '24px' }}>
      <Chip>Gentle</Chip>
    </div>
  )
}

export function On() {
  return (
    <div style={{ padding: '24px' }}>
      <Chip on>Gentle</Chip>
    </div>
  )
}

export function ChipRow() {
  return (
    <div style={{ display: 'flex', gap: '8px', padding: '24px', flexWrap: 'wrap' }}>
      <Chip on>Gentle</Chip>
      <Chip>Silly</Chip>
      <Chip>Adventurous</Chip>
      <Chip>Spooky (mild)</Chip>
    </div>
  )
}
