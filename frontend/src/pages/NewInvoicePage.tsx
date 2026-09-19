import { useState, type FormEvent } from 'react'
import { useNavigate } from 'react-router'

import { ApiError, api } from '../api/client'
import { Checkbox, ErrorNote, Eyebrow, Field, PrimaryButton, TextInput } from '../components/ui'
import { validateInvoice, type InvoiceFormErrors, type InvoiceFormValues } from '../lib/validation'

const EMPTY: InvoiceFormValues = {
  invoice_number: '',
  buyer_name: '',
  buyer_gstin: '',
  buyer_is_corporate: true,
  invoice_date: '',
  acceptance_date: '',
  agreed_credit_days: '',
  amount: '',
}

export default function NewInvoicePage() {
  const navigate = useNavigate()
  const [values, setValues] = useState<InvoiceFormValues>(EMPTY)
  const [errors, setErrors] = useState<InvoiceFormErrors>({})
  const [submitting, setSubmitting] = useState(false)
  const [submitError, setSubmitError] = useState<unknown>(null)

  const set = <K extends keyof InvoiceFormValues>(k: K, v: InvoiceFormValues[K]) =>
    setValues((s) => ({ ...s, [k]: v }))

  async function onSubmit(ev: FormEvent) {
    ev.preventDefault()
    const e = validateInvoice(values)
    setErrors(e)
    if (Object.keys(e).length) return
    setSubmitting(true)
    setSubmitError(null)
    try {
      const created = await api.createInvoice({
        invoice_number: values.invoice_number.trim(),
        buyer_name: values.buyer_name.trim(),
        buyer_gstin: values.buyer_gstin.trim() || null,
        buyer_is_corporate: values.buyer_is_corporate,
        invoice_date: values.invoice_date,
        acceptance_date: values.acceptance_date,
        agreed_credit_days: values.agreed_credit_days.trim() ? Number(values.agreed_credit_days) : null,
        amount: values.amount.trim(),
      })
      navigate(`/invoices/${created.id}`)
    } catch (err) {
      if (err instanceof ApiError && err.kind === 'validation') setErrors(err.fieldErrors() as InvoiceFormErrors)
      setSubmitError(err)
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <div className="max-w-xl">
      <Eyebrow>Manual entry</Eyebrow>
      <h1 className="font-display mt-2 text-4xl tracking-[-0.01em] text-paper">Add an unpaid invoice</h1>
      <p className="mt-3 text-[15px] leading-relaxed text-mute">
        Interest under Section 16 runs from the day after payment fell due — the agreed credit period, capped at 45
        days from acceptance.
      </p>

      <form onSubmit={onSubmit} noValidate className="mt-10 space-y-6">
        <Field label="Invoice number" name="invoice_number" error={errors.invoice_number}>
          <TextInput
            id="invoice_number"
            value={values.invoice_number}
            onChange={(e) => set('invoice_number', e.target.value)}
            autoComplete="off"
            aria-invalid={!!errors.invoice_number}
            className="font-mono"
          />
        </Field>

        <Field label="Buyer name" name="buyer_name" error={errors.buyer_name}>
          <TextInput
            id="buyer_name"
            value={values.buyer_name}
            onChange={(e) => set('buyer_name', e.target.value)}
            autoComplete="organization"
            aria-invalid={!!errors.buyer_name}
          />
        </Field>

        <Field label="Buyer GSTIN" name="buyer_gstin" error={errors.buyer_gstin} optional>
          <TextInput
            id="buyer_gstin"
            value={values.buyer_gstin}
            onChange={(e) => set('buyer_gstin', e.target.value.toUpperCase())}
            placeholder="27AAPFU0939F1ZV"
            maxLength={15}
            autoComplete="off"
            aria-invalid={!!errors.buyer_gstin}
            className="font-mono uppercase"
          />
        </Field>

        <div className="rounded-md border border-rule bg-slate px-4 py-3">
          <Checkbox
            id="buyer_is_corporate"
            label="Buyer is a company"
            checked={values.buyer_is_corporate}
            onChange={(e) => set('buyer_is_corporate', e.target.checked)}
          />
          <p className="mt-1.5 pl-7 text-[13px] leading-relaxed text-mute">
            Companies lose the tax deduction on overdue MSE dues under s.43B(h) — useful leverage in the notice.
          </p>
        </div>

        <div className="grid gap-6 sm:grid-cols-2">
          <Field label="Invoice date" name="invoice_date" error={errors.invoice_date}>
            <TextInput
              id="invoice_date"
              type="date"
              value={values.invoice_date}
              onChange={(e) => set('invoice_date', e.target.value)}
              aria-invalid={!!errors.invoice_date}
              className="font-mono"
            />
          </Field>
          <Field
            label="Date of acceptance"
            name="acceptance_date"
            error={errors.acceptance_date}
            hint="When the buyer accepted the goods or services."
          >
            <TextInput
              id="acceptance_date"
              type="date"
              value={values.acceptance_date}
              onChange={(e) => set('acceptance_date', e.target.value)}
              aria-invalid={!!errors.acceptance_date}
              className="font-mono"
            />
          </Field>
        </div>

        <div className="grid gap-6 sm:grid-cols-2">
          <Field label="Agreed credit days" name="agreed_credit_days" error={errors.agreed_credit_days} optional>
            <TextInput
              id="agreed_credit_days"
              inputMode="numeric"
              value={values.agreed_credit_days}
              onChange={(e) => set('agreed_credit_days', e.target.value)}
              placeholder="defaults to 45"
              aria-invalid={!!errors.agreed_credit_days}
              className="font-mono"
            />
          </Field>
          <Field label="Amount (₹)" name="amount" error={errors.amount}>
            <TextInput
              id="amount"
              inputMode="decimal"
              value={values.amount}
              onChange={(e) => set('amount', e.target.value)}
              placeholder="500000.00"
              aria-invalid={!!errors.amount}
              className="font-mono tabular-nums"
            />
          </Field>
        </div>

        <ErrorNote error={submitError} />

        <div className="pt-2">
          <PrimaryButton type="submit" disabled={submitting}>
            {submitting ? 'Computing…' : 'Save and compute interest'}
          </PrimaryButton>
        </div>
      </form>
    </div>
  )
}
