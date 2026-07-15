/**
 * transaction-edit controller 純邏輯測試（無 DOM）：draft debounce、blur flush、
 * category/tag commit、失敗處理、cache 寫入、reset override。
 *
 * 使用手動 fake clock（``makeClock``）取代 ``vi.useFakeTimers``，因為
 * controller 的 scheduler 是可注入介面而非全域 timer。
 */
import { describe, expect, it, vi } from 'vitest'
import {
  createTransactionEditController,
  NOTE_DEBOUNCE_MS,
  SAVED_RESET_MS,
  type EditScheduler,
  type TimerHandle,
  type TransactionEditDeps,
} from '@/lib/transaction-edit'
import type {
  ApiResponse,
  TransactionDetailItem,
} from '@/lib/types'

// -- Fake clock -------------------------------------------------------------

function makeClock() {
  let now = 0
  let nextId = 1
  const timers = new Map<number, { time: number; fn: () => void }>()

  const scheduler: EditScheduler = {
    setTimeout(fn, ms) {
      const id = nextId++
      timers.set(id, { time: now + ms, fn })
      return id as unknown as TimerHandle
    },
    clearTimeout(handle) {
      timers.delete(handle as unknown as number)
    },
  }

  function tick(ms: number) {
    now += ms
    let firedSomething = true
    while (firedSomething) {
      firedSomething = false
      const due = Array.from(timers.entries())
        .filter(([, t]) => t.time <= now)
        .sort((a, b) => a[1].time - b[1].time)
      for (const [id, t] of due) {
        if (!timers.has(id)) continue
        timers.delete(id)
        t.fn()
        firedSomething = true
      }
    }
  }

  return { scheduler, tick }
}

/** 讓已解析的 promise 有機會跑完 ``.then``/``.catch`` 鏈。 */
async function flush() {
  await Promise.resolve()
  await Promise.resolve()
}

// -- Fixtures -----------------------------------------------------------

const BASE_DETAIL: TransactionDetailItem = {
  id: 42,
  bill_id: 7,
  trans_date: '2026-03-15',
  posting_date: null,
  merchant: 'Starbucks',
  amount: 150,
  currency: 'TWD',
  original_amount: null,
  card_last4: '1234',
  category: '餐飲',
  bank_code: 'CTBC',
  billing_month: '2026-03',
  installment_current: null,
  installment_total: null,
  note: null,
  manual_category_override: false,
  tags: [],
  merchant_alias: '',
  updated_at: '2026-03-16T10:00:00',
}

function okResponse(
  data: TransactionDetailItem,
): ApiResponse<TransactionDetailItem> {
  return { success: true, data, message: '' }
}

interface Harness {
  clock: ReturnType<typeof makeClock>
  patch: ReturnType<typeof vi.fn>
  reset: ReturnType<typeof vi.fn>
  setCache: ReturnType<typeof vi.fn>
  controller: ReturnType<typeof createTransactionEditController>
}

function makeHarness(overrides: Partial<TransactionEditDeps> = {}): Harness {
  const clock = makeClock()
  const deps: TransactionEditDeps = {
    patch: vi.fn().mockResolvedValue(okResponse(BASE_DETAIL)),
    reset: vi.fn().mockResolvedValue(okResponse(BASE_DETAIL)),
    setCache: vi.fn(),
    scheduler: clock.scheduler,
    ...overrides,
  }
  const controller = createTransactionEditController(deps)
  controller.syncServerDetail(BASE_DETAIL)
  return {
    clock,
    patch: deps.patch as ReturnType<typeof vi.fn>,
    reset: deps.reset as ReturnType<typeof vi.fn>,
    setCache: deps.setCache as ReturnType<typeof vi.fn>,
    controller,
  }
}

// -- Draft transitions + noteValue fallback ----------------------------

describe('draft transitions', () => {
  it('falls back to server note/alias before any user edit', () => {
    const { controller } = makeHarness()
    expect(controller.noteValue()).toBe('')
    expect(controller.aliasValue()).toBe('')

    controller.syncServerDetail({ ...BASE_DETAIL, note: '既有備註' })
    expect(controller.noteValue()).toBe('既有備註')
  })

  it('reflects the latest draft once the user has typed', () => {
    const { controller } = makeHarness()
    controller.setNoteDraft('草稿')
    expect(controller.noteValue()).toBe('草稿')
    controller.setAliasDraft('別名草稿')
    expect(controller.aliasValue()).toBe('別名草稿')
  })
})

// -- Debounce -------------------------------------------------------------

describe('note debounce', () => {
  it('collapses rapid setNoteDraft calls into a single PATCH after the debounce window', async () => {
    const { controller, clock, patch } = makeHarness()
    controller.setNoteDraft('a')
    controller.setNoteDraft('ab')
    controller.setNoteDraft('abc')

    expect(patch).not.toHaveBeenCalled()
    clock.tick(NOTE_DEBOUNCE_MS)
    await flush()

    expect(patch).toHaveBeenCalledTimes(1)
    expect(patch).toHaveBeenCalledWith({ note: 'abc' })
  })

  it('does not schedule a save when the draft equals the server value', () => {
    const { controller, clock, patch } = makeHarness()
    controller.setNoteDraft('')
    clock.tick(NOTE_DEBOUNCE_MS)
    expect(patch).not.toHaveBeenCalled()
  })
})

// -- Blur flush -------------------------------------------------------------

describe('flushNote', () => {
  it('saves immediately on flush and does not double-fire when the debounce timer later elapses', async () => {
    const { controller, clock, patch } = makeHarness()
    controller.setNoteDraft('立即送出')
    controller.flushNote()
    await flush()

    expect(patch).toHaveBeenCalledTimes(1)
    expect(patch).toHaveBeenCalledWith({ note: '立即送出' })

    clock.tick(NOTE_DEBOUNCE_MS)
    await flush()
    expect(patch).toHaveBeenCalledTimes(1)
  })

  it('is a no-op when there is no draft or the draft matches the server value', () => {
    const { controller, patch } = makeHarness()
    controller.flushNote()
    expect(patch).not.toHaveBeenCalled()

    controller.setNoteDraft('')
    controller.flushNote()
    expect(patch).not.toHaveBeenCalled()
  })
})

// -- Commit payloads --------------------------------------------------------

describe('commit payloads', () => {
  it('changeCategory commits category_id', () => {
    const { controller, patch } = makeHarness()
    controller.changeCategory(2)
    expect(patch).toHaveBeenCalledWith({ category_id: 2 })
  })

  it('addTag trims and normalizes before committing', () => {
    const { controller, patch } = makeHarness()
    controller.setTagInput('  業務  ')
    controller.addTag()
    expect(patch).toHaveBeenCalledWith({ tags: ['業務'] })
    expect(controller.getSnapshot().tagInput).toBe('')
  })

  it('rejects a duplicate tag without calling patch, clearing the input', () => {
    const { controller, patch } = makeHarness()
    controller.syncServerDetail({ ...BASE_DETAIL, tags: ['業務'] })
    controller.setTagInput('業務')
    controller.addTag()
    expect(patch).not.toHaveBeenCalled()
    expect(controller.getSnapshot().tagInput).toBe('')
  })

  it('rejects an empty/whitespace tag without calling patch', () => {
    const { controller, patch } = makeHarness()
    controller.setTagInput('   ')
    controller.addTag()
    expect(patch).not.toHaveBeenCalled()
  })

  it('removeTag commits the filtered tag list', () => {
    const { controller, patch } = makeHarness()
    controller.syncServerDetail({ ...BASE_DETAIL, tags: ['業務', '出差'] })
    controller.removeTag('業務')
    expect(patch).toHaveBeenCalledWith({ tags: ['出差'] })
  })
})

// -- Failure handling ---------------------------------------------------

describe('auto-save failure', () => {
  it('sets error and does not leave saveStatus as saving; does not call setCache', async () => {
    const err = new Error('網路中斷')
    const { controller, clock, patch, setCache } = makeHarness({
      patch: vi.fn().mockRejectedValue(err) as unknown as TransactionEditDeps['patch'],
    })
    controller.setNoteDraft('失敗備註')
    clock.tick(NOTE_DEBOUNCE_MS)
    await flush()

    const snapshot = controller.getSnapshot()
    expect(snapshot.saveStatus).not.toBe('saving')
    expect(snapshot.error).toBeInstanceOf(Error)
    expect(snapshot.error?.message).toBe('網路中斷')
    expect(setCache).not.toHaveBeenCalled()
    void patch
  })
})

// -- Cache writes on success ----------------------------------------------

describe('cache writes', () => {
  it('calls setCache with the resolved response on successful auto-save', async () => {
    const resp = okResponse({ ...BASE_DETAIL, note: '已儲存' })
    const { controller, clock, setCache } = makeHarness({
      patch: vi.fn().mockResolvedValue(resp) as unknown as TransactionEditDeps['patch'],
    })
    controller.setNoteDraft('已儲存')
    clock.tick(NOTE_DEBOUNCE_MS)
    await flush()

    expect(setCache).toHaveBeenCalledWith(resp)
    expect(controller.getSnapshot().saveStatus).toBe('saved')

    clock.tick(SAVED_RESET_MS)
    expect(controller.getSnapshot().saveStatus).toBe('idle')
  })
})

// -- Reset override -----------------------------------------------------

describe('resetOverride', () => {
  it('preserves note/tags/alias metadata and calls setCache with the reset response', async () => {
    const resp = okResponse({
      ...BASE_DETAIL,
      note: '保留備註',
      tags: ['保留標籤'],
      merchant_alias: '保留別名',
      manual_category_override: false,
    })
    const { controller, reset, setCache } = makeHarness({
      reset: vi.fn().mockResolvedValue(resp) as unknown as TransactionEditDeps['reset'],
    })

    controller.resetOverride()
    expect(controller.getSnapshot().isResetting).toBe(true)
    await flush()

    expect(reset).toHaveBeenCalledTimes(1)
    expect(setCache).toHaveBeenCalledWith(resp)
    expect(setCache.mock.calls[0][0].data.manual_category_override).toBe(false)
    expect(setCache.mock.calls[0][0].data.note).toBe('保留備註')
    expect(setCache.mock.calls[0][0].data.tags).toEqual(['保留標籤'])
    expect(setCache.mock.calls[0][0].data.merchant_alias).toBe('保留別名')
    expect(controller.getSnapshot().isResetting).toBe(false)
  })
})
