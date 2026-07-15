# Pipeline progress throttle related tables

| Table／欄位 | 用途 | 本修正影響 |
|---|---|---|
| `pipeline_runs.current_stage` | 目前執行階段 | 既有更新流程不變 |
| `pipeline_runs.current_stage_processed` | 目前階段已處理數 | 首筆 item progress 現在在低 uptime 也會正確更新 |
| `pipeline_runs.current_stage_total` | 目前階段總數 | 由 `stage_started` 設定，未變更 |
| `pipeline_runs.stage_summary` | 已完成 stage 的摘要 JSON | 僅由 `stage_finished` 更新，本修正不影響 |
