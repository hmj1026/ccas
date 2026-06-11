/**
 * api-client 錯誤訊息萃取測試 -- 驗證 handleResponse 對各種錯誤 body 的處理。
 */
import { afterEach, describe, expect, it, vi } from 'vitest'
import { apiGet } from '@/lib/api-client'

function mockFetchResponse(status: number, body: unknown) {
  vi.stubGlobal(
    'fetch',
    vi.fn().mockResolvedValue(
      new Response(JSON.stringify(body), {
        status,
        headers: { 'Content-Type': 'application/json' },
      }),
    ),
  )
}

describe('apiGet error handling', () => {
  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('uses envelope message when present', async () => {
    mockFetchResponse(400, { success: false, message: '參數錯誤', data: null })
    await expect(apiGet('/api/test')).rejects.toThrow('參數錯誤')
  })

  it('joins msg fields from a raw FastAPI 422 detail array', async () => {
    mockFetchResponse(422, {
      detail: [
        { loc: ['query', 'month'], msg: 'Field required', type: 'missing' },
        { loc: ['query', 'year'], msg: 'Input should be a valid integer', type: 'int_parsing' },
      ],
    })
    await expect(apiGet('/api/test')).rejects.toThrow(
      'Field required; Input should be a valid integer',
    )
  })

  it('does not produce [object Object] for detail arrays', async () => {
    mockFetchResponse(422, {
      detail: [{ loc: ['query', 'month'], msg: 'Field required', type: 'missing' }],
    })
    const error = await apiGet('/api/test').catch((e: unknown) => e)
    expect(error).toBeInstanceOf(Error)
    expect((error as Error).message).not.toContain('[object Object]')
  })

  it('uses string detail when message is absent', async () => {
    mockFetchResponse(404, { detail: 'Not Found' })
    await expect(apiGet('/api/test')).rejects.toThrow('Not Found')
  })

  it('falls back to HTTP status when body is unparseable', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(new Response('not json', { status: 502 })),
    )
    await expect(apiGet('/api/test')).rejects.toThrow('HTTP 502')
  })

  it('falls back to HTTP status when detail array is empty', async () => {
    mockFetchResponse(422, { detail: [] })
    await expect(apiGet('/api/test')).rejects.toThrow('HTTP 422')
  })
})
