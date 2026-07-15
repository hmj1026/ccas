/**
 * route-imports 測試 -- 呼叫每個 dynamic import 工廠並等待 chunk 解析，
 * 確保每個工廠函式本體都被執行且對應頁面模組可載入。
 */
import { describe, expect, it } from 'vitest'
import * as routeImports from '@/lib/route-imports'

type ImportFactory = () => Promise<Record<string, unknown>>

const factories = Object.entries(routeImports) as ReadonlyArray<
  readonly [string, ImportFactory]
>

describe('route-imports', () => {
  it('exports only factory functions', () => {
    expect(factories.length).toBeGreaterThan(0)
    for (const [, factory] of factories) {
      expect(typeof factory).toBe('function')
    }
  })

  it.each(factories)('factory %s resolves to a module object', async (_name, factory) => {
    const mod = await factory()
    expect(mod).toBeTruthy()
    expect(typeof mod).toBe('object')
    expect(Object.keys(mod).length).toBeGreaterThan(0)
  })
})
