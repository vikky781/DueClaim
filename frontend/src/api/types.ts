/** Wire types for /api/v1. Money fields are 2dp decimal STRINGS — render only via formatINR. */

export type EnterpriseCategory = 'micro' | 'small' | 'medium'
export type InvoiceStatus = 'unpaid' | 'partially_paid' | 'paid'

export interface Business {
  udyam_number: string
  legal_name: string
  address: string
  email: string
  enterprise_category: EnterpriseCategory
}

export interface InvoiceCreate {
  invoice_number: string
  buyer_name: string
  buyer_gstin: string | null
  buyer_is_corporate: boolean
  invoice_date: string
  acceptance_date: string
  agreed_credit_days: number | null
  amount: string
  amount_paid?: string
  status?: InvoiceStatus
}

export interface ClaimSummary {
  as_of: string
  appointed_day: string
  days_overdue: number
  principal_outstanding: string
  total_interest: string
  total_recoverable: string
}

export interface InvoiceRead {
  id: string
  invoice_number: string
  buyer_name: string
  buyer_gstin: string | null
  buyer_is_corporate: boolean
  invoice_date: string
  acceptance_date: string
  agreed_credit_days: number | null
  amount: string
  amount_paid: string
  status: InvoiceStatus
  created_at: string
  claim: ClaimSummary
}

export interface RestPeriodRead {
  period_start: string
  period_end: string
  days: number
  annual_rate_applied: string
  accrual_basis: string
  interest_for_period: string
  closing_balance: string
  is_capitalised: boolean
}

export interface InvoiceDetail extends InvoiceRead {
  breakdown: RestPeriodRead[]
}

export interface BuyerSummary {
  buyer_name: string
  principal: string
  interest: string
  oldest_days_overdue: number
  section_43bh_exposed: boolean
}

export interface PortfolioSummary {
  as_of: string
  total_principal_outstanding: string
  total_statutory_interest: string
  total_recoverable: string
  interest_accruing_per_day: string
  invoice_count: number
  overdue_count: number
  per_buyer: BuyerSummary[]
  disclaimer: string
}
