# Pipeline progress throttle data flow

1. Pipeline stage 呼叫 `ProgressReporter.stage_item_done(stage, processed)`。
2. Worker 注入 `DbProgressReporter`，method 取得同一 reporter 的 `asyncio.Lock`。
3. `stage_item_done` 讀取 `time.monotonic()`；若已有上次 flush 且 elapsed 小於 throttle，直接 return。
4. 通過節流後開啟獨立 async session，更新 `pipeline_runs.current_stage` 與 `current_stage_processed`，再 commit。
5. 成功 flush 後記錄 monotonic timestamp；`stage_started` 完成後將 timestamp 清成 `None`，確保新階段首筆立即寫入。

`stage_finished` 不使用 item throttle，獨立處理 stage summary、完成進度與 database-locked retry。
