## Why

CTBC pipeline 各階段程式碼已完成，但端到端流程存在多個斷點：notify 階段無法收到新帳單 ID 導致通知永遠不發、banks.example.yaml 為空導致首次設定無法自動配置 CTBC、缺少預設分類關鍵字導致所有交易為「未分類」。

## What Changes

### Pipeline 修復
- Bill model 新增 `is_notified` 欄位 + Alembic migration
- 修改 `run_notify_job()` 改為查詢 `is_notified=False` 的帳單，發送後標記
- Orchestrator 不再需要傳遞 bill_ids（notify 階段自主查詢）

### 初始配置
- `banks.example.yaml` 填入 CTBC 預設配置
- `seed.py` 補充更多 CTBC 常見消費分類關鍵字

### 整合測試
- 端到端 pipeline 整合測試：mock Gmail + 真實 PDF → parse → classify → verify DB

## Capabilities

### Modified Capabilities
- `pipeline-orchestration`: notify 階段改為查詢未通知帳單
- `database-schema`: Bill 新增 `is_notified` 欄位

### New Capabilities
- `ctbc-bootstrap`: CTBC 初始配置（banks.yaml + 預設分類關鍵字）

## Impact

- **Database**: 新增 `is_notified` 欄位 (Boolean, default False)，需 Alembic migration
- **Notify behavior**: 從「被動接收 bill_ids」改為「主動查詢未通知帳單」
- **Breaking**: `run_notify_job()` 的 `bill_ids` 參數移除
