# Pipeline progress throttle 低 uptime 修正設計

## 問題

`DbProgressReporter` 以 `0.0` 同時表示「尚未 flush」與 monotonic timestamp。當程序 uptime 小於自訂節流窗口時，第一筆 `stage_item_done()` 會被錯誤抑制，GitHub Actions 因此偶發／持續出現 `await_count == 0`。

## 設計決策

將 `_last_flush_at` 改為 `float | None`。`None` 是明確的未初始化狀態；只有已有 timestamp 時才套用節流判斷。`__init__` 與 `stage_started` 都使用 `None` 重置，保留 monotonic clock 與既有 session／lock 行為。

## 測試策略

先新增一個將 `time.monotonic()` 固定在低值、並使用大於該值的 throttle window 的 regression test，確認現行實作失敗；再以最小 production change 使其通過。之後執行目標 unit、全 backend unit coverage、integration、E2E、scripts checks 及 frontend CI 對應命令。

## 非目標與風險

不調整節流時間、不改資料庫 schema、不改 reporter public API，也不改 stage_finished 的 retry 行為。class upstream impact 為 LOW，`stage_item_done` direct callers 為 MEDIUM；回歸測試涵蓋既有 unit／integration progress flows。
