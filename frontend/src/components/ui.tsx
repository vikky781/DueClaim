import type { ButtonHTMLAttributes, InputHTMLAttributes, ReactNode, SelectHTMLAttributes } from 'react'
import { Link } from 'react-router'

import { ApiError } from '../api/client'
import { formatINR } from '../lib/money'
import { DISCLAIMER } from '../lib/text'

/* ---------- typography helpers ---------- */

export function Eyebrow({ children, className = '' }: { children: ReactNode; className?: string }) {
  return (
    <div className={`font-mono text-[11px] uppercase tracking-[0.18em] text-mute ${className}`}>{children}</div>
  )
}

/** The only way money reaches the screen. `display` sets it in the serif for hero figures. */
export function Money({ value, className = '', display = false }: { value: string; className?: string; display?: boolean }) {
  return (
    <span className={`${display ? 'font-display' : 'font-mono'} tabular-nums ${className}`}>{formatINR(value)}</span>
  )
}

/* ---------- buttons ---------- */

const base =
  'inline-flex items-center justify-center gap-2 rounded-md px-4 py-2 text-[15px] font-medium transition-colors disabled:cursor-not-allowed disabled:opacity-50'

export function PrimaryButton({ className = '', ...rest }: ButtonHTMLAttributes<HTMLButtonElement>) {
  return <button {...rest} className={`${base} bg-brass text-ink hover:bg-brass-deep ${className}`} />
}

export function GhostButton({ className = '', ...rest }: ButtonHTMLAttributes<HTMLButtonElement>) {
  return (
    <button
      {...rest}
      className={`${base} border border-rule text-paper hover:border-mute hover:bg-slate ${className}`}
    />
  )
}

export function PrimaryLink({ to, children, className = '' }: { to: string; children: ReactNode; className?: string }) {
  return (
    <Link to={to} className={`${base} bg-brass text-ink hover:bg-brass-deep ${className}`}>
      {children}
    </Link>
  )
}

/* ---------- forms ---------- */

interface FieldProps {
  label: string
  name: string
  error?: string
  hint?: string
  children: ReactNode
  optional?: boolean
  /** Right-hand annotation, e.g. an auto-fill confidence marker. Replaces the "optional" tag. */
  marker?: ReactNode
}

export function Field({ label, name, error, hint, optional, marker, children }: FieldProps) {
  return (
    <div className="flex flex-col gap-1.5">
      <label htmlFor={name} className="flex items-baseline justify-between gap-3 text-[13px] text-mute">
        <span>{label}</span>
        {marker ?? (optional && <span className="font-mono text-[11px] uppercase tracking-[0.14em]">optional</span>)}
      </label>
      {children}
      {error ? (
        <p id={`${name}-error`} className="text-[13px] text-alert" role="alert">
          {error}
        </p>
      ) : hint ? (
        <p className="text-[13px] text-mute">{hint}</p>
      ) : null}
    </div>
  )
}

const control =
  'w-full rounded-md border border-rule bg-slate px-3 py-2 text-[15px] text-paper placeholder:text-mute/60 focus:border-brass focus:outline-none aria-[invalid=true]:border-alert'

export function TextInput({ className = '', ...rest }: InputHTMLAttributes<HTMLInputElement>) {
  return <input {...rest} className={`${control} ${className}`} />
}

export function Select({ className = '', ...rest }: SelectHTMLAttributes<HTMLSelectElement>) {
  return <select {...rest} className={`${control} ${className}`} />
}

export function Checkbox({ label, ...rest }: InputHTMLAttributes<HTMLInputElement> & { label: string }) {
  return (
    <label className="flex cursor-pointer items-center gap-3 text-[15px] text-paper">
      <input type="checkbox" {...rest} className="size-4 accent-brass" />
      {label}
    </label>
  )
}

/* ---------- status & feedback ---------- */

/** Headline + next step for each failure kind. The server's own message is shown underneath, never alone. */
function describe(error: unknown): { headline: string; next: string; detail?: string } {
  if (error instanceof ApiError) {
    switch (error.kind) {
      case 'config':
        return { headline: 'The app is not configured.', next: error.message }
      case 'network':
        return {
          headline: 'Can’t reach the DueClaim API.',
          next: 'Check your connection. If it persists, the backend may be down.',
          detail: error.message,
        }
      case 'auth':
        return { headline: 'Your session has expired.', next: 'Sign out and sign in again to continue.' }
      case 'not_found':
        return {
          headline: 'That isn’t in your account.',
          next: 'It may have been deleted, or the link is from another account.',
        }
      case 'validation':
        return { headline: 'Some details were not accepted.', next: error.message }
      case 'server':
        return { headline: 'Something went wrong on our side.', next: 'Try again in a moment.', detail: error.message }
    }
  }
  return {
    headline: 'Something went wrong.',
    next: 'Try again in a moment.',
    detail: error instanceof Error ? error.message : String(error),
  }
}

export function ErrorNote({ error, onRetry }: { error: unknown; onRetry?: () => void }) {
  if (!error) return null
  const { headline, next, detail } = describe(error)
  return (
    <div role="alert" className="rounded-md border border-alert/40 bg-slate px-4 py-3 text-[14px]">
      <p className="text-alert">{headline}</p>
      <p className="mt-1 text-paper">{next}</p>
      {detail && detail !== next && <p className="mt-1 font-mono text-[12px] text-mute">{detail}</p>}
      {onRetry && (
        <button type="button" onClick={onRetry} className="mt-3 text-[14px] text-brass hover:text-paper">
          Try again
        </button>
      )}
    </div>
  )
}

export function Loading({ label = 'Loading' }: { label?: string }) {
  return (
    <div className="flex items-center gap-2.5 py-8 font-mono text-[13px] text-mute" role="status">
      <span aria-hidden="true" className="inline-block size-2 rounded-full bg-mute animate-pulse-dot" />
      {label}…
    </div>
  )
}

export function Badge43BH() {
  return (
    <span
      className="inline-flex items-center rounded-sm border border-brass px-1.5 py-0.5 font-mono text-[11px] tracking-[0.08em] text-brass"
      title="Buyer is a company and payment is overdue: the expense is disallowed under s.43B(h) of the Income-tax Act until paid."
    >
      43B(h) exposed
    </span>
  )
}

export function DisclaimerFooter() {
  return (
    <footer className="mt-16 border-t border-rule pt-6 text-[13px] leading-relaxed text-mute">{DISCLAIMER}</footer>
  )
}

/** Marker shown beside an auto-filled field. Under 80% confidence it asks the user to check. */
export function AutofillMarker({ confidence }: { confidence: number }) {
  const pct = Math.round(confidence)
  if (confidence < 80) {
    return (
      <span className="font-mono text-[11px] tracking-[0.08em] text-brass">
        ▲ check this · {pct}%
      </span>
    )
  }
  return <span className="font-mono text-[11px] tracking-[0.08em] text-mute">auto-filled · {pct}%</span>
}
