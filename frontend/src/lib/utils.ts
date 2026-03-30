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
