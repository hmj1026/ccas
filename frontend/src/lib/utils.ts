import { clsx, type ClassValue } from "clsx"
import { twMerge } from "tailwind-merge"

/**
 * 合併 CSS class 名稱，自動處理 Tailwind 衝突。
 *
 * 結合 clsx（條件式 class）與 tailwind-merge（衝突解決）。
 *
 * @param inputs - 要合併的 class 名稱（支援條件式語法）
 * @returns 合併並去重後的 class 字串
 */
export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs))
}

// 共用整數千分位 formatter；`Intl.NumberFormat` 實例化成本不低，集中於 module
// scope 重用，避免每次 formatAmount/currencyFormatter 呼叫都重建。
const INTEGER_FORMATTER = new Intl.NumberFormat('en-US')

// 共用日期 formatter，理由同上：實例化成本集中於 module scope 重用。
// `DAY_FORMATTER` 處理完整日期（YYYY-MM-DD / ISO）；`MONTH_FORMATTER` 處理
// billing_month 這類「YYYY-MM」無日的值，避免被解析成 `Invalid Date`。
const DAY_FORMATTER = new Intl.DateTimeFormat('zh-TW', {
  year: 'numeric',
  month: '2-digit',
  day: '2-digit',
})
const MONTH_FORMATTER = new Intl.DateTimeFormat('zh-TW', {
  year: 'numeric',
  month: '2-digit',
})

/**
 * 將後端 ISO 日期字串本地化為 zh-TW 顯示格式。
 *
 * 支援兩種輸入：
 * - 完整日期（`YYYY-MM-DD` 或含時間的 ISO）→ `2026/03/15`
 * - billing_month 的 `YYYY-MM`（無日）→ `2026/03`，避免渲染成 `Invalid Date`
 *
 * 無法解析時回退原字串，確保畫面不出現 `Invalid Date`。
 *
 * @param iso - 後端回傳的日期字串
 * @returns 本地化後的日期字串
 */
export function formatDate(iso: string): string {
  if (!iso) return iso
  // `YYYY-MM`（billing_month）：無日，僅格式化年月。
  const monthOnly = /^(\d{4})-(\d{2})$/.exec(iso)
  if (monthOnly) {
    const [, year, month] = monthOnly
    const date = new Date(Number(year), Number(month) - 1, 1)
    return Number.isNaN(date.getTime()) ? iso : MONTH_FORMATTER.format(date)
  }
  const date = new Date(iso)
  return Number.isNaN(date.getTime()) ? iso : DAY_FORMATTER.format(date)
}

/**
 * 將數字金額格式化為帶幣別前綴的字串。
 * TWD 顯示 `$`，其他幣別顯示幣別代碼。
 *
 * @param amount - 金額數值
 * @param currency - 幣別代碼，預設 `"TWD"`
 * @returns 格式化字串，例如 `$1,234` 或 `USD 50`
 */
export function formatAmount(amount: number, currency = 'TWD'): string {
  const prefix = currency === 'TWD' ? '$' : `${currency} `
  return `${prefix}${INTEGER_FORMATTER.format(amount)}`
}

/**
 * Recharts Tooltip 等元件使用的金額 formatter：
 * 以 `$` 前綴顯示整數千分位。
 *
 * 接受 number / string / readonly array / undefined（Recharts 型別簽章）。
 */
export function currencyFormatter(
  v: number | string | readonly (number | string)[] | undefined,
): string {
  return `$${INTEGER_FORMATTER.format(Number(v))}`
}
