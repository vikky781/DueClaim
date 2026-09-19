/**
 * Money presentation. The API sends money as 2dp decimal strings (quantized
 * once, server-side). This module only groups digits for display — it never
 * parses to a float, so no figure can drift between the API and the screen.
 */

const MONEY = /^(-)?(\d+)(?:\.(\d{1,2}))?$/

function groupIndian(intPart: string): string {
  if (intPart.length <= 3) return intPart
  const last3 = intPart.slice(-3)
  const rest = intPart.slice(0, -3)
  const pairs = rest.replace(/\B(?=(\d{2})+(?!\d))/g, ',')
  return `${pairs},${last3}`
}

/** "1234567.89" -> "₹12,34,567.89". Throws on anything that is not a plain decimal string. */
export function formatINR(value: string): string {
  const m = MONEY.exec(value.trim())
  if (!m) throw new Error(`formatINR: not a money string: ${JSON.stringify(value)}`)
  const [, sign, intPart, frac = ''] = m
  const paise = (frac + '00').slice(0, 2)
  const grouped = groupIndian(intPart.replace(/^0+(?=\d)/, ''))
  return `${sign ? '−' : ''}₹${grouped}.${paise}`
}
