# CCAS Frontend -- 信用卡帳單儀表板

CCAS (Credit Card Automation System) 的前端儀表板，用於瀏覽信用卡帳單、交易明細、消費分析與帳單管理。

完整專案說明請參考根目錄 [README.md](../README.md)。

## 技術棧

| 項目 | 技術 |
|------|------|
| 框架 | React 19, TypeScript |
| 建置工具 | Vite |
| 樣式 | Tailwind CSS, shadcn/ui |
| 路由 | React Router v7 |
| 資料獲取 | TanStack Query v5 |
| 圖表 | Recharts |
| 測試 | Vitest |

## 開發指令

<!-- AUTO-GENERATED from frontend/package.json scripts -->
| 指令 | 說明 |
|------|------|
| `pnpm dev` | 啟動開發伺服器 (port 5173, HMR) |
| `pnpm build` | TypeScript 型別檢查 + 正式建置 |
| `pnpm lint` | ESLint 檢查 |
| `pnpm preview` | 預覽正式建置結果 |
| `pnpm test` | 執行 Vitest 測試（單次） |
| `pnpm test:watch` | 執行 Vitest 測試（監視模式） |
<!-- AUTO-GENERATED END -->

## 環境變數

前端環境變數須使用 `VITE_` 前綴（由根目錄 `.env` 提供）：

| 變數 | 說明 | 預設值 |
|------|------|--------|
| `VITE_API_BASE` | 後端 API base URL（build-time 注入）| — |
| `VITE_API_PROXY_TARGET` | Vite dev server `/api` proxy 目標（僅 dev）| `http://127.0.0.1:8000` |

> Dev 模式不需設定 `VITE_API_BASE`：`vite.config.ts` 會把 `/api` 請求透過 proxy 轉送到 `VITE_API_PROXY_TARGET`。僅在 production build 或連接非預設後端時，才需要設定 `VITE_API_BASE`。

環境設定範本請參考根目錄 [`.env.example`](../.env.example)。
