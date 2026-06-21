/**
 * StagedAttachmentsWarning -- 呈現需要注意的 Gmail 附件。
 *
 * 顯示 fetch_expired / failed / parse_failed 三種異常狀態，
 * 幫助使用者識別哪些帳單是永久無法下載（連結已過期）、
 * 哪些需要人工介入。空結果時不渲染，避免在一切正常時干擾介面。
 */
import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { AlertTriangle, ChevronDown, ChevronUp } from 'lucide-react'
import { apiGet } from '@/lib/api-client'
import type {
  PaginatedResponse,
  StagedAttachmentItem,
  StagedAttachmentStatus,
} from '@/lib/types'
import { formatDate } from '@/lib/utils'

const WARN_STATUSES = [
  'fetch_expired',
  'failed',
  'parse_failed',
] as const satisfies readonly StagedAttachmentStatus[]

type WarnStatus = (typeof WARN_STATUSES)[number]

const STATUS_BADGE: Record<
  WarnStatus,
  { label: string; className: string }
> = {
  fetch_expired: {
    label: '連結已失效',
    className: 'bg-orange-100 text-orange-700 border-orange-300',
  },
  failed: {
    label: '下載失敗',
    className: 'bg-red-100 text-red-700 border-red-300',
  },
  parse_failed: {
    label: '解析失敗',
    className: 'bg-yellow-100 text-yellow-700 border-yellow-300',
  },
}

const STATUS_HINT: Record<WarnStatus, string> = {
  fetch_expired:
    '下載連結已一次性使用過期，無法再自動抓取（此為正常現象，可從銀行網銀補下載後手動匯入）',
  failed: '系統嘗試下載失敗，請檢查憑證或網路',
  parse_failed: 'PDF 解析失敗，請確認檔案格式或建立 parser issue',
}

function isWarnStatus(status: StagedAttachmentStatus): status is WarnStatus {
  return (WARN_STATUSES as readonly StagedAttachmentStatus[]).includes(status)
}

export function StagedAttachmentsWarning() {
  const [expanded, setExpanded] = useState(false)

  const { data, isLoading } = useQuery({
    queryKey: ['staged-attachments', WARN_STATUSES],
    queryFn: () =>
      apiGet<PaginatedResponse<StagedAttachmentItem>>(
        '/api/staged-attachments',
        {
          status: WARN_STATUSES.join(','),
          page_size: 100,
        },
      ),
  })

  if (isLoading || !data) return null
  if (data.data.length === 0) return null

  const countsByStatus = data.data.reduce<
    Partial<Record<StagedAttachmentStatus, number>>
  >((acc, item) => {
    acc[item.status] = (acc[item.status] ?? 0) + 1
    return acc
  }, {})

  return (
    <div className="rounded-lg border border-orange-300 bg-orange-500/10 p-4 dark:border-orange-500/40">
      <button
        type="button"
        className="flex w-full items-center justify-between gap-3"
        onClick={() => setExpanded((v) => !v)}
        aria-expanded={expanded}
        aria-controls="staged-attachments-panel"
      >
        <div className="flex items-center gap-2 text-sm font-medium text-orange-900 dark:text-orange-200">
          <AlertTriangle className="size-4" />
          <span>需要注意的附件（{data.data.length} 筆）</span>
          <span className="text-xs text-orange-700 dark:text-orange-300">
            {WARN_STATUSES.filter((s) => countsByStatus[s])
              .map((s) => `${STATUS_BADGE[s].label} ${countsByStatus[s]}`)
              .join('・')}
          </span>
        </div>
        {expanded ? (
          <ChevronUp className="size-4 text-orange-700 dark:text-orange-300" />
        ) : (
          <ChevronDown className="size-4 text-orange-700 dark:text-orange-300" />
        )}
      </button>

      {/* Panel is always present so the button's aria-controls always resolves
          to a real node; collapsed state is conveyed via the hidden attribute. */}
      <div
        id="staged-attachments-panel"
        hidden={!expanded}
        className="mt-3 space-y-2"
      >
        {expanded &&
          data.data.map((item) => {
            const badge = isWarnStatus(item.status)
              ? STATUS_BADGE[item.status]
              : undefined
            const hint = isWarnStatus(item.status)
              ? STATUS_HINT[item.status]
              : undefined
            return (
              <div
                key={item.id}
                className="rounded border border-orange-200 bg-card p-3 text-sm dark:border-orange-500/30"
              >
                <div className="flex items-center justify-between gap-2">
                  <div className="flex items-center gap-2">
                    <span className="font-medium">
                      {item.bank_name ?? item.bank_code}
                    </span>
                    <span className="text-xs text-muted-foreground">
                      {formatDate(item.message_date)}
                    </span>
                  </div>
                  {badge && (
                    <span
                      className={`rounded border px-2 py-0.5 text-xs ${badge.className}`}
                    >
                      {badge.label}
                    </span>
                  )}
                </div>
                <p className="mt-1 text-xs text-muted-foreground">
                  {item.original_filename}
                </p>
                {hint && (
                  <p className="mt-1 text-xs text-orange-700 dark:text-orange-300">{hint}</p>
                )}
                {item.error_reason && (
                  <p className="mt-1 break-all text-xs text-muted-foreground">
                    {item.error_reason}
                  </p>
                )}
              </div>
            )
          })}
      </div>
    </div>
  )
}
