/**
 * Setup login-credentials 頁測試（P3-7）。
 *
 * 覆蓋：
 * - 來源 badge 渲染（db / env / none）+ bank/key 標籤
 * - master.key 警告 banner 永久顯示
 * - import-from-env 橫幅 + mutation
 * - 設定憑證 dialog 觸發 PUT（複合路徑 {bank}/{key}）
 * - 刪除憑證 dialog 觸發 DELETE
 */
import { screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import SetupLoginCredentialsPage from '../login-credentials'
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
    bank_code: 'FUBON',
    credential_key: 'NATIONAL_ID',
    has_db_value: true,
    has_env_value: false,
    effective_source: 'db' as const,
  },
  {
    bank_code: 'FUBON',
    credential_key: 'ROC_BIRTHDAY',
    has_db_value: false,
    has_env_value: true,
    effective_source: 'env' as const,
  },
]

beforeEach(() => {
  vi.clearAllMocks()
})

describe('SetupLoginCredentialsPage', () => {
  it('renders source badges, key labels and the permanent master.key warning', async () => {
    mockApiGet.mockResolvedValue({
      success: true,
      data: baseItems,
      message: '',
    })

    renderWithProviders(<SetupLoginCredentialsPage />)

    await waitFor(() =>
      expect(screen.getByText('NATIONAL_ID')).toBeInTheDocument(),
    )
    expect(screen.getByText('ROC_BIRTHDAY')).toBeInTheDocument()
    expect(screen.getByLabelText('目前來源：DB')).toBeInTheDocument()
    expect(screen.getByLabelText('目前來源：env')).toBeInTheDocument()
    expect(screen.getByRole('note')).toHaveTextContent('master.key')
  })

  it('shows import-from-env banner when env-only credentials exist', async () => {
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
        credentials_imported: ['FUBON_ROC_BIRTHDAY'],
      },
      message: '',
    })

    const user = userEvent.setup()
    renderWithProviders(<SetupLoginCredentialsPage />)

    const button = await screen.findByRole('button', {
      name: '一鍵匯入 env 憑證',
    })
    await user.click(button)

    await waitFor(() =>
      expect(mockApiPost).toHaveBeenCalledWith(
        '/api/setup/login-credentials/import-from-env',
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

    renderWithProviders(<SetupLoginCredentialsPage />)

    await waitFor(() =>
      expect(screen.getByText('NATIONAL_ID')).toBeInTheDocument(),
    )
    expect(
      screen.queryByRole('button', { name: '一鍵匯入 env 憑證' }),
    ).not.toBeInTheDocument()
  })

  it('submits PUT to the composite path when set-credential form completes', async () => {
    mockApiGet.mockResolvedValue({
      success: true,
      data: [
        {
          bank_code: 'FUBON',
          credential_key: 'NATIONAL_ID',
          has_db_value: false,
          has_env_value: false,
          effective_source: 'none' as const,
        },
      ],
      message: '',
    })
    mockApiPut.mockResolvedValue({
      success: true,
      data: {
        bank_code: 'FUBON',
        credential_key: 'NATIONAL_ID',
        effective_source: 'db',
      },
      message: '',
    })

    const user = userEvent.setup()
    renderWithProviders(<SetupLoginCredentialsPage />)

    await user.click(
      await screen.findByRole('button', { name: '設定 FUBON NATIONAL_ID' }),
    )
    const input = await screen.findByLabelText('FUBON NATIONAL_ID 新憑證值')
    await user.type(input, 'A123456789')
    await user.click(
      screen.getByRole('button', { name: '儲存 FUBON NATIONAL_ID' }),
    )

    await waitFor(() =>
      expect(mockApiPut).toHaveBeenCalledWith(
        '/api/setup/login-credentials/FUBON/NATIONAL_ID',
        { value: 'A123456789' },
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
      data: {
        bank_code: 'FUBON',
        credential_key: 'NATIONAL_ID',
        effective_source: 'none',
      },
      message: '',
    })

    const user = userEvent.setup()
    renderWithProviders(<SetupLoginCredentialsPage />)

    await user.click(
      await screen.findByRole('button', {
        name: '刪除 FUBON NATIONAL_ID DB 憑證',
      }),
    )
    await user.click(
      await screen.findByRole('button', { name: '確認刪除 FUBON NATIONAL_ID' }),
    )

    await waitFor(() =>
      expect(mockApiDelete).toHaveBeenCalledWith(
        '/api/setup/login-credentials/FUBON/NATIONAL_ID',
      ),
    )
  })
})
