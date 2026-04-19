/**
 * Bills 頁面測試 -- 載入、篩選、分頁與付款狀態切換。
 */
import { screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import BillsPage from '../bills'
import { renderWithProviders } from '@/test-utils'

vi.mock('@/lib/api-client', () => ({
  apiGet: vi.fn(),
  apiPatch: vi.fn(),
}))

import { apiGet, apiPatch } from '@/lib/api-client'
const mockApiGet = vi.mocked(apiGet)
const mockApiPatch = vi.mocked(apiPatch)

const MOCK_BILLS_RESPONSE = {
  success: true,
  data: [
    {
      id: 1,
      bank_code: 'CTBC',
      bank_name: '中國信託',
      billing_month: '2026-03',
      total_amount: 25000,
      due_date: '2026-04-15',
      is_paid: false,
      pdf_url: 'https://example.com/bill.pdf',
      created_at: '2026-03-20T10:00:00Z',
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

const MOCK_YEARS = { success: true, data: [2026, 2025], message: '' }
const MOCK_BANKS = {
  success: true,
  data: [{ id: 1, bank_code: 'CTBC', bank_name: '中國信託', gmail_filter: '', active_parser_version: 'v1', is_active: true }],
  message: '',
}
const MOCK_STAGED_EMPTY = {
  success: true,
  data: [],
  message: '',
  pagination: { page: 1, page_size: 100, total: 0, total_pages: 0 },
}

beforeEach(() => {
  vi.clearAllMocks()
  mockApiGet.mockImplementation((path: string) => {
    if (path === '/api/analytics/years') return Promise.resolve(MOCK_YEARS)
    if (path === '/api/settings/banks') return Promise.resolve(MOCK_BANKS)
    if (path === '/api/staged-attachments') return Promise.resolve(MOCK_STAGED_EMPTY)
    return Promise.resolve(MOCK_BILLS_RESPONSE)
  })
})

describe('BillsPage', () => {
  it('shows loading state initially', () => {
    mockApiGet.mockReturnValue(new Promise(() => {}))
    renderWithProviders(<BillsPage />)
    expect(screen.getByText('載入中...')).toBeInTheDocument()
  })

  it('renders bill list', async () => {
    renderWithProviders(<BillsPage />)

    await waitFor(() => {
      expect(screen.getByText('中國信託')).toBeInTheDocument()
    })
    expect(screen.getByText('$25,000')).toBeInTheDocument()
    expect(screen.getByText('PDF')).toBeInTheDocument()
  })

  it('shows total count', async () => {
    renderWithProviders(<BillsPage />)
    await waitFor(() => {
      expect(screen.getByText('共 1 筆')).toBeInTheDocument()
    })
  })

  it('shows empty state when no bills', async () => {
    mockApiGet.mockImplementation((path: string) => {
      if (path === '/api/analytics/years') return Promise.resolve(MOCK_YEARS)
      if (path === '/api/settings/banks') return Promise.resolve(MOCK_BANKS)
      if (path === '/api/staged-attachments') return Promise.resolve(MOCK_STAGED_EMPTY)
      return Promise.resolve({ ...MOCK_BILLS_RESPONSE, data: [], pagination: { ...MOCK_BILLS_RESPONSE.pagination, total: 0 } })
    })

    renderWithProviders(<BillsPage />)

    await waitFor(() => {
      expect(screen.getByText('沒有符合條件的帳單')).toBeInTheDocument()
    })
  })

  it('passes status filter to API', async () => {
    renderWithProviders(<BillsPage />, {
      initialEntries: ['/bills?status=unpaid'],
    })

    await waitFor(() => {
      expect(mockApiGet).toHaveBeenCalledWith(
        '/api/bills',
        expect.objectContaining({ status: 'unpaid' }),
      )
    })
  })

  it('passes year filter to API', async () => {
    renderWithProviders(<BillsPage />, {
      initialEntries: ['/bills?year=2025'],
    })

    await waitFor(() => {
      expect(mockApiGet).toHaveBeenCalledWith(
        '/api/bills',
        expect.objectContaining({ year: 2025 }),
      )
    })
  })

  it('shows pagination controls when multiple pages', async () => {
    mockApiGet.mockImplementation((path: string) => {
      if (path === '/api/analytics/years') return Promise.resolve(MOCK_YEARS)
      if (path === '/api/settings/banks') return Promise.resolve(MOCK_BANKS)
      if (path === '/api/staged-attachments') return Promise.resolve(MOCK_STAGED_EMPTY)
      return Promise.resolve({ ...MOCK_BILLS_RESPONSE, pagination: { page: 1, page_size: 20, total: 50, total_pages: 3 } })
    })

    renderWithProviders(<BillsPage />)

    await waitFor(() => {
      expect(screen.getByText('1 / 3')).toBeInTheDocument()
    })
    expect(screen.getByLabelText('上一頁')).toBeDisabled()
    expect(screen.getByLabelText('下一頁')).not.toBeDisabled()
  })

  it('toggles paid status on button click', async () => {
    const user = userEvent.setup()
    mockApiPatch.mockResolvedValue({
      success: true,
      data: { ...MOCK_BILLS_RESPONSE.data[0], is_paid: true },
      message: '',
    })

    renderWithProviders(<BillsPage />)

    await waitFor(() => {
      expect(screen.getByText('中國信託')).toBeInTheDocument()
    })

    const toggleButton = screen.getByLabelText('標記為已繳')
    await user.click(toggleButton)

    expect(mockApiPatch).toHaveBeenCalledWith('/api/bills/1', { is_paid: true })
  })
})
