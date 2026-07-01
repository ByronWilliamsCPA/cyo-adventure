import { ChoiceButton } from '@cyo/design-system'

export function Default() {
  return (
    <div style={{ padding: '24px', maxWidth: '480px' }}>
      <ChoiceButton label="Climb the old oak tree to get a better view" />
    </div>
  )
}

export function Selected() {
  return (
    <div style={{ padding: '24px', maxWidth: '480px' }}>
      <ChoiceButton label="Follow the sound of the river downstream" selected />
    </div>
  )
}

export function ChoiceList() {
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '8px', padding: '24px', maxWidth: '480px' }}>
      <ChoiceButton label="Enter the ancient stone doorway" />
      <ChoiceButton label="Call out to see if anyone is home" />
      <ChoiceButton label="Hide behind the mossy boulders and wait" selected />
      <ChoiceButton label="Turn back the way you came" />
    </div>
  )
}
