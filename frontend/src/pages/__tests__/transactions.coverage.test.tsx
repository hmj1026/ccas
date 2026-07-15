/**
 * Transactions 頁面補充測試 -- 針對既有 transactions.test.tsx 未覆蓋的分支：
 * CSV 匯出（成功 / 失敗 / 檔名分支）、分頁切換、查詢錯誤重試與所有篩選參數傳遞。
 */
import { screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import TransactionsPage from '../transactions'
import { renderWithProviders } from '@/test-utils'
import type { BankConfigItem, CategoryKeywordItem, PaginatedResponse, TransactionItem } from '@/lib/types'

vi.mock('@/lib/api-client', () => ({
  apiGet: vi.fn(),
  apiFetchBlob: vi.fn(),
}))

import { apiFetchBlob, apiGet } from '@/lib/api-client'

const mockApiGet = vi.mocked(apiGet)
const mockApiFetchBlob = vi.mocked(apiFetchBlob)

const MOCK_RESPONSE: PaginatedResponse<TransactionItem> = {
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
      installment_current: null,
      installment_total: null,
    },
  ],
  message: '',
  pagination: { page: 1, page_size: 20, total: 1, total_pages: 1 },
}

const MULTI_PAGE: PaginatedResponse<TransactionItem> = {
  ...MOCK_RESPONSE,
  pagination: { page: 1, page_size: 20, total: 50, total_pages: 3 },
}

const MOCK_BANKS: BankConfigItem[] = [
  {
    id: 1,
    bank_code: 'CTBC',
    bank_name: '中信',
    gmail_filter: '',
    active_parser_version: 'v1',
    is_active: true,
  },
]

const MOCK_CATEGORIES: CategoryKeywordItem[] = [
  { id: 1, keyword: '星巴克', category: '餐飲' },
  { id: 2, keyword: '麥當勞', category: '餐飲' },
  { id: 3, keyword: '台電', category: '居家' },
]

function setupMocks(txResponse: PaginatedResponse<TransactionItem> = MOCK_RESPONSE) {
  mockApiGet.mockImplementation((path: string) => {
    if (path === '/api/analytics/years') return Promise.resolve({ success: true, data: [2026], message: '' })
    if (path === '/api/settings/banks') return Promise.resolve({ success: true, data: MOCK_BANKS, message: '' })
    if (path === '/api/settings/categories') return Promise.resolve({ success: true, data: MOCK_CATEGORIES, message: '' })
    return Promise.resolve(txResponse)
  })
}

// jsdom does not implement object-URL helpers; the export path calls both.
let anchorDownloads: string[]
let anchorClickSpy: ReturnType<typeof vi.spyOn>

beforeEach(() => {
  vi.clearAllMocks()
  setupMocks()
  URL.createObjectURL = vi.fn(() => 'blob:mock-url')
  URL.revokeObjectURL = vi.fn()
  anchorDownloads = []
  anchorClickSpy = vi
    .spyOn(HTMLAnchorElement.prototype, 'click')
    .mockImplementation(function (this: HTMLAnchorElement) {
      anchorDownloads.push(this.download)
    })
})

afterEach(() => {
  anchorClickSpy.mockRestore()
})

describe('TransactionsPage CSV export', () => {
  const exportCases = [
    { entry: '/transactions', label: 'no filter', expected: 'transactions.csv' },
    { entry: '/transactions?month=2026-03', label: 'month', expected: 'transactions-2026-03.csv' },
    { entry: '/transactions?year=2026', label: 'year', expected: 'transactions-2026.csv' },
  ] as const

  it.each(exportCases)('downloads CSV with filename derived from filters ($label)', async ({ entry, expected }) => {
    mockApiFetchBlob.mockResolvedValue(new Blob(['csv']))
    const user = userEvent.setup()
    renderWithProviders(<TransactionsPage />, { initialEntries: [entry] })

    await waitFor(() => expect(screen.getByText('Starbucks')).toBeInTheDocument())

    await user.click(screen.getByRole('button', { name: /匯出 CSV/ }))

    await waitFor(() => {
      expect(mockApiFetchBlob).toHaveBeenCalledWith(
        '/api/transactions/export',
        expect.any(Object),
      )
    })
    await waitFor(() => expect(anchorDownloads).toContain(expected))
    expect(URL.createObjectURL).toHaveBeenCalledTimes(1)
    expect(URL.revokeObjectURL).toHaveBeenCalledWith('blob:mock-url')
  })

  it('shows export error message when the blob fetch throws an Error', async () => {
    mockApiFetchBlob.mockRejectedValue(new Error('匯出爆炸'))
    const user = userEvent.setup()
    renderWithProviders(<TransactionsPage />)

    await waitFor(() => expect(screen.getByText('Starbucks')).toBeInTheDocument())
    await user.click(screen.getByRole('button', { name: /匯出 CSV/ }))

    await waitFor(() => expect(screen.getByRole('alert')).toHaveTextContent('匯出爆炸'))
  })

  it('falls back to default copy when the rejection is not an Error', async () => {
    mockApiFetchBlob.mockRejectedValue('plain string failure')
    const user = userEvent.setup()
    renderWithProviders(<TransactionsPage />)

    await waitFor(() => expect(screen.getByText('Starbucks')).toBeInTheDocument())
    await user.click(screen.getByRole('button', { name: /匯出 CSV/ }))

    await waitFor(() =>
      expect(screen.getByRole('alert')).toHaveTextContent('CSV 匯出失敗，請稍後再試'),
    )
  })
})

describe('TransactionsPage pagination', () => {
  it('navigates next then prev, syncing the page param (set + delete branches)', async () => {
    setupMocks(MULTI_PAGE)
    const user = userEvent.setup()
    renderWithProviders(<TransactionsPage />)

    await waitFor(() => expect(screen.getByText('Starbucks')).toBeInTheDocument())

    // Page 1: previous is disabled, next is enabled.
    const prev = screen.getByRole('button', { name: '上一頁' })
    const next = screen.getByRole('button', { name: '下一頁' })
    expect(prev).toBeDisabled()
    expect(next).toBeEnabled()

    // Next -> updatePage(2) takes the `set('page', '2')` branch.
    await user.click(next)
    await waitFor(() =>
      expect(mockApiGet).toHaveBeenCalledWith('/api/transactions', expect.objectContaining({ page: 2 })),
    )

    // Prev from page 2 -> updatePage(1) takes the `delete('page')` branch.
    await user.click(screen.getByRole('button', { name: '上一頁' }))
    await waitFor(() => {
      const page1Calls = mockApiGet.mock.calls.filter(
        ([path, params]) =>
          path === '/api/transactions' &&
          (params as { page?: number } | undefined)?.page === 1,
      )
      // Initial load + post-prev load both query page 1.
      expect(page1Calls.length).toBeGreaterThanOrEqual(2)
    })
  })
})

describe('TransactionsPage error + filters', () => {
  it('renders error state and refetches on retry click', async () => {
    mockApiGet.mockImplementation((path: string) => {
      if (path === '/api/analytics/years') return Promise.resolve({ success: true, data: [2026], message: '' })
      if (path === '/api/settings/banks') return Promise.resolve({ success: true, data: MOCK_BANKS, message: '' })
      if (path === '/api/settings/categories') return Promise.resolve({ success: true, data: MOCK_CATEGORIES, message: '' })
      return Promise.reject(new Error('讀取失敗'))
    })
    const user = userEvent.setup()
    renderWithProviders(<TransactionsPage />)

    await waitFor(() => expect(screen.getByText('讀取失敗')).toBeInTheDocument())

    await user.click(screen.getByRole('button', { name: '重試' }))

    await waitFor(() => {
      const txCalls = mockApiGet.mock.calls.filter(([path]) => path === '/api/transactions')
      expect(txCalls.length).toBeGreaterThanOrEqual(2)
    })
  })

  it('passes every populated filter param to the transactions query', async () => {
    renderWithProviders(<TransactionsPage />, {
      initialEntries: ['/transactions?year=2026&month=2026-03&bank_code=CTBC&category=%E9%A4%90%E9%A3%B2&q=star'],
    })

    await waitFor(() => {
      expect(mockApiGet).toHaveBeenCalledWith(
        '/api/transactions',
        expect.objectContaining({
          year: 2026,
          month: '2026-03',
          bank_code: 'CTBC',
          category: '餐飲',
          q: 'star',
        }),
      )
    })
  })
})
