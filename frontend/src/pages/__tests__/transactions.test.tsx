/**
 * Transactions 頁面測試 -- 載入、篩選與 query param 同步。
 */
import { screen, waitFor, within } from '@testing-library/react'
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

const MOCK_BANKS = [
  { id: 1, bank_code: 'CTBC', bank_name: '中信', gmail_filter: '', active_parser_version: 'v1', is_active: true },
]

const MOCK_CATEGORIES = [
  { id: 1, keyword: '星巴克', category: '餐飲' },
  { id: 2, keyword: '麥當勞', category: '餐飲' },
  { id: 3, keyword: '台電', category: '居家' },
]

function setupMocks(txResponse = MOCK_RESPONSE) {
  mockApiGet.mockImplementation((path: string) => {
    if (path === '/api/analytics/years') return Promise.resolve({ success: true, data: [2026], message: '' })
    if (path === '/api/settings/banks') return Promise.resolve({ success: true, data: MOCK_BANKS, message: '' })
    if (path === '/api/settings/categories') return Promise.resolve({ success: true, data: MOCK_CATEGORIES, message: '' })
    return Promise.resolve(txResponse)
  })
}

beforeEach(() => {
  vi.clearAllMocks()
  setupMocks()
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
    // '餐飲' appears both in the row cell and as a category <option>; assert the
    // table cell specifically via its row.
    const row = screen.getByText('Starbucks').closest('tr')
    expect(row).not.toBeNull()
    expect(within(row as HTMLElement).getByText('餐飲')).toBeInTheDocument()
    expect(screen.getByText('$150')).toBeInTheDocument()
  })

  it('shows empty state when no data', async () => {
    setupMocks({ ...MOCK_RESPONSE, data: [] })

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
    await user.keyboard('{Enter}')

    // Verify apiGet was called with q param
    await waitFor(() => {
      expect(mockApiGet).toHaveBeenCalledWith(
        '/api/transactions',
        expect.objectContaining({ q: 'star' }),
      )
    })
  })

  it('writes bank filter under the bank_code URL alias (not bank)', async () => {
    const user = userEvent.setup()
    renderWithProviders(<TransactionsPage />)

    await waitFor(() => {
      expect(screen.getByText('Starbucks')).toBeInTheDocument()
    })

    // useFilterParams maps the `bank` FilterKey to the `bank_code` URL param,
    // which the page reads back to drive the API query.
    await user.selectOptions(screen.getByLabelText('銀行篩選'), 'CTBC')

    await waitFor(() => {
      expect(mockApiGet).toHaveBeenCalledWith(
        '/api/transactions',
        expect.objectContaining({ bank_code: 'CTBC' }),
      )
    })
    // The raw `bank` key must never reach the API.
    const sawBareBankKey = mockApiGet.mock.calls.some(
      ([path, params]) =>
        path === '/api/transactions' &&
        params != null &&
        Object.prototype.hasOwnProperty.call(params, 'bank'),
    )
    expect(sawBareBankKey).toBe(false)
  })

  it('resets pagination to page 1 when a filter changes', async () => {
    const user = userEvent.setup()
    renderWithProviders(<TransactionsPage />, {
      initialEntries: ['/transactions?page=2'],
    })

    await waitFor(() => {
      expect(screen.getByText('Starbucks')).toBeInTheDocument()
    })

    // Sanity: initial load honored page=2 from the URL.
    expect(mockApiGet).toHaveBeenCalledWith(
      '/api/transactions',
      expect.objectContaining({ page: 2 }),
    )

    // Changing a filter must drop the `page` param (resetPage=true), so the
    // next query falls back to page 1.
    await user.selectOptions(screen.getByLabelText('分類篩選'), '餐飲')

    await waitFor(() => {
      expect(mockApiGet).toHaveBeenCalledWith(
        '/api/transactions',
        expect.objectContaining({ category: '餐飲', page: 1 }),
      )
    })
  })
})
