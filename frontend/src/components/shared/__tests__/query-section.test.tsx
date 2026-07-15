/**
 * QuerySection 測試 -- loading / error / retry / success render-prop 各分支。
 */
import { screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import { QuerySection, type SectionQuery } from '../query-section'
import { renderWithProviders } from '@/test-utils'

function makeQuery<T>(overrides: Partial<SectionQuery<T>>): SectionQuery<T> {
  return { isLoading: false, error: null, ...overrides }
}

describe('QuerySection', () => {
  it('renders the loading state while query.isLoading is true', () => {
    renderWithProviders(
      <QuerySection query={makeQuery<string>({ isLoading: true })}>
        {() => <div>內容</div>}
      </QuerySection>,
    )
    expect(screen.getByText('載入中...')).toBeInTheDocument()
    expect(screen.queryByText('內容')).not.toBeInTheDocument()
  })

  it('renders the error message without a retry button when onRetry is omitted', () => {
    renderWithProviders(
      <QuerySection query={makeQuery<string>({ error: new Error('查詢失敗') })}>
        {() => <div>內容</div>}
      </QuerySection>,
    )
    expect(screen.getByText('查詢失敗')).toBeInTheDocument()
    expect(screen.queryByRole('button')).not.toBeInTheDocument()
  })

  it('renders a retry button wired to onRetry on error', async () => {
    const onRetry = vi.fn()
    const user = userEvent.setup()
    renderWithProviders(
      <QuerySection
        query={makeQuery<string>({ error: new Error('查詢失敗') })}
        onRetry={onRetry}
      >
        {() => <div>內容</div>}
      </QuerySection>,
    )
    await user.click(screen.getByRole('button', { name: '重試' }))
    expect(onRetry).toHaveBeenCalledTimes(1)
  })

  it('disables the retry button while query.isFetching is true', () => {
    renderWithProviders(
      <QuerySection
        query={makeQuery<string>({
          error: new Error('查詢失敗'),
          isFetching: true,
        })}
        onRetry={vi.fn()}
      >
        {() => <div>內容</div>}
      </QuerySection>,
    )
    expect(screen.getByRole('button', { name: '重試中...' })).toBeDisabled()
  })

  it('renders children with the unwrapped data on success', () => {
    renderWithProviders(
      <QuerySection
        query={makeQuery<string>({
          data: { success: true, data: ['a', 'b'], message: '' },
        })}
      >
        {(data) => <div data-testid="content">{data.join('|')}</div>}
      </QuerySection>,
    )
    expect(screen.getByTestId('content')).toHaveTextContent('a|b')
  })

  it('falls back to an empty array when success data is missing', () => {
    renderWithProviders(
      <QuerySection query={makeQuery<string>({})}>
        {(data) => <div data-testid="content">len:{data.length}</div>}
      </QuerySection>,
    )
    expect(screen.getByTestId('content')).toHaveTextContent('len:0')
  })
})
