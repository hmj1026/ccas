/**
 * Vitest for SettingsBudgetsPage (bills-management-and-insights §12.6)。
 */
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'

vi.mock('@/lib/api-client', () => ({
  apiGet: vi.fn(),
  apiPost: vi.fn(),
  apiPut: vi.fn(),
  apiDelete: vi.fn(),
}))

import { apiDelete, apiGet, apiPost, apiPut } from '@/lib/api-client'
import SettingsBudgetsPage from '@/pages/settings-budgets'
import type { BudgetItem } from '@/lib/types'

const mockedGet = vi.mocked(apiGet)
const mockedPost = vi.mocked(apiPost)
const mockedPut = vi.mocked(apiPut)
const mockedDelete = vi.mocked(apiDelete)

const sampleBudget: BudgetItem = {
  id: 1,
  scope: 'monthly_total',
  scope_ref: null,
  amount_minor_units: 30000,
  alert_threshold_percent: 80,
  enabled: true,
  created_at: '2026-05-01T00:00:00Z',
  updated_at: '2026-05-01T00:00:00Z',
}

function renderPage() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  })
  return render(
    <QueryClientProvider client={client}>
      <SettingsBudgetsPage />
    </QueryClientProvider>,
  )
}

describe('SettingsBudgetsPage', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('shows empty state when no budgets', async () => {
    mockedGet.mockImplementation((path: string) => {
      if (path === '/api/budgets') {
        return Promise.resolve({ success: true, data: [], message: '' })
      }
      return Promise.resolve({ success: true, data: null, message: '' })
    })
    renderPage()
    await waitFor(() => {
      expect(
        screen.getByText(/尚未設定任何預算/),
      ).toBeInTheDocument()
    })
  })

  it('renders budget with progress bar', async () => {
    mockedGet.mockImplementation((path: string) => {
      if (path === '/api/budgets') {
        return Promise.resolve({
          success: true,
          data: [sampleBudget],
          message: '',
        })
      }
      if (path === '/api/budgets/1/current-period') {
        return Promise.resolve({
          success: true,
          data: {
            budget_id: 1,
            period_year_month: '2026-05',
            amount_minor_units: 30000,
            current_amount_minor_units: 24000,
            percent: 80.0,
            threshold_breached: true,
            alert_threshold_percent: 80,
          },
          message: '',
        })
      }
      return Promise.resolve({ success: true, data: null, message: '' })
    })

    renderPage()
    await waitFor(() => {
      expect(screen.getByText('整月支出')).toBeInTheDocument()
    })
    await waitFor(() => {
      expect(screen.getByText(/80\.0%/)).toBeInTheDocument()
    })
    expect(screen.getByText(/已花 \$24,000/)).toBeInTheDocument()
  })

  it('creates a new budget via dialog', async () => {
    mockedGet.mockResolvedValue({ success: true, data: [], message: '' })
    mockedPost.mockResolvedValue({
      success: true,
      data: sampleBudget,
      message: '',
    })

    renderPage()
    const newBtn = await screen.findByRole('button', { name: /新增預算/ })
    await userEvent.click(newBtn)

    const amountInput = screen.getByLabelText(/月度上限金額/)
    await userEvent.clear(amountInput)
    await userEvent.type(amountInput, '30000')

    const submitBtn = screen.getByRole('button', { name: '建立' })
    await userEvent.click(submitBtn)

    await waitFor(() => {
      expect(mockedPost).toHaveBeenCalledWith(
        '/api/budgets',
        expect.objectContaining({
          scope: 'monthly_total',
          scope_ref: null,
          amount_minor_units: 30000,
          alert_threshold_percent: 80,
          enabled: true,
        }),
      )
    })
  })

  it('rejects creation when monthly_category lacks scope_ref', async () => {
    mockedGet.mockResolvedValue({ success: true, data: [], message: '' })
    renderPage()
    await userEvent.click(
      await screen.findByRole('button', { name: /新增預算/ }),
    )

    const scopeSelect = screen.getByLabelText(/範圍/)
    await userEvent.selectOptions(scopeSelect, 'monthly_category')

    const amountInput = screen.getByLabelText(/月度上限金額/)
    await userEvent.type(amountInput, '5000')
    await userEvent.click(screen.getByRole('button', { name: '建立' }))

    expect(screen.getByText(/必須指定範圍/)).toBeInTheDocument()
    expect(mockedPost).not.toHaveBeenCalled()
  })

  it('deletes a budget', async () => {
    mockedGet.mockImplementation((path: string) => {
      if (path === '/api/budgets') {
        return Promise.resolve({
          success: true,
          data: [sampleBudget],
          message: '',
        })
      }
      return Promise.resolve({ success: true, data: null, message: '' })
    })
    mockedDelete.mockResolvedValue({
      success: true,
      data: { deleted_id: 1 },
      message: '',
    })

    renderPage()
    const deleteBtn = await screen.findByRole('button', { name: /刪除/ })
    await userEvent.click(deleteBtn)
    await waitFor(() => {
      expect(mockedDelete).toHaveBeenCalledWith('/api/budgets/1')
    })
  })

  it('toggles enabled flag', async () => {
    mockedGet.mockImplementation((path: string) => {
      if (path === '/api/budgets') {
        return Promise.resolve({
          success: true,
          data: [sampleBudget],
          message: '',
        })
      }
      return Promise.resolve({ success: true, data: null, message: '' })
    })
    mockedPut.mockResolvedValue({
      success: true,
      data: { ...sampleBudget, enabled: false },
      message: '',
    })

    renderPage()
    const checkbox = await screen.findByLabelText('啟用')
    await userEvent.click(checkbox)
    await waitFor(() => {
      expect(mockedPut).toHaveBeenCalledWith('/api/budgets/1', {
        enabled: false,
      })
    })
  })
})
