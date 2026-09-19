import { describe, expect, it } from 'vitest'
import { formatINR } from './money'

describe('formatINR', () => {
  it('groups with Indian lakh/crore digits and a rupee prefix', () => {
    expect(formatINR('1234567.89')).toBe('₹12,34,567.89')
    expect(formatINR('547230.62')).toBe('₹5,47,230.62')
    expect(formatINR('123456.78')).toBe('₹1,23,456.78')
    expect(formatINR('12345678901.05')).toBe('₹12,34,56,78,901.05')
  })
  it('handles small values and always shows two decimals', () => {
    expect(formatINR('0.00')).toBe('₹0.00')
    expect(formatINR('999')).toBe('₹999.00')
    expect(formatINR('1000')).toBe('₹1,000.00')
    expect(formatINR('99999.5')).toBe('₹99,999.50')
    expect(formatINR('273.38')).toBe('₹273.38')
  })
  it('never goes through a float: preserves large 2dp strings exactly', () => {
    // 16 significant digits: a Number round-trip would not be exact.
    expect(formatINR('98765432109876.54')).toBe('₹9,87,65,43,21,09,876.54')
  })
  it('handles negatives and accepts numbers of paise-strings only', () => {
    expect(formatINR('-1500.25')).toBe('−₹1,500.25')
  })
  it('throws on non-numeric input so raw API garbage never renders', () => {
    expect(() => formatINR('abc')).toThrow()
    expect(() => formatINR('')).toThrow()
  })
})
