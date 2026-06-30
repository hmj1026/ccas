/**
 * TopMerchantsTable 測試 -- 空清單的 EmptyState 與有資料的列渲染。
 */
import { render, screen } from '@testing-library/react'
import { describe, it, expect } from 'vitest'
import { TopMerchantsTable } from '../top-merchants-table'
import type { TopMerchantItem } from '@/lib/types'

const MERCHANTS: readonly TopMerchantItem[] = [
  { merchant: '全聯', total: 12000, count: 8 },
  { merchant: '7-11', total: 3500, count: 15 },
]

describe('TopMerchantsTable', () => {
  it('shows empty state when there is no merchant data', () => {
    render(<TopMerchantsTable data={[]} />)
    expect(screen.getByText('尚無商家資料')).toBeInTheDocument()
  })

  it('renders ranked rows with formatted amounts and counts', () => {
    render(<TopMerchantsTable data={MERCHANTS} />)

    expect(screen.getByText('全聯')).toBeInTheDocument()
    expect(screen.getByText('7-11')).toBeInTheDocument()
    expect(screen.getByText('$12,000')).toBeInTheDocument()
    expect(screen.getByText('$3,500')).toBeInTheDocument()
    expect(screen.getByText('8')).toBeInTheDocument()
    expect(screen.getByText('15')).toBeInTheDocument()
    // Rank indices are 1-based.
    expect(screen.getByText('1')).toBeInTheDocument()
    expect(screen.getByText('2')).toBeInTheDocument()
    // Header + 2 data rows.
    expect(screen.getAllByRole('row')).toHaveLength(3)
  })
})
