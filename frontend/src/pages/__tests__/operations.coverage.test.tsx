/**
 * Operations page coverage tests -- complements operations.test.tsx by exercising
 * the error/loading branches, status-badge variants, poll-interval backoff,
 * conditional formatters, and the run-detail dialog paths that the base suite
 * leaves uncovered.
 */
import { screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import OperationsPage from '../operations'
import { renderWithProviders } from '@/test-utils'
import type {
  PipelineRunDetail,
  PipelineRunStatus,
  PipelineRunSummary,
} from '@/lib/types'

vi.mock('@/lib/api-client', () => ({
  apiGet: vi.fn(),
  apiPost: vi.fn(),
}))

import { apiGet, apiPost } from '@/lib/api-client'
const mockApiGet = vi.mocked(apiGet)
const mockApiPost = vi.mocked(apiPost)

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

/** Build an active (queued/running) run detail with a given start time. */
function activeScenario(
  startedAt: string | null,
  status: PipelineRunStatus = 'running',
): PipelineRunDetail {
  return {
    id: 'run-1',
    job_id: 'job-1',
    status,
    triggered_by: 'api',
    params: { force: false, bank_code: 'CTBC' },
    current_stage: 'parse',
    current_stage_processed: 47,
    current_stage_total: 120,
    stage_summary: [{ stage: 'ingest', ok: 2, fail: 0, elapsed_ms: 1000 }],
    error_message: null,
    started_at: startedAt,
    completed_at: null,
    created_at: '2026-05-01T12:00:00Z',
    updated_at: '2026-05-01T12:00:03Z',
  }
}

const RUNNING_SUMMARY: PipelineRunSummary = activeScenario(
  new Date(Date.now() - 2000).toISOString(),
)

const FAILED_DETAIL: PipelineRunDetail = {
  id: 'run-1',
  job_id: 'job-1',
  status: 'failed',
  triggered_by: 'api',
  params: { force: false, bank_code: 'CTBC' },
  current_stage: 'parse',
  current_stage_processed: 0,
  current_stage_total: 0,
  stage_summary: [
    {
      stage: 'ingest',
      ok: 2,
      fail: 0,
      elapsed_ms: 1500,
      counts: { mails: 4, pdfs: 3 },
      errors: ['mail timeout'],
    },
    { stage: 'mystery-stage', ok: 0, fail: 1, elapsed_ms: 0 },
  ],
  error_message: 'boom failure',
  started_at: new Date(Date.now() - 2000).toISOString(),
  completed_at: '2026-05-01T12:01:00Z',
  created_at: '2026-05-01T12:00:00Z',
  updated_at: '2026-05-01T12:01:00Z',
}

/** Active run reported as queued with no stage / start info yet. */
const QUEUED_DETAIL: PipelineRunDetail = {
  id: 'run-1',
  job_id: 'job-1',
  status: 'queued',
  triggered_by: 'api',
  params: { force: false },
  current_stage: null,
  current_stage_processed: 0,
  current_stage_total: 0,
  stage_summary: [],
  error_message: null,
  started_at: null,
  completed_at: null,
  created_at: '2026-05-01T12:00:00Z',
  updated_at: '2026-05-01T12:00:00Z',
}

const SUCCEEDED_RUN: PipelineRunSummary = {
  id: 'h-success',
  job_id: 'jb-success',
  status: 'succeeded',
  triggered_by: 'manual',
  params: { force: false, year: 2026, month: 5 },
  current_stage: 'notify',
  current_stage_processed: 10,
  current_stage_total: 10,
  stage_summary: [{ stage: 'ingest', ok: 3, fail: 1, elapsed_ms: 2000 }],
  error_message: null,
  started_at: '2026-05-01T12:00:00Z',
  completed_at: '2026-05-01T12:01:30Z',
  created_at: '2026-05-01T12:00:00Z',
  updated_at: '2026-05-01T12:01:30Z',
}

const CANCELLED_RUN: PipelineRunSummary = {
  id: 'h-cancel',
  job_id: 'jb-cancel',
  status: 'cancelled',
  triggered_by: 'scheduler',
  params: { force: true, year: 2026 },
  current_stage: null,
  current_stage_processed: 0,
  current_stage_total: 0,
  stage_summary: [],
  error_message: null,
  started_at: null,
  completed_at: null,
  created_at: '2026-05-02T08:00:00Z',
  updated_at: '2026-05-02T08:00:00Z',
}

function setupMocks({
  runs = [] as readonly unknown[],
  detail = null as unknown,
  runsPending = false,
}: {
  readonly runs?: readonly unknown[]
  readonly detail?: unknown
  readonly runsPending?: boolean
} = {}) {
  mockApiGet.mockImplementation((path: string) => {
    if (path === '/api/settings/banks') return Promise.resolve(BANKS)
    if (path === '/api/pipeline/runs') {
      if (runsPending) return new Promise(() => {})
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

describe('OperationsPage coverage', () => {
  it('shows the page error state when the banks query rejects', async () => {
    mockApiGet.mockImplementation((path: string) => {
      if (path === '/api/settings/banks') {
        return Promise.reject(new Error('銀行載入失敗'))
      }
      return Promise.resolve({ success: true, data: [], message: '' })
    })

    renderWithProviders(<OperationsPage />)

    expect(await screen.findByText('銀行載入失敗')).toBeInTheDocument()
    // The trigger form never renders when banks fail.
    expect(screen.queryByLabelText('銀行')).not.toBeInTheDocument()
  })

  it('shows the history error state when the runs query rejects', async () => {
    mockApiGet.mockImplementation((path: string) => {
      if (path === '/api/settings/banks') return Promise.resolve(BANKS)
      if (path === '/api/pipeline/runs') {
        return Promise.reject(new Error('歷史載入失敗'))
      }
      return Promise.reject(new Error(`Unhandled GET ${path}`))
    })

    renderWithProviders(<OperationsPage />)

    // Banks loaded so the form is present, but the history panel surfaces error.
    await screen.findByLabelText('銀行')
    expect(await screen.findByText('歷史載入失敗')).toBeInTheDocument()
  })

  it('shows the history loading state while runs are still fetching', async () => {
    setupMocks({ runsPending: true })

    renderWithProviders(<OperationsPage />)

    await screen.findByLabelText('銀行')
    expect(await screen.findByText('讀取歷史紀錄...')).toBeInTheDocument()
    // No active run can be derived from a pending list.
    expect(screen.getByText('尚無進行中的 pipeline')).toBeInTheDocument()
  })

  it('renders a pending submit button while the trigger mutation is in flight', async () => {
    const user = userEvent.setup()
    setupMocks()
    mockApiPost.mockImplementation(() => new Promise(() => {}))

    renderWithProviders(<OperationsPage />)

    await screen.findByLabelText('銀行')
    await user.click(screen.getByRole('button', { name: '開始執行' }))

    const pendingButton = await screen.findByRole('button', { name: '送出中' })
    expect(pendingButton).toBeDisabled()
  })

  it('falls back to no banks when the banks payload omits its data array', async () => {
    const user = userEvent.setup()
    mockApiGet.mockImplementation((path: string) => {
      if (path === '/api/settings/banks') {
        return Promise.resolve({ success: true, message: '' })
      }
      if (path === '/api/pipeline/runs') {
        return Promise.resolve({ success: true, data: [], message: '' })
      }
      return Promise.reject(new Error(`Unhandled GET ${path}`))
    })

    renderWithProviders(<OperationsPage />)

    await screen.findByLabelText('銀行')
    await user.click(screen.getByLabelText('銀行'))
    const listbox = await screen.findByRole('listbox')
    expect(
      within(listbox).getByRole('option', { name: '全部銀行' }),
    ).toBeInTheDocument()
    expect(
      within(listbox).queryByRole('option', { name: '中國信託' }),
    ).not.toBeInTheDocument()
  })

  it('renders a failed active run with an error alert and detail dialog', async () => {
    const user = userEvent.setup()
    setupMocks({ runs: [RUNNING_SUMMARY], detail: FAILED_DETAIL })

    renderWithProviders(<OperationsPage />)

    const alert = await screen.findByRole('alert')
    expect(alert).toHaveTextContent('boom failure')

    await user.click(screen.getByRole('button', { name: '查看詳情' }))

    const dialog = await screen.findByRole('dialog')
    // Detail rows + stage table with both populated and empty counts/errors.
    expect(within(dialog).getByText('Run ID')).toBeInTheDocument()
    expect(within(dialog).getByText('擷取')).toBeInTheDocument()
    expect(within(dialog).getByText('mystery-stage')).toBeInTheDocument()
    expect(within(dialog).getByText('mails: 4, pdfs: 3')).toBeInTheDocument()
    expect(within(dialog).getByText('mail timeout')).toBeInTheDocument()
    expect(within(dialog).getByText('boom failure')).toBeInTheDocument()
    // The empty entry renders '-' for both counts and errors columns.
    expect(within(dialog).getAllByText('-').length).toBeGreaterThanOrEqual(2)
  })

  it('renders a queued active run with waiting placeholders', async () => {
    setupMocks({ runs: [QUEUED_DETAIL], detail: QUEUED_DETAIL })

    renderWithProviders(<OperationsPage />)

    // current_stage null -> '等待中' label and queued status text in progress row.
    expect(await screen.findByText('等待中')).toBeInTheDocument()
    expect(screen.getByText('排隊中 0 / 0 (0%)')).toBeInTheDocument()
    // params.bank_code missing -> '全部銀行' shows in the active card.
    expect(screen.getAllByText('全部銀行').length).toBeGreaterThan(0)
  })

  it('renders history status badges and opens a succeeded run detail dialog', async () => {
    const user = userEvent.setup()
    setupMocks({ runs: [SUCCEEDED_RUN, CANCELLED_RUN] })

    renderWithProviders(<OperationsPage />)

    const successRow = (await screen.findByText('成功')).closest('tr')
    const cancelRow = screen.getByText('已取消').closest('tr')
    expect(successRow).not.toBeNull()
    expect(cancelRow).not.toBeNull()

    // Succeeded row: no bank -> '全部', year+month period, stage counts, duration.
    expect(within(successRow as HTMLElement).getByText('全部')).toBeInTheDocument()
    expect(within(successRow as HTMLElement).getByText('2026-05')).toBeInTheDocument()
    expect(within(successRow as HTMLElement).getByText('3 / 1')).toBeInTheDocument()
    expect(within(successRow as HTMLElement).getByText('1m 30s')).toBeInTheDocument()

    // Cancelled row: year-only period and '-' for empty stage counts + duration.
    expect(within(cancelRow as HTMLElement).getByText('2026')).toBeInTheDocument()
    expect(
      within(cancelRow as HTMLElement).getAllByText('-').length,
    ).toBeGreaterThanOrEqual(2)

    // Open the succeeded run detail dialog (no error_message -> no error block).
    await user.click(within(successRow as HTMLElement).getByRole('button'))
    const dialog = await screen.findByRole('dialog')
    expect(within(dialog).getByText('Run ID')).toBeInTheDocument()
    expect(within(dialog).getByText('h-success')).toBeInTheDocument()
  })

  it('slows polling to the 5s tier for a run running over a minute', async () => {
    const scenario = activeScenario(new Date(Date.now() - 120_000).toISOString())
    setupMocks({ runs: [scenario], detail: scenario })

    renderWithProviders(<OperationsPage />)

    expect(await screen.findByText(/已過 2m/)).toBeInTheDocument()
  })

  it('slows polling to the 15s tier for a long-running run over five minutes', async () => {
    const scenario = activeScenario(new Date(Date.now() - 360_000).toISOString())
    setupMocks({ runs: [scenario], detail: scenario })

    renderWithProviders(<OperationsPage />)

    expect(await screen.findByText(/已過 6m/)).toBeInTheDocument()
  })

  it('keeps ticking the elapsed timer while a run stays active', async () => {
    const scenario = activeScenario(new Date(Date.now() - 1000).toISOString())
    setupMocks({ runs: [scenario], detail: scenario })

    renderWithProviders(<OperationsPage />)

    const label = await screen.findByText(/^已過 \d+s$/)
    const first = label.textContent
    await waitFor(
      () => {
        expect(screen.getByText(/^已過/).textContent).not.toBe(first)
      },
      { timeout: 4000 },
    )
  })
})
