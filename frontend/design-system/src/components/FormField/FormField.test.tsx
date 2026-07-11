import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { FormField } from './FormField'

describe('FormField', () => {
  it('renders the label text and the input slot', () => {
    render(
      <FormField label="Name">
        <input value="Alex" onChange={() => {}} />
      </FormField>,
    )
    expect(screen.getByText('Name')).toBeInTheDocument()
    expect(screen.getByRole('textbox')).toHaveValue('Alex')
  })

  it('carries the cyo-field class on the wrapping label', () => {
    render(
      <FormField label="Name">
        <input value="Alex" onChange={() => {}} />
      </FormField>,
    )
    expect(screen.getByText('Name').closest('label')?.className).toContain('cyo-field')
  })

  it('forwards className and other label props', () => {
    render(
      <FormField label="Name" className="request-form__field" htmlFor="name-input">
        <input id="name-input" value="Alex" onChange={() => {}} />
      </FormField>,
    )
    const label = screen.getByText('Name').closest('label')
    expect(label?.className).toContain('request-form__field')
    expect(label).toHaveAttribute('for', 'name-input')
  })
})
