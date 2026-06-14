/**
 * 全應用 Error Boundary（R01）。
 *
 * 捕捉子樹 render 例外與 lazy chunk 載入失敗，避免整頁白屏：
 * - 一般 render 例外：顯示錯誤畫面 + 重試鈕（重置 boundary 狀態）。
 * - chunk 載入失敗（部署後舊 chunk 失效常見）：自動重新整理頁面取得新資產。
 */
import { Component, type ErrorInfo, type ReactNode } from 'react'
import { AlertCircle } from 'lucide-react'
import { Button } from '@/components/ui/button'

interface ErrorBoundaryProps {
  readonly children: ReactNode
}

interface ErrorBoundaryState {
  readonly error: Error | null
}

const CHUNK_ERROR_PATTERN =
  /Loading chunk|Failed to fetch dynamically imported module|Importing a module script failed/i

export class ErrorBoundary extends Component<ErrorBoundaryProps, ErrorBoundaryState> {
  state: ErrorBoundaryState = { error: null }

  static getDerivedStateFromError(error: Error): ErrorBoundaryState {
    return { error }
  }

  componentDidCatch(error: Error, info: ErrorInfo): void {
    // chunk 失效時自動 reload；其餘錯誤記錄到 console 供除錯。
    if (CHUNK_ERROR_PATTERN.test(error.message)) {
      window.location.reload()
      return
    }
    console.error('[ErrorBoundary] 未預期的 render 例外', error, info.componentStack)
  }

  private readonly handleRetry = (): void => {
    this.setState({ error: null })
  }

  render(): ReactNode {
    if (this.state.error === null) {
      return this.props.children
    }

    return (
      <div
        role="alert"
        className="flex min-h-[60vh] flex-col items-center justify-center gap-4 px-6 text-center"
      >
        <AlertCircle className="size-10 text-destructive" aria-hidden="true" />
        <div>
          <p className="text-lg font-semibold">頁面發生錯誤</p>
          <p className="mt-1 text-sm text-muted-foreground">
            請重試，或重新整理頁面。若問題持續，請稍後再試。
          </p>
        </div>
        <div className="flex gap-2">
          <Button variant="outline" onClick={this.handleRetry}>
            重試
          </Button>
          <Button onClick={() => window.location.reload()}>重新整理</Button>
        </div>
      </div>
    )
  }
}
