/**
 * Transaction detail 頁面編輯狀態的 pure controller（無 React / DOM 依賴）。
 *
 * 從 ``transaction-detail.tsx`` 抽出 note / merchant_alias debounce、
 * category / tags 立即 commit、reset override 等狀態轉換邏輯，讓
 * ``useTransactionEdit`` hook 只負責把 controller 接上 React Query 與
 * ``useSyncExternalStore``，同時讓這些轉換能在無 DOM 環境下被單元測試涵蓋。
 */
import type {
  ApiResponse,
  TransactionDetailItem,
  TransactionUpdateRequest,
} from '@/lib/types'

export const NOTE_DEBOUNCE_MS = 500
export const ALIAS_DEBOUNCE_MS = 500
export const SAVED_RESET_MS = 2000

/** note / merchant_alias 自動儲存的狀態；category / tags 的立即 commit 不使用此欄位。 */
export type SaveStatus = 'idle' | 'saving' | 'saved' | 'error'

/** 計時器 handle 的型別（沿用 ``setTimeout`` 回傳型別，容許測試注入 fake clock）。 */
export type TimerHandle = ReturnType<typeof setTimeout>

/** 可注入的計時器介面，預設實作在呼叫當下才存取全域 ``setTimeout`` / ``clearTimeout``。 */
export interface EditScheduler {
  setTimeout(fn: () => void, ms: number): TimerHandle
  clearTimeout(handle: TimerHandle): void
}

const defaultScheduler: EditScheduler = {
  setTimeout: (fn, ms) => setTimeout(fn, ms),
  clearTimeout: (handle) => clearTimeout(handle),
}

export interface TransactionEditDeps {
  patch(
    body: TransactionUpdateRequest,
  ): Promise<ApiResponse<TransactionDetailItem>>
  reset(): Promise<ApiResponse<TransactionDetailItem>>
  setCache(resp: ApiResponse<TransactionDetailItem>): void
  scheduler?: EditScheduler
  debounceMs?: number
  savedResetMs?: number
}

export interface TransactionEditState {
  readonly noteDraft: string | null
  readonly aliasDraft: string | null
  readonly tagInput: string
  readonly saveStatus: SaveStatus
  readonly error: Error | null
  readonly isResetting: boolean
}

export interface TransactionEditController {
  getSnapshot(): TransactionEditState
  subscribe(listener: () => void): () => void
  /** 只儲存最新的 server detail，不觸發 notify——供 render 期間呼叫。 */
  syncServerDetail(detail: TransactionDetailItem | undefined): void
  noteValue(): string
  aliasValue(): string
  setNoteDraft(value: string): void
  flushNote(): void
  setAliasDraft(value: string): void
  flushAlias(): void
  setTagInput(value: string): void
  changeCategory(categoryId: number): void
  addTag(): void
  removeTag(tag: string): void
  resetOverride(): void
  dispose(): void
}

function toError(err: unknown): Error {
  return err instanceof Error ? err : new Error(String(err))
}

/**
 * 建立交易編輯 controller，管理 note / alias debounce、category / tags 立即
 * commit、reset override 等狀態轉換。所有狀態變更皆透過 ``subscribe`` 通知。
 */
export function createTransactionEditController(
  deps: TransactionEditDeps,
): TransactionEditController {
  const scheduler = deps.scheduler ?? defaultScheduler
  const debounceMs = deps.debounceMs ?? NOTE_DEBOUNCE_MS
  const savedResetMs = deps.savedResetMs ?? SAVED_RESET_MS

  let detail: TransactionDetailItem | undefined
  let state: TransactionEditState = {
    noteDraft: null,
    aliasDraft: null,
    tagInput: '',
    saveStatus: 'idle',
    error: null,
    isResetting: false,
  }
  const listeners = new Set<() => void>()

  let noteTimer: TimerHandle | null = null
  let aliasTimer: TimerHandle | null = null
  let savedResetTimer: TimerHandle | null = null

  function setState(patch: Partial<TransactionEditState>) {
    state = { ...state, ...patch }
    for (const listener of listeners) listener()
  }

  function clearNoteTimer() {
    if (noteTimer !== null) {
      scheduler.clearTimeout(noteTimer)
      noteTimer = null
    }
  }

  function clearAliasTimer() {
    if (aliasTimer !== null) {
      scheduler.clearTimeout(aliasTimer)
      aliasTimer = null
    }
  }

  function clearSavedResetTimer() {
    if (savedResetTimer !== null) {
      scheduler.clearTimeout(savedResetTimer)
      savedResetTimer = null
    }
  }

  function autoSave(body: TransactionUpdateRequest) {
    clearSavedResetTimer()
    setState({ saveStatus: 'saving', error: null })
    deps
      .patch(body)
      .then((resp) => {
        deps.setCache(resp)
        setState({ saveStatus: 'saved' })
        savedResetTimer = scheduler.setTimeout(() => {
          savedResetTimer = null
          setState({ saveStatus: 'idle' })
        }, savedResetMs)
      })
      .catch((err: unknown) => {
        setState({ saveStatus: 'error', error: toError(err) })
      })
  }

  function commit(body: TransactionUpdateRequest) {
    setState({ error: null })
    deps
      .patch(body)
      .then((resp) => {
        deps.setCache(resp)
      })
      .catch((err: unknown) => {
        setState({ error: toError(err) })
      })
  }

  return {
    getSnapshot() {
      return state
    },
    subscribe(listener) {
      listeners.add(listener)
      return () => listeners.delete(listener)
    },
    syncServerDetail(nextDetail) {
      detail = nextDetail
    },
    noteValue() {
      return state.noteDraft ?? detail?.note ?? ''
    },
    aliasValue() {
      return state.aliasDraft ?? detail?.merchant_alias ?? ''
    },
    setNoteDraft(value) {
      clearNoteTimer()
      setState({ noteDraft: value })
      if (value !== (detail?.note ?? '')) {
        noteTimer = scheduler.setTimeout(() => {
          noteTimer = null
          autoSave({ note: value })
        }, debounceMs)
      }
    },
    flushNote() {
      if (state.noteDraft !== null && state.noteDraft !== (detail?.note ?? '')) {
        clearNoteTimer()
        autoSave({ note: state.noteDraft })
      }
    },
    setAliasDraft(value) {
      clearAliasTimer()
      setState({ aliasDraft: value })
      if (value !== detail?.merchant_alias) {
        aliasTimer = scheduler.setTimeout(() => {
          aliasTimer = null
          autoSave({ merchant_alias: value })
        }, debounceMs)
      }
    },
    flushAlias() {
      if (state.aliasDraft !== null && state.aliasDraft !== detail?.merchant_alias) {
        clearAliasTimer()
        autoSave({ merchant_alias: state.aliasDraft })
      }
    },
    setTagInput(value) {
      setState({ tagInput: value })
    },
    changeCategory(categoryId) {
      commit({ category_id: categoryId })
    },
    addTag() {
      const trimmed = state.tagInput.trim()
      if (!trimmed || !detail) return
      if (detail.tags.includes(trimmed)) {
        setState({ tagInput: '' })
        return
      }
      commit({ tags: [...detail.tags, trimmed] })
      setState({ tagInput: '' })
    },
    removeTag(tag) {
      if (!detail) return
      commit({ tags: detail.tags.filter((t) => t !== tag) })
    },
    resetOverride() {
      setState({ isResetting: true, error: null })
      deps
        .reset()
        .then((resp) => {
          deps.setCache(resp)
        })
        .catch((err: unknown) => {
          setState({ error: toError(err) })
        })
        .finally(() => {
          setState({ isResetting: false })
        })
    },
    dispose() {
      clearNoteTimer()
      clearAliasTimer()
      clearSavedResetTimer()
    },
  }
}
