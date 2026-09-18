import { useEffect, useState } from 'react'

const DISCLAIMER =
  'Estimate only. Not legal advice. Verify Udyam registration status and the date of acceptance of goods/services before relying on these figures.'

const API_URL = (import.meta.env.VITE_API_URL ?? '').replace(/\/+$/, '')

type Health =
  | { state: 'loading' }
  | { state: 'ok'; body: unknown }
  | { state: 'error'; message: string; detail?: string }

const MISSING_ENV: Health = {
  state: 'error',
  message: 'VITE_API_URL is not set.',
  detail: 'Copy frontend/.env.example to frontend/.env and set it to the ApiUrl stack output.',
}

function useHealth(): Health {
  const [health, setHealth] = useState<Health>(() => (API_URL ? { state: 'loading' } : MISSING_ENV))

  useEffect(() => {
    if (!API_URL) return
    const controller = new AbortController()
    const timeout = setTimeout(() => controller.abort(), 8000)

    fetch(`${API_URL}/health`, { signal: controller.signal })
      .then(async (res) => {
        const text = await res.text()
        if (!res.ok) {
          setHealth({ state: 'error', message: `The API answered ${res.status} ${res.statusText}.`, detail: text })
          return
        }
        try {
          setHealth({ state: 'ok', body: JSON.parse(text) })
        } catch {
          setHealth({ state: 'error', message: 'The API answered, but not with JSON.', detail: text })
        }
      })
      .catch((err: unknown) => {
        if (controller.signal.aborted) {
          setHealth({ state: 'error', message: 'The API did not answer within 8 seconds.' })
          return
        }
        setHealth({
          state: 'error',
          message: `Couldn't reach the API at ${API_URL}.`,
          detail: err instanceof Error ? err.message : String(err),
        })
      })
      .finally(() => clearTimeout(timeout))

    return () => {
      clearTimeout(timeout)
      controller.abort()
    }
  }, [])

  return health
}

function StatusDot({ state }: { state: Health['state'] }) {
  const tone =
    state === 'ok' ? 'bg-brass' : state === 'error' ? 'bg-alert' : 'bg-mute animate-pulse-dot'
  return <span aria-hidden="true" className={`inline-block size-2 rounded-full ${tone}`} />
}

export default function App() {
  const health = useHealth()

  const statusLabel =
    health.state === 'loading' ? 'Checking' : health.state === 'ok' ? 'Reachable' : 'Unreachable'

  return (
    <div className="mx-auto flex min-h-dvh w-full max-w-2xl flex-col px-6 py-10 sm:px-8 sm:py-14">
      <header className="animate-rise flex items-baseline justify-between">
        <span className="font-display text-xl font-medium tracking-tight">DueClaim</span>
        <span className="font-mono text-[11px] uppercase tracking-[0.18em] text-mute">
          MSMED Act 2006 · s.16
        </span>
      </header>

      <main className="animate-rise flex flex-1 flex-col justify-center py-16 [animation-delay:120ms] sm:py-24">
        <h1 className="font-display text-[2.75rem] leading-[1.05] font-normal tracking-[-0.015em] text-balance sm:text-6xl">
          Every overdue invoice is already{' '}
          <em className="text-brass italic">earning interest.</em>
        </h1>
        <p className="mt-6 max-w-prose text-lg leading-relaxed text-mute">
          Statutory interest on unpaid MSE invoices, computed to the paise, month by month, and
          drafted into a demand notice.
        </p>

        <section aria-labelledby="backend-heading" className="mt-16">
          <h2
            id="backend-heading"
            className="font-mono text-[11px] uppercase tracking-[0.18em] text-mute"
          >
            Backend
          </h2>
          <dl className="mt-4 space-y-3 text-[15px]">
            <div className="leader">
              <dt className="text-paper">API</dt>
              <dd className="flex items-center gap-2.5 font-mono" aria-live="polite">
                <StatusDot state={health.state} />
                <span className={health.state === 'error' ? 'text-alert' : 'text-paper'}>
                  {statusLabel}
                </span>
              </dd>
            </div>
            <div className="leader">
              <dt className="text-paper">Endpoint</dt>
              <dd className="max-w-[70%] truncate font-mono text-mute" title={API_URL || undefined}>
                {API_URL ? `${API_URL}/health` : '—'}
              </dd>
            </div>
          </dl>

          <div className="mt-6 rounded-md border border-rule bg-slate px-4 py-3 font-mono text-[13px] leading-relaxed">
            {health.state === 'loading' && <span className="text-mute">Waiting for a response…</span>}
            {health.state === 'ok' && (
              <pre className="whitespace-pre-wrap break-all text-paper">
                {JSON.stringify(health.body, null, 2)}
              </pre>
            )}
            {health.state === 'error' && (
              <div role="alert">
                <p className="text-alert">{health.message}</p>
                {health.detail && <p className="mt-1 break-all text-mute">{health.detail}</p>}
              </div>
            )}
          </div>
        </section>
      </main>

      <footer className="animate-rise border-t border-rule pt-6 text-[13px] leading-relaxed text-mute [animation-delay:240ms]">
        {DISCLAIMER}
      </footer>
    </div>
  )
}
