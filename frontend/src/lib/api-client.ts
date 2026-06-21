/**
 * API client -- 封裝 fetch，統一 Bearer Token 認證與錯誤處理。
 */

const API_BASE = import.meta.env.VITE_API_BASE ?? ''

/** 所有 JSON API 請求共用的標準 headers。 */
const JSON_HEADERS: HeadersInit = { 'Content-Type': 'application/json' }

/**
 * 從錯誤回應 body 萃取可讀的錯誤訊息。
 * 優先序：`message` 欄位 → FastAPI 422 `detail` 陣列（串接各項 msg）
 * → `detail` 字串 → HTTP 狀態碼。
 *
 * @param body - 解析後的回應 body（可能為 null）
 * @param status - HTTP 狀態碼，作為最後 fallback
 */
function extractErrorMessage(body: unknown, status: number): string {
  if (body && typeof body === 'object') {
    if ('message' in body) {
      const { message } = body as { message: unknown }
      if (typeof message === 'string' && message) return message
    }
    // TODO: 下版移除 detail fallback（後端已統一改用 message 信封；
    // 暫時保留以相容尚未升級的部署 / 快取的舊回應）。
    if ('detail' in body) {
      const { detail } = body as { detail: unknown }
      if (Array.isArray(detail)) {
        // Defensive: raw FastAPI validation errors are objects with a `msg`
        // field; join them so users never see "[object Object]".
        const joined = detail
          .map((item) =>
            item && typeof item === 'object' && 'msg' in item
              ? String((item as { msg: unknown }).msg)
              : String(item),
          )
          .join('; ')
        if (joined) return joined
      } else if (detail !== null && detail !== undefined) {
        return String(detail)
      }
    }
  }
  return `HTTP ${status}`
}

/**
 * 解析 fetch Response，非 2xx 時拋出帶訊息的 Error。
 * 優先從回應 body 的 `message` 或 `detail` 欄位取得錯誤訊息。
 *
 * @param response - 原始 fetch Response
 * @returns 解析後的 JSON 資料
 * @throws {Error} HTTP 狀態非 OK 時
 */
async function handleResponse<T>(response: Response): Promise<T> {
  if (!response.ok) {
    const body = await response.json().catch(() => null)
    throw new Error(extractErrorMessage(body, response.status))
  }
  if (response.status === 204) {
    return null as T
  }
  return response.json() as Promise<T>
}

/**
 * 發送 GET 請求，支援 query 參數。
 * undefined 與空字串的參數會自動略過。
 *
 * @param path - API 路徑（含前綴 `/api/...`）
 * @param params - 可選的 query 參數，值為 undefined 或空字串時略過
 * @returns 解析後的 JSON 回應
 */
export async function apiGet<T>(
  path: string,
  params?: Record<string, string | number | boolean | undefined>,
): Promise<T> {
  const url = new URL(`${API_BASE}${path}`, window.location.origin)
  if (params) {
    for (const [key, value] of Object.entries(params)) {
      if (value !== undefined && value !== '') {
        url.searchParams.set(key, String(value))
      }
    }
  }
  const response = await fetch(url.toString(), {
    headers: JSON_HEADERS,
    credentials: 'include',
  })
  return handleResponse<T>(response)
}

/**
 * 發送 POST 請求，body 序列化為 JSON。
 *
 * @param path - API 路徑
 * @param body - 請求 body
 * @returns 解析後的 JSON 回應
 */
export async function apiPost<T>(path: string, body: unknown): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, {
    method: 'POST',
    headers: JSON_HEADERS,
    body: JSON.stringify(body),
    credentials: 'include',
  })
  return handleResponse<T>(response)
}

/**
 * 發送 PUT 請求，body 序列化為 JSON。
 *
 * @param path - API 路徑
 * @param body - 請求 body（完整替換）
 * @returns 解析後的 JSON 回應
 */
export async function apiPut<T>(path: string, body: unknown): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, {
    method: 'PUT',
    headers: JSON_HEADERS,
    body: JSON.stringify(body),
    credentials: 'include',
  })
  return handleResponse<T>(response)
}

/**
 * 發送 PATCH 請求，body 序列化為 JSON。
 *
 * @param path - API 路徑
 * @param body - 請求 body（部分更新）
 * @returns 解析後的 JSON 回應
 */
export async function apiPatch<T>(path: string, body: unknown): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, {
    method: 'PATCH',
    headers: JSON_HEADERS,
    body: JSON.stringify(body),
    credentials: 'include',
  })
  return handleResponse<T>(response)
}

/**
 * 發送 DELETE 請求。
 *
 * @param path - API 路徑（含資源 ID）
 * @returns 解析後的 JSON 回應
 */
export async function apiDelete<T>(path: string): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, {
    method: 'DELETE',
    headers: JSON_HEADERS,
    credentials: 'include',
  })
  return handleResponse<T>(response)
}

/**
 * 發送 GET 請求並回傳原始 Blob，用於 CSV / PDF 下載。
 * 非 OK 時直接拋出 HTTP 狀態錯誤，不解析 body。
 *
 * @param path - API 路徑
 * @param params - 可選的 query 參數
 * @returns 回應的 Blob 資料
 * @throws {Error} HTTP 狀態非 OK 時
 */
export async function apiFetchBlob(
  path: string,
  params?: Record<string, string | number | boolean | undefined>,
): Promise<Blob> {
  const url = new URL(`${API_BASE}${path}`, window.location.origin)
  if (params) {
    for (const [key, value] of Object.entries(params)) {
      if (value !== undefined && value !== '') {
        url.searchParams.set(key, String(value))
      }
    }
  }
  const response = await fetch(url.toString(), {
    headers: JSON_HEADERS,
    credentials: 'include',
  })
  if (!response.ok) {
    throw new Error(`HTTP ${response.status}`)
  }
  return response.blob()
}
