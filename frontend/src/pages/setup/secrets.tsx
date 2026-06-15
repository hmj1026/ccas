/**
 * PDF secrets 設定頁（oauth-onboarding-ui §10）。
 *
 * 提供：
 * - 永久顯示 master.key 備份警告 banner（不可關閉）
 * - 來源 badge：db（綠）/ env（黃）/ none（灰），DB 優先於 env
 * - 設定 / 刪除單一銀行密碼（dialog 確認）
 * - 一鍵將既有 env 密碼匯入 DB（adopt 既有部署）
 *
 * Response **不會**回傳明文；本頁也不要求使用者重複輸入即可看到密碼。
 */
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { AlertTriangle, KeyRound, Trash2 } from 'lucide-react'
import { useState } from 'react'
import { apiDelete, apiGet, apiPost, apiPut } from '@/lib/api-client'
import type {
  ApiResponse,
  BankSecretStatus,
  ImportFromEnvResult,
  SecretSource,
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

const QUERY_KEY = ['setup', 'secrets'] as const

function SetupSecretsPage() {
  const queryClient = useQueryClient()
  const [mutationError, setMutationError] = useState('')
  const [importMessage, setImportMessage] = useState('')

  const secretsQuery = useQuery({
    queryKey: QUERY_KEY,
    queryFn: () =>
      apiGet<ApiResponse<readonly BankSecretStatus[]>>('/api/setup/secrets'),
  })

  const importMutation = useMutation({
    mutationFn: () =>
      apiPost<ApiResponse<ImportFromEnvResult>>(
        '/api/setup/secrets/import-from-env',
        {},
      ),
    onSuccess: (resp) => {
      setMutationError('')
      setImportMessage(
        `已匯入 ${resp.data.imported} 筆，略過 ${resp.data.skipped_already_in_db} 筆既有 DB 條目。`,
      )
      void queryClient.invalidateQueries({ queryKey: QUERY_KEY })
    },
    onError: (error: Error) => {
      setImportMessage('')
      setMutationError(error.message)
    },
  })

  if (secretsQuery.isLoading) return <LoadingState message="讀取密碼設定..." />
  if (secretsQuery.isError) {
    return <ErrorState message={(secretsQuery.error as Error).message} />
  }
  const items = secretsQuery.data?.data ?? []
  const envOnlyCount = items.filter(
    (i) => i.has_env_secret && !i.has_db_secret,
  ).length

  return (
    <div className="space-y-4">
      <header className="space-y-1">
        <h2 className="text-lg font-semibold">PDF 密碼</h2>
        <p className="text-sm text-muted-foreground">
          DB 條目優先於環境變數；明文密碼不會被回傳。
        </p>
      </header>

      <div
        role="note"
        className="flex items-start gap-2 rounded-md border border-amber-500/40 bg-amber-500/10 px-3 py-2 text-sm text-amber-800 dark:text-amber-200"
      >
        <AlertTriangle className="mt-0.5 size-4 shrink-0" />
        <p>
          備份提醒：密碼以 <code>master.key</code> 加密儲存。請定期完整備份{' '}
          <code>${'{CCAS_DATA_LOCATION}'}</code> 目錄；遺失 master.key 將導致
          所有 DB 密碼永久無法解密。
        </p>
      </div>

      {mutationError ? (
        <p
          role="alert"
          className="rounded-md border border-destructive/40 bg-destructive/10 px-3 py-2 text-sm text-destructive"
        >
          {mutationError}
        </p>
      ) : null}
      {importMessage ? (
        <p
          role="status"
          className="rounded-md border border-emerald-500/40 bg-emerald-500/10 px-3 py-2 text-sm text-emerald-800 dark:text-emerald-200"
        >
          {importMessage}
        </p>
      ) : null}

      {envOnlyCount > 0 ? (
        <div className="flex flex-col gap-2 rounded-md border border-border bg-card p-3 sm:flex-row sm:items-center sm:justify-between">
          <p className="text-sm">
            偵測到 {envOnlyCount} 筆環境變數密碼尚未匯入 DB。是否一鍵加密匯入？
          </p>
          <Button
            size="sm"
            onClick={() => importMutation.mutate()}
            disabled={importMutation.isPending}
            aria-label="一鍵匯入 env 密碼"
          >
            {importMutation.isPending ? '匯入中...' : '一鍵匯入'}
          </Button>
        </div>
      ) : null}

      <ul className="space-y-2" aria-label="銀行密碼列表">
        {items.map((item) => (
          <SecretRow
            key={item.bank_code}
            item={item}
            onChanged={() => {
              setMutationError('')
              setImportMessage('')
              void queryClient.invalidateQueries({ queryKey: QUERY_KEY })
            }}
            onError={setMutationError}
          />
        ))}
      </ul>
    </div>
  )
}

function SecretRow({
  item,
  onChanged,
  onError,
}: {
  readonly item: BankSecretStatus
  readonly onChanged: () => void
  readonly onError: (message: string) => void
}) {
  return (
    <li className="flex flex-col gap-3 rounded-lg border border-border bg-card p-4 sm:flex-row sm:items-center sm:justify-between">
      <div className="flex flex-wrap items-center gap-2">
        <span className="text-base font-medium">{item.bank_code}</span>
        <SourceBadge source={item.effective_source} />
        {item.has_env_secret ? (
          <span className="text-xs text-muted-foreground">env 仍存在</span>
        ) : null}
      </div>
      <div className="flex gap-2">
        <SetPasswordDialog
          code={item.bank_code}
          onSaved={onChanged}
          onError={onError}
        />
        {item.has_db_secret ? (
          <DeletePasswordDialog
            code={item.bank_code}
            hasEnvFallback={item.has_env_secret}
            onDeleted={onChanged}
            onError={onError}
          />
        ) : null}
      </div>
    </li>
  )
}

function SourceBadge({ source }: { readonly source: SecretSource }) {
  const styles: Record<SecretSource, string> = {
    db: 'border-emerald-500/40 bg-emerald-500/10 text-emerald-800 dark:text-emerald-200',
    env: 'border-amber-500/40 bg-amber-500/10 text-amber-800 dark:text-amber-200',
    none: 'border-border bg-muted text-muted-foreground',
  }
  const label: Record<SecretSource, string> = {
    db: 'DB',
    env: 'env',
    none: '未設定',
  }
  return (
    <span
      className={`inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-xs font-medium ${styles[source]}`}
      aria-label={`目前來源：${label[source]}`}
      title="DB 優先於 env；DB 刪除後 env 仍生效則自動 fallback"
    >
      {label[source]}
    </span>
  )
}

function SetPasswordDialog({
  code,
  onSaved,
  onError,
}: {
  readonly code: string
  readonly onSaved: () => void
  readonly onError: (message: string) => void
}) {
  const [password, setPassword] = useState('')
  const [open, setOpen] = useState(false)

  const mutation = useMutation({
    mutationFn: (pw: string) =>
      apiPut<ApiResponse<unknown>>(`/api/setup/secrets/${code}`, {
        password: pw,
      }),
    onSuccess: () => {
      setPassword('')
      setOpen(false)
      onSaved()
    },
    onError: (error: Error) => {
      onError(error.message)
    },
  })

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger
        render={
          <Button variant="outline" size="sm" aria-label={`設定 ${code} 密碼`}>
            <KeyRound className="size-3.5" data-icon="inline-start" />
            設定密碼
          </Button>
        }
      />
      <DialogContent>
        <DialogHeader>
          <DialogTitle>設定 {code} 的 PDF 密碼</DialogTitle>
          <DialogDescription>
            密碼會立即用 <code>master.key</code> 加密後儲存於 DB。
            既有條目將被覆寫。
          </DialogDescription>
        </DialogHeader>
        <form
          className="space-y-3 py-2"
          onSubmit={(event) => {
            event.preventDefault()
            if (password) mutation.mutate(password)
          }}
        >
          <label className="block space-y-1 text-sm">
            <span>新密碼</span>
            <input
              type="password"
              value={password}
              onChange={(event) => setPassword(event.target.value)}
              required
              autoFocus
              aria-label={`${code} 新密碼`}
              className="block w-full rounded-md border border-input bg-background px-3 py-1.5 text-sm shadow-sm focus:border-ring focus:outline-none focus:ring-1 focus:ring-ring"
            />
          </label>
          <DialogFooter>
            <DialogClose
              render={
                <Button variant="outline" size="sm" type="button">
                  取消
                </Button>
              }
            />
            <Button
              type="submit"
              size="sm"
              disabled={!password || mutation.isPending}
              aria-label={`儲存 ${code} 密碼`}
            >
              {mutation.isPending ? '儲存中...' : '儲存'}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}

function DeletePasswordDialog({
  code,
  hasEnvFallback,
  onDeleted,
  onError,
}: {
  readonly code: string
  readonly hasEnvFallback: boolean
  readonly onDeleted: () => void
  readonly onError: (message: string) => void
}) {
  const mutation = useMutation({
    mutationFn: () =>
      apiDelete<ApiResponse<unknown>>(`/api/setup/secrets/${code}`),
    onSuccess: onDeleted,
    onError: (error: Error) => onError(error.message),
  })

  return (
    <Dialog>
      <DialogTrigger
        render={
          <Button
            variant="destructive"
            size="sm"
            aria-label={`刪除 ${code} DB 密碼`}
          >
            <Trash2 className="size-3.5" data-icon="inline-start" />
            刪除 DB 條目
          </Button>
        }
      />
      <DialogContent>
        <DialogHeader>
          <DialogTitle>刪除 {code} 的 DB 密碼？</DialogTitle>
          <DialogDescription>
            {hasEnvFallback
              ? `刪除後仍會 fallback 至環境變數 PDF_PASSWORD_${code}，pipeline 解密不受影響。`
              : `刪除後該銀行將無 PDF 密碼可用，pipeline 解密階段會失敗。請先設定 env 或在 ${code} 重新設定密碼。`}
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
                onClick={() => mutation.mutate()}
                disabled={mutation.isPending}
                aria-label={`確認刪除 ${code}`}
              >
                {mutation.isPending ? '刪除中...' : '確認刪除'}
              </Button>
            }
          />
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

export default SetupSecretsPage
