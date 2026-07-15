/**
 * states 測試 -- LoadingState / ErrorState / EmptyState 的預設值與選填分支。
 */
import { screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import { EmptyState, ErrorState, LoadingState } from '../states'
import { renderWithProviders } from '@/test-utils'

describe('LoadingState', () => {
  it('renders the default message', () => {
    renderWithProviders(<LoadingState />)
    expect(screen.getByRole('status')).toBeInTheDocument()
    expect(screen.getByText('載入中...')).toBeInTheDocument()
  })

  it('renders a custom message', () => {
    renderWithProviders(<LoadingState message="正在計算..." />)
    expect(screen.getByText('正在計算...')).toBeInTheDocument()
  })
})

describe('ErrorState', () => {
  it('renders the default message and no retry button', () => {
    renderWithProviders(<ErrorState />)
    expect(screen.getByRole('alert')).toBeInTheDocument()
    expect(screen.getByText('發生錯誤')).toBeInTheDocument()
    expect(screen.queryByRole('button')).not.toBeInTheDocument()
  })

  it('renders a custom error message', () => {
    renderWithProviders(<ErrorState message="伺服器爆炸" />)
    expect(screen.getByText('伺服器爆炸')).toBeInTheDocument()
  })

  it('renders an enabled retry button when onRetry is provided and fires it on click', async () => {
    const onRetry = vi.fn()
    const user = userEvent.setup()
    const { container } = renderWithProviders(<ErrorState onRetry={onRetry} />)

    const button = screen.getByRole('button', { name: '重試' })
    expect(button).toBeEnabled()
    // not retrying -> spinner icon must not have the spin animation.
    expect(container.querySelector('.animate-spin')).toBeNull()

    await user.click(button)
    expect(onRetry).toHaveBeenCalledTimes(1)
  })

  it('disables the retry button and shows the retrying label while isRetrying is true', () => {
    const onRetry = vi.fn()
    const { container } = renderWithProviders(
      <ErrorState onRetry={onRetry} isRetrying />,
    )

    const button = screen.getByRole('button', { name: '重試中...' })
    expect(button).toBeDisabled()
    // retrying -> spinner icon carries the spin animation class.
    expect(container.querySelector('.animate-spin')).not.toBeNull()
  })
})

describe('EmptyState', () => {
  it('renders the default message', () => {
    renderWithProviders(<EmptyState />)
    expect(screen.getByRole('status')).toBeInTheDocument()
    expect(screen.getByText('暫無資料')).toBeInTheDocument()
  })

  it('renders a custom message', () => {
    renderWithProviders(<EmptyState message="找不到符合的交易" />)
    expect(screen.getByText('找不到符合的交易')).toBeInTheDocument()
  })
})
