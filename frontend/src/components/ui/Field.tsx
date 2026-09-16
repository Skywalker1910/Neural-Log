import type { ReactNode, SelectHTMLAttributes, InputHTMLAttributes } from 'react'
import { useId } from 'react'

import { cn } from '../../lib/cn'

/**
 * Labelled form controls.
 *
 * Extracted in R9 rather than earlier because until then every input was one of
 * a kind, inline on the page that owned it. Onboarding and Settings ask the same
 * questions in two places, and two hand-styled copies of "birth year" is exactly
 * how they end up validating differently.
 *
 * The control styling matches the 30-odd inline inputs already in the codebase,
 * so this is a home for the pattern, not a new one.
 */
const CONTROL =
  'w-full rounded-md border border-line bg-surface-base px-3 py-2 text-label text-ink ' +
  'outline-none transition-colors duration-200 ease-apple ' +
  'hover:border-line-strong focus:border-brand disabled:opacity-50'

interface FieldProps {
  label: string
  /** Shown under the control. Say what the answer is *for*, not what to type. */
  hint?: ReactNode
  /** Server-side validation message. Replaces the hint while present. */
  error?: string
  children: (id: string) => ReactNode
  className?: string
}

export function Field({ label, hint, error, children, className }: FieldProps) {
  const id = useId()

  return (
    <div className={cn('flex flex-col gap-1.5', className)}>
      <label htmlFor={id} className="text-label font-medium text-ink">
        {label}
      </label>
      {children(id)}
      {error ? (
        <p className="text-meta text-danger">{error}</p>
      ) : (
        hint && <p className="text-meta text-ink-subtle">{hint}</p>
      )}
    </div>
  )
}

export function TextInput({ className, ...props }: InputHTMLAttributes<HTMLInputElement>) {
  return <input className={cn(CONTROL, props.type === 'number' && 'tabular', className)} {...props} />
}

export function Select({ className, children, ...props }: SelectHTMLAttributes<HTMLSelectElement>) {
  return (
    <select
      className={cn(
        CONTROL,
        // Native arrow removed and redrawn, because the platform one renders as
        // a light glyph on a light chip in several browsers on a dark ground.
        'appearance-none bg-[length:16px] bg-[right_0.75rem_center] bg-no-repeat pr-10',
        className,
      )}
      style={{
        backgroundImage:
          "url(\"data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='16' height='16' viewBox='0 0 24 24' fill='none' stroke='%23a1a1a6' stroke-width='2' stroke-linecap='round' stroke-linejoin='round'%3E%3Cpath d='m6 9 6 6 6-6'/%3E%3C/svg%3E\")",
      }}
      {...props}
    >
      {children}
    </select>
  )
}

interface ChoiceGroupProps<T extends string> {
  value: T | null
  options: { value: T; label: string; hint?: string }[]
  onChange: (value: T) => void
  name: string
}

/**
 * A closed set as tappable cards rather than a `<select>`.
 *
 * Used where the options need explaining - "moderate" means nothing without
 * "3-5 days a week" beside it, and a dropdown has nowhere to put that.
 */
export function ChoiceGroup<T extends string>({
  value,
  options,
  onChange,
  name,
}: ChoiceGroupProps<T>) {
  return (
    <div role="radiogroup" aria-label={name} className="grid gap-2 sm:grid-cols-2">
      {options.map((option) => {
        const selected = value === option.value
        return (
          <button
            key={option.value}
            type="button"
            role="radio"
            aria-checked={selected}
            onClick={() => onChange(option.value)}
            className={cn(
              'flex min-w-0 flex-col items-start gap-0.5 rounded-md border px-4 py-3 text-left',
              'transition-colors duration-200 ease-apple',
              selected
                ? 'border-brand bg-brand/10 text-ink'
                : 'border-line bg-surface-base text-ink-muted hover:border-line-strong hover:text-ink',
            )}
          >
            <span className="text-label font-medium">{option.label}</span>
            {option.hint && <span className="text-meta text-ink-subtle">{option.hint}</span>}
          </button>
        )
      })}
    </div>
  )
}
