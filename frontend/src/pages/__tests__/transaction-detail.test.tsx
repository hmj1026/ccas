/**
 * Transaction detail 頁測試（bills-management-and-insights §9.8）：
 * 編輯 / debounce / 樂觀更新 / 失敗 revert。
 */
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes } from 'react-router'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import TransactionDetailPage from '../transaction-detail'

function renderDetail(initialEntry: string) {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false, gcTime: 0 } },
  })
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={[initialEntry]}>
        <Routes>
          <Route
            path="transactions/:id"
            element={<TransactionDetailPage />}
          />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

vi.mock('@/lib/api-client', () => ({
  apiGet: vi.fn(),
  apiPatch: vi.fn(),
  apiDelete: vi.fn(),
}))

import { apiDelete, apiGet, apiPatch } from '@/lib/api-client'

const mockApiGet = vi.mocked(apiGet)
const mockApiPatch = vi.mocked(apiPatch)
const mockApiDelete = vi.mocked(apiDelete)

const BASE_DETAIL = {
  id: 42,
  bill_id: 7,
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
  installment_current: null as number | null,
  installment_total: null as number | null,
  note: null,
  manual_category_override: false,
  tags: [],
  merchant_alias: '',
  updated_at: '2026-03-16T10:00:00',
}

const CATEGORIES = [
  { id: 1, keyword: '星巴克', category: '餐飲' },
  { id: 2, keyword: '購物-key', category: '購物' },
]

function setupApi(detailOverrides: Partial<typeof BASE_DETAIL> = {}) {
  mockApiGet.mockImplementation((path: string) => {
    if (path === '/api/transactions/42') {
      return Promise.resolve({
        success: true,
        data: { ...BASE_DETAIL, ...detailOverrides },
        message: '',
      })
    }
    if (path === '/api/settings/categories') {
      return Promise.resolve({ success: true, data: CATEGORIES, message: '' })
    }
    return Promise.reject(new Error(`unexpected GET ${path}`))
  })
  mockApiPatch.mockImplementation((_path: string, body: unknown) => {
    void _path
    const merged = { ...BASE_DETAIL, ...detailOverrides, ...(body as object) }
    return Promise.resolve({ success: true, data: merged, message: '' })
  })
  mockApiDelete.mockImplementation(() => {
    return Promise.resolve({
      success: true,
      data: {
        ...BASE_DETAIL,
        ...detailOverrides,
        manual_category_override: false,
      },
      message: '',
    })
  })
}

beforeEach(() => {
  vi.clearAllMocks()
  setupApi()
})

describe('TransactionDetailPage', () => {
  it('renders detail and category select', async () => {
    renderDetail('/transactions/42')
    await waitFor(() => {
      expect(screen.getByText('Starbucks')).toBeInTheDocument()
    })
    expect(screen.getByLabelText('分類')).toBeInTheDocument()
    expect(screen.getByText('自動分類')).toBeInTheDocument()
  })

  it('changing category triggers PUT with category_id', async () => {
    const user = userEvent.setup()
    renderDetail('/transactions/42')
    await waitFor(() => {
      expect(screen.getByText('Starbucks')).toBeInTheDocument()
    })

    // 分類 is a SelectField (base-ui): open listbox + click option.
    await user.click(screen.getByLabelText('分類'))
    await user.click(await screen.findByRole('option', { name: '購物' }))
    await waitFor(() => {
      expect(mockApiPatch).toHaveBeenCalledWith('/api/transactions/42', {
        category_id: 2,
      })
    })
  })

  it('debounces note typing and PUTs once', async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true })
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime })
    renderDetail('/transactions/42')
    await waitFor(() => {
      expect(screen.getByLabelText('備註')).toBeInTheDocument()
    })
    const note = screen.getByLabelText('備註')
    await user.type(note, '公司聚餐')
    // before debounce window — no PUT yet
    expect(mockApiPatch).not.toHaveBeenCalled()
    vi.advanceTimersByTime(600)
    await waitFor(() => {
      expect(mockApiPatch).toHaveBeenCalledWith('/api/transactions/42', {
        note: '公司聚餐',
      })
    })
    vi.useRealTimers()
  })

  it('shows manual override badge and reset button when override is active', async () => {
    setupApi({ manual_category_override: true, category: '購物' })
    renderDetail('/transactions/42')
    await waitFor(() => {
      expect(screen.getByText('手動覆寫')).toBeInTheDocument()
    })
    expect(screen.getByLabelText('重置覆寫')).toBeInTheDocument()
  })

  it('reset button calls DELETE /manual-override', async () => {
    setupApi({ manual_category_override: true, category: '購物' })
    const user = userEvent.setup()
    renderDetail('/transactions/42')
    await waitFor(() => {
      expect(screen.getByLabelText('重置覆寫')).toBeInTheDocument()
    })
    await user.click(screen.getByLabelText('重置覆寫'))
    await waitFor(() => {
      expect(mockApiDelete).toHaveBeenCalledWith(
        '/api/transactions/42/manual-override',
      )
    })
  })

  it('adds tag and PUTs new tag list', async () => {
    const user = userEvent.setup()
    renderDetail('/transactions/42')
    await waitFor(() => {
      expect(screen.getByLabelText('新增標籤')).toBeInTheDocument()
    })
    await user.type(screen.getByLabelText('新增標籤'), '業務{Enter}')
    await waitFor(() => {
      expect(mockApiPatch).toHaveBeenCalledWith('/api/transactions/42', {
        tags: ['業務'],
      })
    })
  })

  it('shows error and revert link when PUT fails', async () => {
    mockApiPatch.mockRejectedValueOnce(new Error('boom'))
    const user = userEvent.setup()
    renderDetail('/transactions/42')
    await waitFor(() => {
      expect(screen.getByLabelText('分類')).toBeInTheDocument()
    })
    await user.click(screen.getByLabelText('分類'))
    await user.click(await screen.findByRole('option', { name: '購物' }))
    await waitFor(() => {
      expect(screen.getByText(/儲存失敗/)).toBeInTheDocument()
    })
    expect(screen.getByText('重新整理')).toBeInTheDocument()
  })

  it('rejects invalid id', () => {
    renderDetail('/transactions/abc')
    expect(screen.getByText('無效的交易 ID')).toBeInTheDocument()
  })

  it('shows installment info when present', async () => {
    setupApi({ installment_current: 3, installment_total: 12 })
    renderDetail('/transactions/42')
    await waitFor(() => {
      expect(screen.getByText('Starbucks')).toBeInTheDocument()
    })
    expect(screen.getByText('分期 3/12')).toBeInTheDocument()
  })

  it('hides installment info when absent', async () => {
    renderDetail('/transactions/42')
    await waitFor(() => {
      expect(screen.getByText('Starbucks')).toBeInTheDocument()
    })
    expect(screen.queryByText(/^分期 /)).not.toBeInTheDocument()
  })
})
