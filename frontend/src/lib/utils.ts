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
  return `${prefix}${amount.toLocaleString()}`
}
