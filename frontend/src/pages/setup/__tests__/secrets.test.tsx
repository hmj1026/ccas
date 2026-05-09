/**
 * Setup secrets 頁測試（oauth-onboarding-ui §10.7）。
 *
 * 覆蓋：
 * - 來源 badge 渲染（db / env / none）
 * - master.key 警告 banner 永久顯示
 * - import-from-env 橫幅 + mutation
 * - 設定密碼 dialog 觸發 PUT
 * - 刪除密碼 dialog 觸發 DELETE
 */
import { screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import SetupSecretsPage from '../secrets'
import { renderWithProviders } from '@/test-utils'

vi.mock('@/lib/api-client', () => ({
  apiGet: vi.fn(),
  apiPost: vi.fn(),
  apiPut: vi.fn(),
  apiDelete: vi.fn(),
}))

import { apiDelete, apiGet, apiPost, apiPut } from '@/lib/api-client'

const mockApiGet = vi.mocked(apiGet)
const mockApiPut = vi.mocked(apiPut)
const mockApiPost = vi.mocked(apiPost)
const mockApiDelete = vi.mocked(apiDelete)

const baseItems = [
  {
    bank_code: 'CTBC',
    has_db_secret: true,
    has_env_secret: false,
    effective_source: 'db' as const,
  },
  {
    bank_code: 'ESUN',
    has_db_secret: false,
    has_env_secret: true,
    effective_source: 'env' as const,
  },
  {
    bank_code: 'HSBC',
    has_db_secret: false,
    has_env_secret: false,
    effective_source: 'none' as const,
  },
]

beforeEach(() => {
  vi.clearAllMocks()
})

describe('SetupSecretsPage', () => {
  it('renders source badges and the permanent master.key warning', async () => {
    mockApiGet.mockResolvedValue({
      success: true,
      data: baseItems,
      message: '',
    })

    renderWithProviders(<SetupSecretsPage />)

    await waitFor(() =>
      expect(screen.getByText('CTBC')).toBeInTheDocument(),
    )
    expect(screen.getByLabelText('目前來源：DB')).toBeInTheDocument()
    expect(screen.getByLabelText('目前來源：env')).toBeInTheDocument()
    expect(screen.getByLabelText('目前來源：未設定')).toBeInTheDocument()
    expect(screen.getByRole('note')).toHaveTextContent('master.key')
  })

  it('shows import-from-env banner when env-only secrets exist', async () => {
    mockApiGet.mockResolvedValue({
      success: true,
      data: baseItems,
      message: '',
    })
    mockApiPost.mockResolvedValue({
      success: true,
      data: {
        imported: 1,
        skipped_already_in_db: 0,
        bank_codes_imported: ['ESUN'],
      },
      message: '',
    })

    const user = userEvent.setup()
    renderWithProviders(<SetupSecretsPage />)

    const button = await screen.findByRole('button', {
      name: '一鍵匯入 env 密碼',
    })
    await user.click(button)

    await waitFor(() =>
      expect(mockApiPost).toHaveBeenCalledWith(
        '/api/setup/secrets/import-from-env',
        {},
      ),
    )
    await waitFor(() =>
      expect(screen.getByRole('status')).toHaveTextContent('已匯入 1'),
    )
  })

  it('hides import banner when no env-only entries', async () => {
    mockApiGet.mockResolvedValue({
      success: true,
      data: [baseItems[0]!],
      message: '',
    })

    renderWithProviders(<SetupSecretsPage />)

    await waitFor(() => expect(screen.getByText('CTBC')).toBeInTheDocument())
    expect(
      screen.queryByRole('button', { name: '一鍵匯入 env 密碼' }),
    ).not.toBeInTheDocument()
  })

  it('submits PUT when set-password form is completed', async () => {
    mockApiGet.mockResolvedValue({
      success: true,
      data: [baseItems[2]!],
      message: '',
    })
    mockApiPut.mockResolvedValue({
      success: true,
      data: { bank_code: 'HSBC', effective_source: 'db' },
      message: '',
    })

    const user = userEvent.setup()
    renderWithProviders(<SetupSecretsPage />)

    await user.click(
      await screen.findByRole('button', { name: '設定 HSBC 密碼' }),
    )
    const input = await screen.findByLabelText('HSBC 新密碼')
    await user.type(input, 'super-secret-pw')
    await user.click(screen.getByRole('button', { name: '儲存 HSBC 密碼' }))

    await waitFor(() =>
      expect(mockApiPut).toHaveBeenCalledWith(
        '/api/setup/secrets/HSBC',
        { password: 'super-secret-pw' },
      ),
    )
  })

  it('submits DELETE when user confirms in delete dialog', async () => {
    mockApiGet.mockResolvedValue({
      success: true,
      data: [baseItems[0]!],
      message: '',
    })
    mockApiDelete.mockResolvedValue({
      success: true,
      data: { bank_code: 'CTBC', effective_source: 'none' },
      message: '',
    })

    const user = userEvent.setup()
    renderWithProviders(<SetupSecretsPage />)

    await user.click(
      await screen.findByRole('button', { name: '刪除 CTBC DB 密碼' }),
    )
    await user.click(
      await screen.findByRole('button', { name: '確認刪除 CTBC' }),
    )

    await waitFor(() =>
      expect(mockApiDelete).toHaveBeenCalledWith('/api/setup/secrets/CTBC'),
    )
  })
})
