/**
 * Bills 頁面測試 -- 載入、篩選、query param 同步與付款狀態切換。
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

const MOCK_BILLS = {
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
}

beforeEach(() => {
  vi.clearAllMocks()
  mockApiGet.mockResolvedValue(MOCK_BILLS)
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

  it('shows empty state when no bills', async () => {
    mockApiGet.mockResolvedValue({ ...MOCK_BILLS, data: [] })

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

  it('toggles paid status on button click', async () => {
    const user = userEvent.setup()
    mockApiPatch.mockResolvedValue({
      success: true,
      data: { ...MOCK_BILLS.data[0], is_paid: true },
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
