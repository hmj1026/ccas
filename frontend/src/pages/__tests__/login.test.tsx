/**
 * Login 頁面測試 -- 表單渲染、成功重導、失敗錯誤訊息與空值驗證分支。
 */
import { screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import LoginPage from '../login'
import { renderWithProviders } from '@/test-utils'

vi.mock('@/lib/api-client', () => ({
  apiGet: vi.fn(),
  apiPost: vi.fn(),
}))

// useNavigate 以 hoisted spy 取代，保留 react-router 其餘導出（含 MemoryRouter）。
const mockNavigate = vi.hoisted(() => vi.fn())
vi.mock('react-router', async (importOriginal) => {
  const actual = await importOriginal<typeof import('react-router')>()
  return { ...actual, useNavigate: () => mockNavigate }
})

import { apiPost } from '@/lib/api-client'

const mockApiPost = vi.mocked(apiPost)

beforeEach(() => {
  vi.clearAllMocks()
})

describe('LoginPage', () => {
  it('renders the login form', () => {
    renderWithProviders(<LoginPage />)

    expect(
      screen.getByRole('heading', { name: '登入 CCAS' }),
    ).toBeInTheDocument()
    expect(screen.getByLabelText('API Token')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '登入' })).toBeInTheDocument()
  })

  it('navigates to /overview after a successful login', async () => {
    mockApiPost.mockResolvedValue({ success: true, data: null, message: '' })

    const user = userEvent.setup()
    renderWithProviders(<LoginPage />)

    await user.type(screen.getByLabelText('API Token'), 'secret-token')
    await user.click(screen.getByRole('button', { name: '登入' }))

    await waitFor(() =>
      expect(mockApiPost).toHaveBeenCalledWith('/api/auth/session', {
        token: 'secret-token',
      }),
    )
    await waitFor(() =>
      expect(mockNavigate).toHaveBeenCalledWith('/overview', { replace: true }),
    )
  })

  it('shows the error message when login fails', async () => {
    mockApiPost.mockRejectedValue(new Error('Token 無效'))

    const user = userEvent.setup()
    renderWithProviders(<LoginPage />)

    await user.type(screen.getByLabelText('API Token'), 'bad-token')
    await user.click(screen.getByRole('button', { name: '登入' }))

    await waitFor(() =>
      expect(screen.getByRole('alert')).toHaveTextContent('Token 無效'),
    )
    expect(mockNavigate).not.toHaveBeenCalled()
  })

  it('validates an empty token without calling the API', async () => {
    const user = userEvent.setup()
    renderWithProviders(<LoginPage />)

    await user.click(screen.getByRole('button', { name: '登入' }))

    expect(screen.getByRole('alert')).toHaveTextContent('請輸入 API Token')
    expect(mockApiPost).not.toHaveBeenCalled()
    expect(mockNavigate).not.toHaveBeenCalled()
  })
})
