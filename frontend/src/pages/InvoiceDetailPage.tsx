import { useEffect, useState, type ReactNode } from 'react'
import { Link, useParams } from 'react-router'

import { api } from '../api/client'
import type { InvoiceDetail, NoticeResponse } from '../api/types'
import NoticePanel from '../components/NoticePanel'
import { Badge43BH, ErrorNote, Eyebrow, Loading, Money } from '../components/ui'
import { fmtDate } from '../lib/text'

type State =
  | { status: 'loading' }
  | { id: string; status: 'ready'; invoice: InvoiceDetail }
  | { id: string; status: 'error'; error: unknown }

export default function InvoiceDetailPage() {
  const { id = '' } = useParams()
  const [loaded, setLoaded] = useState<State>({ status: 'loading' })
  // A result for a different id (after navigation) is stale: show loading instead.
  const state: State = loaded.status !== 'loading' && loaded.id === id ? loaded : { status: 'loading' }

  useEffect(() => {
    let alive = true
    api
      .getInvoice(id)
      .then((invoice) => alive && setLoaded({ id, status: 'ready', invoice }))
      .catch((error: unknown) => alive && setLoaded({ id, status: 'error', error }))
    return () => {
      alive = false
    }
  }, [id])

  function onGenerated(result: NoticeResponse) {
    setLoaded((prev) =>
      prev.status === 'ready' && prev.id === id
        ? {
            ...prev,
            invoice: {
              ...prev.invoice,
              notices: [
                ...prev.invoice.notices,
                {
                  key: result.key,
                  generated_at: result.generated_at,
                  as_of: result.as_of,
                  principal_outstanding: result.principal_outstanding,
                  total_interest: result.total_interest,
                  total_recoverable: result.total_recoverable,
                },
              ],
            },
          }
        : prev,
    )
  }

  if (state.status === 'loading') return <Loading label="Computing interest" />
  if (state.status === 'error') return <ErrorNote error={state.error} />

  const inv = state.invoice
  const { claim, breakdown } = inv
  const exposed = inv.buyer_is_corporate && claim.days_overdue > 0

  return (
    <div className="animate-rise">
      <Link to="/dashboard" className="text-[13px] text-mute hover:text-paper">
        ← Dashboard
      </Link>

      {/* ---- Invoice facts ---- */}
      <header className="mt-6 flex flex-wrap items-end justify-between gap-x-12 gap-y-6">
        <div className="min-w-0">
          <Eyebrow>
            Invoice <span className="text-paper">{inv.invoice_number}</span>
          </Eyebrow>
          <h1 className="font-display mt-2 flex flex-wrap items-center gap-3 text-4xl tracking-[-0.01em] text-paper">
            {inv.buyer_name}
            {exposed && <Badge43BH />}
          </h1>
          {inv.buyer_gstin && <p className="mt-1 font-mono text-[13px] text-mute">GSTIN {inv.buyer_gstin}</p>}
        </div>
        <div className="ml-auto text-right">
          <Eyebrow>Recoverable · {fmtDate(claim.as_of)}</Eyebrow>
          <p className="font-display mt-1 text-4xl tabular-nums text-paper sm:text-5xl">
            <Money value={claim.total_recoverable} display />
          </p>
        </div>
      </header>

      <dl className="mt-10 grid grid-cols-2 gap-x-8 gap-y-5 text-[15px] sm:grid-cols-4">
        <Fact label="Invoice amount">
          <Money value={inv.amount} />
        </Fact>
        <Fact label="Paid so far">
          <Money value={inv.amount_paid} />
        </Fact>
        <Fact label="Principal outstanding">
          <Money value={claim.principal_outstanding} />
        </Fact>
        <Fact label="Statutory interest">
          <Money value={claim.total_interest} className="text-brass" />
        </Fact>
        <Fact label="Invoice date">{fmtDate(inv.invoice_date)}</Fact>
        <Fact label="Accepted">{fmtDate(inv.acceptance_date)}</Fact>
        <Fact label="Credit period">
          {inv.agreed_credit_days ? `${inv.agreed_credit_days} days` : 'None agreed'}{' '}
          <span className="text-mute">→ due {fmtDate(claim.appointed_day)}</span>
        </Fact>
        <Fact label="Overdue">
          {claim.days_overdue > 0 ? `${claim.days_overdue} days` : 'Not yet due'}
        </Fact>
      </dl>

      <NoticePanel invoiceId={inv.id} buyerName={inv.buyer_name} history={inv.notices} onGenerated={onGenerated} />

      {/* ---- Breakdown ---- */}
      <section aria-labelledby="breakdown-heading" className="mt-16">
        <div className="flex flex-wrap items-baseline justify-between gap-2">
          <Eyebrow>
            <h2 id="breakdown-heading" className="inline">
              Statement of interest
            </h2>{' '}
            · MSMED Act 2006, s.16
          </Eyebrow>
          <span className="text-[13px] text-mute">
            3 × RBI Bank Rate · monthly rests from the appointed day · days ÷ 365
          </span>
        </div>

        {breakdown.length === 0 ? (
          <p className="mt-6 text-[15px] text-mute">
            No interest has accrued. Payment falls due on {fmtDate(claim.appointed_day)}; interest begins the day
            after.
          </p>
        ) : (
          <div className="mt-4 overflow-x-auto">
            <table className="w-full min-w-[720px] border-collapse font-mono text-[13px] tabular-nums">
              <thead>
                <tr className="border-b border-rule text-[11px] uppercase tracking-[0.14em] text-mute">
                  <Th align="left">From</Th>
                  <Th align="left">To</Th>
                  <Th>Days</Th>
                  <Th>Rate p.a.</Th>
                  <Th>Accrual basis</Th>
                  <Th>Interest</Th>
                  <Th>Closing balance</Th>
                  <Th align="center">
                    <abbr title="Interest capitalised at the end of this rest period" className="no-underline">
                      Cap.
                    </abbr>
                  </Th>
                </tr>
              </thead>
              <tbody className="divide-y divide-rule/70">
                {breakdown.map((row, i) => (
                  <tr key={i} className={row.is_capitalised ? '' : 'text-paper/80'}>
                    <Td align="left">{fmtDate(row.period_start)}</Td>
                    <Td align="left">{fmtDate(row.period_end)}</Td>
                    <Td>{row.days}</Td>
                    <Td>{row.annual_rate_applied}%</Td>
                    <Td className="text-mute">
                      <Money value={row.accrual_basis} />
                    </Td>
                    <Td>
                      <Money value={row.interest_for_period} />
                    </Td>
                    <Td>
                      <Money value={row.closing_balance} />
                    </Td>
                    <Td align="center">
                      {row.is_capitalised ? (
                        <span aria-label="Capitalised" className="inline-block size-1.5 rounded-full bg-brass" />
                      ) : (
                        <span aria-label="Not capitalised" className="text-mute">
                          ·
                        </span>
                      )}
                    </Td>
                  </tr>
                ))}
              </tbody>
              <tfoot>
                <tr className="border-t border-paper/40 text-paper">
                  <Td align="left" colSpan={5} className="text-mute">
                    Total statutory interest
                  </Td>
                  <Td className="text-brass">
                    <Money value={claim.total_interest} />
                  </Td>
                  <Td>
                    <Money value={claim.total_recoverable} />
                  </Td>
                  <Td />
                </tr>
              </tfoot>
            </table>
          </div>
        )}

        <p className="mt-4 max-w-prose text-[13px] leading-relaxed text-mute">
          Each row's interest is <span className="text-paper/80">accrual basis × rate × days ÷ 365</span>. The closing
          balance of a capitalised row (<span className="inline-block size-1.5 translate-y-[-1px] rounded-full bg-brass" />)
          becomes the next row's accrual basis. The final partial month accrues simple interest and is not
          capitalised.
        </p>
      </section>
    </div>
  )
}

function Fact({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div>
      <dt className="text-[12px] text-mute">{label}</dt>
      <dd className="mt-0.5 text-paper">{children}</dd>
    </div>
  )
}

const ALIGN = { left: 'text-left', right: 'text-right', center: 'text-center' } as const

function Th({ children, align = 'right' }: { children?: ReactNode; align?: 'left' | 'right' | 'center' }) {
  return (
    <th scope="col" className={`px-2 pb-2 font-normal first:pl-0 last:pr-0 ${ALIGN[align]}`}>
      {children}
    </th>
  )
}

function Td({
  children,
  align = 'right',
  className = '',
  colSpan,
}: {
  children?: ReactNode
  align?: 'left' | 'right' | 'center'
  className?: string
  colSpan?: number
}) {
  return (
    <td colSpan={colSpan} className={`px-2 py-2.5 whitespace-nowrap first:pl-0 last:pr-0 ${ALIGN[align]} ${className}`}>
      {children}
    </td>
  )
}
