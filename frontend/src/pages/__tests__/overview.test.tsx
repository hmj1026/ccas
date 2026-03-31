/**
 * Overview 頁面測試 -- 載入、資料顯示與空狀態。
 */
import { screen, waitFor } from '@testing-library/react'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import OverviewPage from '../overview'
import { renderWithProviders } from '@/test-utils'

vi.mock('@/lib/api-client', () => ({
  apiGet: vi.fn(),
}))

import { apiGet } from '@/lib/api-client'
const mockApiGet = vi.mocked(apiGet)

beforeEach(() => {
  vi.clearAllMocks()
})

describe('OverviewPage', () => {
  it('shows loading state initially', () => {
    mockApiGet.mockReturnValue(new Promise(() => {}))
    renderWithProviders(<OverviewPage />)
    expect(screen.getByText('載入中...')).toBeInTheDocument()
  })

  it('renders overview data', async () => {
    mockApiGet.mockResolvedValue({
      success: true,
      data: {
        month: '2026-03',
        total_spending: 50000,
        total_paid: 30000,
        total_unpaid: 20000,
        upcoming_bills: [
          {
            id: 1,
            bank_code: 'CTBC',
            bank_name: '中國信託',
            billing_month: '2026-03',
            total_amount: 20000,
            due_date: '2026-04-15',
            is_paid: false,
          },
        ],
      },
      message: '',
    })

    renderWithProviders(<OverviewPage />)

    await waitFor(() => {
      expect(screen.getByText('2026-03 總覽')).toBeInTheDocument()
    })
    expect(screen.getByText('$50,000')).toBeInTheDocument()
    expect(screen.getByText('$30,000')).toBeInTheDocument()
    expect(screen.getAllByText('$20,000')).toHaveLength(2)
    expect(screen.getByText('中國信託')).toBeInTheDocument()
    expect(screen.getAllByText('未繳')).toHaveLength(2)
  })

  it('shows empty state when no data', async () => {
    mockApiGet.mockResolvedValue({
      success: true,
      data: null,
      message: '',
    })

    renderWithProviders(<OverviewPage />)

    await waitFor(() => {
      expect(screen.getByText('尚無本月資料')).toBeInTheDocument()
    })
  })

  it('shows error state on failure', async () => {
    mockApiGet.mockRejectedValue(new Error('Network error'))

    renderWithProviders(<OverviewPage />)

    await waitFor(() => {
      expect(screen.getByText('Network error')).toBeInTheDocument()
    })
  })
})
