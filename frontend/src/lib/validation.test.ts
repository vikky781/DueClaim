import { describe, expect, it } from 'vitest'
import { GSTIN_PATTERN, validateInvoice, type InvoiceFormValues } from './validation'

const valid: InvoiceFormValues = {
  invoice_number: 'INV-001',
  buyer_name: 'Acme Industries Pvt Ltd',
  buyer_gstin: '27AAPFU0939F1ZV',
  buyer_is_corporate: true,
  invoice_date: '2026-01-10',
  acceptance_date: '2026-01-15',
  agreed_credit_days: '',
  amount: '500000',
}

describe('validateInvoice (mirrors backend InvoiceCreate)', () => {
  it('accepts a valid form', () => {
    expect(validateInvoice(valid)).toEqual({})
  })
  it('requires invoice number, buyer name and both dates', () => {
    const e = validateInvoice({ ...valid, invoice_number: ' ', buyer_name: '', invoice_date: '', acceptance_date: '' })
    expect(Object.keys(e).sort()).toEqual(['acceptance_date', 'buyer_name', 'invoice_date', 'invoice_number'])
  })
  it('rejects amount <= 0 and non-numeric amounts', () => {
    expect(validateInvoice({ ...valid, amount: '0' })).toHaveProperty('amount')
    expect(validateInvoice({ ...valid, amount: '-1' })).toHaveProperty('amount')
    expect(validateInvoice({ ...valid, amount: 'ten' })).toHaveProperty('amount')
    expect(validateInvoice({ ...valid, amount: '1.005' })).toHaveProperty('amount') // more than paise
    expect(validateInvoice({ ...valid, amount: '0.01' })).toEqual({})
  })
  it('validates GSTIN only when provided', () => {
    expect(validateInvoice({ ...valid, buyer_gstin: '' })).toEqual({})
    expect(validateInvoice({ ...valid, buyer_gstin: '27aapfu0939f1zv' })).toHaveProperty('buyer_gstin')
    expect(validateInvoice({ ...valid, buyer_gstin: 'XXAAPFU0939F1ZV' })).toHaveProperty('buyer_gstin')
    expect(GSTIN_PATTERN.test('07AABCU9603R1ZM')).toBe(true)
  })
  it('agreed_credit_days must be a positive integer when provided', () => {
    expect(validateInvoice({ ...valid, agreed_credit_days: '' })).toEqual({})
    expect(validateInvoice({ ...valid, agreed_credit_days: '30' })).toEqual({})
    expect(validateInvoice({ ...valid, agreed_credit_days: '0' })).toHaveProperty('agreed_credit_days')
    expect(validateInvoice({ ...valid, agreed_credit_days: '1.5' })).toHaveProperty('agreed_credit_days')
  })
})
