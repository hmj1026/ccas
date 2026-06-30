/**
 * Gmail OAuth 設定頁補充覆蓋測試 -- 補齊既有 gmail.test.tsx 未覆蓋的分支：
 * credentials.json 上傳（成功 / 各種失敗）、授權按鈕啟用態、授權失敗錯誤態、
 * loading / error state、status=connected callback effect，以及 email 缺漏顯示。
 *
 * 與 gmail.test.tsx 互補，不重複既有的三步驟 / connected / revoke 案例。
 * 授權成功的跳轉行為刻意不在此觸發（會操作 window.location.href，交由 Playwright）。
 */
import { screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import GmailSetupPage from '../gmail'
import { renderWithProviders } from '@/test-utils'
import type { ApiResponse, GmailConnectionStatus } from '@/lib/types'

vi.mock('@/lib/api-client', () => ({
  apiGet: vi.fn(),
  apiPost: vi.fn(),
}))

import { apiGet, apiPost } from '@/lib/api-client'

const mockApiGet = vi.mocked(apiGet)
const mockApiPost = vi.mocked(apiPost)

/** 建立 GET /status 的回應信封，預設為「未連線」。 */
function statusResponse(
  overrides: Partial<GmailConnectionStatus> = {},
): ApiResponse<GmailConnectionStatus> {
  return {
    success: true,
    message: '',
    data: { connected: false, email: null, granted_scopes: [], ...overrides },
  }
}

/** stub 上傳端點 (raw fetch) 的成功 Response。 */
function uploadOkResponse(client_id_last8 = 'ab12cd34'): Response {
  return new Response(
    JSON.stringify({
      success: true,
      message: '',
      data: { saved_path: '/data/credentials.json', client_id_last8 },
    }),
    { status: 200, headers: { 'Content-Type': 'application/json' } },
  )
}

const CREDENTIALS_FILE = new File(['{}'], 'credentials.json', {
  type: 'application/json',
})

beforeEach(() => {
  vi.clearAllMocks()
})

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('GmailSetupPage status query states', () => {
  it('renders loading state while status query is pending', async () => {
    mockApiGet.mockReturnValue(new Promise<never>(() => {}))

    renderWithProviders(<GmailSetupPage />, { initialEntries: ['/setup/gmail'] })

    expect(
      await screen.findByText('讀取 Gmail 連線狀態...'),
    ).toBeInTheDocument()
  })

  it('renders error state when status query rejects', async () => {
    mockApiGet.mockRejectedValue(new Error('狀態讀取失敗'))

    renderWithProviders(<GmailSetupPage />, { initialEntries: ['/setup/gmail'] })

    expect(await screen.findByText('狀態讀取失敗')).toBeInTheDocument()
  })
})

describe('GmailSetupPage connected callback + view', () => {
  it('invalidates status when returning with ?status=connected', async () => {
    mockApiGet.mockResolvedValue(
      statusResponse({ connected: true, email: 'paul@example.com' }),
    )

    renderWithProviders(<GmailSetupPage />, {
      initialEntries: ['/setup/gmail?status=connected'],
    })

    expect(await screen.findByText('Gmail 已連線')).toBeInTheDocument()
  })

  it('shows placeholder when connected without an email', async () => {
    mockApiGet.mockResolvedValue(
      statusResponse({
        connected: true,
        email: null,
        granted_scopes: ['https://www.googleapis.com/auth/gmail.readonly'],
      }),
    )

    renderWithProviders(<GmailSetupPage />, { initialEntries: ['/setup/gmail'] })

    expect(await screen.findByText('Gmail 已連線')).toBeInTheDocument()
    expect(screen.getByText('（未取得使用者資訊）')).toBeInTheDocument()
  })
})

describe('GmailSetupPage credentials upload', () => {
  it('uploads credentials.json and enables the authorize button', async () => {
    const user = userEvent.setup()
    mockApiGet.mockResolvedValue(statusResponse())
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(uploadOkResponse()))

    renderWithProviders(<GmailSetupPage />, { initialEntries: ['/setup/gmail'] })

    const input = await screen.findByLabelText('上傳 credentials.json')
    expect(
      screen.getByRole('button', { name: '授權 Google' }),
    ).toBeDisabled()

    await user.upload(input, CREDENTIALS_FILE)

    await waitFor(() =>
      expect(
        screen.getByText(/client_id 末 8 字：ab12cd34/),
      ).toBeInTheDocument(),
    )
    expect(screen.getByRole('button', { name: '授權 Google' })).toBeEnabled()
  })

  it('shows the detail message when upload fails', async () => {
    const user = userEvent.setup()
    mockApiGet.mockResolvedValue(statusResponse())
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(
        new Response(JSON.stringify({ detail: 'credentials.json 格式不正確' }), {
          status: 400,
          headers: { 'Content-Type': 'application/json' },
        }),
      ),
    )

    renderWithProviders(<GmailSetupPage />, { initialEntries: ['/setup/gmail'] })

    const input = await screen.findByLabelText('上傳 credentials.json')
    await user.upload(input, CREDENTIALS_FILE)

    await waitFor(() =>
      expect(
        screen.getByText('credentials.json 格式不正確'),
      ).toBeInTheDocument(),
    )
    expect(screen.getByRole('button', { name: '授權 Google' })).toBeDisabled()
  })

  it('uses the message field when detail is absent', async () => {
    const user = userEvent.setup()
    mockApiGet.mockResolvedValue(statusResponse())
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(
        new Response(JSON.stringify({ message: '伺服器內部錯誤' }), {
          status: 500,
          headers: { 'Content-Type': 'application/json' },
        }),
      ),
    )

    renderWithProviders(<GmailSetupPage />, { initialEntries: ['/setup/gmail'] })

    const input = await screen.findByLabelText('上傳 credentials.json')
    await user.upload(input, CREDENTIALS_FILE)

    await waitFor(() =>
      expect(screen.getByText('伺服器內部錯誤')).toBeInTheDocument(),
    )
  })

  it('falls back to HTTP status when the error body is not JSON', async () => {
    const user = userEvent.setup()
    mockApiGet.mockResolvedValue(statusResponse())
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(new Response('boom', { status: 502 })),
    )

    renderWithProviders(<GmailSetupPage />, { initialEntries: ['/setup/gmail'] })

    const input = await screen.findByLabelText('上傳 credentials.json')
    await user.upload(input, CREDENTIALS_FILE)

    await waitFor(() =>
      expect(screen.getByText('HTTP 502')).toBeInTheDocument(),
    )
  })
})

describe('GmailSetupPage authorize errors', () => {
  it('shows an authorize error when the authorize request fails', async () => {
    const user = userEvent.setup()
    mockApiGet.mockImplementation(((path: string) => {
      if (path === '/api/setup/gmail/authorize') {
        return Promise.reject(new Error('尚未設定 OAuth client'))
      }
      return Promise.resolve(statusResponse())
    }) as typeof apiGet)
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(uploadOkResponse()))

    renderWithProviders(<GmailSetupPage />, { initialEntries: ['/setup/gmail'] })

    const input = await screen.findByLabelText('上傳 credentials.json')
    await user.upload(input, CREDENTIALS_FILE)

    await waitFor(() =>
      expect(
        screen.getByRole('button', { name: '授權 Google' }),
      ).toBeEnabled(),
    )

    await user.click(screen.getByRole('button', { name: '授權 Google' }))

    await waitFor(() =>
      expect(screen.getByText('尚未設定 OAuth client')).toBeInTheDocument(),
    )
    // revoke 不應在此流程被觸發
    expect(mockApiPost).not.toHaveBeenCalled()
  })
})
