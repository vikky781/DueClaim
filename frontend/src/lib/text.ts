export const DISCLAIMER =
  'Estimate only. Not legal advice. Verify Udyam registration status and the date of acceptance of goods/services before relying on these figures.'

/** "2026-09-19" -> "19 Sept 2026" (en-IN), timezone-safe. */
export function fmtDate(iso: string): string {
  const [y, m, d] = iso.split('-').map(Number)
  return new Date(Date.UTC(y, m - 1, d)).toLocaleDateString('en-IN', {
    day: 'numeric',
    month: 'short',
    year: 'numeric',
    timeZone: 'UTC',
  })
}
