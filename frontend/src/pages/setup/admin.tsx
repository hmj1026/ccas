/**
 * Admin token rotate 頁（oauth-onboarding-ui §11）。
 *
 * 顯示目前 token 的 last4 + 建立時間 + version；按下「rotate」會：
 * 1. 開 confirm dialog（警告舊 token / cookie 立即失效）
 * 2. 呼叫 POST /api/setup/admin/token-rotate，dialog 切到「新 token」狀態
 * 3. 提供「複製到剪貼簿」與「登出 session」按鈕；登出後跳回 /login
 *
 * 新 token 只會在 rotate response 出現一次；前端不持久化、不寫 localStorage。
 */
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { useNavigate } from 'react-router'
import { apiDelete, apiGet, apiPost } from '@/lib/api-client'
import type {
  AdminTokenInfo,
  AdminTokenRotateResult,
  ApiResponse,
} from '@/lib/types'
import { Button } from '@/components/ui/button'
import {
  Dialog,
  DialogClose,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from '@/components/ui/dialog'
import { ErrorState, LoadingState } from '@/components/shared/states'

const QUERY_KEY = ['setup', 'admin', 'token-info'] as const

function formatCreatedAt(value: string | null): string {
  if (!value) return '未知'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return '未知'
  return date.toLocaleString()
}

function SetupAdminPage() {
  const queryClient = useQueryClient()
  const navigate = useNavigate()
  const [rotateError, setRotateError] = useState('')
  const [rotated, setRotated] = useState<AdminTokenRotateResult | null>(null)
  const [copyState, setCopyState] = useState<'idle' | 'copied' | 'failed'>(
    'idle',
  )

  const tokenInfo = useQuery({
    queryKey: QUERY_KEY,
    queryFn: () =>
      apiGet<ApiResponse<AdminTokenInfo>>('/api/setup/admin/token-info'),
  })

  const rotateMutation = useMutation({
    mutationFn: () =>
      apiPost<ApiResponse<AdminTokenRotateResult>>(
        '/api/setup/admin/token-rotate',
        {},
      ),
    onSuccess: (resp) => {
      setRotateError('')
      setRotated(resp.data)
      setCopyState('idle')
      // 立即同步 token-info（last4 已變）。後續登出會清整個 query cache。
      void queryClient.invalidateQueries({ queryKey: QUERY_KEY })
    },
    onError: (error: Error) => {
      setRotateError(error.message)
    },
  })

  const logoutMutation = useMutation({
    mutationFn: () => apiDelete<null>('/api/auth/session'),
    onSuccess: () => {
      queryClient.setQueryData(['auth', 'session'], false)
      void queryClient.invalidateQueries({ queryKey: ['auth', 'session'] })
      navigate('/login', { replace: true })
    },
    onError: (error: Error) => {
      // logout 失敗也不擋畫面：仍跳回 /login，讓 AuthGuard 攔截
      setRotateError(error.message)
      navigate('/login', { replace: true })
    },
  })

  async function handleCopy() {
    if (!rotated) return
    try {
      await navigator.clipboard.writeText(rotated.token)
      setCopyState('copied')
    } catch {
      setCopyState('failed')
    }
  }

  if (tokenInfo.isLoading) return <LoadingState message="讀取 token 資訊..." />
  if (tokenInfo.isError) {
    return <ErrorState message={(tokenInfo.error as Error).message} />
  }
  const info = tokenInfo.data?.data

  return (
    <div className="space-y-4">
      <header className="space-y-1">
        <h2 className="text-lg font-semibold">API Token 管理</h2>
        <p className="text-sm text-muted-foreground">
          rotate 會立刻使所有舊 Bearer token 與瀏覽器 session cookie 失效；
          請先確認新 token 已安全保存再關閉本頁。
        </p>
      </header>

      {rotateError ? (
        <p
          role="alert"
          className="rounded-md border border-destructive/40 bg-destructive/10 px-3 py-2 text-sm text-destructive"
        >
          {rotateError}
        </p>
      ) : null}

      <section
        aria-label="目前 token 資訊"
        className="space-y-3 rounded-lg border border-border bg-card p-4"
      >
        <dl className="grid grid-cols-2 gap-y-2 text-sm">
          <dt className="text-muted-foreground">末 4 字元</dt>
          <dd className="font-mono">···· {info?.last4 ?? ''}</dd>
          <dt className="text-muted-foreground">建立時間</dt>
          <dd>{formatCreatedAt(info?.created_at ?? null)}</dd>
          <dt className="text-muted-foreground">版本</dt>
          <dd>v{info?.version ?? 1}</dd>
        </dl>
        <Dialog>
          <DialogTrigger
            render={
              <Button variant="default" size="sm" aria-label="產生新 token">
                產生新 token
              </Button>
            }
          />
          <DialogContent>
            {rotated ? (
              <RotatedTokenView
                rotated={rotated}
                copyState={copyState}
                onCopy={handleCopy}
                onLogout={() => logoutMutation.mutate()}
                logoutPending={logoutMutation.isPending}
              />
            ) : (
              <RotateConfirmView
                onConfirm={() => rotateMutation.mutate()}
                isPending={rotateMutation.isPending}
              />
            )}
          </DialogContent>
        </Dialog>
      </section>
    </div>
  )
}

function RotateConfirmView({
  onConfirm,
  isPending,
}: {
  readonly onConfirm: () => void
  readonly isPending: boolean
}) {
  return (
    <>
      <DialogHeader>
        <DialogTitle>確定要產生新 token？</DialogTitle>
        <DialogDescription>
          rotate 後**舊** Bearer token 與瀏覽器 session cookie 立即失效。
          新 token 只會顯示一次，請事先準備保存位置。
        </DialogDescription>
      </DialogHeader>
      <DialogFooter>
        <DialogClose
          render={
            <Button variant="outline" size="sm" type="button">
              取消
            </Button>
          }
        />
        <Button
          variant="destructive"
          size="sm"
          onClick={onConfirm}
          disabled={isPending}
          aria-label="確認產生新 token"
        >
          {isPending ? 'rotate 中...' : '確認 rotate'}
        </Button>
      </DialogFooter>
    </>
  )
}

function RotatedTokenView({
  rotated,
  copyState,
  onCopy,
  onLogout,
  logoutPending,
}: {
  readonly rotated: AdminTokenRotateResult
  readonly copyState: 'idle' | 'copied' | 'failed'
  readonly onCopy: () => void
  readonly onLogout: () => void
  readonly logoutPending: boolean
}) {
  return (
    <>
      <DialogHeader>
        <DialogTitle>新 token（v{rotated.version}）</DialogTitle>
        <DialogDescription>
          複製並安全保存後，再點「登出此 session」用新 token 重新登入。
          關閉本對話框後將無法再次取得明文。
        </DialogDescription>
      </DialogHeader>
      <div className="space-y-3 py-2">
        <pre
          aria-label="新 token 明文"
          className="overflow-x-auto rounded-md border border-border bg-muted/50 p-3 font-mono text-xs"
        >
          {rotated.token}
        </pre>
        <div className="flex items-center gap-2">
          <Button
            variant="outline"
            size="sm"
            onClick={onCopy}
            aria-label="複製到剪貼簿"
          >
            複製到剪貼簿
          </Button>
          {copyState === 'copied' ? (
            <span role="status" className="text-xs text-emerald-600">
              已複製
            </span>
          ) : copyState === 'failed' ? (
            <span role="status" className="text-xs text-destructive">
              複製失敗，請手動選取
            </span>
          ) : null}
        </div>
      </div>
      <DialogFooter>
        <Button
          variant="default"
          size="sm"
          onClick={onLogout}
          disabled={logoutPending}
          aria-label="登出 session 並回登入頁"
        >
          {logoutPending ? '登出中...' : '我已複製，登出此 session'}
        </Button>
      </DialogFooter>
    </>
  )
}

export default SetupAdminPage
