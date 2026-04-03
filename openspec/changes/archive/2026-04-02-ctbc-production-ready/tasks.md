## 1. Database Schema

- [x] 1.1 Bill model 新增 `is_notified: bool = False` 欄位
- [x] 1.2 建立 Alembic migration（既有記錄 default True）

## 2. Notify 階段修復

- [x] 2.1 修改 `run_notify_job()` 改為查詢 `is_notified=False`
- [x] 2.2 發送成功後標記 `is_notified=True`
- [x] 2.3 移除 `bill_ids` 參數
- [x] 2.4 更新 orchestrator `_run_stage` 的 notify 呼叫（已正確，無需改）
- [x] 2.5 更新 e2e tests 移除 bill_ids 參數

## 3. 初始配置

- [x] 3.1 更新 `banks.example.yaml` 填入 CTBC 預設配置
- [x] 3.2 擴充 `seed.py` 分類關鍵字（超商、餐飲、交通、串流、百貨等 55 組）

## 4. 整合測試

- [x] 4.1 既有 e2e tests 已涵蓋 notify 成功/失敗場景（7 tests pass）
