/**
 * Gmail OAuth Web flow 頁面（oauth-onboarding-ui §8）。
 *
 * 階段式 UI，由 GET /api/setup/gmail/status 與本地 step state 共同決定當前畫面：
 * 1. 上傳 credentials.json
 * 2. 顯示 redirect URI 提示 + 「授權 Google」按鈕
 * 3. 跳轉 Google 完成授權後，由後端 callback 303 redirect 回 ?status=connected
 * 4. 已連線狀態：顯示授權 scopes、提供 revoke
 *
 * 設計取捨：
 * - credentials 狀態不暴露於 status API；以 useState 持有「本次 session 上傳成功」
 *   的旗標，重整頁面後若已 connected 直接跳到 step 4，否則回到 step 1。
 * - 使用 useQuery polling（refetchInterval=5000）等待 callback 完成；connected 後
 *   停止輪詢避免噪音。
 */
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { CheckCircle2, ExternalLink, Loader2, Upload } from 'lucide-react'
import { useEffect, useState } from 'react'
import { useSearchParams } from 'react-router'
import { apiGet, apiPost } from '@/lib/api-client'
import type { ApiResponse } from '@/lib/types'
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

interface GmailConnectionStatus {
  readonly connected: boolean
  readonly email: string | null
  readonly granted_scopes: readonly string[]
}

interface GmailCredentialsUploadResult {
  readonly saved_path: string
  readonly client_id_last8: string
}

interface GmailAuthorizeUrl {
  readonly authorize_url: string
  readonly state: string
}

const STATUS_QUERY_KEY = ['setup', 'gmail', 'status'] as const

function GmailSetupPage() {
  const queryClient = useQueryClient()
  const [searchParams, setSearchParams] = useSearchParams()
  const [credentialsUploaded, setCredentialsUploaded] = useState(false)
  const [uploadError, setUploadError] = useState('')
  const [authorizeError, setAuthorizeError] = useState('')

  const statusQuery = useQuery({
    queryKey: STATUS_QUERY_KEY,
    queryFn: () =>
      apiGet<ApiResponse<GmailConnectionStatus>>('/api/setup/gmail/status'),
    refetchInterval: (query) =>
      query.state.data?.data.connected ? false : 5000,
  })

  const callbackStatus = searchParams.get('status')
  useEffect(() => {
    if (callbackStatus === 'connected') {
      void queryClient.invalidateQueries({ queryKey: STATUS_QUERY_KEY })
      // 清掉 query string，避免 reload 重複觸發
      const next = new URLSearchParams(searchParams)
      next.delete('status')
      setSearchParams(next, { replace: true })
    }
  }, [callbackStatus, queryClient, searchParams, setSearchParams])

  const uploadMutation = useMutation({
    mutationFn: async (file: File) => {
      const form = new FormData()
      form.append('file', file)
      const response = await fetch('/api/setup/gmail/credentials', {
        method: 'POST',
        body: form,
        credentials: 'include',
      })
      if (!response.ok) {
        const body = (await response.json().catch(() => null)) as
          | { detail?: string; message?: string }
          | null
        throw new Error(
          body?.detail ?? body?.message ?? `HTTP ${response.status}`,
        )
      }
      return (await response.json()) as ApiResponse<GmailCredentialsUploadResult>
    },
    onSuccess: () => {
      setUploadError('')
      setCredentialsUploaded(true)
    },
    onError: (error: Error) => {
      setUploadError(error.message)
    },
  })

  const authorizeMutation = useMutation({
    mutationFn: () =>
      apiGet<ApiResponse<GmailAuthorizeUrl>>('/api/setup/gmail/authorize'),
    onSuccess: (response) => {
      setAuthorizeError('')
      window.location.href = response.data.authorize_url
    },
    onError: (error: Error) => {
      setAuthorizeError(error.message)
    },
  })

  const revokeMutation = useMutation({
    mutationFn: () =>
      apiPost<ApiResponse<GmailConnectionStatus>>(
        '/api/setup/gmail/revoke',
        {},
      ),
    onSuccess: () => {
      setCredentialsUploaded(false)
      void queryClient.invalidateQueries({ queryKey: STATUS_QUERY_KEY })
    },
  })

  if (statusQuery.isLoading) {
    return <LoadingState message="讀取 Gmail 連線狀態..." />
  }
  if (statusQuery.isError) {
    return <ErrorState message={(statusQuery.error as Error).message} />
  }

  const connected = statusQuery.data?.data.connected ?? false
  const grantedScopes = statusQuery.data?.data.granted_scopes ?? []
  const email = statusQuery.data?.data.email ?? null

  const redirectUri =
    typeof window !== 'undefined'
      ? `${window.location.origin}/setup/gmail/callback`
      : '/setup/gmail/callback'

  if (connected) {
    return (
      <ConnectedView
        email={email}
        scopes={grantedScopes}
        onRevoke={() => revokeMutation.mutate()}
        revoking={revokeMutation.isPending}
      />
    )
  }

  return (
    <div className="space-y-6">
      <StepCard
        index={1}
        title="上傳 credentials.json"
        active={!credentialsUploaded}
        done={credentialsUploaded}
      >
        <p className="text-sm text-muted-foreground">
          請先在 Google Cloud Console 啟用 Gmail API、建立 OAuth client，
          下載 credentials.json 後上傳於此。
        </p>
        <CredentialsUpload
          onUpload={(file) => uploadMutation.mutate(file)}
          uploading={uploadMutation.isPending}
          error={uploadError}
          uploadedClientLast8={
            uploadMutation.data?.data.client_id_last8 ?? null
          }
        />
      </StepCard>

      <StepCard
        index={2}
        title="確認 redirect URI"
        active={credentialsUploaded}
        done={false}
      >
        <p className="text-sm text-muted-foreground">
          目前的 redirect URI 為以下字串，請確認 Google Cloud Console 的
          OAuth client 已將其加入 Authorized redirect URIs。
        </p>
        <code className="block break-all rounded-md border border-border bg-muted px-3 py-2 text-xs">
          {redirectUri}
        </code>
        <p className="text-xs text-muted-foreground">
          若 CCAS_PORT 已調整或部署於非 localhost，請以實際對外 URL 為準。
        </p>
      </StepCard>

      <StepCard
        index={3}
        title="授權 Google"
        active={credentialsUploaded}
        done={false}
      >
        <p className="text-sm text-muted-foreground">
          按下方按鈕後將跳轉至 Google 授權頁，授權成功後會自動回到 CCAS。
        </p>
        <Button
          onClick={() => authorizeMutation.mutate()}
          disabled={!credentialsUploaded || authorizeMutation.isPending}
          aria-label="授權 Google"
        >
          {authorizeMutation.isPending ? (
            <Loader2 className="size-4 animate-spin" data-icon="inline-start" />
          ) : (
            <ExternalLink className="size-4" data-icon="inline-start" />
          )}
          授權 Google
        </Button>
        {authorizeError ? (
          <p className="text-sm text-destructive">{authorizeError}</p>
        ) : null}
      </StepCard>
    </div>
  )
}

function StepCard({
  index,
  title,
  active,
  done,
  children,
}: {
  readonly index: number
  readonly title: string
  readonly active: boolean
  readonly done: boolean
  readonly children: React.ReactNode
}) {
  return (
    <section
      className={`space-y-3 rounded-lg border p-4 ${
        active
          ? 'border-primary/40 bg-card'
          : done
            ? 'border-border bg-muted/30'
            : 'border-border bg-card opacity-70'
      }`}
      aria-current={active ? 'step' : undefined}
    >
      <header className="flex items-center gap-2">
        <span
          className={`flex size-6 items-center justify-center rounded-full text-xs font-semibold ${
            done
              ? 'bg-primary text-primary-foreground'
              : 'bg-muted text-muted-foreground'
          }`}
        >
          {done ? <CheckCircle2 className="size-4" /> : index}
        </span>
        <h2 className="text-base font-semibold">{title}</h2>
      </header>
      <div className="space-y-3 pl-8">{children}</div>
    </section>
  )
}

function CredentialsUpload({
  onUpload,
  uploading,
  error,
  uploadedClientLast8,
}: {
  readonly onUpload: (file: File) => void
  readonly uploading: boolean
  readonly error: string
  readonly uploadedClientLast8: string | null
}) {
  return (
    <div className="space-y-2">
      <label className="inline-flex cursor-pointer items-center gap-2">
        <input
          type="file"
          accept="application/json,.json"
          aria-label="上傳 credentials.json"
          className="block w-full text-sm file:mr-3 file:rounded-md file:border-0 file:bg-primary file:px-3 file:py-1.5 file:text-sm file:font-medium file:text-primary-foreground hover:file:bg-primary/90"
          disabled={uploading}
          onChange={(event) => {
            const file = event.target.files?.[0]
            if (file) onUpload(file)
          }}
        />
        {uploading ? (
          <Loader2 className="size-4 animate-spin text-muted-foreground" />
        ) : (
          <Upload className="size-4 text-muted-foreground" />
        )}
      </label>
      {uploadedClientLast8 ? (
        <p className="text-xs text-muted-foreground">
          已儲存 credentials.json（client_id 末 8 字：{uploadedClientLast8}）
        </p>
      ) : null}
      {error ? <p className="text-sm text-destructive">{error}</p> : null}
    </div>
  )
}

function ConnectedView({
  email,
  scopes,
  onRevoke,
  revoking,
}: {
  readonly email: string | null
  readonly scopes: readonly string[]
  readonly onRevoke: () => void
  readonly revoking: boolean
}) {
  return (
    <section className="space-y-4 rounded-lg border border-border bg-card p-4">
      <header className="flex items-center gap-2">
        <CheckCircle2 className="size-5 text-emerald-500" />
        <h2 className="text-base font-semibold">Gmail 已連線</h2>
      </header>
      <dl className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-2 text-sm">
        <dt className="text-muted-foreground">帳號</dt>
        <dd>{email ?? '（未取得使用者資訊）'}</dd>
        <dt className="text-muted-foreground">授權 scopes</dt>
        <dd className="space-y-1">
          {scopes.length > 0 ? (
            scopes.map((scope) => (
              <code
                key={scope}
                className="block break-all rounded bg-muted px-2 py-0.5 text-xs"
              >
                {scope}
              </code>
            ))
          ) : (
            <span className="text-muted-foreground">（無）</span>
          )}
        </dd>
      </dl>
      <Dialog>
        <DialogTrigger
          render={
            <Button variant="outline" size="sm" aria-label="解除 Gmail 連線">
              解除連線
            </Button>
          }
        />
        <DialogContent>
          <DialogHeader>
            <DialogTitle>確認解除 Gmail 連線？</DialogTitle>
            <DialogDescription>
              解除後 CCAS 將無法繼續從 Gmail 拉取信用卡帳單；本機 token.json
              會被刪除，並通知 Google 撤銷授權。下次使用前需重新上傳
              credentials.json 並完成授權流程。
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <DialogClose
              render={
                <Button variant="outline" size="sm">
                  取消
                </Button>
              }
            />
            <DialogClose
              render={
                <Button
                  variant="destructive"
                  size="sm"
                  onClick={onRevoke}
                  disabled={revoking}
                  aria-label="確認解除連線"
                >
                  {revoking ? '解除中...' : '確認解除'}
                </Button>
              }
            />
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </section>
  )
}

export default GmailSetupPage
