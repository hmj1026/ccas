/**
 * ExportDialog 測試 -- 驗證銀行下拉選單、查詢失敗 fallback 與日期區間驗證。
 */
import { fireEvent, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { ExportDialog } from '../export-dialog'
import { renderWithProviders } from '@/test-utils'

vi.mock('@/lib/api-client', () => ({
  apiGet: vi.fn(),
  apiFetchBlob: vi.fn(),
}))

import { apiFetchBlob, apiGet } from '@/lib/api-client'

const mockApiGet = vi.mocked(apiGet)
const mockApiFetchBlob = vi.mocked(apiFetchBlob)

const BANKS_RESPONSE = {
  success: true,
  message: '',
  data: [
    {
      id: 1,
      bank_code: 'CTBC',
      bank_name: '中國信託',
      gmail_filter: 'from:ctbc',
      active_parser_version: 'v1',
      is_active: true,
    },
    {
      id: 2,
      bank_code: 'ESUN',
      bank_name: '玉山',
      gmail_filter: 'from:esun',
      active_parser_version: 'v1',
      is_active: true,
    },
  ],
}

describe('ExportDialog', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mockApiGet.mockResolvedValue(BANKS_RESPONSE)
  })

  it('renders bank select fed by settings banks query with 全部銀行 first', async () => {
    renderWithProviders(<ExportDialog isOpen onClose={() => {}} />)

    // SelectField (base-ui): options live in a portal listbox, rendered on open.
    await userEvent.click(screen.getByRole('combobox', { name: '銀行' }))
    const listbox = await screen.findByRole('listbox')
    const options = within(listbox)
      .getAllByRole('option')
      .map((o) => o.textContent)
    expect(options[0]).toBe('全部銀行')
    expect(options).toContain('中國信託（CTBC）')
    expect(options).toContain('玉山（ESUN）')
    expect(mockApiGet).toHaveBeenCalledWith('/api/settings/banks')
  })

  it('falls back to a text input when the banks query fails', async () => {
    mockApiGet.mockRejectedValue(new Error('boom'))
    renderWithProviders(<ExportDialog isOpen onClose={() => {}} />)

    const input = await screen.findByPlaceholderText('例：CTBC')
    expect(input).toBeInTheDocument()
  })

  it('rejects end date earlier than start date without calling the API', async () => {
    renderWithProviders(<ExportDialog isOpen onClose={() => {}} />)
    await screen.findByLabelText('起始日期')

    fireEvent.change(screen.getByLabelText('起始日期'), {
      target: { value: '2026-05-10' },
    })
    const endInput = screen.getByLabelText('結束日期')
    fireEvent.change(endInput, { target: { value: '2026-05-01' } })
    // Native min-constraint blocks click-submit in browsers; dispatch submit
    // directly to exercise the JS guard as a defensive second layer.
    fireEvent.submit(endInput.closest('form') as HTMLFormElement)

    expect(
      await screen.findByText('結束日期不能早於起始日期'),
    ).toBeInTheDocument()
    expect(mockApiFetchBlob).not.toHaveBeenCalled()
  })

  it('sets end date min to the chosen start date', async () => {
    renderWithProviders(<ExportDialog isOpen onClose={() => {}} />)
    await screen.findByLabelText('起始日期')

    const endInput = screen.getByLabelText('結束日期')
    expect(endInput).not.toHaveAttribute('min')

    fireEvent.change(screen.getByLabelText('起始日期'), {
      target: { value: '2026-05-10' },
    })
    expect(endInput).toHaveAttribute('min', '2026-05-10')
  })

  it('submits selected bank code as export param', async () => {
    const onClose = vi.fn()
    mockApiFetchBlob.mockResolvedValue(new Blob(['x']))
    // jsdom may lack URL.createObjectURL; polyfill for downloadBlob.
    if (typeof URL.createObjectURL !== 'function') {
      Object.defineProperty(URL, 'createObjectURL', {
        value: () => 'blob:fake',
        configurable: true,
      })
    }
    if (typeof URL.revokeObjectURL !== 'function') {
      Object.defineProperty(URL, 'revokeObjectURL', {
        value: () => undefined,
        configurable: true,
      })
    }
    renderWithProviders(<ExportDialog isOpen onClose={onClose} />)

    await screen.findByLabelText('起始日期')
    // SelectField (base-ui): open listbox + click option to pick a bank.
    await userEvent.click(screen.getByRole('combobox', { name: '銀行' }))
    await userEvent.click(
      await screen.findByRole('option', { name: '中國信託（CTBC）' }),
    )
    await userEvent.click(screen.getByRole('button', { name: /下載/ }))

    await waitFor(() => {
      expect(mockApiFetchBlob).toHaveBeenCalledWith(
        '/api/transactions/export',
        expect.objectContaining({ bank: 'CTBC' }),
      )
    })
    expect(onClose).toHaveBeenCalled()
  })
})
