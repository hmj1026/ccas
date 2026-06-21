/**
 * 銀行登入憑證設定頁（P3-7）。
 *
 * 管理網銀登入憑證（如 FUBON 的 NATIONAL_ID / ROC_BIRTHDAY），與 PDF 密碼
 * （/setup/secrets）分離。提供：
 * - 永久顯示 master.key 備份警告 banner（不可關閉）
 * - 來源 badge：db（綠）/ env（黃）/ none（灰），DB 優先於 env
 * - 設定 / 刪除單一憑證（dialog 確認）
 * - 一鍵將既有 env 憑證加密匯入 DB（adopt 既有部署）
 *
 * 憑證組合由後端註冊表（BANK_LOGIN_CREDENTIAL_KEYS）列舉；明文**不會**回傳。
 */
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { AlertTriangle, Lock, Trash2 } from 'lucide-react'
import { useState } from 'react'
import { apiDelete, apiGet, apiPost, apiPut } from '@/lib/api-client'
import type {
  ApiResponse,
  BankLoginCredentialStatus,
  CredentialSource,
  LoginCredentialImportResult,
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

const QUERY_KEY = ['setup', 'login-credentials'] as const

function SetupLoginCredentialsPage() {
  const queryClient = useQueryClient()
  const [mutationError, setMutationError] = useState('')
  const [importMessage, setImportMessage] = useState('')

  const credentialsQuery = useQuery({
    queryKey: QUERY_KEY,
    queryFn: () =>
      apiGet<ApiResponse<readonly BankLoginCredentialStatus[]>>(
        '/api/setup/login-credentials',
      ),
  })

  const importMutation = useMutation({
    mutationFn: () =>
      apiPost<ApiResponse<LoginCredentialImportResult>>(
        '/api/setup/login-credentials/import-from-env',
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

  if (credentialsQuery.isLoading) {
    return <LoadingState message="讀取登入憑證設定..." />
  }
  if (credentialsQuery.isError) {
    return <ErrorState message={(credentialsQuery.error as Error).message} />
  }
  const items = credentialsQuery.data?.data ?? []
  const envOnlyCount = items.filter(
    (i) => i.has_env_value && !i.has_db_value,
  ).length

  return (
    <div className="space-y-4">
      <header className="space-y-1">
        <h2 className="text-lg font-semibold">登入憑證</h2>
        <p className="text-sm text-muted-foreground">
          銀行網銀登入所需憑證（如身分證字號、生日）；DB 條目優先於環境變數，
          明文不會被回傳。
        </p>
      </header>

      <div
        role="note"
        className="flex items-start gap-2 rounded-md border border-amber-500/40 bg-amber-500/10 px-3 py-2 text-sm text-amber-800 dark:text-amber-200"
      >
        <AlertTriangle className="mt-0.5 size-4 shrink-0" />
        <p>
          備份提醒：憑證以 <code>master.key</code> 加密儲存。請定期完整備份{' '}
          <code>${'{CCAS_DATA_LOCATION}'}</code> 目錄；遺失 master.key 將導致
          所有 DB 憑證永久無法解密。
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
            偵測到 {envOnlyCount} 筆環境變數憑證尚未匯入 DB。是否一鍵加密匯入？
          </p>
          <Button
            size="sm"
            onClick={() => importMutation.mutate()}
            disabled={importMutation.isPending}
            aria-label="一鍵匯入 env 憑證"
          >
            {importMutation.isPending ? '匯入中...' : '一鍵匯入'}
          </Button>
        </div>
      ) : null}

      <ul className="space-y-2" aria-label="登入憑證列表">
        {items.map((item) => (
          <CredentialRow
            key={`${item.bank_code}_${item.credential_key}`}
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

function CredentialRow({
  item,
  onChanged,
  onError,
}: {
  readonly item: BankLoginCredentialStatus
  readonly onChanged: () => void
  readonly onError: (message: string) => void
}) {
  const envVar = `${item.bank_code}_${item.credential_key}`
  return (
    <li className="flex flex-col gap-3 rounded-lg border border-border bg-card p-4 sm:flex-row sm:items-center sm:justify-between">
      <div className="flex flex-wrap items-center gap-2">
        <span className="text-base font-medium">{item.bank_code}</span>
        <span className="text-sm text-muted-foreground">
          {item.credential_key}
        </span>
        <SourceBadge source={item.effective_source} />
        {item.has_env_value ? (
          <span className="text-xs text-muted-foreground">env 仍存在</span>
        ) : null}
      </div>
      <div className="flex gap-2">
        <SetCredentialDialog
          bankCode={item.bank_code}
          credentialKey={item.credential_key}
          onSaved={onChanged}
          onError={onError}
        />
        {item.has_db_value ? (
          <DeleteCredentialDialog
            bankCode={item.bank_code}
            credentialKey={item.credential_key}
            envVar={envVar}
            hasEnvFallback={item.has_env_value}
            onDeleted={onChanged}
            onError={onError}
          />
        ) : null}
      </div>
    </li>
  )
}

function SourceBadge({ source }: { readonly source: CredentialSource }) {
  const styles: Record<CredentialSource, string> = {
    db: 'border-emerald-500/40 bg-emerald-500/10 text-emerald-800 dark:text-emerald-200',
    env: 'border-amber-500/40 bg-amber-500/10 text-amber-800 dark:text-amber-200',
    none: 'border-border bg-muted text-muted-foreground',
  }
  const label: Record<CredentialSource, string> = {
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

function SetCredentialDialog({
  bankCode,
  credentialKey,
  onSaved,
  onError,
}: {
  readonly bankCode: string
  readonly credentialKey: string
  readonly onSaved: () => void
  readonly onError: (message: string) => void
}) {
  const [value, setValue] = useState('')
  const [open, setOpen] = useState(false)
  const label = `${bankCode} ${credentialKey}`

  const mutation = useMutation({
    mutationFn: (v: string) =>
      apiPut<ApiResponse<unknown>>(
        `/api/setup/login-credentials/${bankCode}/${credentialKey}`,
        { value: v },
      ),
    onSuccess: () => {
      setValue('')
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
          <Button variant="outline" size="sm" aria-label={`設定 ${label}`}>
            <Lock className="size-3.5" data-icon="inline-start" />
            設定憑證
          </Button>
        }
      />
      <DialogContent>
        <DialogHeader>
          <DialogTitle>
            設定 {bankCode} 的 {credentialKey}
          </DialogTitle>
          <DialogDescription>
            憑證會立即用 <code>master.key</code> 加密後儲存於 DB。
            既有條目將被覆寫。
          </DialogDescription>
        </DialogHeader>
        <form
          className="space-y-3 py-2"
          onSubmit={(event) => {
            event.preventDefault()
            if (value) mutation.mutate(value)
          }}
        >
          <label className="block space-y-1 text-sm">
            <span>新憑證值</span>
            <input
              type="password"
              value={value}
              onChange={(event) => setValue(event.target.value)}
              required
              autoFocus
              aria-label={`${label} 新憑證值`}
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
              disabled={!value || mutation.isPending}
              aria-label={`儲存 ${label}`}
            >
              {mutation.isPending ? '儲存中...' : '儲存'}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}

function DeleteCredentialDialog({
  bankCode,
  credentialKey,
  envVar,
  hasEnvFallback,
  onDeleted,
  onError,
}: {
  readonly bankCode: string
  readonly credentialKey: string
  readonly envVar: string
  readonly hasEnvFallback: boolean
  readonly onDeleted: () => void
  readonly onError: (message: string) => void
}) {
  const label = `${bankCode} ${credentialKey}`
  const mutation = useMutation({
    mutationFn: () =>
      apiDelete<ApiResponse<unknown>>(
        `/api/setup/login-credentials/${bankCode}/${credentialKey}`,
      ),
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
            aria-label={`刪除 ${label} DB 憑證`}
          >
            <Trash2 className="size-3.5" data-icon="inline-start" />
            刪除 DB 條目
          </Button>
        }
      />
      <DialogContent>
        <DialogHeader>
          <DialogTitle>刪除 {label} 的 DB 憑證？</DialogTitle>
          <DialogDescription>
            {hasEnvFallback
              ? `刪除後仍會 fallback 至環境變數 ${envVar}，web-fetch 登入不受影響。`
              : `刪除後該憑證將無值可用，web-fetch 登入會失敗。請先設定 env（${envVar}）或重新設定憑證。`}
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
                aria-label={`確認刪除 ${label}`}
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

export default SetupLoginCredentialsPage
