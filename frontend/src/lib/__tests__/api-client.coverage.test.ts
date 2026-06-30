/**
 * api-client 補充覆蓋測試 -- 補齊既有 api-client.test.ts 未覆蓋的分支：
 * query 參數組裝、各 HTTP 動詞 (POST/PUT/PATCH/DELETE)、204 No Content、
 * 以及 apiFetchBlob 的成功 / 非 OK 路徑。
 *
 * 與 api-client.test.ts 互補，不重複既有的錯誤訊息萃取案例。
 */
import { afterEach, describe, expect, it, vi } from 'vitest'
import {
  apiDelete,
  apiFetchBlob,
  apiGet,
  apiPatch,
  apiPost,
  apiPut,
} from '@/lib/api-client'

type FetchArgs = readonly [string, RequestInit?]

/** 以指定 Response stub 全域 fetch，回傳 mock 以便檢視呼叫參數。 */
function stubFetch(response: Response) {
  const mock = vi.fn().mockResolvedValue(response)
  vi.stubGlobal('fetch', mock)
  return mock
}

/** 建立帶 JSON body 的 Response。 */
function jsonResponse(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  })
}

/** 取出 fetch 第一次呼叫的參數（url 與 init）。 */
function firstCall(mock: ReturnType<typeof vi.fn>): FetchArgs {
  return mock.mock.calls[0] as unknown as FetchArgs
}

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('apiGet query params', () => {
  it('appends defined params and skips undefined / empty string', async () => {
    const mock = stubFetch(jsonResponse(200, { ok: true }))

    await apiGet('/api/items', {
      keep: 'yes',
      num: 7,
      flag: false,
      skipUndef: undefined,
      skipEmpty: '',
    })

    const url = firstCall(mock)[0]
    expect(url).toContain('keep=yes')
    expect(url).toContain('num=7')
    expect(url).toContain('flag=false')
    expect(url).not.toContain('skipUndef')
    expect(url).not.toContain('skipEmpty')
  })

  it('sends GET headers and credentials', async () => {
    const mock = stubFetch(jsonResponse(200, { value: 42 }))

    await expect(apiGet<{ value: number }>('/api/x')).resolves.toEqual({
      value: 42,
    })

    const init = firstCall(mock)[1]
    expect(init?.credentials).toBe('include')
    expect(init?.headers).toEqual({ 'Content-Type': 'application/json' })
  })

  it('returns null on 204 No Content', async () => {
    stubFetch(new Response(null, { status: 204 }))
    await expect(apiGet('/api/x')).resolves.toBeNull()
  })
})

describe('mutating verbs', () => {
  it('apiPost sends POST with JSON body, headers and credentials', async () => {
    const mock = stubFetch(jsonResponse(201, { id: 1 }))

    await expect(apiPost<{ id: number }>('/api/things', { name: 'a' })).resolves.toEqual(
      { id: 1 },
    )

    const [url, init] = firstCall(mock)
    expect(url).toBe('/api/things')
    expect(init?.method).toBe('POST')
    expect(init?.body).toBe(JSON.stringify({ name: 'a' }))
    expect(init?.credentials).toBe('include')
    expect(init?.headers).toEqual({ 'Content-Type': 'application/json' })
  })

  it('apiPut sends PUT with JSON body', async () => {
    const mock = stubFetch(jsonResponse(200, { updated: true }))

    await expect(apiPut('/api/things/1', { name: 'b' })).resolves.toEqual({
      updated: true,
    })

    const init = firstCall(mock)[1]
    expect(init?.method).toBe('PUT')
    expect(init?.body).toBe(JSON.stringify({ name: 'b' }))
  })

  it('apiPatch sends PATCH with JSON body', async () => {
    const mock = stubFetch(jsonResponse(200, { patched: true }))

    await expect(apiPatch('/api/things/1', { name: 'c' })).resolves.toEqual({
      patched: true,
    })

    const init = firstCall(mock)[1]
    expect(init?.method).toBe('PATCH')
    expect(init?.body).toBe(JSON.stringify({ name: 'c' }))
  })

  it('apiDelete sends DELETE and returns parsed JSON', async () => {
    const mock = stubFetch(jsonResponse(200, { deleted: true }))

    await expect(apiDelete('/api/things/1')).resolves.toEqual({ deleted: true })
    expect(firstCall(mock)[1]?.method).toBe('DELETE')
  })

  it('apiDelete returns null on 204', async () => {
    stubFetch(new Response(null, { status: 204 }))
    await expect(apiDelete('/api/things/1')).resolves.toBeNull()
  })
})

describe('apiFetchBlob', () => {
  it('returns a Blob and appends defined params', async () => {
    const mock = stubFetch(new Response(new Blob(['csv-data']), { status: 200 }))

    const blob = await apiFetchBlob('/api/export', {
      month: '2026-06',
      skip: undefined,
    })

    expect(blob).toBeInstanceOf(Blob)
    const url = firstCall(mock)[0]
    expect(url).toContain('month=2026-06')
    expect(url).not.toContain('skip')
  })

  it('throws HTTP status on a non-ok response', async () => {
    stubFetch(new Response(null, { status: 500 }))
    await expect(apiFetchBlob('/api/export')).rejects.toThrow('HTTP 500')
  })
})
