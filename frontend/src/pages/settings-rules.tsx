/**
 * Settings 子頁：個人分類規則（bills-management-and-insights §10）。
 *
 * 列出所有 user rules（priority DESC + id ASC），支援：
 * - 新增規則對話框（pattern + type + category + priority + 即時測試）
 * - inline 切換 enabled
 * - inline 編輯 priority（number input + debounced PUT）
 * - 刪除（含確認）
 * - regex 複雜度警示（nested quantifier 偵測）
 */
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { AlertTriangle, Plus, Trash2 } from 'lucide-react'
import { useMemo, useRef, useState } from 'react'
import { apiDelete, apiGet, apiPost, apiPut } from '@/lib/api-client'
import type {
  ApiResponse,
  CategoryKeywordItem,
  ClassificationRuleCreateRequest,
  ClassificationRuleItem,
  ClassificationRuleTestRequest,
  ClassificationRuleTestResponse,
  ClassificationRuleUpdateRequest,
  PatternType,
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
import {
  EmptyState,
  ErrorState,
  LoadingState,
} from '@/components/shared/states'

const PATTERN_TYPE_LABELS: Record<PatternType, string> = {
  keyword: '關鍵字 (keyword)',
  exact: '完全相符 (exact)',
  regex: '正規表達式 (regex)',
}

const PATTERN_TYPE_HELP: Record<PatternType, string> = {
  keyword: '不分大小寫的子字串比對；例：「星巴克」可命中「星巴克 #1234」',
  exact: '大小寫敏感的完全相等；適合精確商家名',
  regex: 'Python 風格 regex；含 100ms timeout fail-soft',
}

/**
 * 偵測 regex 中疑似 nested quantifier 的 ReDoS 風險 pattern。
 * 命中如 `(a+)+`、`(a*)*`、`(a+)*` 等 catastrophic backtracking 經典 case。
 */
function detectComplexRegex(pattern: string): boolean {
  // Match a quantifier (+/*/{n,m}) inside a group, followed by another quantifier outside.
  return /\([^)]*[+*][^)]*\)[+*]/.test(pattern)
}

function RuleDialog({
  onClose,
  categories,
  onCreated,
}: {
  readonly onClose: () => void
  readonly categories: readonly CategoryKeywordItem[]
  readonly onCreated: () => void
}) {
  const [pattern, setPattern] = useState('')
  const [patternType, setPatternType] = useState<PatternType>('keyword')
  const [categoryId, setCategoryId] = useState<number | ''>('')
  const [priority, setPriority] = useState<number>(10)
  const [sampleText, setSampleText] = useState('')
  const [testResult, setTestResult] =
    useState<ClassificationRuleTestResponse | null>(null)
  const [error, setError] = useState<string | null>(null)

  const complexRegexWarning =
    patternType === 'regex' && pattern !== '' && detectComplexRegex(pattern)

  const testMutation = useMutation({
    mutationFn: (body: ClassificationRuleTestRequest) =>
      apiPost<ApiResponse<ClassificationRuleTestResponse>>(
        '/api/rules/test',
        body,
      ),
    onSuccess: (resp) => setTestResult(resp.data),
    onError: (err: Error) => setError(err.message),
  })

  const createMutation = useMutation({
    mutationFn: (body: ClassificationRuleCreateRequest) =>
      apiPost<ApiResponse<ClassificationRuleItem>>('/api/rules', body),
    onSuccess: () => {
      onCreated()
      onClose()
    },
    onError: (err: Error) => setError(err.message),
  })

  const canSubmit = pattern.trim() !== '' && categoryId !== ''

  function handleTest() {
    if (pattern.trim() === '' || sampleText.trim() === '') return
    setError(null)
    testMutation.mutate({
      pattern,
      pattern_type: patternType,
      sample_text: sampleText,
    })
  }

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    if (!canSubmit) return
    setError(null)
    createMutation.mutate({
      pattern: pattern.trim(),
      pattern_type: patternType,
      category_id: Number(categoryId),
      priority,
      enabled: true,
    })
  }

  return (
    <Dialog open onOpenChange={(open) => !open && onClose()}>
      <DialogContent className="sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>新增規則</DialogTitle>
        </DialogHeader>
        <form onSubmit={handleSubmit} className="space-y-3">
        <label className="flex flex-col text-sm">
          <span className="text-muted-foreground">類型</span>
          <select
            className="rounded border border-input bg-background px-2 py-1"
            value={patternType}
            onChange={(e) => setPatternType(e.target.value as PatternType)}
            aria-label="pattern_type"
          >
            {(Object.keys(PATTERN_TYPE_LABELS) as PatternType[]).map((t) => (
              <option key={t} value={t}>
                {PATTERN_TYPE_LABELS[t]}
              </option>
            ))}
          </select>
          <span className="mt-1 text-xs text-muted-foreground">
            {PATTERN_TYPE_HELP[patternType]}
          </span>
        </label>

        <label className="flex flex-col text-sm">
          <span className="text-muted-foreground">Pattern</span>
          <input
            id="rule-pattern"
            type="text"
            className="rounded border border-input bg-background px-2 py-1"
            value={pattern}
            onChange={(e) => setPattern(e.target.value)}
            placeholder={
              patternType === 'regex' ? '^蝦皮商城.*' : '例：星巴克'
            }
            aria-label="pattern"
            aria-describedby="rule-error"
            aria-invalid={error !== null}
            required
          />
        </label>

        {complexRegexWarning && (
          <div
            className="flex items-start gap-2 rounded border border-amber-300 bg-amber-500/10 p-2 text-xs text-amber-900 dark:border-amber-500/40 dark:text-amber-200"
            role="alert"
          >
            <AlertTriangle className="mt-0.5 size-4 shrink-0" />
            <p>
              偵測到 nested quantifier（如 <code>(a+)+</code>），可能造成 ReDoS。
              系統有 100ms timeout 保護，但建議改寫為更明確的 pattern。
            </p>
          </div>
        )}

        <div className="grid grid-cols-2 gap-3">
          <label className="flex flex-col text-sm">
            <span className="text-muted-foreground">類別</span>
            <select
              className="rounded border border-input bg-background px-2 py-1"
              value={categoryId === '' ? '' : String(categoryId)}
              onChange={(e) =>
                setCategoryId(e.target.value === '' ? '' : Number(e.target.value))
              }
              aria-label="category"
              required
            >
              <option value="">— 請選擇 —</option>
              {categories.map((c) => (
                <option key={c.id} value={c.id}>
                  {c.category}（{c.keyword}）
                </option>
              ))}
            </select>
          </label>
          <label className="flex flex-col text-sm">
            <span className="text-muted-foreground">priority</span>
            <input
              type="number"
              className="rounded border border-input bg-background px-2 py-1"
              value={priority}
              onChange={(e) => setPriority(Number(e.target.value))}
              min={0}
              aria-label="priority"
            />
          </label>
        </div>

        <fieldset className="space-y-2 rounded border border-border p-2">
          <legend className="px-1 text-xs text-muted-foreground">測試規則</legend>
          <div className="flex gap-2">
            <input
              type="text"
              className="flex-1 rounded border border-input bg-background px-2 py-1 text-sm"
              value={sampleText}
              onChange={(e) => setSampleText(e.target.value)}
              placeholder="輸入要測試的 merchant 字串"
              aria-label="sample_text"
            />
            <Button
              type="button"
              variant="outline"
              size="sm"
              onClick={handleTest}
              disabled={
                pattern.trim() === '' ||
                sampleText.trim() === '' ||
                testMutation.isPending
              }
            >
              {testMutation.isPending ? '…' : '測試'}
            </Button>
          </div>
          {testResult !== null && (
            <p
              className={`text-xs ${
                testResult.matches ? 'text-green-700' : 'text-muted-foreground'
              }`}
              role="status"
            >
              {testResult.matches ? '✓ 命中' : '✗ 未命中'}
            </p>
          )}
        </fieldset>

        {/* 持續掛載的 live region：min-h 預留高度避免 layout shift。 */}
        <p
          id="rule-error"
          role="alert"
          className="min-h-4 text-xs text-destructive"
        >
          {error ?? ''}
        </p>

        <Button type="submit" disabled={!canSubmit || createMutation.isPending}>
          {createMutation.isPending ? '建立中…' : '建立規則'}
        </Button>
        </form>
      </DialogContent>
    </Dialog>
  )
}

function RuleRow({
  rule,
  onUpdate,
  onDelete,
  isPending,
}: {
  readonly rule: ClassificationRuleItem
  readonly onUpdate: (body: ClassificationRuleUpdateRequest) => void
  readonly onDelete: () => void
  readonly isPending: boolean
}) {
  const [priorityDraft, setPriorityDraft] = useState<string>(
    String(rule.priority),
  )
  // Re-sync local draft when the upstream rule.priority changes (e.g. after
  // server invalidate). This is the documented "adjust state on prop change"
  // pattern — set during render rather than in useEffect to avoid the lint
  // rule banning setState-in-effect.
  const [lastPriority, setLastPriority] = useState(rule.priority)
  if (rule.priority !== lastPriority) {
    setLastPriority(rule.priority)
    setPriorityDraft(String(rule.priority))
  }
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  function handlePriorityChange(v: string) {
    setPriorityDraft(v)
    if (debounceRef.current !== null) clearTimeout(debounceRef.current)
    debounceRef.current = setTimeout(() => {
      const n = Number.parseInt(v, 10)
      if (Number.isFinite(n) && n !== rule.priority) {
        onUpdate({ priority: n })
      }
    }, 500)
  }

  return (
    <tr
      className={
        rule.enabled
          ? ''
          : 'opacity-60 [&_td]:bg-muted/30'
      }
      data-testid={`rule-row-${rule.id}`}
    >
      <td className="px-2 py-1 font-mono text-xs">{rule.pattern}</td>
      <td className="px-2 py-1 text-xs">{rule.pattern_type}</td>
      <td className="px-2 py-1 text-xs">{rule.category_name}</td>
      <td className="px-2 py-1">
        <input
          type="number"
          className="w-16 rounded border border-input bg-background px-1 py-0.5 text-sm"
          value={priorityDraft}
          onChange={(e) => handlePriorityChange(e.target.value)}
          aria-label={`priority of ${rule.pattern}`}
          min={0}
          disabled={isPending}
        />
      </td>
      <td className="px-2 py-1">
        <input
          type="checkbox"
          checked={rule.enabled}
          disabled={isPending}
          onChange={(e) => onUpdate({ enabled: e.target.checked })}
          aria-label={`toggle ${rule.pattern}`}
        />
      </td>
      <td className="px-2 py-1">
        <Button
          type="button"
          variant="ghost"
          size="sm"
          onClick={onDelete}
          disabled={isPending}
          aria-label={`delete ${rule.pattern}`}
        >
          <Trash2 className="size-4 text-destructive" />
        </Button>
      </td>
    </tr>
  )
}

function SettingsRulesPage() {
  const queryClient = useQueryClient()
  const [dialogOpen, setDialogOpen] = useState(false)
  const [mutationError, setMutationError] = useState<string | null>(null)
  const [deleteTarget, setDeleteTarget] = useState<{
    id: number
    pattern: string
  } | null>(null)

  const rulesQuery = useQuery({
    queryKey: ['rules'],
    queryFn: () =>
      apiGet<ApiResponse<readonly ClassificationRuleItem[]>>('/api/rules'),
  })

  const categoriesQuery = useQuery({
    queryKey: ['settings', 'categories'],
    queryFn: () =>
      apiGet<ApiResponse<readonly CategoryKeywordItem[]>>(
        '/api/settings/categories',
      ),
  })

  const updateMutation = useMutation({
    mutationFn: ({
      id,
      body,
    }: {
      id: number
      body: ClassificationRuleUpdateRequest
    }) =>
      apiPut<ApiResponse<ClassificationRuleItem>>(`/api/rules/${id}`, body),
    onSuccess: () => {
      setMutationError(null)
      queryClient.invalidateQueries({ queryKey: ['rules'] })
    },
    onError: (err: Error) => setMutationError(err.message),
  })

  const deleteMutation = useMutation({
    mutationFn: (id: number) =>
      apiDelete<ApiResponse<{ deleted_id: number }>>(`/api/rules/${id}`),
    onSuccess: () => {
      setMutationError(null)
      queryClient.invalidateQueries({ queryKey: ['rules'] })
    },
    onError: (err: Error) => setMutationError(err.message),
  })

  const uniqueCategories = useMemo(() => {
    const list = categoriesQuery.data?.data ?? []
    return Array.from(new Map(list.map((c) => [c.category, c])).values())
  }, [categoriesQuery.data])

  if (rulesQuery.isLoading) return <LoadingState />
  if (rulesQuery.error)
    return <ErrorState message={rulesQuery.error.message} />

  const rules = rulesQuery.data?.data ?? []

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold">分類規則</h1>
          <p className="text-sm text-muted-foreground">
            自訂規則優先序高於內建 engine；priority 大者勝。
          </p>
        </div>
        <Button onClick={() => setDialogOpen(true)} size="sm">
          <Plus className="size-4" data-icon="inline-start" />
          新增規則
        </Button>
      </div>

      {mutationError ? (
        <p
          role="alert"
          className="rounded-md border border-destructive/40 bg-destructive/10 px-3 py-2 text-sm text-destructive"
        >
          {mutationError}
        </p>
      ) : null}

      {rules.length === 0 ? (
        <EmptyState message="尚未建立規則。點右上「新增規則」開始。" />
      ) : (
        <div className="overflow-x-auto rounded-lg border border-border">
          <table className="w-full text-sm">
            <thead>
              <tr className="bg-muted/50 text-left">
                <th className="px-2 py-2">Pattern</th>
                <th className="px-2 py-2">類型</th>
                <th className="px-2 py-2">類別</th>
                <th className="px-2 py-2">Priority</th>
                <th className="px-2 py-2">啟用</th>
                <th className="px-2 py-2 sr-only">操作</th>
              </tr>
            </thead>
            <tbody>
              {rules.map((rule) => (
                <RuleRow
                  key={rule.id}
                  rule={rule}
                  isPending={updateMutation.isPending || deleteMutation.isPending}
                  onUpdate={(body) =>
                    updateMutation.mutate({ id: rule.id, body })
                  }
                  onDelete={() =>
                    setDeleteTarget({ id: rule.id, pattern: rule.pattern })
                  }
                />
              ))}
            </tbody>
          </table>
        </div>
      )}

      {dialogOpen && (
        <RuleDialog
          onClose={() => setDialogOpen(false)}
          categories={uniqueCategories}
          onCreated={() => queryClient.invalidateQueries({ queryKey: ['rules'] })}
        />
      )}

      {/* Delete confirmation dialog */}
      <Dialog
        open={deleteTarget !== null}
        onOpenChange={(open) => {
          if (!open) setDeleteTarget(null)
        }}
      >
        <DialogContent>
          <DialogHeader>
            <DialogTitle>刪除規則</DialogTitle>
            <DialogDescription>
              確定要刪除規則「{deleteTarget?.pattern}」？此動作無法復原。
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <DialogClose render={<Button variant="outline" />}>取消</DialogClose>
            <Button
              variant="destructive"
              disabled={deleteMutation.isPending}
              onClick={() => {
                if (deleteTarget) deleteMutation.mutate(deleteTarget.id)
                setDeleteTarget(null)
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

export default SettingsRulesPage
