import { useEffect, useState } from 'react'
import { Link } from 'react-router'

import { api } from '../api/client'
import type { InvoiceRead, PortfolioSummary } from '../api/types'
import { Badge43BH, ErrorNote, Eyebrow, Loading, Money, PrimaryLink } from '../components/ui'
import { fmtDate } from '../lib/text'

type State =
  | { status: 'loading' }
  | { status: 'ready'; summary: PortfolioSummary; invoices: InvoiceRead[] }
  | { status: 'error'; error: unknown }

const STATUS_LABEL: Record<InvoiceRead['status'], string> = {
  unpaid: 'Unpaid',
  partially_paid: 'Part paid',
  paid: 'Paid',
}

export default function DashboardPage() {
  const [state, setState] = useState<State>({ status: 'loading' })

  useEffect(() => {
    let alive = true
    Promise.all([api.portfolioSummary(), api.listInvoices()])
      .then(([summary, invoices]) => alive && setState({ status: 'ready', summary, invoices }))
      .catch((error: unknown) => alive && setState({ status: 'error', error }))
    return () => {
      alive = false
    }
  }, [])

  if (state.status === 'loading') return <Loading label="Computing your position" />
  if (state.status === 'error') return <ErrorNote error={state.error} />

  const { summary, invoices } = state
  if (summary.invoice_count === 0) return <EmptyState />

  const open = invoices.filter((i) => i.status !== 'paid')

  return (
    <div className="animate-rise">
      {/* ---- Hero figure ---- */}
      <section aria-labelledby="recoverable-heading">
        <Eyebrow>
          <h1 id="recoverable-heading" className="inline">
            Recoverable today
          </h1>{' '}
          · {fmtDate(summary.as_of)}
        </Eyebrow>
        <p className="font-display mt-3 text-[3.25rem] leading-none tracking-[-0.02em] tabular-nums text-paper sm:text-[5.5rem]">
          <Money value={summary.total_recoverable} display />
        </p>
        <dl className="mt-6 flex flex-wrap items-baseline gap-x-8 gap-y-2 text-[15px]">
          <div className="flex items-baseline gap-2">
            <dt className="text-mute">Principal</dt>
            <dd>
              <Money value={summary.total_principal_outstanding} />
            </dd>
          </div>
          <div className="flex items-baseline gap-2">
            <dt className="text-mute">Statutory interest</dt>
            <dd>
              <Money value={summary.total_statutory_interest} />
            </dd>
          </div>
          <div className="flex items-baseline gap-2">
            <dt className="text-mute">accruing</dt>
            <dd className="text-brass">
              <Money value={summary.interest_accruing_per_day} className="text-lg font-medium" />
              <span className="text-mute"> per day</span>
            </dd>
          </div>
        </dl>
      </section>

      {/* ---- Per-buyer ledger ---- */}
      <section aria-labelledby="buyers-heading" className="mt-16">
        <div className="flex items-baseline justify-between">
          <Eyebrow>
            <h2 id="buyers-heading" className="inline">
              By buyer
            </h2>
          </Eyebrow>
          <span className="font-mono text-[11px] uppercase tracking-[0.14em] text-mute">
            {summary.overdue_count} of {summary.invoice_count} overdue
            {summary.notices_generated > 0 && (
              <>
                {' '}· {summary.notices_generated} notice{summary.notices_generated === 1 ? '' : 's'} sent
              </>
            )}
          </span>
        </div>
        <div className="mt-2 hidden justify-end gap-8 font-mono text-[11px] uppercase tracking-[0.14em] text-mute sm:flex">
          <span className="w-24 text-right">Overdue</span>
          <span className="w-36 text-right">Principal</span>
          <span className="w-36 text-right">Interest</span>
        </div>
        <ul className="mt-2 divide-y divide-rule">
          {summary.per_buyer.map((b) => (
            <li key={b.buyer_name} className="py-3.5">
              <div className="leader text-[15px]">
                <span className="flex min-w-0 items-center gap-3">
                  <span className="truncate text-paper">{b.buyer_name}</span>
                  {b.section_43bh_exposed && <Badge43BH />}
                </span>
                <span className="flex shrink-0 items-baseline gap-8">
                  <span className="w-24 text-right font-mono tabular-nums text-mute">
                    {b.oldest_days_overdue > 0 ? `${b.oldest_days_overdue} d` : '—'}
                  </span>
                  <Money value={b.principal} className="hidden w-36 text-right text-mute sm:inline-block" />
                  <Money value={b.interest} className="w-36 text-right text-paper" />
                </span>
              </div>
            </li>
          ))}
        </ul>
      </section>

      {/* ---- Invoice list ---- */}
      <section aria-labelledby="invoices-heading" className="mt-16">
        <div className="flex items-baseline justify-between">
          <Eyebrow>
            <h2 id="invoices-heading" className="inline">
              Invoices
            </h2>
          </Eyebrow>
          <Link to="/invoices/new" className="text-[14px] text-brass hover:text-paper">
            + New invoice
          </Link>
        </div>
        <ul className="mt-3 divide-y divide-rule">
          {open.map((inv) => (
            <li key={inv.id}>
              <Link
                to={`/invoices/${inv.id}`}
                className="group -mx-3 flex items-baseline gap-4 rounded-md px-3 py-3.5 transition-colors hover:bg-slate"
              >
                <span className="w-28 shrink-0 font-mono text-[13px] text-mute">{inv.invoice_number}</span>
                <span className="min-w-0 flex-1">
                  <span className="block truncate text-[15px] text-paper">{inv.buyer_name}</span>
                  <span className="block text-[13px] text-mute">
                    {fmtDate(inv.invoice_date)}
                    {inv.status !== 'unpaid' && <> · {STATUS_LABEL[inv.status]}</>}
                    {inv.claim.days_overdue > 0 ? (
                      <> · {inv.claim.days_overdue} days overdue</>
                    ) : (
                      <> · due {fmtDate(inv.claim.appointed_day)}</>
                    )}
                  </span>
                </span>
                <span className="text-right">
                  <Money value={inv.claim.total_recoverable} className="block text-[15px] text-paper" />
                  <span className="block text-[12px] text-mute">
                    incl. <Money value={inv.claim.total_interest} /> interest
                  </span>
                </span>
                <span aria-hidden="true" className="text-mute transition-colors group-hover:text-brass">
                  →
                </span>
              </Link>
            </li>
          ))}
        </ul>
        {open.length < invoices.length && (
          <p className="mt-4 text-[13px] text-mute">
            {invoices.length - open.length} paid invoice{invoices.length - open.length === 1 ? '' : 's'} not shown.
          </p>
        )}
      </section>
    </div>
  )
}

function EmptyState() {
  return (
    <div className="animate-rise max-w-xl py-10">
      <Eyebrow>Nothing to claim yet</Eyebrow>
      <h1 className="font-display mt-3 text-[2.75rem] leading-[1.05] tracking-[-0.015em] text-balance text-paper sm:text-6xl">
        Add the first invoice a buyer has <em className="text-brass italic">not paid.</em>
      </h1>
      <p className="mt-6 text-lg leading-relaxed text-mute">
        If they are more than 45 days past acceptance, statutory interest is already running at three times the RBI
        Bank Rate, compounded monthly. We will show you exactly how much.
      </p>
      <div className="mt-10">
        <PrimaryLink to="/invoices/new">Add an unpaid invoice</PrimaryLink>
      </div>
    </div>
  )
}
