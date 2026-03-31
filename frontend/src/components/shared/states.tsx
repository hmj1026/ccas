/**
 * 共用 loading、error、empty state 元件。
 */
import { AlertCircle, Inbox, Loader2 } from 'lucide-react'

export function LoadingState({ message = '載入中...' }: { readonly message?: string }) {
  return (
    <div className="flex flex-col items-center justify-center py-12 text-muted-foreground">
      <Loader2 className="size-8 animate-spin" />
      <p className="mt-3 text-sm">{message}</p>
    </div>
  )
}

export function ErrorState({ message = '發生錯誤' }: { readonly message?: string }) {
  return (
    <div className="flex flex-col items-center justify-center py-12 text-destructive">
      <AlertCircle className="size-8" />
      <p className="mt-3 text-sm">{message}</p>
    </div>
  )
}

export function EmptyState({ message = '暫無資料' }: { readonly message?: string }) {
  return (
    <div className="flex flex-col items-center justify-center py-12 text-muted-foreground">
      <Inbox className="size-8" />
      <p className="mt-3 text-sm">{message}</p>
    </div>
  )
}
