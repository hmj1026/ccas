/**
 * Transactions 頁面測試 -- 載入、篩選與 query param 同步。
 */
import { screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import TransactionsPage from '../transactions'
import { renderWithProviders } from '@/test-utils'

vi.mock('@/lib/api-client', () => ({
  apiGet: vi.fn(),
  apiFetchBlob: vi.fn(),
}))

import { apiGet } from '@/lib/api-client'
const mockApiGet = vi.mocked(apiGet)

const MOCK_RESPONSE = {
  success: true,
  data: [
    {
      id: 1,
      bill_id: 1,
      trans_date: '2026-03-15',
      posting_date: null,
      merchant: 'Starbucks',
      amount: 150,
      currency: 'TWD',
      original_amount: null,
      card_last4: '1234',
      category: '餐飲',
      bank_code: 'CTBC',
      billing_month: '2026-03',
    },
  ],
  message: '',
  pagination: {
    page: 1,
    page_size: 20,
    total: 1,
    total_pages: 1,
  },
}

beforeEach(() => {
  vi.clearAllMocks()
  mockApiGet.mockResolvedValue(MOCK_RESPONSE)
})

describe('TransactionsPage', () => {
  it('shows loading state initially', () => {
    mockApiGet.mockReturnValue(new Promise(() => {}))
    renderWithProviders(<TransactionsPage />)
    expect(screen.getByText('載入中...')).toBeInTheDocument()
  })

  it('renders transaction list', async () => {
    renderWithProviders(<TransactionsPage />)

    await waitFor(() => {
      expect(screen.getByText('Starbucks')).toBeInTheDocument()
    })
    expect(screen.getByText('餐飲')).toBeInTheDocument()
    expect(screen.getByText('$150')).toBeInTheDocument()
  })

  it('shows empty state when no data', async () => {
    mockApiGet.mockResolvedValue({
      ...MOCK_RESPONSE,
      data: [],
    })

    renderWithProviders(<TransactionsPage />)

    await waitFor(() => {
      expect(screen.getByText('找不到符合條件的交易')).toBeInTheDocument()
    })
  })

  it('passes filter params to API', async () => {
    renderWithProviders(<TransactionsPage />, {
      initialEntries: ['/transactions?bank_code=CTBC&category=%E9%A4%90%E9%A3%B2'],
    })

    await waitFor(() => {
      expect(mockApiGet).toHaveBeenCalledWith(
        '/api/transactions',
        expect.objectContaining({
          bank_code: 'CTBC',
          category: '餐飲',
        }),
      )
    })
  })

  it('updates search params when typing in search', async () => {
    const user = userEvent.setup()
    renderWithProviders(<TransactionsPage />)

    await waitFor(() => {
      expect(screen.getByText('Starbucks')).toBeInTheDocument()
    })

    const searchInput = screen.getByLabelText('商家搜尋')
    await user.type(searchInput, 'star')

    // Verify apiGet was called with q param
    await waitFor(() => {
      expect(mockApiGet).toHaveBeenCalledWith(
        '/api/transactions',
        expect.objectContaining({ q: 'star' }),
      )
    })
  })
})
