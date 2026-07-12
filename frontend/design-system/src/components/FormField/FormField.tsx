import type { LabelHTMLAttributes, ReactNode } from 'react'
import './FormField.css'

export interface FormFieldProps extends LabelHTMLAttributes<HTMLLabelElement> {
  label: string
  children: ReactNode
}

/**
 * A labeled field-stack wrapper: the label text stacked above its input
 * slot. The `cyo-field` (stack layout) and `cyo-field__control` (input box
 * treatment) classes this component applies are also exported as raw class
 * names so existing `<label>...<input/></label>` markup can adopt the same
 * look without restructuring into this component.
 */
export function FormField({ label, children, className = '', ...props }: FormFieldProps) {
  return (
    <label className={`cyo-field ${className}`.trim()} {...props}>
      {label}
      {children}
    </label>
  )
}
