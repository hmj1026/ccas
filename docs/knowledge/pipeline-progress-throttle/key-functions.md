# Pipeline progress throttle key functions

| Symbol | File | Responsibility |
|---|---|---|
| `DbProgressReporter.__init__` | `backend/src/ccas/pipeline/progress.py` | 建立 reporter、session factory、lock 與未初始化 throttle state |
| `DbProgressReporter.stage_started` | `backend/src/ccas/pipeline/progress.py` | 寫入 stage total／processed=0，並重置 throttle state |
| `DbProgressReporter.stage_item_done` | `backend/src/ccas/pipeline/progress.py` | 以 monotonic elapsed 節流 item progress，通過後更新 DB |
| `DbProgressReporter.stage_finished` | `backend/src/ccas/pipeline/progress.py` | 強制完成 stage、追加 summary，並處理 SQLite locked retry |
| `test_first_item_flushes_when_uptime_is_below_throttle` | `backend/tests/unit/pipeline/test_progress.py` | 防止低 uptime 首筆 progress 被誤抑制的 regression test |
