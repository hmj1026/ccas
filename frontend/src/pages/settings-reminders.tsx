/**
 * Settings 子頁：付款提醒設定（bills-management-and-insights §11）。
 *
 * 列出所有未付帳單的提醒設定（enabled / days_before / channel），
 * 允許 toggle、編輯天數陣列與通知管道，提供「測試發送」按鈕。
 */
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Send } from 'lucide-react'
import { useState } from 'react'
import { apiGet, apiPost, apiPut } from '@/lib/api-client'
import type {
  ApiResponse,
  ReminderChannel,
  ReminderSettingItem,
  ReminderSettingUpdateRequest,
  ReminderTestResult,
} from '@/lib/types'
import { Button } from '@/components/ui/button'
import { SelectField } from '@/components/ui/select-field'
import { EmptyState, ErrorState, LoadingState } from '@/components/shared/states'

const CHANNEL_LABELS: Record<ReminderChannel, string> = {
  telegram: 'Telegram',
  ui_banner: 'UI Banner',
  both: 'Telegram + Banner',
}

function formatDays(days: readonly number[]): string {
  if (days.length === 0) return '（無）'
  return days.map((d) => `${d} 天`).join('、')
}

function ReminderRow({
  item,
  onUpdate,
  onTest,
  isPending,
  testResult,
}: {
  readonly item: ReminderSettingItem
  readonly onUpdate: (body: ReminderSettingUpdateRequest) => void
  readonly onTest: () => void
  readonly isPending: boolean
  readonly testResult?: ReminderTestResult | null
}) {
  const [daysInput, setDaysInput] = useState(item.days_before.join(','))

  const handleDaysCommit = () => {
    const parsed = daysInput
      .split(/[,\s]+/)
      .map((s) => Number.parseInt(s.trim(), 10))
      .filter((n) => Number.isFinite(n) && n >= 1)
    onUpdate({ days_before: parsed })
  }

  return (
    <div className="rounded-lg border border-border p-4 space-y-3">
      <div className="flex items-center justify-between gap-3">
        <div>
          <p className="text-sm font-semibold">
            {item.bank_name ?? item.bank_code}
            <span className="ml-2 text-xs text-muted-foreground">
              帳單月份 {item.billing_month} · 到期 {item.due_date}
            </span>
          </p>
          {!item.has_setting && (
            <p className="text-xs text-muted-foreground">尚未自訂，使用預設設定</p>
          )}
        </div>
        <label className="flex items-center gap-2 text-sm">
          <input
            type="checkbox"
            checked={item.enabled}
            disabled={isPending}
            onChange={(e) => onUpdate({ enabled: e.target.checked })}
          />
          啟用
        </label>
      </div>

      <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
        <label className="flex flex-col text-sm">
          <span className="text-muted-foreground">提前天數（逗號分隔）</span>
          <input
            type="text"
            className="rounded border border-input bg-background px-2 py-1"
            value={daysInput}
            onChange={(e) => setDaysInput(e.target.value)}
            onBlur={handleDaysCommit}
            disabled={isPending}
          />
          <span className="mt-1 text-xs text-muted-foreground">
            目前：{formatDays(item.days_before)}
          </span>
        </label>
        <SelectField
          label="通知管道"
          triggerClassName="h-auto rounded px-2 py-1"
          value={item.channel}
          disabled={isPending}
          onValueChange={(v) => onUpdate({ channel: v as ReminderChannel })}
          options={Object.entries(CHANNEL_LABELS).map(([k, label]) => ({
            value: k,
            label,
          }))}
        />
      </div>

      <div className="flex items-center gap-3">
        <Button
          variant="outline"
          size="sm"
          onClick={onTest}
          disabled={isPending}
        >
          <Send className="size-4" data-icon="inline-start" />
          測試發送
        </Button>
        {testResult && (
          <span
            className={`text-xs ${
              testResult.sent ? 'text-green-600' : 'text-muted-foreground'
            }`}
          >
            {testResult.sent ? '✓ ' : ''}
            {testResult.detail || (testResult.sent ? '已送出' : '未送出')}
          </span>
        )}
      </div>
    </div>
  )
}

function SettingsRemindersPage() {
  const queryClient = useQueryClient()
  const { data, isLoading, error } = useQuery({
    queryKey: ['reminders', 'settings'],
    queryFn: () =>
      apiGet<ApiResponse<readonly ReminderSettingItem[]>>(
        '/api/reminders/settings',
      ),
  })

  const [testResults, setTestResults] = useState<
    Record<number, ReminderTestResult | null>
  >({})

  const updateMutation = useMutation({
    mutationFn: ({
      billId,
      body,
    }: {
      billId: number
      body: ReminderSettingUpdateRequest
    }) =>
      apiPut<ApiResponse<ReminderSettingItem>>(
        `/api/reminders/${billId}/settings`,
        body,
      ),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['reminders', 'settings'] })
    },
  })

  const testMutation = useMutation({
    mutationFn: (billId: number) =>
      apiPost<ApiResponse<ReminderTestResult>>(
        `/api/reminders/${billId}/test`,
        {},
      ),
    onSuccess: (resp, billId) => {
      setTestResults((prev) => ({ ...prev, [billId]: resp.data }))
    },
    onError: (err: Error, billId) => {
      setTestResults((prev) => ({
        ...prev,
        [billId]: {
          sent: false,
          channel: 'telegram',
          detail: err.message,
        },
      }))
    },
  })

  if (isLoading) return <LoadingState />
  if (error) return <ErrorState message={error.message} />
  if (!data?.data.length)
    return <EmptyState message="目前沒有未付帳單需要設定提醒" />

  return (
    <div className="space-y-4">
      <div>
        <h1 className="text-xl font-bold">付款提醒設定</h1>
        <p className="text-sm text-muted-foreground">
          每張帳單可獨立設定提前提醒天數與通知管道。
        </p>
      </div>
      <div className="space-y-3">
        {data.data.map((item) => (
          <ReminderRow
            key={item.bill_id}
            item={item}
            onUpdate={(body) =>
              updateMutation.mutate({ billId: item.bill_id, body })
            }
            onTest={() => testMutation.mutate(item.bill_id)}
            isPending={updateMutation.isPending || testMutation.isPending}
            testResult={testResults[item.bill_id] ?? null}
          />
        ))}
      </div>
    </div>
  )
}

export default SettingsRemindersPage
