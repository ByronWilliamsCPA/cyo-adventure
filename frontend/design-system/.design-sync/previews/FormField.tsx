import { FormField } from '@cyo/design-system'

export function Default() {
  return (
    <div style={{ padding: '24px', maxWidth: '360px' }}>
      <FormField label="Name">
        <input className="cyo-field__control" defaultValue="" />
      </FormField>
    </div>
  )
}

export function WithSelect() {
  return (
    <div style={{ padding: '24px', maxWidth: '360px' }}>
      <FormField label="Age band">
        <select className="cyo-field__control" defaultValue="5-8">
          <option value="5-8">5-8</option>
          <option value="9-12">9-12</option>
        </select>
      </FormField>
    </div>
  )
}

export function FormStack() {
  return (
    <div
      style={{
        display: 'flex',
        flexDirection: 'column',
        gap: '12px',
        padding: '24px',
        maxWidth: '360px',
      }}
    >
      <FormField label="Name">
        <input className="cyo-field__control" defaultValue="" />
      </FormField>
      <FormField label="What should the story be about?">
        <textarea className="cyo-field__control" rows={3} />
      </FormField>
    </div>
  )
}
