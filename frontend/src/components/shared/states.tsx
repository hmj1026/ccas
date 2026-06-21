/**
 * 共用 loading、error、empty state 元件。
 */
import { AlertCircle, Inbox, Loader2, RefreshCw } from 'lucide-react'
import { cn } from '@/lib/utils'

/**
 * 資料載入中狀態，顯示旋轉圖示與提示文字。
 *
 * @param message - 提示文字，預設為「載入中...」
 */
export function LoadingState({ message = '載入中...' }: { readonly message?: string }) {
  return (
    <div
      role="status"
      aria-live="polite"
      className="flex flex-col items-center justify-center py-12 text-muted-foreground"
    >
      <Loader2 className="size-8 animate-spin" aria-hidden="true" />
      <p className="mt-3 text-sm">{message}</p>
    </div>
  )
}

/**
 * 錯誤狀態，以紅色顯示錯誤訊息，並可選擇性提供「重試」按鈕。
 *
 * @param message - 錯誤說明文字，預設為「發生錯誤」
 * @param onRetry - 提供時於訊息下方渲染重試按鈕；省略則維持純錯誤顯示
 * @param isRetrying - 重試進行中（按鈕停用並顯示旋轉圖示），避免重複觸發
 */
export function ErrorState({
  message = '發生錯誤',
  onRetry,
  isRetrying = false,
}: {
  readonly message?: string
  readonly onRetry?: () => void
  readonly isRetrying?: boolean
}) {
  return (
    <div
      role="alert"
      className="flex flex-col items-center justify-center py-12 text-destructive"
    >
      <AlertCircle className="size-8" aria-hidden="true" />
      <p className="mt-3 text-sm">{message}</p>
      {onRetry && (
        <button
          type="button"
          onClick={onRetry}
          disabled={isRetrying}
          className="mt-3 inline-flex items-center gap-1.5 rounded border border-destructive/40 px-3 py-1 text-xs hover:bg-destructive/10 disabled:cursor-not-allowed disabled:opacity-50"
        >
          <RefreshCw
            className={cn('size-3.5', isRetrying && 'animate-spin')}
            aria-hidden="true"
          />
          {isRetrying ? '重試中...' : '重試'}
        </button>
      )}
    </div>
  )
}

/**
 * 空資料狀態，顯示收件匣圖示與提示文字。
 *
 * @param message - 提示文字，預設為「暫無資料」
 */
export function EmptyState({ message = '暫無資料' }: { readonly message?: string }) {
  return (
    <div
      role="status"
      className="flex flex-col items-center justify-center py-12 text-muted-foreground"
    >
      <Inbox className="size-8" aria-hidden="true" />
      <p className="mt-3 text-sm">{message}</p>
    </div>
  )
}
