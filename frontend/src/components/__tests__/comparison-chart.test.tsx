/**
 * Comparison chart 測試 -- 空資料的 EmptyState 與有資料的圖表渲染分支。
 *
 * ResponsiveContainer 在 jsdom 量不到尺寸，故 mock 成把固定寬高 clone 給子圖，
 * 使 Bar/Line 圖實際渲染（觸發 axis label formatter）而不依賴 ResizeObserver。
 */
import { cloneElement, type ReactElement } from 'react'
import { render, screen } from '@testing-library/react'
import { describe, it, expect, vi } from 'vitest'
import {
  BankComparisonBarChart,
  YearComparisonLineChart,
} from '../comparison-chart'
import type { BankCompareItem, YearCompareItem } from '@/lib/types'

vi.mock('recharts', async (importOriginal) => {
  const actual = await importOriginal<typeof import('recharts')>()
  return {
    ...actual,
    ResponsiveContainer: ({
      children,
    }: {
      children: ReactElement<{ width?: number; height?: number }>
    }) => cloneElement(children, { width: 400, height: 300 }),
  }
})

const BANKS: readonly BankCompareItem[] = [
  { bank_code: 'CTBC', bank_name: '中國信託', total: 50000 },
  { bank_code: 'FUBON', bank_name: null, total: 30000 },
]

const YEARS: readonly YearCompareItem[] = [
  { year: 2025, value: 120000 },
  { year: 2026, value: 150000 },
]

describe('BankComparisonBarChart', () => {
  it('shows empty state when there is no bank data', () => {
    render(<BankComparisonBarChart data={[]} />)
    expect(screen.getByText('尚無銀行資料')).toBeInTheDocument()
  })

  it('renders the labelled bar chart when data is present', () => {
    render(<BankComparisonBarChart data={BANKS} />)
    expect(
      screen.getByRole('img', { name: '各銀行消費金額對比圖' }),
    ).toBeInTheDocument()
  })
})

describe('YearComparisonLineChart', () => {
  it('shows empty state when there is no year data', () => {
    render(<YearComparisonLineChart data={[]} metricLabel="金額" />)
    expect(screen.getByText('尚無年度資料')).toBeInTheDocument()
  })

  it('renders the line chart with currency tooltip for 金額 metric', () => {
    render(<YearComparisonLineChart data={YEARS} metricLabel="金額" />)
    expect(
      screen.getByRole('img', { name: '年度金額對比圖' }),
    ).toBeInTheDocument()
  })

  it('renders the line chart with count tooltip for non-金額 metric', () => {
    render(<YearComparisonLineChart data={YEARS} metricLabel="筆數" />)
    expect(
      screen.getByRole('img', { name: '年度筆數對比圖' }),
    ).toBeInTheDocument()
  })
})
