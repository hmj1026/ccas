/**
 * Vitest for InsightsPage (bills-management-and-insights §13.8)。
 */
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router'
import { beforeEach, describe, expect, it, vi } from 'vitest'

vi.mock('@/lib/api-client', () => ({
  apiGet: vi.fn(),
  apiFetchBlob: vi.fn(),
}))

import { apiGet, apiFetchBlob } from '@/lib/api-client'
import InsightsPage from '@/pages/insights'

const mockedGet = vi.mocked(apiGet)
const mockedBlob = vi.mocked(apiFetchBlob)

function renderPage(url = '/insights') {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  })
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={[url]}>
        <InsightsPage />
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

function defaultMockResponses() {
  mockedGet.mockImplementation((path: string) => {
    if (path === '/api/analytics/trend') {
      return Promise.resolve({
        success: true,
        message: '',
        data: [{ month: '2026-04', total: 5000 }, { month: '2026-05', total: 7500 }],
      })
    }
    if (path === '/api/analytics/compare/banks') {
      return Promise.resolve({
        success: true,
        message: '',
        data: [
          { bank_code: 'CTBC', bank_name: '中國信託', total: 12000 },
          { bank_code: 'ESUN', bank_name: '玉山', total: 8000 },
        ],
      })
    }
    if (path === '/api/analytics/compare/years') {
      return Promise.resolve({
        success: true,
        message: '',
        data: [
          { year: 2025, value: 100000 },
          { year: 2026, value: 50000 },
        ],
      })
    }
    if (path === '/api/analytics/top-merchants') {
      return Promise.resolve({
        success: true,
        message: '',
        data: [
          { merchant: 'STARBUCKS', total: 5000, count: 12 },
          { merchant: 'UBER', total: 3000, count: 8 },
        ],
      })
    }
    if (path === '/api/analytics/categories') {
      return Promise.resolve({
        success: true,
        message: '',
        data: [
          {
            category: '餐飲',
            total: 1500,
            previous_total: 1000,
            change_percent: 50.0,
          },
        ],
      })
    }
    return Promise.resolve({ success: true, message: '', data: [] })
  })
}

describe('InsightsPage', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('renders all insight sections with default state', async () => {
    defaultMockResponses()
    renderPage()
    expect(screen.getByRole('heading', { name: 'Insights' })).toBeInTheDocument()
    expect(screen.getByText('銀行對比')).toBeInTheDocument()
    expect(screen.getByText('年度對比')).toBeInTheDocument()
    expect(screen.getByText('商家排行')).toBeInTheDocument()
    // Data renders progressively per section; wait for merchant row to appear.
    expect(await screen.findByText('STARBUCKS')).toBeInTheDocument()
  })

  it('switches year metric via select', async () => {
    defaultMockResponses()
    renderPage()
    await waitFor(() => {
      expect(screen.getByLabelText('年度對比指標')).toBeInTheDocument()
    })
    const select = screen.getByLabelText('年度對比指標')
    await userEvent.selectOptions(select, 'count')
    await waitFor(() => {
      expect(mockedGet).toHaveBeenCalledWith(
        '/api/analytics/compare/years',
        { metric: 'count' },
      )
    })
  })

  it('shows month-over-month compare section when month set', async () => {
    defaultMockResponses()
    renderPage('/insights?month=2026-05')
    expect(screen.getByText('類別 vs 上月')).toBeInTheDocument()
    // Categories data loads asynchronously; wait for the row to appear.
    expect(await screen.findByText('餐飲')).toBeInTheDocument()
    expect(screen.getByText('▲50.0%')).toBeInTheDocument()
  })

  it('opens export dialog and triggers blob download', async () => {
    defaultMockResponses()
    const blob = new Blob(['hello'], { type: 'text/csv' })
    mockedBlob.mockResolvedValueOnce(blob)

    // jsdom provides URL.createObjectURL via vitest setup; if missing, polyfill.
    if (typeof URL.createObjectURL !== 'function') {
      Object.defineProperty(URL, 'createObjectURL', {
        value: () => 'blob:fake',
        configurable: true,
      })
    }
    if (typeof URL.revokeObjectURL !== 'function') {
      Object.defineProperty(URL, 'revokeObjectURL', {
        value: () => undefined,
        configurable: true,
      })
    }

    renderPage()
    const exportBtn = await screen.findByRole('button', { name: /匯出/ })
    await userEvent.click(exportBtn)
    await waitFor(() => {
      expect(screen.getByRole('dialog')).toBeInTheDocument()
    })
    const submit = screen.getByRole('button', { name: /下載/ })
    await userEvent.click(submit)
    await waitFor(() => {
      expect(mockedBlob).toHaveBeenCalledWith(
        '/api/transactions/export',
        expect.objectContaining({ format: 'csv', include_user_fields: false }),
      )
    })
  })
})
