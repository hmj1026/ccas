/**
 * Settings 頁面 -- 銀行設定與分類關鍵字管理。
 */
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Plus, Trash2 } from 'lucide-react'
import { useState } from 'react'
import { Link } from 'react-router'
import { apiGet, apiPost, apiPatch, apiDelete } from '@/lib/api-client'
import type {
  ApiResponse,
  BankConfigItem,
  BankConfigUpdateRequest,
  CategoryKeywordItem,
  CategoryKeywordCreateRequest,
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
} from '@/components/ui/dialog'
import { LoadingState, ErrorState, EmptyState } from '@/components/shared/states'

// -- Bank Config Section --

/**
 * 銀行設定管理區塊。
 * 顯示所有銀行設定列表，並提供啟用/停用切換功能。
 */
function BankConfigSection() {
  const queryClient = useQueryClient()
  const { data, isLoading, error } = useQuery({
    queryKey: ['settings', 'banks'],
    queryFn: () =>
      apiGet<ApiResponse<readonly BankConfigItem[]>>('/api/settings/banks'),
  })

  const updateBank = useMutation({
    mutationFn: ({
      id,
      body,
    }: {
      id: number
      body: BankConfigUpdateRequest
    }) => apiPatch<ApiResponse<BankConfigItem>>(`/api/settings/banks/${id}`, body),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['settings', 'banks'] })
    },
  })

  if (isLoading) return <LoadingState />
  if (error) return <ErrorState message={error.message} />
  if (!data?.data.length) return <EmptyState message="尚無銀行設定" />

  return (
    <div className="space-y-3">
      {data.data.map((bank) => (
        <BankConfigRow
          key={bank.id}
          bank={bank}
          onUpdate={(body) => updateBank.mutate({ id: bank.id, body })}
          isPending={updateBank.isPending}
        />
      ))}
    </div>
  )
}

/**
 * 單列銀行設定，顯示銀行名稱、代碼、Gmail 篩選條件，並提供啟用/停用按鈕。
 *
 * @param bank - 銀行設定資料
 * @param onUpdate - 更新設定的 callback
 * @param isPending - mutation 進行中時禁用按鈕
 */
function BankConfigRow({
  bank,
  onUpdate,
  isPending,
}: {
  readonly bank: BankConfigItem
  readonly onUpdate: (body: BankConfigUpdateRequest) => void
  readonly isPending: boolean
}) {
  return (
    <div className="flex items-center justify-between rounded-lg border border-border p-3">
      <div className="space-y-0.5">
        <p className="font-medium">{bank.bank_name}</p>
        <p className="text-xs text-muted-foreground">
          {bank.bank_code} / {bank.gmail_filter} / parser: {bank.active_parser_version}
        </p>
      </div>
      <Button
        variant={bank.is_active ? 'secondary' : 'outline'}
        size="sm"
        disabled={isPending}
        onClick={() => onUpdate({ is_active: !bank.is_active })}
        aria-label={bank.is_active ? '停用銀行' : '啟用銀行'}
      >
        {bank.is_active ? '啟用中' : '已停用'}
      </Button>
    </div>
  )
}

// -- Category Keyword Section --

/**
 * 分類關鍵字管理區塊。
 * 顯示現有關鍵字規則列表，並提供新增與刪除功能。
 * 新增時驗證關鍵字與分類欄位均非空。
 */
function CategoryKeywordSection() {
  const queryClient = useQueryClient()
  const [newKeyword, setNewKeyword] = useState('')
  const [newCategory, setNewCategory] = useState('')
  const [mutationError, setMutationError] = useState<string | null>(null)
  const [pendingDelete, setPendingDelete] =
    useState<CategoryKeywordItem | null>(null)

  const { data, isLoading, error } = useQuery({
    queryKey: ['settings', 'categories'],
    queryFn: () =>
      apiGet<ApiResponse<readonly CategoryKeywordItem[]>>(
        '/api/settings/categories',
      ),
  })

  const createCategory = useMutation({
    mutationFn: (body: CategoryKeywordCreateRequest) =>
      apiPost<ApiResponse<CategoryKeywordItem>>('/api/settings/categories', body),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['settings', 'categories'] })
      setNewKeyword('')
      setNewCategory('')
    },
  })

  const deleteCategory = useMutation({
    mutationFn: (id: number) =>
      apiDelete<ApiResponse<{ deleted_id: number }>>(
        `/api/settings/categories/${id}`,
      ),
    onSuccess: () => {
      setMutationError(null)
      queryClient.invalidateQueries({ queryKey: ['settings', 'categories'] })
    },
    onError: (err: Error) => setMutationError(err.message),
  })

  /**
   * 驗證欄位非空後送出新增分類關鍵字請求。
   * 任一欄位為空時提早返回，不送出請求。
   */
  function handleAdd() {
    if (!newKeyword.trim() || !newCategory.trim()) return
    createCategory.mutate({
      keyword: newKeyword.trim(),
      category: newCategory.trim(),
    })
  }

  if (isLoading) return <LoadingState />
  if (error) return <ErrorState message={error.message} />

  return (
    <div className="space-y-3">
      {mutationError ? (
        <p
          role="alert"
          className="rounded-md border border-destructive/40 bg-destructive/10 px-3 py-2 text-sm text-destructive"
        >
          {mutationError}
        </p>
      ) : null}
      {/* Add form */}
      <div className="flex gap-2">
        <input
          type="text"
          placeholder="關鍵字"
          value={newKeyword}
          onChange={(e) => setNewKeyword(e.target.value)}
          className="h-8 flex-1 rounded-lg border border-input bg-background px-3 text-sm"
          aria-label="新增關鍵字"
        />
        <input
          type="text"
          placeholder="分類"
          value={newCategory}
          onChange={(e) => setNewCategory(e.target.value)}
          className="h-8 flex-1 rounded-lg border border-input bg-background px-3 text-sm"
          aria-label="新增分類"
        />
        <Button
          variant="outline"
          size="sm"
          onClick={handleAdd}
          disabled={createCategory.isPending}
          aria-label="新增分類規則"
        >
          <Plus className="size-4" data-icon="inline-start" />
          新增
        </Button>
      </div>

      {/* List */}
      {!data?.data.length ? (
        <EmptyState message="尚無分類關鍵字" />
      ) : (
        <div className="space-y-2">
          {data.data.map((item) => (
            <div
              key={item.id}
              className="flex items-center justify-between rounded-lg border border-border px-3 py-2"
            >
              <div className="flex gap-3 text-sm">
                <span className="font-medium">{item.keyword}</span>
                <span className="text-muted-foreground">{item.category}</span>
              </div>
              <Button
                variant="ghost"
                size="icon-xs"
                onClick={() => setPendingDelete(item)}
                disabled={deleteCategory.isPending}
                aria-label={`刪除 ${item.keyword}`}
              >
                <Trash2 className="size-4 text-destructive" />
              </Button>
            </div>
          ))}
        </div>
      )}

      {/* Delete confirmation dialog */}
      <Dialog
        open={pendingDelete !== null}
        onOpenChange={(open) => {
          if (!open) setPendingDelete(null)
        }}
      >
        <DialogContent>
          <DialogHeader>
            <DialogTitle>刪除分類關鍵字</DialogTitle>
            <DialogDescription>
              確定要刪除「{pendingDelete?.keyword}」？刪除後可重新新增，不影響歷史交易分類。
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <DialogClose render={<Button variant="outline" />}>取消</DialogClose>
            <Button
              variant="destructive"
              disabled={deleteCategory.isPending}
              onClick={() => {
                if (pendingDelete) deleteCategory.mutate(pendingDelete.id)
                setPendingDelete(null)
              }}
            >
              確認刪除
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  )
}

// -- Settings Page --

/**
 * 設定頁面，整合銀行設定與分類關鍵字兩個管理區塊。
 */
function SettingsPage() {
  return (
    <div className="space-y-8">
      <h1 className="text-2xl font-bold">設定</h1>

      <div
        role="note"
        className="rounded-md border border-amber-500/40 bg-amber-500/10 px-3 py-2 text-sm text-amber-800 dark:text-amber-200"
      >
        銀行啟用 / 密碼 / API token 管理已遷移至{' '}
        <Link to="/setup/banks" className="font-medium underline">
          設定中心
        </Link>
        。本頁僅保留分類關鍵字編輯，後續 bills-management-and-insights
        change 落地時將整體遷出。
      </div>

      <section>
        <h2 className="mb-3 text-lg font-semibold">銀行設定（舊版）</h2>
        <BankConfigSection />
      </section>

      <section>
        <h2 className="mb-3 text-lg font-semibold">分類關鍵字</h2>
        <CategoryKeywordSection />
      </section>
    </div>
  )
}

export default SettingsPage
