## 緣由 (Why)

`gmail-ingestor` change 最初在 ingestion job hook 中隱含了 pipeline 觸發的概念，但實際的 pipeline 協調、排程觸發與付款提醒通知屬於獨立的關切面，不應與帳單抓取耦合在一起。隨著其他功能 change（parser、分類、Telegram 通知）陸續完成，需要一個明確的協調者把五個階段串成完整的端到端流程，並提供穩定的排程觸發與付款到期提醒機制。

## 變更內容 (What Changes)

- 新增 `run_pipeline()` 協調器，依序呼叫 ingest → decrypt → parse → classify → notify 五個階段，並匯集各階段摘要
- 新增各階段獨立容錯機制，確保單一階段的部分失敗不阻斷後續階段處理已成功的項目
- 新增 APScheduler 整合，提供可設定頻率的週期性 pipeline 觸發排程
- 新增付款提醒排程工作，於帳單到期前 3 天與 1 天查詢未付帳單並觸發 Telegram 通知
- 新增 CLI 入口與 API 端點，供手動觸發 pipeline 並回傳執行摘要

## 能力範圍 (Capabilities)

### 新增能力 (New Capabilities)
- `pipeline-orchestration`: 五階段 pipeline 協調器，含各階段摘要聚合、總耗時追蹤與獨立容錯行為
- `scheduler-jobs`: APScheduler 工作註冊與週期性 pipeline 觸發，排程設定可透過 Settings 調整
- `payment-reminders`: 付款到期提醒排程工作，查詢未付帳單並於到期前 3 天與 1 天觸發 Telegram 通知

### 修改能力 (Modified Capabilities)
(無 -- 沒有既有 capability 的 requirement 被修改)

## 影響範圍 (Impact)

- **後端模組**: 新增 `pipeline/`、`scheduler/` 模組
- **依賴關係**: 依賴所有其他 change（gmail-ingestor、parser-engine、keyword-classifier、telegram-bot、frontend-dashboard）
- **外部系統**: APScheduler 週期觸發、Telegram Bot API（付款提醒）
- **執行行為**: 建立可重跑、可手動觸發、可排程的端到端帳單處理流程
