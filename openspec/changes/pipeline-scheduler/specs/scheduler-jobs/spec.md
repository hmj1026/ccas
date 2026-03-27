## ADDED Requirements

### Requirement: 應用程式啟動時初始化並啟動排程器
系統 SHALL 在應用程式啟動時初始化 APScheduler `BackgroundScheduler` 並自動啟動，應用程式關閉時優雅停止排程器。

#### Scenario: 排程器隨應用程式啟動
- **WHEN** 應用程式（FastAPI server 或 CLI 模式）啟動
- **THEN** APScheduler BackgroundScheduler 被初始化並啟動，所有排程工作開始生效

#### Scenario: 排程器隨應用程式關閉
- **WHEN** 應用程式收到關閉信號
- **THEN** 排程器執行優雅停止，等待正在執行的工作完成後再退出

### Requirement: 週期性 pipeline 排程工作可設定觸發頻率
系統 SHALL 提供週期性觸發 `run_pipeline()` 的排程工作，觸發頻率由 `Settings` 統一設定，不硬編碼在程式中。

#### Scenario: 依 Settings 設定的頻率週期觸發 pipeline
- **WHEN** 排程器啟動且 pipeline 排程工作被註冊
- **THEN** 系統依照 `Settings` 中的排程設定（cron 表達式或 interval）週期性呼叫 `run_pipeline()`

#### Scenario: 排程設定更新後下次觸發反映新設定
- **WHEN** `Settings` 中的 pipeline 排程設定被修改並套用
- **THEN** 後續的觸發時機依照新設定執行，不影響已在進行中的執行

### Requirement: 排程工作執行時不阻塞主程序
系統 SHALL 確保所有排程工作在背景執行緒中執行，不阻塞 FastAPI 主執行緒的正常請求處理。

#### Scenario: Pipeline 排程工作在背景執行
- **WHEN** 排程工作觸發 `run_pipeline()` 執行
- **THEN** 執行在 APScheduler 的背景執行緒中進行，FastAPI 仍可正常回應其他 API 請求

#### Scenario: 前一次排程尚未完成時新一次觸發不重疊執行
- **WHEN** pipeline 排程工作的觸發時間到來，但前一次執行尚未完成
- **THEN** 此次觸發被略過，避免多個 pipeline 同時執行造成資料衝突
