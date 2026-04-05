/**
 * 共用 loading、error、empty state 元件。
 */
import { AlertCircle, Inbox, Loader2 } from 'lucide-react'

/**
 * 資料載入中狀態，顯示旋轉圖示與提示文字。
 *
 * @param message - 提示文字，預設為「載入中...」
 */
export function LoadingState({ message = '載入中...' }: { readonly message?: string }) {
  return (
    <div className="flex flex-col items-center justify-center py-12 text-muted-foreground">
      <Loader2 className="size-8 animate-spin" />
      <p className="mt-3 text-sm">{message}</p>
    </div>
  )
}

/**
 * 錯誤狀態，以紅色顯示錯誤訊息。
 *
 * @param message - 錯誤說明文字，預設為「發生錯誤」
 */
export function ErrorState({ message = '發生錯誤' }: { readonly message?: string }) {
  return (
    <div className="flex flex-col items-center justify-center py-12 text-destructive">
      <AlertCircle className="size-8" />
      <p className="mt-3 text-sm">{message}</p>
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
    <div className="flex flex-col items-center justify-center py-12 text-muted-foreground">
      <Inbox className="size-8" />
      <p className="mt-3 text-sm">{message}</p>
    </div>
  )
}
