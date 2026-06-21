/**
 * Vitest for SettingsRemindersPage (bills-management-and-insights §11.3)。
 */
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'

vi.mock('@/lib/api-client', () => ({
  apiGet: vi.fn(),
  apiPut: vi.fn(),
  apiPost: vi.fn(),
}))

import { apiGet, apiPost, apiPut } from '@/lib/api-client'
import SettingsRemindersPage from '@/pages/settings-reminders'

const mockedGet = vi.mocked(apiGet)
const mockedPut = vi.mocked(apiPut)
const mockedPost = vi.mocked(apiPost)

function renderPage() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  })
  return render(
    <QueryClientProvider client={client}>
      <SettingsRemindersPage />
    </QueryClientProvider>,
  )
}

const sampleItem = {
  bill_id: 1,
  bank_code: 'CTBC',
  bank_name: '中國信託',
  billing_month: '2026-05',
  due_date: '2026-05-15',
  is_paid: false,
  enabled: true,
  days_before: [3, 1] as readonly number[],
  channel: 'telegram' as const,
  has_setting: false,
}

describe('SettingsRemindersPage', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('renders empty state when no bills', async () => {
    mockedGet.mockResolvedValueOnce({ success: true, data: [], message: '' })
    renderPage()
    await waitFor(() => {
      expect(
        screen.getByText('目前沒有未付帳單需要設定提醒'),
      ).toBeInTheDocument()
    })
  })

  it('renders bills with default settings hint', async () => {
    mockedGet.mockResolvedValueOnce({
      success: true,
      data: [sampleItem],
      message: '',
    })
    renderPage()
    await waitFor(() => {
      expect(screen.getByText(/中國信託/)).toBeInTheDocument()
    })
    expect(screen.getByText(/尚未自訂/)).toBeInTheDocument()
    expect(screen.getByText(/3 天/)).toBeInTheDocument()
  })

  it('toggles enabled via checkbox -> PUT', async () => {
    mockedGet.mockResolvedValue({
      success: true,
      data: [sampleItem],
      message: '',
    })
    mockedPut.mockResolvedValue({
      success: true,
      data: { ...sampleItem, enabled: false, has_setting: true },
      message: '',
    })

    renderPage()
    const checkbox = await screen.findByLabelText('啟用')
    await userEvent.click(checkbox)
    await waitFor(() => {
      expect(mockedPut).toHaveBeenCalledWith(
        '/api/reminders/1/settings',
        { enabled: false },
      )
    })
  })

  it('changes channel via select -> PUT', async () => {
    mockedGet.mockResolvedValue({
      success: true,
      data: [sampleItem],
      message: '',
    })
    mockedPut.mockResolvedValue({
      success: true,
      data: { ...sampleItem, channel: 'both', has_setting: true },
      message: '',
    })

    renderPage()
    // 通知管道 is a SelectField (base-ui): open listbox + click option.
    await userEvent.click(await screen.findByLabelText('通知管道'))
    const listbox = await screen.findByRole('listbox')
    await userEvent.click(
      within(listbox).getByRole('option', { name: 'Telegram + Banner' }),
    )
    await waitFor(() => {
      expect(mockedPut).toHaveBeenCalledWith(
        '/api/reminders/1/settings',
        { channel: 'both' },
      )
    })
  })

  it('test push button shows detail on success', async () => {
    mockedGet.mockResolvedValue({
      success: true,
      data: [sampleItem],
      message: '',
    })
    mockedPost.mockResolvedValue({
      success: true,
      data: {
        sent: true,
        channel: 'telegram',
        detail: '已送出 Telegram 測試訊息',
      },
      message: '',
    })

    renderPage()
    const testBtn = await screen.findByRole('button', { name: /測試發送/ })
    await userEvent.click(testBtn)
    await waitFor(() => {
      expect(mockedPost).toHaveBeenCalledWith('/api/reminders/1/test', {})
    })
    await waitFor(() => {
      expect(screen.getByText(/已送出 Telegram/)).toBeInTheDocument()
    })
  })

  it('parses days_before input on blur', async () => {
    mockedGet.mockResolvedValue({
      success: true,
      data: [sampleItem],
      message: '',
    })
    mockedPut.mockResolvedValue({
      success: true,
      data: { ...sampleItem, days_before: [7, 3, 1], has_setting: true },
      message: '',
    })

    renderPage()
    const input = await screen.findByDisplayValue('3,1')
    await userEvent.clear(input)
    await userEvent.type(input, '7,3,1')
    await userEvent.tab() // blur
    await waitFor(() => {
      expect(mockedPut).toHaveBeenCalledWith(
        '/api/reminders/1/settings',
        { days_before: [7, 3, 1] },
      )
    })
  })
})
