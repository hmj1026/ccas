/**
 * Settings 頁面 -- 銀行設定與分類關鍵字管理。
 */
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Plus, Trash2 } from 'lucide-react'
import { useState } from 'react'
import { apiGet, apiPost, apiDelete } from '@/lib/api-client'
import type {
  ApiResponse,
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
      setMutationError(null)
      queryClient.invalidateQueries({ queryKey: ['settings', 'categories'] })
      setNewKeyword('')
      setNewCategory('')
    },
    onError: (err: Error) => setMutationError(err.message),
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
   * 任一欄位為空時顯示 inline 錯誤訊息，不送出請求。
   */
  function handleAdd() {
    if (!newKeyword.trim() || !newCategory.trim()) {
      setMutationError('請輸入關鍵字與分類名稱')
      return
    }
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
          onChange={(e) => {
            setNewKeyword(e.target.value)
            if (mutationError) setMutationError(null)
          }}
          className="h-8 flex-1 rounded-lg border border-input bg-background px-3 text-sm"
          aria-label="新增關鍵字"
        />
        <input
          type="text"
          placeholder="分類"
          value={newCategory}
          onChange={(e) => {
            setNewCategory(e.target.value)
            if (mutationError) setMutationError(null)
          }}
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
 * 設定頁面：分類關鍵字管理。
 *
 * 銀行啟用 / 密碼 / API token 已遷移至設定中心（/setup）；本頁僅保留分類關鍵字，
 * 待分類關鍵字遷移完成後整頁將重導至 /setup。
 */
function SettingsPage() {
  return (
    <div className="space-y-8">
      <h1 className="text-2xl font-bold">設定</h1>

      <section>
        <h2 className="mb-3 text-lg font-semibold">分類關鍵字</h2>
        <CategoryKeywordSection />
      </section>
    </div>
  )
}

export default SettingsPage
