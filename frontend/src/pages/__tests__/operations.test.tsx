/**
 * Operations page tests -- pipeline trigger, active run, and history states.
 */
import { screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import OperationsPage from '../operations'
import { renderWithProviders } from '@/test-utils'

vi.mock('@/lib/api-client', () => ({
  apiGet: vi.fn(),
  apiPost: vi.fn(),
}))

import { apiGet, apiPost } from '@/lib/api-client'
const mockApiGet = vi.mocked(apiGet)
const mockApiPost = vi.mocked(apiPost)

/**
 * Pick an option from a SelectField (base-ui) by its trigger label and the
 * visible option text. Replaces native `selectOptions`, which only works on
 * <select>.
 */
async function pickOption(
  user: ReturnType<typeof userEvent.setup>,
  triggerLabel: string,
  optionName: string,
) {
  await user.click(screen.getByLabelText(triggerLabel))
  const listbox = await screen.findByRole('listbox')
  // findByRole waits for async option data (e.g. banks query) to populate.
  await user.click(await within(listbox).findByRole('option', { name: optionName }))
}

const BANKS = {
  success: true,
  data: [
    {
      id: 1,
      bank_code: 'CTBC',
      bank_name: '中國信託',
      gmail_filter: 'from:ctbc',
      active_parser_version: 'v1',
      is_active: true,
    },
  ],
  message: '',
}

const RUNNING_RUN = {
  id: 'run-1',
  job_id: 'job-1',
  status: 'running',
  triggered_by: 'api',
  params: { force: false, bank_code: 'CTBC' },
  current_stage: 'parse',
  current_stage_processed: 47,
  current_stage_total: 120,
  stage_summary: [{ stage: 'ingest', ok: 2, fail: 0, elapsed_ms: 1000 }],
  error_message: null,
  started_at: new Date(Date.now() - 3000).toISOString(),
  completed_at: null,
  created_at: '2026-05-01T12:00:00Z',
  updated_at: '2026-05-01T12:00:03Z',
}

const FAILED_RUN = {
  ...RUNNING_RUN,
  id: 'run-2',
  job_id: 'job-2',
  status: 'failed',
  current_stage: 'notify',
  current_stage_processed: 0,
  current_stage_total: 0,
  error_message: 'boom',
  completed_at: '2026-05-01T12:01:00Z',
  created_at: '2026-05-01T12:01:00Z',
}

function setupMocks({
  runs = [],
  detail = null,
}: {
  readonly runs?: readonly unknown[]
  readonly detail?: unknown
} = {}) {
  mockApiGet.mockImplementation((path: string) => {
    if (path === '/api/settings/banks') return Promise.resolve(BANKS)
    if (path === '/api/pipeline/runs') {
      return Promise.resolve({ success: true, data: runs, message: '' })
    }
    if (path === '/api/pipeline/runs/run-1' && detail) {
      return Promise.resolve({ success: true, data: detail, message: '' })
    }
    return Promise.reject(new Error(`Unhandled GET ${path}`))
  })
}

beforeEach(() => {
  vi.clearAllMocks()
  Element.prototype.scrollIntoView = vi.fn()
  mockApiPost.mockResolvedValue({
    success: true,
    data: { job_id: 'job-new', run_id: 'run-new' },
    message: '',
  })
})

describe('OperationsPage', () => {
  it('submits trigger payload and invalidates the active section', async () => {
    const user = userEvent.setup()
    setupMocks()

    renderWithProviders(<OperationsPage />)

    await screen.findByLabelText('銀行')

    await pickOption(user, '銀行', '中國信託')
    await pickOption(user, '年度', '2026')
    await pickOption(user, '月份', '3')
    await pickOption(user, '起始階段', '解析')
    await pickOption(user, '結束階段', '分類')
    await user.click(screen.getByLabelText('強制重跑'))
    await user.click(screen.getByRole('button', { name: '開始執行' }))

    await waitFor(() => {
      expect(mockApiPost).toHaveBeenCalledWith('/api/pipeline/trigger', {
        force: true,
        bank_code: 'CTBC',
        year: 2026,
        month: 3,
        from_stage: 'parse',
        to_stage: 'classify',
      })
    })
    expect(Element.prototype.scrollIntoView).toHaveBeenCalled()
  })

  it('renders stage options with Chinese labels', async () => {
    // SelectField (base-ui) items expose no value attribute; the Chinese
    // label → English value mapping is verified functionally by the trigger
    // test above (選「解析」→ from_stage: 'parse').
    const user = userEvent.setup()
    setupMocks()

    renderWithProviders(<OperationsPage />)

    await screen.findByLabelText('銀行')

    await user.click(screen.getByLabelText('起始階段'))
    const listbox = await screen.findByRole('listbox')
    expect(
      within(listbox).getByRole('option', { name: '擷取' }),
    ).toBeInTheDocument()
    expect(
      within(listbox).getByRole('option', { name: '解析' }),
    ).toBeInTheDocument()
    expect(
      within(listbox).getByRole('option', { name: '通知' }),
    ).toBeInTheDocument()
  })

  it('blocks submit when from_stage is after to_stage', async () => {
    const user = userEvent.setup()
    setupMocks()

    renderWithProviders(<OperationsPage />)

    await screen.findByLabelText('銀行')
    await pickOption(user, '起始階段', '分類')
    await pickOption(user, '結束階段', '解析')
    await user.click(screen.getByRole('button', { name: '開始執行' }))

    expect(screen.getByRole('alert')).toHaveTextContent(
      'from_stage 必須在 to_stage 之前或相同',
    )
    expect(mockApiPost).not.toHaveBeenCalled()
  })

  it('renders active run progress', async () => {
    setupMocks({ runs: [RUNNING_RUN], detail: RUNNING_RUN })

    renderWithProviders(<OperationsPage />)

    await waitFor(() => {
      expect(screen.getByText('解析 47 / 120 (39%)')).toBeInTheDocument()
    })
    // Stage labels also appear in the stage select options now.
    expect(screen.getAllByText('擷取').length).toBeGreaterThan(0)
    expect(screen.getAllByText('解析').length).toBeGreaterThan(0)
  })

  it('renders history status badges', async () => {
    setupMocks({ runs: [FAILED_RUN] })

    renderWithProviders(<OperationsPage />)

    await waitFor(() => {
      expect(screen.getByText('失敗')).toBeInTheDocument()
    })
    expect(screen.getByText('api')).toBeInTheDocument()
    expect(
      screen.getByText('僅手動觸發紀錄；scheduler 自動排程結果請查看 logs'),
    ).toBeInTheDocument()
  })
})
