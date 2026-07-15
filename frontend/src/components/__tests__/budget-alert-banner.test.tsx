/**
 * BudgetAlertBanner 測試 -- 空陣列不渲染、警示描述（含/不含 scope_ref）、acknowledge。
 */
import { screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { BudgetAlertBanner } from '../budget-alert-banner'
import { renderWithProviders } from '@/test-utils'
import type { BudgetAlertItem } from '@/lib/types'

vi.mock('@/lib/api-client', () => ({
  apiGet: vi.fn(),
  apiPost: vi.fn(),
}))

import { apiGet, apiPost } from '@/lib/api-client'
const mockApiGet = vi.mocked(apiGet)
const mockApiPost = vi.mocked(apiPost)

const CATEGORY_ALERT: BudgetAlertItem = {
  id: 1,
  budget_id: 10,
  scope: 'monthly_category',
  scope_ref: '餐飲',
  period_year_month: '2026-03',
  threshold_breached_percent: 125,
  current_amount_ntd: 5000,
  amount_ntd: 4000,
  triggered_at: '2026-03-20T08:00:00',
  acknowledged_at: null,
}

const TOTAL_ALERT: BudgetAlertItem = {
  id: 2,
  budget_id: 11,
  scope: 'monthly_total',
  scope_ref: null,
  period_year_month: '2026-03',
  threshold_breached_percent: 120,
  current_amount_ntd: 12000,
  amount_ntd: 10000,
  triggered_at: '2026-03-20T08:00:00',
  acknowledged_at: null,
}

function envelope(data: readonly BudgetAlertItem[]) {
  return { success: true, data, message: '' }
}

beforeEach(() => {
  vi.clearAllMocks()
})

describe('BudgetAlertBanner', () => {
  it('renders nothing when there are no active alerts', async () => {
    mockApiGet.mockResolvedValue(envelope([]))
    const { container } = renderWithProviders(<BudgetAlertBanner />)
    await waitFor(() => {
      expect(mockApiGet).toHaveBeenCalledWith('/api/budgets/alerts/active')
    })
    expect(container.firstChild).toBeNull()
  })

  it('renders alert descriptions for both scope_ref and total scopes', async () => {
    mockApiGet.mockResolvedValue(envelope([CATEGORY_ALERT, TOTAL_ALERT]))
    renderWithProviders(<BudgetAlertBanner />)

    await waitFor(() => {
      expect(screen.getByText('預算超支警示')).toBeInTheDocument()
    })
    // scope_ref branch -> 類別「餐飲」
    expect(
      screen.getByText('類別「餐飲」：$5,000 / $4,000（125% 已達）'),
    ).toBeInTheDocument()
    // no scope_ref branch -> 整月支出
    expect(
      screen.getByText('整月支出：$12,000 / $10,000（120% 已達）'),
    ).toBeInTheDocument()
    expect(screen.getByRole('alert')).toBeInTheDocument()
  })

  it('acknowledges an alert via apiPost when 已知曉 is clicked', async () => {
    mockApiGet.mockResolvedValue(envelope([CATEGORY_ALERT]))
    mockApiPost.mockResolvedValue({
      success: true,
      data: { acknowledged_id: 1 },
      message: '',
    })
    const user = userEvent.setup()
    renderWithProviders(<BudgetAlertBanner />)

    const ackButton = await screen.findByRole('button', {
      name: /確認已知曉/,
    })
    await user.click(ackButton)

    await waitFor(() => {
      expect(mockApiPost).toHaveBeenCalledWith(
        '/api/budgets/alerts/1/acknowledge',
        {},
      )
    })
  })
})
