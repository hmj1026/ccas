/**
 * Overview 頁面測試 -- 載入、資料顯示與空狀態。
 */
import { screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import OverviewPage from '../overview'
import { renderWithProviders } from '@/test-utils'

vi.mock('@/lib/api-client', () => ({
  apiGet: vi.fn(),
}))

import { apiGet } from '@/lib/api-client'
const mockApiGet = vi.mocked(apiGet)

const MOCK_OVERVIEW = {
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
}

function setupMocks(overviewData = MOCK_OVERVIEW) {
  mockApiGet.mockImplementation((path: string) => {
    if (path === '/api/analytics/years') return Promise.resolve({ success: true, data: [2026], message: '' })
    if (path === '/api/settings/banks') return Promise.resolve({ success: true, data: [], message: '' })
    if (path === '/api/settings/categories') return Promise.resolve({ success: true, data: [], message: '' })
    // BudgetAlertBanner expects an array envelope; return empty so it renders null.
    if (path === '/api/budgets/alerts/active') return Promise.resolve({ success: true, data: [], message: '' })
    return Promise.resolve(overviewData)
  })
}

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
    setupMocks()
    renderWithProviders(<OverviewPage />)

    await waitFor(() => {
      // billing_month "2026-03" is localized to zh-TW year/month via formatDate.
      expect(screen.getByText('2026/03 總覽')).toBeInTheDocument()
    })
    expect(screen.getByText('$50,000')).toBeInTheDocument()
    expect(screen.getByText('$30,000')).toBeInTheDocument()
    expect(screen.getAllByText('$20,000')).toHaveLength(2)
    expect(screen.getByText('中國信託')).toBeInTheDocument()
    expect(screen.getAllByText('未繳')).toHaveLength(2)
  })

  it('shows empty state when no data', async () => {
    setupMocks({ success: true, data: null as never, message: '' })
    renderWithProviders(<OverviewPage />)

    await waitFor(() => {
      expect(screen.getByText('尚無本月資料')).toBeInTheDocument()
    })
  })

  it('shows error state on failure', async () => {
    mockApiGet.mockImplementation((path: string) => {
      if (path === '/api/analytics/years') return Promise.resolve({ success: true, data: [], message: '' })
      if (path === '/api/settings/banks') return Promise.resolve({ success: true, data: [], message: '' })
      return Promise.reject(new Error('Network error'))
    })
    renderWithProviders(<OverviewPage />)

    await waitFor(() => {
      expect(screen.getByText('Network error')).toBeInTheDocument()
    })
  })

  it('renders a retry button on error and refetches when clicked', async () => {
    let shouldFail = true
    mockApiGet.mockImplementation((path: string) => {
      if (path === '/api/budgets/alerts/active')
        return Promise.resolve({ success: true, data: [], message: '' })
      if (path === '/api/overview') {
        if (shouldFail) return Promise.reject(new Error('Network error'))
        return Promise.resolve(MOCK_OVERVIEW)
      }
      return Promise.resolve({ success: true, data: [], message: '' })
    })

    const user = userEvent.setup()
    renderWithProviders(<OverviewPage />)

    // Error state surfaces with a retry button.
    const retryButton = await screen.findByRole('button', { name: '重試' })
    expect(retryButton).toBeInTheDocument()

    // Next attempt should succeed; clicking 重試 triggers a refetch and recovers.
    shouldFail = false
    await user.click(retryButton)

    await waitFor(() => {
      expect(screen.getByText('2026/03 總覽')).toBeInTheDocument()
    })
  })
})
