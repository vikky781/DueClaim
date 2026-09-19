import { useState } from 'react'

import { api } from '../api/client'
import type { NoticeRecord, NoticeResponse } from '../api/types'
import { fmtDate } from '../lib/text'
import { ErrorNote, Eyebrow, Money, PrimaryButton } from './ui'

type Phase = { kind: 'idle' } | { kind: 'working' } | { kind: 'done'; result: NoticeResponse } | { kind: 'failed'; error: unknown }

interface Props {
  invoiceId: string
  buyerName: string
  /** Notices already generated for this invoice (from the invoice record). */
  history: NoticeRecord[]
  /** Called after a successful generation so the parent can refresh its record. */
  onGenerated?: (result: NoticeResponse) => void
}

function fmtTime(iso: string): string {
  return new Date(iso).toLocaleString('en-IN', { day: 'numeric', month: 'short', year: 'numeric', hour: 'numeric', minute: '2-digit' })
}

/**
 * The payoff: turn the computed claim into a demand notice PDF.
 * Opens the PDF in a new tab and confirms the figures it was generated against.
 */
export default function NoticePanel({ invoiceId, buyerName, history, onGenerated }: Props) {
  const [phase, setPhase] = useState<Phase>({ kind: 'idle' })

  async function generate() {
    // Open the tab synchronously inside the click so popup blockers allow it,
    // then point it at the PDF once the URL arrives. If blocked, the inline link still works.
    const tab = window.open('', '_blank')
    setPhase({ kind: 'working' })
    try {
      const result = await api.generateNotice(invoiceId)
      if (tab) tab.location.href = result.url
      setPhase({ kind: 'done', result })
      onGenerated?.(result)
    } catch (error) {
      tab?.close()
      setPhase({ kind: 'failed', error })
    }
  }

  const working = phase.kind === 'working'

  return (
    <section aria-labelledby="notice-heading" className="mt-16 rounded-md border border-rule bg-slate p-6">
      <div className="flex flex-wrap items-start justify-between gap-6">
        <div className="max-w-md">
          <Eyebrow>
            <h2 id="notice-heading" className="inline">
              Demand notice
            </h2>
          </Eyebrow>
          <p className="mt-2 text-[15px] leading-relaxed text-paper">
            A formal notice to {buyerName} under Sections 15, 16 and 24 of the MSMED Act, with the full statement of
            interest attached.
          </p>
          <p className="mt-1 text-[13px] text-mute">
            Figures are computed as of today when you generate it. Review it before sending.
          </p>
        </div>
        <PrimaryButton type="button" onClick={generate} disabled={working} className="shrink-0">
          {working ? (
            <>
              <span aria-hidden="true" className="inline-block size-2 rounded-full bg-ink/60 animate-pulse-dot" />
              Generating…
            </>
          ) : history.length > 0 ? (
            'Generate a fresh notice'
          ) : (
            'Generate demand notice'
          )}
        </PrimaryButton>
      </div>

      {phase.kind === 'done' && (
        <div role="status" aria-live="polite" className="mt-6 border-t border-rule pt-5">
          <p className="text-[15px] text-paper">
            Notice generated as of {fmtDate(phase.result.as_of)}.{' '}
            <a href={phase.result.url} target="_blank" rel="noopener" className="text-brass underline-offset-4 hover:underline">
              Open the PDF
            </a>
            <span className="text-mute"> — link valid for one hour.</span>
          </p>
          <dl className="mt-4 grid grid-cols-2 gap-x-8 gap-y-3 text-[15px] sm:grid-cols-4">
            <div>
              <dt className="text-[12px] text-mute">Principal</dt>
              <dd>
                <Money value={phase.result.principal_outstanding} />
              </dd>
            </div>
            <div>
              <dt className="text-[12px] text-mute">Statutory interest</dt>
              <dd>
                <Money value={phase.result.total_interest} className="text-brass" />
              </dd>
            </div>
            <div>
              <dt className="text-[12px] text-mute">Total demanded</dt>
              <dd>
                <Money value={phase.result.total_recoverable} />
              </dd>
            </div>
            <div>
              <dt className="text-[12px] text-mute">Overdue</dt>
              <dd className="font-mono tabular-nums">{phase.result.days_overdue} days</dd>
            </div>
          </dl>
        </div>
      )}

      {phase.kind === 'failed' && (
        <div className="mt-6">
          <ErrorNote error={phase.error} />
        </div>
      )}

      {history.length > 0 && (
        <div className="mt-6 border-t border-rule pt-5">
          <Eyebrow>Previously generated</Eyebrow>
          <ul className="mt-2 divide-y divide-rule/60">
            {[...history].reverse().map((n) => (
              <li key={n.key} className="leader py-2 text-[13px]">
                <span className="text-mute">
                  {fmtTime(n.generated_at)} <span className="text-mute/70">· as of {fmtDate(n.as_of)}</span>
                </span>
                <Money value={n.total_recoverable} className="text-paper" />
              </li>
            ))}
          </ul>
        </div>
      )}
    </section>
  )
}
