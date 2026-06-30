/**
 * Transaction detail 頁補充測試 -- 針對既有 transaction-detail.test.tsx 未覆蓋的分支：
 * loading / 查詢錯誤 / 交易不存在、note blur 自動儲存、別名 debounce、
 * 移除標籤、儲存失敗後重新整理、重複 / 空白標籤、別名顯示與重置覆寫失敗。
 */
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes } from 'react-router'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import TransactionDetailPage from '../transaction-detail'
import type { CategoryKeywordItem, TransactionDetailItem } from '@/lib/types'

function renderDetail(initialEntry: string) {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false, gcTime: 0 }, mutations: { retry: false } },
  })
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={[initialEntry]}>
        <Routes>
          <Route path="transactions/:id" element={<TransactionDetailPage />} />
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

const BASE_DETAIL: TransactionDetailItem = {
  id: 42,
  bill_id: 7,
  trans_date: '2026-03-15',
  posting_date: '2026-03-17',
  merchant: 'Starbucks',
  amount: 150,
  currency: 'TWD',
  original_amount: 4.99,
  card_last4: '1234',
  category: '餐飲',
  bank_code: 'CTBC',
  billing_month: '2026-03',
  installment_current: null,
  installment_total: null,
  note: null,
  manual_category_override: false,
  tags: [],
  merchant_alias: '',
  updated_at: '2026-03-16T10:00:00',
}

const CATEGORIES: CategoryKeywordItem[] = [
  { id: 1, keyword: '星巴克', category: '餐飲' },
  { id: 2, keyword: '購物-key', category: '購物' },
]

function setupApi(detailOverrides: Partial<TransactionDetailItem> = {}) {
  mockApiGet.mockImplementation((path: string) => {
    if (path === '/api/transactions/42') {
      return Promise.resolve({ success: true, data: { ...BASE_DETAIL, ...detailOverrides }, message: '' })
    }
    if (path === '/api/settings/categories') {
      return Promise.resolve({ success: true, data: CATEGORIES, message: '' })
    }
    return Promise.reject(new Error(`unexpected GET ${path}`))
  })
  mockApiPatch.mockImplementation((_path: string, body: unknown) => {
    void _path
    return Promise.resolve({ success: true, data: { ...BASE_DETAIL, ...detailOverrides, ...(body as object) }, message: '' })
  })
  mockApiDelete.mockResolvedValue({
    success: true,
    data: { ...BASE_DETAIL, ...detailOverrides, manual_category_override: false },
    message: '',
  })
}

beforeEach(() => {
  vi.clearAllMocks()
  setupApi()
})

// Safety net: any test that switches to fake timers (e.g. the alias-debounce
// test) is guaranteed to revert here even if an assertion throws first, so a
// fake-timer leak can never hang a subsequent test in this file.
afterEach(() => {
  vi.useRealTimers()
})

describe('TransactionDetailPage states', () => {
  it('shows the loading state while the detail query is pending', () => {
    mockApiGet.mockReturnValue(new Promise(() => {}))
    renderDetail('/transactions/42')
    expect(screen.getByText('載入中...')).toBeInTheDocument()
  })

  it('renders the query error state and refetches on retry', async () => {
    mockApiGet.mockImplementation((path: string) => {
      if (path === '/api/settings/categories') {
        return Promise.resolve({ success: true, data: CATEGORIES, message: '' })
      }
      return Promise.reject(new Error('讀取失敗'))
    })
    const user = userEvent.setup()
    renderDetail('/transactions/42')

    await waitFor(() => expect(screen.getByText('讀取失敗')).toBeInTheDocument())
    await user.click(screen.getByRole('button', { name: '重試' }))

    await waitFor(() => {
      const detailCalls = mockApiGet.mock.calls.filter(([p]) => p === '/api/transactions/42')
      expect(detailCalls.length).toBeGreaterThanOrEqual(2)
    })
  })

  it('renders the not-found state when the detail payload is null', async () => {
    mockApiGet.mockImplementation((path: string) => {
      if (path === '/api/transactions/42') {
        return Promise.resolve({ success: true, data: null, message: '' })
      }
      if (path === '/api/settings/categories') {
        return Promise.resolve({ success: true, data: CATEGORIES, message: '' })
      }
      return Promise.reject(new Error(`unexpected GET ${path}`))
    })
    const user = userEvent.setup()
    renderDetail('/transactions/42')
    await waitFor(() => expect(screen.getByText('交易不存在')).toBeInTheDocument())

    // The not-found ErrorState also wires onRetry -> refetch.
    await user.click(screen.getByRole('button', { name: '重試' }))
    await waitFor(() => {
      const detailCalls = mockApiGet.mock.calls.filter(([p]) => p === '/api/transactions/42')
      expect(detailCalls.length).toBeGreaterThanOrEqual(2)
    })
  })

  it('invokes the back-navigation handler when 返回 is clicked', async () => {
    const user = userEvent.setup()
    renderDetail('/transactions/42')
    await waitFor(() => expect(screen.getByText('Starbucks')).toBeInTheDocument())

    // navigate(-1) is a no-op at the top of the MemoryRouter stack, but the
    // click still exercises the handler.
    await user.click(screen.getByRole('button', { name: '返回' }))
    expect(screen.getByText('交易詳情')).toBeInTheDocument()
  })
})

describe('TransactionDetailPage editing', () => {
  it('flushes the note via PATCH on blur (without waiting for the debounce)', async () => {
    const user = userEvent.setup()
    renderDetail('/transactions/42')
    await waitFor(() => expect(screen.getByLabelText('備註')).toBeInTheDocument())

    await user.type(screen.getByLabelText('備註'), '機場接送')
    // Tab away -> textarea onBlur flushes the draft immediately.
    await user.tab()

    await waitFor(() => {
      expect(mockApiPatch).toHaveBeenCalledWith('/api/transactions/42', { note: '機場接送' })
    })
  })

  it('debounces the merchant alias and surfaces the saved status', async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true })
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime })
    renderDetail('/transactions/42')
    await waitFor(() => expect(screen.getByLabelText('商家別名')).toBeInTheDocument())

    await user.type(screen.getByLabelText('商家別名'), '常用店')
    expect(mockApiPatch).not.toHaveBeenCalled()

    vi.advanceTimersByTime(600)
    await waitFor(() => {
      expect(mockApiPatch).toHaveBeenCalledWith('/api/transactions/42', { merchant_alias: '常用店' })
    })
    // autoSave onSuccess flips status to "已儲存" then resets after SAVED_RESET_MS.
    await waitFor(() => expect(screen.getByText(/已儲存/)).toBeInTheDocument())
    vi.advanceTimersByTime(2100)
    await waitFor(() => expect(screen.getByText('自動儲存（500ms）')).toBeInTheDocument())
    // Real timers restored by the top-level afterEach.
  })

  it('resets the save status to idle when an auto-save PATCH fails', async () => {
    mockApiPatch.mockRejectedValue(new Error('網路中斷'))
    const user = userEvent.setup()
    renderDetail('/transactions/42')
    await waitFor(() => expect(screen.getByLabelText('備註')).toBeInTheDocument())

    await user.type(screen.getByLabelText('備註'), '失敗備註')
    await user.tab()

    await waitFor(() => expect(screen.getByRole('alert')).toHaveTextContent('儲存失敗'))
    expect(screen.getByRole('alert')).toHaveTextContent('網路中斷')
  })

  it('removes a tag and PATCHes the trimmed tag list', async () => {
    setupApi({ tags: ['業務', '出差'] })
    const user = userEvent.setup()
    renderDetail('/transactions/42')
    await waitFor(() => expect(screen.getByLabelText('移除標籤 業務')).toBeInTheDocument())

    await user.click(screen.getByLabelText('移除標籤 業務'))
    await waitFor(() => {
      expect(mockApiPatch).toHaveBeenCalledWith('/api/transactions/42', { tags: ['出差'] })
    })
  })

  it('ignores a duplicate tag and an empty tag without calling PATCH', async () => {
    setupApi({ tags: ['業務'] })
    const user = userEvent.setup()
    renderDetail('/transactions/42')
    await waitFor(() => expect(screen.getByLabelText('新增標籤')).toBeInTheDocument())

    // Duplicate tag -> early return, input cleared, no PATCH.
    await user.type(screen.getByLabelText('新增標籤'), '業務{Enter}')
    // Empty tag via the 新增 button -> guard clause returns early.
    await user.click(screen.getByRole('button', { name: '新增' }))

    expect(mockApiPatch).not.toHaveBeenCalled()
  })

  it('refetches detail when the refresh link inside the error alert is clicked', async () => {
    mockApiPatch.mockRejectedValueOnce(new Error('boom'))
    const user = userEvent.setup()
    renderDetail('/transactions/42')
    await waitFor(() => expect(screen.getByLabelText('分類')).toBeInTheDocument())

    await user.click(screen.getByLabelText('分類'))
    await user.click(await screen.findByRole('option', { name: '購物' }))
    await waitFor(() => expect(screen.getByText(/儲存失敗/)).toBeInTheDocument())

    await user.click(screen.getByRole('button', { name: '重新整理' }))
    await waitFor(() => {
      const detailCalls = mockApiGet.mock.calls.filter(([p]) => p === '/api/transactions/42')
      expect(detailCalls.length).toBeGreaterThanOrEqual(2)
    })
  })
})

describe('TransactionDetailPage conditional rendering', () => {
  it('shows the merchant alias line when an alias is set', async () => {
    setupApi({ merchant_alias: '常用咖啡' })
    renderDetail('/transactions/42')
    await waitFor(() => expect(screen.getByText('別名：常用咖啡')).toBeInTheDocument())
  })

  it('falls back to "未分類" in the category select when category is null', async () => {
    setupApi({ category: null })
    renderDetail('/transactions/42')
    await waitFor(() => expect(screen.getByText('Starbucks')).toBeInTheDocument())
    expect(screen.getByText('未分類')).toBeInTheDocument()
  })

  it('shows the reset-override error when the DELETE fails', async () => {
    setupApi({ manual_category_override: true, category: '購物' })
    mockApiDelete.mockRejectedValue(new Error('刪除失敗'))
    const user = userEvent.setup()
    renderDetail('/transactions/42')
    await waitFor(() => expect(screen.getByLabelText('重置覆寫')).toBeInTheDocument())

    await user.click(screen.getByLabelText('重置覆寫'))
    await waitFor(() => expect(screen.getByRole('alert')).toHaveTextContent('刪除失敗'))
  })
})
