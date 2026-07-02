import { AvatarCircle, AVATARS } from '@cyo/design-system'

export function WithPresetGlyph() {
  return (
    <div style={{ padding: '24px' }}>
      <AvatarCircle avatar="fox" name="Remy" />
    </div>
  )
}

export function InitialFallback() {
  return (
    <div style={{ display: 'flex', gap: '16px', padding: '24px' }}>
      <AvatarCircle avatar={null} name="Zoe" />
      <AvatarCircle avatar={null} name="   " />
    </div>
  )
}

export function FullCatalog() {
  return (
    <div style={{ display: 'flex', gap: '12px', flexWrap: 'wrap', padding: '24px' }}>
      {AVATARS.map((option) => (
        <AvatarCircle key={option.id} avatar={option.id} name={option.label} />
      ))}
    </div>
  )
}
