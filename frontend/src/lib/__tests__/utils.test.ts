/**
 * utils 純函式測試 -- 覆蓋 cn / formatDate / formatAmount / currencyFormatter。
 */
import { describe, expect, it } from 'vitest'
import { cn, currencyFormatter, formatAmount, formatDate } from '@/lib/utils'

describe('cn', () => {
  it('merges multiple classes into one string', () => {
    expect(cn('px-2', 'py-1')).toBe('px-2 py-1')
  })

  it('resolves Tailwind conflicts keeping the last class', () => {
    expect(cn('px-2', 'px-4')).toBe('px-4')
  })

  it('drops falsey conditional arguments', () => {
    expect(cn('a', false && 'b', null, undefined, 'c')).toBe('a c')
  })

  it('keeps truthy conditional arguments', () => {
    expect(cn('px-2', true && 'py-1')).toBe('px-2 py-1')
  })
})

describe('formatDate', () => {
  it('returns empty string unchanged', () => {
    expect(formatDate('')).toBe('')
  })

  it('formats a YYYY-MM month-only value to a zh-TW year/month string', () => {
    const result = formatDate('2026-03')
    expect(result).toContain('2026')
    expect(result).not.toContain('Invalid Date')
  })

  it('formats a full YYYY-MM-DD date to a zh-TW date string', () => {
    const result = formatDate('2026-03-15')
    expect(result).toContain('2026')
    expect(result).not.toContain('Invalid Date')
  })

  it('falls back to the original string when the date is unparseable', () => {
    expect(formatDate('not-a-date')).toBe('not-a-date')
  })

  it('formats an out-of-range month-only value via Date normalization (no Invalid Date)', () => {
    // JS Date 會把溢位的月份正規化（month 99 → 進位到後續年份），
    // 因此 month-only 分支不會產生 Invalid Date，不會回退原字串。
    const result = formatDate('2026-99')
    expect(result).not.toContain('Invalid Date')
    expect(result.length).toBeGreaterThan(0)
  })
})

describe('formatAmount', () => {
  it('formats a TWD amount with a $ prefix and thousands separator', () => {
    expect(formatAmount(1234)).toBe('$1,234')
  })

  it('formats a non-TWD amount with the currency code prefix', () => {
    expect(formatAmount(50, 'USD')).toBe('USD 50')
  })
})

describe('currencyFormatter', () => {
  it('formats a number with a $ prefix and thousands separator', () => {
    expect(currencyFormatter(1234)).toBe('$1,234')
  })

  it('formats a string input', () => {
    expect(currencyFormatter('1234')).toBe('$1,234')
  })

  it('formats a single-element array input', () => {
    expect(currencyFormatter(['5'])).toBe('$5')
  })

  it('produces a $-prefixed string for undefined input', () => {
    expect(currencyFormatter(undefined)).toMatch(/^\$/)
  })
})
