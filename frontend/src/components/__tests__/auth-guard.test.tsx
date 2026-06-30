/**
 * AuthGuard 測試 -- 載入態、已驗證渲染 children、未驗證重導 /login。
 */
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import AuthGuard from '../auth-guard'

vi.mock('@/lib/api-client', () => ({
  apiGet: vi.fn(),
}))

import { apiGet } from '@/lib/api-client'
const mockApiGet = vi.mocked(apiGet)

function renderGuard() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false, gcTime: 0 } },
  })
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={['/']}>
        <Routes>
          <Route
            path="/"
            element={
              <AuthGuard>
                <p>受保護內容</p>
              </AuthGuard>
            }
          />
          <Route path="/login" element={<p>登入頁</p>} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

beforeEach(() => {
  vi.clearAllMocks()
})

describe('AuthGuard', () => {
  it('shows a loading state while verifying the session', () => {
    mockApiGet.mockReturnValue(new Promise(() => {}))
    renderGuard()
    expect(screen.getByText('驗證登入狀態...')).toBeInTheDocument()
  })

  it('renders children when the session is authenticated', async () => {
    mockApiGet.mockResolvedValue({
      success: true,
      data: { authenticated: true },
      message: '',
    })
    renderGuard()
    await waitFor(() => {
      expect(screen.getByText('受保護內容')).toBeInTheDocument()
    })
  })

  it('redirects to /login when the session check throws', async () => {
    mockApiGet.mockRejectedValue(new Error('network down'))
    renderGuard()
    await waitFor(() => {
      expect(screen.getByText('登入頁')).toBeInTheDocument()
    })
  })

  it('redirects to /login when the session is not authenticated', async () => {
    mockApiGet.mockResolvedValue({
      success: true,
      data: { authenticated: false },
      message: '',
    })
    renderGuard()
    await waitFor(() => {
      expect(screen.getByText('登入頁')).toBeInTheDocument()
    })
    expect(screen.queryByText('受保護內容')).not.toBeInTheDocument()
  })
})
