# Pipeline progress throttle 修正方案

## 根因摘要

`_last_flush_at = 0.0` 被同時當作 timestamp 與未初始化 sentinel。當低 uptime 程序的 `time.monotonic()` 小於自訂 `throttle_seconds`，首筆 `stage_item_done` 會被誤判為節流中。

## 方案比較

### 方案 A：使用 `None` sentinel（採用）

將 `_last_flush_at` 定義為 `float | None`；只有非 `None` 才計算 elapsed。初始化與新階段 reset 使用 `None`。

- 優點：狀態語意明確、改動最小、涵蓋低 uptime 與所有 throttle 設定。
- 風險：需更新型別與單元測試。

### 方案 B：以 `time.monotonic() - throttle_seconds` 初始化

讓初始值在數學上保證首筆通過。

- 優點：判斷式變更少。
- 風險：仍以 timestamp 偽裝狀態；每次 reset 都依賴 clock 計算，語意較不直接。

### 方案 C：timestamp 加 boolean flag

另加 `_has_flushed` 控制是否套用節流。

- 優點：語意可表達。
- 風險：兩個狀態欄位可能不一致，超出此 bug 的最小修正範圍。

## 決策與驗證

採用方案 A。新增測試先以 monotonic 值 `1.0` 與 throttle `100.0` 驗證舊程式失敗，再驗證修正後首筆寫入；目標 unit、backend 全量、integration、E2E、scripts 與 frontend gate 均已通過。
