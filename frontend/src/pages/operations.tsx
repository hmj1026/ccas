/**
 * Pipeline 操作中心頁面。
 */
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  Activity,
  CheckCircle2,
  Circle,
  History,
  Info,
  LoaderCircle,
  Play,
} from 'lucide-react'
import { useEffect, useMemo, useRef, useState } from 'react'
import { apiGet, apiPost } from '@/lib/api-client'
import type {
  ApiResponse,
  BankConfigItem,
  PaginatedResponse,
  PipelineRunDetail,
  PipelineRunStatus,
  PipelineRunSummary,
  PipelineStage,
  PipelineTriggerData,
  PipelineTriggerRequest,
} from '@/lib/types'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Progress } from '@/components/ui/progress'
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from '@/components/ui/dialog'
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from '@/components/ui/tooltip'
import { ErrorState, LoadingState } from '@/components/shared/states'
import { SelectField } from '@/components/ui/select-field'

const STAGES: readonly PipelineStage[] = [
  'ingest',
  'decrypt',
  'parse',
  'classify',
  'notify',
]

const STAGE_LABELS: Record<PipelineStage, string> = {
  ingest: '擷取',
  decrypt: '解密',
  parse: '解析',
  classify: '分類',
  notify: '通知',
}

/**
 * Polling backoff: fast at first, then slow down for long-running runs.
 * <1min → baseMs, 1-5min → 5s, >5min → 15s.
 */
function pollInterval(startedAt: string | null, baseMs: number) {
  const elapsedMs = startedAt
    ? Date.now() - new Date(startedAt).getTime()
    : 0
  if (elapsedMs < 60_000) return baseMs
  if (elapsedMs < 5 * 60_000) return 5_000
  return 15_000
}

function OperationsPage() {
  const activeRunRef = useRef<HTMLElement>(null)
  const [submitError, setSubmitError] = useState('')
  const queryClient = useQueryClient()

  const banksQuery = useQuery({
    queryKey: ['settings', 'banks'],
    queryFn: () =>
      apiGet<ApiResponse<readonly BankConfigItem[]>>('/api/settings/banks'),
    staleTime: 5 * 60 * 1000,
  })

  const runsQuery = useQuery({
    queryKey: ['pipeline-runs'],
    queryFn: () =>
      // /runs 採統一 PaginatedResponse 信封；此頁僅讀 data，pagination 暫未使用。
      apiGet<PaginatedResponse<PipelineRunSummary>>('/api/pipeline/runs'),
    staleTime: 30_000,
    refetchInterval: (query) => {
      const active = query.state.data?.data.find((run) =>
        isActiveStatus(run.status),
      )
      return active ? pollInterval(active.started_at, 3_000) : false
    },
    refetchIntervalInBackground: false,
  })

  const activeRunId = runsQuery.data?.data.find((run) =>
    isActiveStatus(run.status),
  )?.id

  const activeRunQuery = useQuery({
    queryKey: ['pipeline-runs', activeRunId],
    enabled: Boolean(activeRunId),
    queryFn: () =>
      apiGet<ApiResponse<PipelineRunDetail>>(
        `/api/pipeline/runs/${activeRunId}`,
      ),
    refetchInterval: (query) => {
      const run = query.state.data?.data
      return run && isActiveStatus(run.status)
        ? pollInterval(run.started_at, 1_000)
        : false
    },
    refetchIntervalInBackground: false,
  })

  const triggerMutation = useMutation({
    mutationFn: (payload: PipelineTriggerRequest) =>
      apiPost<ApiResponse<PipelineTriggerData>>('/api/pipeline/trigger', payload),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ['pipeline-runs'] })
      activeRunRef.current?.scrollIntoView({ behavior: 'smooth', block: 'start' })
    },
  })

  if (banksQuery.isLoading) return <LoadingState message="讀取銀行..." />
  if (banksQuery.isError) {
    return <ErrorState message={(banksQuery.error as Error).message} />
  }

  const runs = runsQuery.data?.data ?? []
  const activeRun = activeRunQuery.data?.data ?? null

  return (
    <div className="space-y-6">
      <header>
        <h1 className="text-2xl font-bold">操作中心</h1>
      </header>

      <section className="grid gap-4 xl:grid-cols-[minmax(0,380px)_minmax(0,1fr)]">
        <Panel
          icon={<Play className="size-4 text-muted-foreground" />}
          title="觸發 pipeline"
        >
          <TriggerForm
            banks={banksQuery.data?.data ?? []}
            isPending={triggerMutation.isPending}
            error={submitError || triggerMutation.error?.message || ''}
            onSubmit={(payload) => {
              setSubmitError('')
              const fromIndex = payload.from_stage
                ? STAGES.indexOf(payload.from_stage)
                : 0
              const toIndex = payload.to_stage
                ? STAGES.indexOf(payload.to_stage)
                : STAGES.length - 1
              if (fromIndex > toIndex) {
                setSubmitError('from_stage 必須在 to_stage 之前或相同')
                return
              }
              triggerMutation.mutate(payload)
            }}
          />
        </Panel>

        <Panel
          ref={activeRunRef}
          icon={<Activity className="size-4 text-muted-foreground" />}
          title="進行中"
        >
          {activeRunQuery.isLoading && activeRunId ? (
            <LoadingState message="讀取執行狀態..." />
          ) : activeRun ? (
            <ActiveRunCard run={activeRun} />
          ) : (
            <div className="rounded-md border border-dashed border-border bg-muted/30 p-6 text-sm text-muted-foreground">
              尚無進行中的 pipeline
            </div>
          )}
        </Panel>
      </section>

      <Panel
        icon={<History className="size-4 text-muted-foreground" />}
        title="歷史紀錄"
      >
        <HistoryBanner />
        {runsQuery.isLoading ? (
          <LoadingState message="讀取歷史紀錄..." />
        ) : runsQuery.isError ? (
          <ErrorState message={(runsQuery.error as Error).message} />
        ) : (
          <HistoryTable runs={runs} />
        )}
      </Panel>
    </div>
  )
}

function TriggerForm({
  banks,
  isPending,
  error,
  onSubmit,
}: {
  readonly banks: readonly BankConfigItem[]
  readonly isPending: boolean
  readonly error: string
  readonly onSubmit: (payload: PipelineTriggerRequest) => void
}) {
  const currentYear = new Date().getFullYear()
  const years = useMemo(
    () => Array.from({ length: 5 }, (_, index) => currentYear - 3 + index),
    [currentYear],
  )
  const [bankCode, setBankCode] = useState('')
  const [year, setYear] = useState('')
  const [month, setMonth] = useState('')
  const [fromStage, setFromStage] = useState<PipelineStage>('ingest')
  const [toStage, setToStage] = useState<PipelineStage>('notify')
  const [force, setForce] = useState(false)

  return (
    <form
      className="space-y-4"
      onSubmit={(event) => {
        event.preventDefault()
        onSubmit({
          force,
          bank_code: bankCode || null,
          year: year ? Number(year) : null,
          month: month ? Number(month) : null,
          from_stage: fromStage,
          to_stage: toStage,
        })
      }}
    >
      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-1">
        <SelectField
          label="銀行"
          triggerClassName="w-full"
          value={bankCode}
          onValueChange={setBankCode}
          options={[
            { value: '', label: '全部銀行' },
            ...banks.map((bank) => ({
              value: bank.bank_code,
              label: bank.bank_name,
            })),
          ]}
        />

        <div className="grid grid-cols-2 gap-2">
          <SelectField
            label="年度"
            triggerClassName="w-full"
            value={year}
            onValueChange={setYear}
            options={[
              { value: '', label: '全部' },
              ...years.map((item) => ({
                value: String(item),
                label: String(item),
              })),
            ]}
          />
          <SelectField
            label="月份"
            triggerClassName="w-full"
            value={month}
            onValueChange={setMonth}
            options={[
              { value: '', label: '全部' },
              ...Array.from({ length: 12 }, (_, index) => index + 1).map(
                (item) => ({ value: String(item), label: String(item) }),
              ),
            ]}
          />
        </div>

        <div className="grid grid-cols-2 gap-2">
          <StageSelect
            label="起始階段"
            value={fromStage}
            onChange={setFromStage}
          />
          <StageSelect label="結束階段" value={toStage} onChange={setToStage} />
        </div>
      </div>

      <label className="flex items-center gap-2 text-sm">
        <input
          type="checkbox"
          checked={force}
          onChange={(event) => setForce(event.target.checked)}
          className="size-4 rounded border-input"
        />
        強制重跑
      </label>

      {error ? (
        <p role="alert" className="text-sm text-destructive">
          {error}
        </p>
      ) : null}

      <Button type="submit" disabled={isPending}>
        <Play className="size-4" data-icon="inline-start" />
        {isPending ? '送出中' : '開始執行'}
      </Button>
    </form>
  )
}

function ActiveRunCard({ run }: { readonly run: PipelineRunDetail }) {
  const elapsedSeconds = useElapsedSeconds(
    run.started_at,
    isActiveStatus(run.status),
  )
  const processed = run.current_stage_processed
  const total = run.current_stage_total
  const progress = total > 0 ? Math.round((processed / total) * 100) : 0
  const currentStage = isKnownStage(run.current_stage) ? run.current_stage : null

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="flex items-center gap-2">
          <StatusBadge status={run.status} />
          <span className="text-sm text-muted-foreground">
            {run.params.bank_code ?? '全部銀行'}
          </span>
        </div>
        <span className="text-sm text-muted-foreground">
          已過 {formatDuration(elapsedSeconds)}
        </span>
      </div>

      <ol className="grid grid-cols-5 gap-2" aria-label="pipeline 階段">
        {STAGES.map((stage) => (
          <StageStep key={stage} stage={stage} run={run} />
        ))}
      </ol>

      <div className="space-y-2">
        <div className="flex justify-between text-sm">
          <span>{currentStage ? STAGE_LABELS[currentStage] : '等待中'}</span>
          <span>
            {run.current_stage ?? 'queued'} {processed} / {total} ({progress}%)
          </span>
        </div>
        <Progress value={progress} />
      </div>

      {run.status === 'failed' && run.error_message ? (
        <div
          role="alert"
          className="flex flex-wrap items-center justify-between gap-2 rounded-md border border-destructive/30 bg-destructive/10 px-3 py-2 text-sm text-destructive"
        >
          <span>{run.error_message}</span>
          <Dialog>
            <DialogTrigger className="font-medium underline underline-offset-4">
              查看詳情
            </DialogTrigger>
            <DialogContent className="sm:max-w-2xl">
              <DialogHeader>
                <DialogTitle>執行詳情</DialogTitle>
              </DialogHeader>
              <RunDetailContent run={run} />
            </DialogContent>
          </Dialog>
        </div>
      ) : null}
    </div>
  )
}

function StageStep({
  stage,
  run,
}: {
  readonly stage: PipelineStage
  readonly run: PipelineRunDetail
}) {
  const done = run.stage_summary.some((entry) => entry.stage === stage)
  const active = run.current_stage === stage && isActiveStatus(run.status)

  return (
    <li className="flex min-w-0 flex-col items-center gap-1 rounded-md border border-border px-2 py-3 text-center">
      {done ? (
        <CheckCircle2 className="size-4 text-green-600" />
      ) : active ? (
        <LoaderCircle className="size-4 animate-spin text-blue-600" />
      ) : (
        <Circle className="size-4 text-muted-foreground" />
      )}
      <span className="max-w-full truncate text-xs">{STAGE_LABELS[stage]}</span>
    </li>
  )
}

function HistoryBanner() {
  return (
    <div className="mb-3 flex items-center justify-between gap-2 rounded-md border border-blue-600/30 bg-blue-600/10 px-3 py-2 text-sm text-blue-800 dark:text-blue-200">
      <span>僅手動觸發紀錄；scheduler 自動排程結果請查看 logs</span>
      <Tooltip>
        <TooltipTrigger
          className="inline-flex size-7 items-center justify-center rounded-md hover:bg-blue-600/10"
          aria-label="scheduler 歷史說明"
        >
          <Info className="size-4" />
        </TooltipTrigger>
        <TooltipContent>
          scheduler 路徑刻意走 NoopProgressReporter，不寫入 pipeline_runs。
        </TooltipContent>
      </Tooltip>
    </div>
  )
}

function HistoryTable({
  runs,
}: {
  readonly runs: readonly PipelineRunSummary[]
}) {
  if (runs.length === 0) {
    return (
      <div className="rounded-md border border-dashed border-border bg-muted/30 p-6 text-sm text-muted-foreground">
        尚無手動觸發紀錄
      </div>
    )
  }

  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm">
        <thead className="border-b border-border text-left text-xs text-muted-foreground">
          <tr>
            <th className="py-2 pr-3 font-medium">時間</th>
            <th className="py-2 pr-3 font-medium">銀行</th>
            <th className="py-2 pr-3 font-medium">期別</th>
            <th className="py-2 pr-3 font-medium">狀態</th>
            <th className="py-2 pr-3 font-medium">階段筆數</th>
            <th className="py-2 pr-3 font-medium">耗時</th>
            <th className="py-2 pr-3 font-medium">觸發者</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-border">
          {runs.map((run) => (
            <tr key={run.id}>
              <td className="py-2 pr-3">
                <RunDetailDialog run={run} />
              </td>
              <td className="py-2 pr-3">{run.params.bank_code ?? '全部'}</td>
              <td className="py-2 pr-3">{formatPeriod(run.params)}</td>
              <td className="py-2 pr-3">
                <StatusBadge status={run.status} />
              </td>
              <td className="py-2 pr-3">{formatStageCounts(run)}</td>
              <td className="py-2 pr-3">{formatRunDuration(run)}</td>
              <td className="py-2 pr-3">{run.triggered_by}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

function RunDetailDialog({ run }: { readonly run: PipelineRunSummary }) {
  return (
    <Dialog>
      <DialogTrigger className="text-left text-primary underline-offset-4 hover:underline">
        {formatDateTime(run.created_at)}
      </DialogTrigger>
      <DialogContent className="sm:max-w-2xl">
        <DialogHeader>
          <DialogTitle>執行詳情</DialogTitle>
        </DialogHeader>
        <RunDetailContent run={run} />
      </DialogContent>
    </Dialog>
  )
}

function RunDetailContent({ run }: { readonly run: PipelineRunSummary }) {
  return (
    <div className="space-y-4">
      <div className="grid gap-2 text-sm sm:grid-cols-2">
        <DetailRow label="Run ID" value={run.id} />
        <DetailRow label="Job ID" value={run.job_id} />
        <DetailRow label="狀態" value={run.status} />
        <DetailRow label="觸發者" value={run.triggered_by} />
      </div>
      <table className="w-full text-sm">
        <thead className="border-b border-border text-left text-xs text-muted-foreground">
          <tr>
            <th className="py-2 pr-3 font-medium">階段</th>
            <th className="py-2 pr-3 font-medium">成功</th>
            <th className="py-2 pr-3 font-medium">失敗</th>
            <th className="py-2 pr-3 font-medium">耗時</th>
            <th className="py-2 pr-3 font-medium">明細</th>
            <th className="py-2 font-medium">錯誤</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-border">
          {run.stage_summary.map((entry) => (
            <tr key={entry.stage} className="align-top">
              <td className="py-2 pr-3">{entry.stage}</td>
              <td className="py-2 pr-3">{entry.ok}</td>
              <td className="py-2 pr-3">{entry.fail}</td>
              <td className="py-2 pr-3">{formatDurationMs(entry.elapsed_ms)}</td>
              <td className="max-w-48 py-2 pr-3 text-xs text-muted-foreground">
                {formatEntryCounts(entry.counts)}
              </td>
              <td className="max-w-56 py-2 text-xs text-destructive">
                {formatEntryErrors(entry.errors)}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      {run.error_message ? (
        <p className="rounded-md border border-destructive/30 bg-destructive/10 px-3 py-2 text-sm text-destructive">
          {run.error_message}
        </p>
      ) : null}
    </div>
  )
}

function DetailRow({
  label,
  value,
}: {
  readonly label: string
  readonly value: string
}) {
  return (
    <div>
      <p className="text-xs text-muted-foreground">{label}</p>
      <p className="break-all font-mono text-xs">{value}</p>
    </div>
  )
}

function StatusBadge({ status }: { readonly status: PipelineRunStatus }) {
  const variant =
    status === 'succeeded'
      ? 'success'
      : status === 'failed'
        ? 'destructive'
        : status === 'running'
          ? 'info'
          : 'outline'

  return <Badge variant={variant}>{status}</Badge>
}

function StageSelect({
  label,
  value,
  onChange,
}: {
  readonly label: string
  readonly value: PipelineStage
  readonly onChange: (value: PipelineStage) => void
}) {
  return (
    <SelectField
      label={label}
      triggerClassName="w-full"
      value={value}
      onValueChange={(v) => onChange(v as PipelineStage)}
      options={STAGES.map((stage) => ({
        value: stage,
        label: STAGE_LABELS[stage],
      }))}
    />
  )
}

function Panel({
  ref,
  icon,
  title,
  children,
}: {
  readonly ref?: React.Ref<HTMLElement>
  readonly icon: React.ReactNode
  readonly title: string
  readonly children: React.ReactNode
}) {
  return (
    <section ref={ref} className="rounded-lg border border-border bg-card p-4">
      <div className="mb-4 flex items-center gap-2">
        {icon}
        <h2 className="text-base font-semibold">{title}</h2>
      </div>
      {children}
    </section>
  )
}

function useElapsedSeconds(startedAt: string | null, enabled: boolean) {
  const [now, setNow] = useState(() => Date.now())

  useEffect(() => {
    if (!enabled) return undefined
    const id = window.setInterval(() => setNow(Date.now()), 1000)
    return () => window.clearInterval(id)
  }, [enabled])

  if (!startedAt) return 0
  return Math.max(0, Math.floor((now - new Date(startedAt).getTime()) / 1000))
}

function isActiveStatus(status: PipelineRunStatus) {
  return status === 'queued' || status === 'running'
}

function isKnownStage(stage: string | null): stage is PipelineStage {
  return Boolean(stage && STAGES.includes(stage as PipelineStage))
}

function formatDateTime(value: string) {
  return new Date(value).toLocaleString('zh-TW')
}

function formatDuration(seconds: number) {
  const minutes = Math.floor(seconds / 60)
  const remaining = seconds % 60
  return minutes > 0 ? `${minutes}m ${remaining}s` : `${remaining}s`
}

function formatDurationMs(ms: number) {
  return formatDuration(Math.round(ms / 1000))
}

function formatRunDuration(run: PipelineRunSummary) {
  if (!run.started_at || !run.completed_at) return '-'
  const seconds = Math.max(
    0,
    Math.round(
      (new Date(run.completed_at).getTime() - new Date(run.started_at).getTime()) /
        1000,
    ),
  )
  return formatDuration(seconds)
}

function formatPeriod(params: PipelineTriggerRequest) {
  if (params.year && params.month) {
    return `${params.year}-${String(params.month).padStart(2, '0')}`
  }
  if (params.year) return String(params.year)
  return '全部'
}

function formatStageCounts(run: PipelineRunSummary) {
  if (run.stage_summary.length === 0) return '-'
  const ok = run.stage_summary.reduce((sum, entry) => sum + entry.ok, 0)
  const fail = run.stage_summary.reduce((sum, entry) => sum + entry.fail, 0)
  return `${ok} / ${fail}`
}

function formatEntryCounts(counts: Readonly<Record<string, number>> | undefined) {
  if (!counts || Object.keys(counts).length === 0) return '-'
  return Object.entries(counts)
    .map(([name, value]) => `${name}: ${value}`)
    .join(', ')
}

function formatEntryErrors(errors: readonly string[] | undefined) {
  if (!errors || errors.length === 0) return '-'
  return errors.join('；')
}

export default OperationsPage
