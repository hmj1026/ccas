/**
 * Setup admin token rotate 頁測試（oauth-onboarding-ui §11.4）。
 *
 * 覆蓋：
 * - 渲染 last4 / 建立時間 / version
 * - 點 rotate → 顯示確認 dialog
 * - confirm → 顯示新 token + 複製按鈕
 * - 「登出此 session」呼叫 DELETE /api/auth/session 並導去 /login
 */
import { screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import SetupAdminPage from '../admin'
import { renderWithProviders } from '@/test-utils'

vi.mock('@/lib/api-client', () => ({
  apiGet: vi.fn(),
  apiPost: vi.fn(),
  apiDelete: vi.fn(),
}))

const navigateMock = vi.fn()
vi.mock('react-router', async (importOriginal) => {
  const actual =
    await importOriginal<typeof import('react-router')>()
  return {
    ...actual,
    useNavigate: () => navigateMock,
  }
})

import { apiDelete, apiGet, apiPost } from '@/lib/api-client'

const mockApiGet = vi.mocked(apiGet)
const mockApiPost = vi.mocked(apiPost)
const mockApiDelete = vi.mocked(apiDelete)

const baseTokenInfo = {
  last4: 'abcd',
  created_at: '2026-05-02T03:00:00Z',
  version: 1,
}

beforeEach(() => {
  vi.clearAllMocks()
  navigateMock.mockClear()
})

describe('SetupAdminPage', () => {
  it('renders last4 / created_at / version from token-info', async () => {
    mockApiGet.mockResolvedValue({
      success: true,
      data: baseTokenInfo,
      message: '',
    })

    renderWithProviders(<SetupAdminPage />)

    await waitFor(() =>
      expect(screen.getByText(/abcd/)).toBeInTheDocument(),
    )
    expect(screen.getByText('v1')).toBeInTheDocument()
  })

  it('opens confirmation dialog when rotate button is clicked', async () => {
    mockApiGet.mockResolvedValue({
      success: true,
      data: baseTokenInfo,
      message: '',
    })

    const user = userEvent.setup()
    renderWithProviders(<SetupAdminPage />)

    await user.click(
      await screen.findByRole('button', { name: '產生新 token' }),
    )

    expect(
      screen.getByRole('button', { name: '確認產生新 token' }),
    ).toBeInTheDocument()
    // pre-rotate dialog must NOT show plaintext yet
    expect(
      screen.queryByLabelText('新 token 明文'),
    ).not.toBeInTheDocument()
  })

  it('shows new token + copy button after confirming rotate', async () => {
    mockApiGet.mockResolvedValue({
      success: true,
      data: baseTokenInfo,
      message: '',
    })
    mockApiPost.mockResolvedValue({
      success: true,
      data: {
        token: 'NEWTOKEN123456789012345678901234',
        version: 2,
        last4: '1234',
      },
      message: '',
    })

    const user = userEvent.setup()
    renderWithProviders(<SetupAdminPage />)

    await user.click(
      await screen.findByRole('button', { name: '產生新 token' }),
    )
    await user.click(
      screen.getByRole('button', { name: '確認產生新 token' }),
    )

    await waitFor(() =>
      expect(mockApiPost).toHaveBeenCalledWith(
        '/api/setup/admin/token-rotate',
        {},
      ),
    )
    expect(
      await screen.findByLabelText('新 token 明文'),
    ).toHaveTextContent('NEWTOKEN123456789012345678901234')
    expect(
      screen.getByRole('button', { name: '複製到剪貼簿' }),
    ).toBeInTheDocument()
  })

  it('calls logout API and navigates to /login on logout button click', async () => {
    mockApiGet.mockResolvedValue({
      success: true,
      data: baseTokenInfo,
      message: '',
    })
    mockApiPost.mockResolvedValue({
      success: true,
      data: {
        token: 'NEWTOKEN123456789012345678901234',
        version: 2,
        last4: '1234',
      },
      message: '',
    })
    mockApiDelete.mockResolvedValue(null)

    const user = userEvent.setup()
    renderWithProviders(<SetupAdminPage />)

    await user.click(
      await screen.findByRole('button', { name: '產生新 token' }),
    )
    await user.click(
      screen.getByRole('button', { name: '確認產生新 token' }),
    )
    await user.click(
      await screen.findByRole('button', {
        name: '登出 session 並回登入頁',
      }),
    )

    await waitFor(() =>
      expect(mockApiDelete).toHaveBeenCalledWith('/api/auth/session'),
    )
    await waitFor(() =>
      expect(navigateMock).toHaveBeenCalledWith('/login', { replace: true }),
    )
  })
})
