/**
 * App 元件冒煙測試。
 *
 * 驗證根元件會先做 session 驗證，未登入時顯示登入表單。
 */
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, it, expect, vi } from 'vitest'
import App from './App'

vi.mock('@/lib/api-client', () => ({
  apiGet: vi.fn(),
  apiPost: vi.fn(),
}))

import { apiGet, apiPost } from '@/lib/api-client'

const mockApiGet = vi.mocked(apiGet)
const mockApiPost = vi.mocked(apiPost)

beforeEach(() => {
  vi.clearAllMocks()
})

describe('App', () => {
  it('renders the sidebar with navigation for an authenticated session', async () => {
    mockApiGet.mockImplementation((path: string) => {
      if (path === '/api/auth/session') {
        return Promise.resolve({
          success: true,
          data: { authenticated: true },
          message: '',
        })
      }
      return new Promise(() => {})
    })

    render(<App />)

    await waitFor(() => {
      expect(screen.getByText('總覽')).toBeInTheDocument()
    })
    expect(screen.getByText('交易')).toBeInTheDocument()
    expect(screen.getByText('分析')).toBeInTheDocument()
    expect(screen.getByText('帳單')).toBeInTheDocument()
    expect(screen.getByText('設定')).toBeInTheDocument()
  })

  it('renders a login form when the session is missing', async () => {
    mockApiGet.mockRejectedValue(new Error('HTTP 401'))

    render(<App />)

    await waitFor(() => {
      expect(screen.getByRole('heading', { name: '登入 CCAS' })).toBeInTheDocument()
    })
    expect(screen.getByLabelText('API Token')).toBeInTheDocument()
  })

  it('submits the login form to create a session cookie', async () => {
    const user = userEvent.setup()
    mockApiGet.mockRejectedValue(new Error('HTTP 401'))
    mockApiPost.mockResolvedValue({ success: true, data: null, message: '' })

    render(<App />)

    await waitFor(() => {
      expect(screen.getByLabelText('API Token')).toBeInTheDocument()
    })

    await user.type(screen.getByLabelText('API Token'), 'test-token')
    await user.click(screen.getByRole('button', { name: '登入' }))

    expect(mockApiPost).toHaveBeenCalledWith('/api/auth/session', {
      token: 'test-token',
    })
  })
})
