/**
 * BudgetProgressCard 測試 -- 三色階（綠/黃/紅）、scope 標題、停用標記、空 current。
 */
import { render, screen } from '@testing-library/react'
import { describe, it, expect } from 'vitest'
import { BudgetProgressCard } from '../budget-progress-card'
import type { BudgetItem, BudgetCurrentPeriod } from '@/lib/types'

function makeBudget(overrides: Partial<BudgetItem> = {}): BudgetItem {
  return {
    id: 1,
    scope: 'monthly_total',
    scope_ref: null,
    amount_ntd: 10000,
    alert_threshold_percent: 80,
    enabled: true,
    created_at: '2026-03-01T00:00:00',
    updated_at: '2026-03-01T00:00:00',
    ...overrides,
  }
}

function makeCurrent(
  overrides: Partial<BudgetCurrentPeriod> = {},
): BudgetCurrentPeriod {
  return {
    budget_id: 1,
    period_year_month: '2026-03',
    amount_ntd: 10000,
    current_amount_ntd: 5000,
    percent: 50,
    threshold_breached: false,
    alert_threshold_percent: 80,
    ...overrides,
  }
}

describe('BudgetProgressCard', () => {
  it('renders green state and scope_ref title when under 80%', () => {
    render(
      <BudgetProgressCard
        budget={makeBudget({ scope: 'monthly_category', scope_ref: '餐飲' })}
        current={makeCurrent({ percent: 50, current_amount_ntd: 5000 })}
      />,
    )
    expect(screen.getByText('類別：餐飲')).toBeInTheDocument()
    const percent = screen.getByText('50.0%')
    expect(percent).toHaveClass('text-green-700')
    const bar = screen.getByRole('progressbar')
    expect(bar).toHaveClass('bg-green-500')
    expect(bar).toHaveAttribute('aria-valuenow', '50')
    expect(screen.getByText('已花 $5,000 / $10,000')).toBeInTheDocument()
    expect(screen.getByText('警示閾值 80%')).toBeInTheDocument()
  })

  it('renders yellow state between 80% and 100%', () => {
    render(
      <BudgetProgressCard
        budget={makeBudget()}
        current={makeCurrent({ percent: 85, current_amount_ntd: 8500 })}
      />,
    )
    const percent = screen.getByText('85.0%')
    expect(percent).toHaveClass('text-yellow-700')
    expect(screen.getByRole('progressbar')).toHaveClass('bg-yellow-500')
  })

  it('renders red state and caps the bar width at 100% when over budget', () => {
    render(
      <BudgetProgressCard
        budget={makeBudget()}
        current={makeCurrent({ percent: 120, current_amount_ntd: 12000 })}
      />,
    )
    const percent = screen.getByText('120.0%')
    expect(percent).toHaveClass('text-red-600')
    const bar = screen.getByRole('progressbar')
    expect(bar).toHaveClass('bg-red-500')
    expect(bar).toHaveStyle({ width: '100%' })
    // 整月支出 default scope label (no scope_ref).
    expect(screen.getByText('整月支出')).toBeInTheDocument()
  })

  it('falls back to 0% green when current period is null', () => {
    render(<BudgetProgressCard budget={makeBudget()} current={null} />)
    const percent = screen.getByText('0.0%')
    expect(percent).toHaveClass('text-green-700')
    expect(screen.getByText('已花 $0 / $10,000')).toBeInTheDocument()
  })

  it('shows the disabled marker when the budget is not enabled', () => {
    render(
      <BudgetProgressCard
        budget={makeBudget({ enabled: false })}
        current={makeCurrent()}
      />,
    )
    expect(screen.getByText('（已停用）')).toBeInTheDocument()
  })
})
