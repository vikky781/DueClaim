/** Client-side mirror of backend/app/models.py InvoiceCreate. The server remains the authority. */

export const GSTIN_PATTERN = /^[0-9]{2}[A-Z]{5}[0-9]{4}[A-Z][1-9A-Z]Z[0-9A-Z]$/

export interface InvoiceFormValues {
  invoice_number: string
  buyer_name: string
  buyer_gstin: string
  buyer_is_corporate: boolean
  invoice_date: string
  acceptance_date: string
  agreed_credit_days: string
  amount: string
}

export type InvoiceFormErrors = Partial<Record<keyof InvoiceFormValues, string>>

const AMOUNT = /^\d+(\.\d{1,2})?$/

export function validateInvoice(v: InvoiceFormValues): InvoiceFormErrors {
  const e: InvoiceFormErrors = {}
  if (!v.invoice_number.trim()) e.invoice_number = 'Enter the invoice number.'
  if (!v.buyer_name.trim()) e.buyer_name = 'Enter the buyer’s name as it appears on the invoice.'
  if (v.buyer_gstin.trim() && !GSTIN_PATTERN.test(v.buyer_gstin.trim())) {
    e.buyer_gstin = 'GSTIN should be 15 characters, e.g. 27AAPFU0939F1ZV.'
  }
  if (!v.invoice_date) e.invoice_date = 'Enter the invoice date.'
  if (!v.acceptance_date) e.acceptance_date = 'Enter the date the buyer accepted the goods or services.'
  if (v.agreed_credit_days.trim()) {
    const n = Number(v.agreed_credit_days)
    if (!Number.isInteger(n) || n < 1) e.agreed_credit_days = 'Credit days must be a whole number of at least 1.'
  }
  const amt = v.amount.trim()
  if (!AMOUNT.test(amt)) e.amount = 'Enter the amount in rupees, up to two decimal places.'
  else if (!/[1-9]/.test(amt)) e.amount = 'Amount must be greater than zero.'
  return e
}
