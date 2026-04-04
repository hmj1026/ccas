## Context

Codex 對抗性審查揭露 5 個流水線可靠性缺陷，涵蓋 Docker 部署（worker 缺失、URL 不可達）與資料完整性（failed 附件永久跳過、Gmail 分頁遺漏、巢狀 MIME 遺漏）。所有問題均已在程式碼層級驗證。

受影響模組：
- `docker-compose.yaml` — 服務定義
- `backend/src/ccas/config.py` — 設定模型
- `backend/src/ccas/scheduler/jobs.py` — 排程觸發
- `backend/src/ccas/ingestor/job.py` — 附件 staging dedupe
- `backend/src/ccas/ingestor/gmail_client.py` — Gmail 搜尋與附件擷取

## Goals / Non-Goals

**Goals:**
- Docker 部署下 pipeline 佇列任務能被正確消費（RQ worker）
- Scheduler 在 Docker 內能正確路由至 backend API
- 暫時性下載失敗的附件在下次執行時自動重試
- Gmail 搜尋能取回所有分頁結果
- 巢狀 MIME 結構中的 PDF 附件能被正確擷取

**Non-Goals:**
- 不重構 pipeline 架構（維持 RQ + APScheduler 設計）
- 不新增 retry count / backoff 機制於 staging 層（留待後續迭代）
- 不處理 Gmail OAuth token refresh 問題（不在審查範圍）
- 不修改前端或 API 介面

## Decisions

### D1: 新增 Docker worker 服務 vs. 改為同步執行

**選擇：新增 worker 服務**

理由：現有程式碼（`worker.py`、retry handler、`on_failure_handler`）完全圍繞 RQ 設計，`scheduler-jobs` spec 明確要求 RQ worker 獨立 process。改為同步會需要重寫 retry 邏輯且阻塞 API 30+ 分鐘。新增一個 docker-compose service 是最小修改。

### D2: Scheduler URL 分離 vs. 修改 api_host 預設值

**選擇：新增獨立設定 `scheduler_api_base_url`**

理由：`api_host` 同時用於 uvicorn binding（必須是 `0.0.0.0`）和 scheduler HTTP client。這是兩個不同用途，應分離。新設定為空時 fallback 到原行為，保持本地開發相容。

### D3: Failed 附件重試策略 — 自動重試 vs. retry count

**選擇：簡單自動重試（status != "failed" 才 skip）**

理由：最小修改原則。永久性失敗（如附件已刪除）會再次失敗並維持 `failed` 狀態，不會膨脹。若未來需要限制重試次數，可在 `StagedAttachment` 加欄位，但目前不需要 schema migration。

### D4: Gmail 分頁安全限制

**選擇：_MAX_PAGES = 10（約 1000 封郵件上限）**

理由：正常使用場景每月每銀行 1-2 封帳單郵件，不會觸及上限。但首次 backfill 或寬泛 filter 可能匹配大量郵件，需要安全閥防止 API quota 耗盡。超過時記錄 warning log。

### D5: MIME 遞迴深度限制

**選擇：max depth = 10**

理由：Gmail 本身限制 MIME 巢狀深度，10 層已遠超實際需求。純防禦性措施。

## Risks / Trade-offs

| 風險 | 緩解 |
|------|------|
| Failed 附件若為永久性錯誤，每次 run 都會重試一次 | 重試後仍失敗會維持 `failed` 狀態；日誌可追蹤；未來可加 retry_count 欄位 |
| 首次啟用分頁後可能拉回大量歷史郵件 | `_MAX_PAGES` 安全限制 + 既有 dedupe 防重複 staging |
| Worker 服務增加 Docker 資源消耗 | Worker 閒置時幾乎無 CPU 使用；共用 backend image 不增加 build 時間 |
| `scheduler_api_base_url` 空值 fallback 到 `0.0.0.0` 本地可行但語義不佳 | 本地開發通常直接 `python -m ccas.scheduler`，不走 Docker；Docker 下必設此值 |
