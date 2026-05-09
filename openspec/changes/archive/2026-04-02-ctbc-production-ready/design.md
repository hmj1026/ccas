## Context

Pipeline orchestrator 呼叫 `run_notify_job(session)` 時未傳 `bill_ids`，導致 notify 永遠回傳空 summary。根本原因：parse 階段建立的 Bill ID 沒有傳遞到 notify 階段。

## Goals / Non-Goals

**Goals:**
- notify 階段自主發現未通知帳單並發送通知
- CTBC 首次設定可一鍵完成
- 分類有實用的預設關鍵字

**Non-Goals:**
- 不改變其他四個階段的行為
- 不做通知重試機制
- 不做通知模板客製化

## Decisions

### D1: Bill 加 `is_notified` 欄位取代 bill_ids 傳遞

在 `Bill` model 新增 `is_notified: bool = False`。`run_notify_job()` 改為查詢 `is_notified=False` 的帳單。發送成功後標記 `is_notified=True`。

移除 `bill_ids` 參數，notify 階段完全自主。

**優點**：
- 支援 `--from notify` 單獨重跑
- 冪等（已通知的不會重發）
- 不需要跨階段傳遞資料

### D2: banks.example.yaml 提供 CTBC 預設值

將註解中的 CTBC 範例改為實際的 YAML 資料（非註解），讓 `cp banks.example.yaml banks.yaml` 後直接可用。

### D3: 預設分類關鍵字擴充

在 `seed.py` 和文件中提供更完整的 CTBC 常見消費分類關鍵字（統一超商、全聯、蝦皮、UBER EATS 等）。

## Risks / Trade-offs

| Risk | Mitigation |
|------|-----------|
| 既有 Bill 記錄沒有 is_notified | Migration 預設 True（假設舊帳單已處理） |
| notify 重跑會重發通知 | is_notified=True 後不會重發 |
