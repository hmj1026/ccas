/**
 * StagedAttachmentsWarning 測試 -- 驗證空結果不渲染、badge 呈現、展開互動。
 */
import { screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { StagedAttachmentsWarning } from '../staged-attachments-warning'
import { renderWithProviders } from '@/test-utils'

vi.mock('@/lib/api-client', () => ({
  apiGet: vi.fn(),
}))

import { apiGet } from '@/lib/api-client'
const mockApiGet = vi.mocked(apiGet)

const EMPTY_RESPONSE = {
  success: true,
  data: [],
  message: '',
  pagination: { page: 1, page_size: 100, total: 0, total_pages: 0 },
}

const WARN_RESPONSE = {
  success: true,
  data: [
    {
      id: 1,
      bank_code: 'FUBON',
      bank_name: '富邦',
      status: 'fetch_expired',
      original_filename: 'fubon-2026-03.pdf',
      message_date: '2026-03-15T00:00:00',
      error_reason: 'fetch_expired: serial_key expired',
      source_type: 'web_fetch',
      created_at: '2026-03-16T00:00:00',
    },
    {
      id: 2,
      bank_code: 'CTBC',
      bank_name: '中國信託',
      status: 'failed',
      original_filename: 'ctbc-2026-02.pdf',
      message_date: '2026-02-20T00:00:00',
      error_reason: 'download_error',
      source_type: 'attachment',
      created_at: '2026-02-21T00:00:00',
    },
  ],
  message: '',
  pagination: { page: 1, page_size: 100, total: 2, total_pages: 1 },
}

beforeEach(() => {
  vi.clearAllMocks()
})

describe('StagedAttachmentsWarning', () => {
  it('renders nothing when there are no warning attachments', async () => {
    mockApiGet.mockResolvedValue(EMPTY_RESPONSE)
    const { container } = renderWithProviders(<StagedAttachmentsWarning />)
    await waitFor(() => {
      expect(mockApiGet).toHaveBeenCalled()
    })
    expect(container.firstChild).toBeNull()
  })

  it('renders nothing while loading', () => {
    mockApiGet.mockReturnValue(new Promise(() => {}))
    const { container } = renderWithProviders(<StagedAttachmentsWarning />)
    expect(container.firstChild).toBeNull()
  })

  it('shows summary count and status breakdown when data present', async () => {
    mockApiGet.mockResolvedValue(WARN_RESPONSE)
    renderWithProviders(<StagedAttachmentsWarning />)

    await waitFor(() => {
      expect(screen.getByText(/需要注意的附件（2 筆）/)).toBeInTheDocument()
    })
    expect(screen.getByText(/連結已失效 1/)).toBeInTheDocument()
    expect(screen.getByText(/下載失敗 1/)).toBeInTheDocument()
  })

  it('expands detail list on click and shows per-status hint', async () => {
    const user = userEvent.setup()
    mockApiGet.mockResolvedValue(WARN_RESPONSE)
    renderWithProviders(<StagedAttachmentsWarning />)

    const toggle = await screen.findByRole('button', {
      name: /需要注意的附件/,
    })
    expect(toggle).toHaveAttribute('aria-expanded', 'false')
    expect(toggle).toHaveAttribute(
      'aria-controls',
      'staged-attachments-panel',
    )
    // Panel exists even while collapsed so aria-controls always resolves.
    const panel = document.getElementById('staged-attachments-panel')
    expect(panel).not.toBeNull()
    expect(panel).toHaveAttribute('hidden')

    await user.click(toggle)

    expect(toggle).toHaveAttribute('aria-expanded', 'true')
    expect(
      document.getElementById('staged-attachments-panel'),
    ).not.toHaveAttribute('hidden')
    expect(screen.getByText('富邦')).toBeInTheDocument()
    expect(screen.getByText('fubon-2026-03.pdf')).toBeInTheDocument()
    expect(screen.getByText('中國信託')).toBeInTheDocument()
    expect(screen.getByText('ctbc-2026-02.pdf')).toBeInTheDocument()
    expect(
      screen.getByText(/下載連結已一次性使用過期/),
    ).toBeInTheDocument()
    expect(
      screen.getByText(/系統嘗試下載失敗/),
    ).toBeInTheDocument()
  })

  it('requests only warning statuses from the API', async () => {
    mockApiGet.mockResolvedValue(EMPTY_RESPONSE)
    renderWithProviders(<StagedAttachmentsWarning />)

    await waitFor(() => {
      expect(mockApiGet).toHaveBeenCalledWith(
        '/api/staged-attachments',
        expect.objectContaining({
          status: 'fetch_expired,failed,parse_failed',
          page_size: 100,
        }),
      )
    })
  })
})
