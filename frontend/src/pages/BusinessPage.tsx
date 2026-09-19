import { useState, type FormEvent } from 'react'
import { useLocation, useNavigate } from 'react-router'

import { ApiError, api } from '../api/client'
import type { Business, EnterpriseCategory } from '../api/types'
import { useBusiness } from '../lib/businessContext'
import { ErrorNote, Eyebrow, Field, PrimaryButton, Select, TextInput } from '../components/ui'

const EMPTY: Business = {
  udyam_number: '',
  legal_name: '',
  address: '',
  email: '',
  enterprise_category: 'micro',
}

const CATEGORIES: { value: EnterpriseCategory; label: string }[] = [
  { value: 'micro', label: 'Micro' },
  { value: 'small', label: 'Small' },
  { value: 'medium', label: 'Medium' },
]

type Errors = Partial<Record<keyof Business, string>>

function validate(b: Business): Errors {
  const e: Errors = {}
  if (!b.udyam_number.trim()) e.udyam_number = 'Enter your Udyam registration number.'
  if (!b.legal_name.trim()) e.legal_name = 'Enter the legal name of the enterprise.'
  if (!b.address.trim()) e.address = 'Enter the registered address.'
  if (!/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(b.email.trim())) e.email = 'Enter a valid email address.'
  return e
}

export default function BusinessPage() {
  const { business, setBusiness } = useBusiness()
  const navigate = useNavigate()
  const location = useLocation() as { state?: { reason?: string; from?: string } }
  const redirected = location.state?.reason === 'missing'

  const [values, setValues] = useState<Business>(business ?? EMPTY)
  const [errors, setErrors] = useState<Errors>({})
  const [submitting, setSubmitting] = useState(false)
  const [submitError, setSubmitError] = useState<unknown>(null)

  const set = <K extends keyof Business>(k: K, v: Business[K]) => setValues((s) => ({ ...s, [k]: v }))

  async function onSubmit(ev: FormEvent) {
    ev.preventDefault()
    const trimmed: Business = {
      ...values,
      udyam_number: values.udyam_number.trim(),
      legal_name: values.legal_name.trim(),
      address: values.address.trim(),
      email: values.email.trim(),
    }
    const e = validate(trimmed)
    setErrors(e)
    if (Object.keys(e).length) return
    setSubmitting(true)
    setSubmitError(null)
    try {
      const saved = await api.putBusiness(trimmed)
      setBusiness(saved)
      navigate(location.state?.from ?? '/dashboard', { replace: true })
    } catch (err) {
      if (err instanceof ApiError && err.kind === 'validation') setErrors(err.fieldErrors() as Errors)
      setSubmitError(err)
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <div className="max-w-xl">
      <Eyebrow>Your enterprise</Eyebrow>
      <h1 className="font-display mt-2 text-4xl tracking-[-0.01em] text-paper">
        {business ? 'Business profile' : 'Set up your business'}
      </h1>
      <p className="mt-3 text-[15px] leading-relaxed text-mute">
        {redirected
          ? 'Before we can quantify a claim we need to know who the supplier is. This takes a minute and only has to be done once.'
          : 'These details identify the supplier on every claim. Only an MSE registered under Udyam can claim under Section 16.'}
      </p>

      <form onSubmit={onSubmit} noValidate className="mt-10 space-y-6">
        <Field label="Udyam registration number" name="udyam_number" error={errors.udyam_number} hint="Format: UDYAM-XX-00-0000000">
          <TextInput
            id="udyam_number"
            value={values.udyam_number}
            onChange={(e) => set('udyam_number', e.target.value)}
            placeholder="UDYAM-MH-18-0012345"
            autoComplete="off"
            aria-invalid={!!errors.udyam_number}
            className="font-mono"
          />
        </Field>
        <Field label="Legal name" name="legal_name" error={errors.legal_name}>
          <TextInput
            id="legal_name"
            value={values.legal_name}
            onChange={(e) => set('legal_name', e.target.value)}
            autoComplete="organization"
            aria-invalid={!!errors.legal_name}
          />
        </Field>
        <Field label="Registered address" name="address" error={errors.address}>
          <TextInput
            id="address"
            value={values.address}
            onChange={(e) => set('address', e.target.value)}
            autoComplete="street-address"
            aria-invalid={!!errors.address}
          />
        </Field>
        <Field label="Email for notices" name="email" error={errors.email}>
          <TextInput
            id="email"
            type="email"
            value={values.email}
            onChange={(e) => set('email', e.target.value)}
            autoComplete="email"
            aria-invalid={!!errors.email}
          />
        </Field>
        <Field label="Enterprise category" name="enterprise_category" hint="As shown on the Udyam certificate.">
          <Select
            id="enterprise_category"
            value={values.enterprise_category}
            onChange={(e) => set('enterprise_category', e.target.value as EnterpriseCategory)}
          >
            {CATEGORIES.map((c) => (
              <option key={c.value} value={c.value}>
                {c.label}
              </option>
            ))}
          </Select>
        </Field>

        <ErrorNote error={submitError} />

        <div className="flex items-center gap-4 pt-2">
          <PrimaryButton type="submit" disabled={submitting}>
            {submitting ? 'Saving…' : business ? 'Save changes' : 'Save and continue'}
          </PrimaryButton>
        </div>
      </form>
    </div>
  )
}
