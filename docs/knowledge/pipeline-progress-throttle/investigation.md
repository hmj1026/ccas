# Pipeline progress throttle CI 失敗調查

## 調查狀態

- Phase 1 問題釐清：完成
- Phase 2 證據蒐集：完成
- Phase 3 根因分析：完成
- Phase 4 修正方案：完成
- Phase 5 知識文件化：完成

## Phase 1：問題定義

### 預期行為

`DbProgressReporter.stage_item_done()` 的第一筆進度回報應立即寫入資料庫；同一 reporter 在節流窗口內的後續回報才應被抑制。`stage_started()` 也應重置節流窗口，讓新階段的第一筆回報立即寫入。

### 實際行為

GitHub Actions 的 backend unit test 在完整 suite 中失敗：

```text
FAILED tests/unit/pipeline/test_progress.py::TestStageItemDone::test_throttle_suppresses_rapid_calls
AssertionError: assert 0 == 1
```

失敗時 coverage 仍為 89.47%–89.49%，高於 80% 門檻；不是 coverage 不足。

### 影響範圍

目前失敗集中在 `Backend Tests → Run unit tests with coverage`。同一 CI run 的 backend lint/type check、integration tests、E2E、frontend lint/test、frontend E2E、scripts checks 均成功。

## Phase 2：證據蒐集

### CI run 證據

| Run | Commit | 日期 | 失敗 job／測試 | 結果 |
|---|---|---|---|---|
| [29402384024](https://github.com/hmj1026/ccas/actions/runs/29402384024) | `32aec64` | 2026-07-15 | backend unit：`test_throttle_suppresses_rapid_calls` | 1 failed, 1508 passed, coverage 89.49% |
| [29384083013](https://github.com/hmj1026/ccas/actions/runs/29384083013) | `aedae42` | 2026-07-15 | backend unit：同一測試 | 1 failed, 1473 passed, coverage 89.47% |
| [28711414416](https://github.com/hmj1026/ccas/actions/runs/28711414416) | `882d3d7` | 2026-07-04 | backend unit：同一測試 | 1 failed, 1473 passed, coverage 89.47% |

7/15 最新 run 的其他 CI jobs 全數成功，故問題可定位在 backend unit suite 的測試／production 邊界，而非整體 CI 環境或 coverage 設定。

### 本機對照

- 目標單測獨立執行：`1 passed in 0.21s`
- 完整 backend unit suite：`1509 passed, 2 warnings, coverage 89.54%`
- 完整 suite 與 CI 皆使用同一個測試案例與 production method；差異是執行環境的 monotonic clock 起始值。

### 最小重現

現行程式以 `_last_flush_at = 0.0` 當作「尚未 flush」哨兵，但判斷式是：

```python
if now - self._last_flush_at < self._throttle_seconds:
    return
```

在不改檔的診斷中將 `ccas.pipeline.progress.time.monotonic()` 固定為 `1.0`、將測試的 `throttle_seconds` 設為 `100.0`，第一、二次呼叫的 `session.execute.await_count` 為 `0`。這與 CI 的 `0 == 1` 完全一致。

## Phase 3：根因分析

### 資料流

1. pipeline stage 呼叫 `ProgressReporter.stage_item_done(stage, processed)`。
2. worker 路徑注入 `DbProgressReporter`；其 method 取得 `_lock`。
3. method 讀取 `time.monotonic()`，以 `_last_flush_at` 與 `throttle_seconds` 決定是否 return。
4. 通過節流後才建立短生命週期 async session、執行 `UPDATE pipeline_runs`、commit。

### 分歧點

`DbProgressReporter.__init__()` 與 `stage_started()` 都把 `_last_flush_at` 設為 `0.0`。這個數值只有在 monotonic clock 已經超過節流秒數時，才等價於「無上次 flush」。GitHub-hosted runner 在測試開始時可能尚未運行 100 秒，而 unit test 為了抑制第二次呼叫使用 `throttle_seconds=100.0`，因此首筆呼叫被錯誤抑制。

這是環境 uptime 對 sentinel 數值的隱含依賴，不是非同步 session 或 coverage 問題。production 預設 0.25 秒較不容易觸發，但自訂較大 throttle、測試、以及低 uptime 的新程序都會暴露同一缺陷。

### 對照正常流程

integration test `test_db_reporter_throttle_resets_on_new_stage` 同樣使用 `throttle_seconds=10.0`，在本機能通過是因為本機 monotonic uptime 遠大於 10 秒；它沒有保證低 uptime 程序的首筆 flush。`stage_finished()` 另行直接寫入，並不經過這個判斷，因此 CI 其他 progress tests 能通過。

### 單一根因假設

> `0.0` 被同時當成時間值與「尚未 flush」狀態，導致低 monotonic uptime 且 throttle window 較大的程序把第一筆 item progress 誤判為節流中。

最小驗證已重現該假設，與三次 CI failure 的同一 assertion 相符。

## GitNexus 影響分析

- `DbProgressReporter` class upstream：LOW；直接 import caller 為 `pipeline/worker.py`、`pipeline/orchestrator.py`，共 6 個受影響 symbol。
- `stage_item_done` method upstream：MEDIUM；8 個直接 caller，包含 unit 與 integration progress tests，集中在 Pipeline module。
- 沒有 HIGH／CRITICAL execution-flow 風險；修正仍需回歸完整 backend unit、integration 與 frontend CI 對應命令。

## 下一步

修正設計已核准並完成：

1. 以低 monotonic uptime 重現首筆 flush 的 failing test，已先 RED。
2. 將 sentinel 改為明確的 `None` 狀態，保留 `time.monotonic()` 的節流語意，已 GREEN。
3. 執行目標測試、backend unit、backend integration／E2E、scripts checks、frontend lint/build/test/E2E，全部通過。
4. 已補上 solution proposal 與 Phase 5 知識文件，並進行 OpenSpec validation 與 GitNexus change detection。
