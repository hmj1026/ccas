## ADDED Requirements

### Requirement: 提供端到端 pipeline 執行入口
系統 SHALL 提供 `run_pipeline()` 入口，依序執行 ingest -> parse -> classify -> notify 四個階段，並回傳各階段的處理摘要。

#### Scenario: 完整 pipeline 執行
- **WHEN** pipeline 被觸發（排程或手動）
- **THEN** 系統會依序執行 Gmail ingestion、PDF parsing、keyword classification、Telegram notification 四個階段

#### Scenario: 各階段的新產出自動成為下一階段的輸入
- **WHEN** ingestion 階段成功 staged 新的 PDF 附件
- **THEN** parse 階段會自動處理這些新 staged 附件；classify 階段會處理新解析的交易；notify 階段會為新解析的帳單發送通知

### Requirement: 各階段獨立容錯
系統 SHALL 確保 pipeline 中某一階段的部分失敗不會阻止後續階段處理已成功的項目。

#### Scenario: ingestion 部分失敗但 parse 仍執行
- **WHEN** ingestion 階段有部分附件下載失敗，但其他附件成功 staged
- **THEN** parse 階段仍會處理所有狀態為待解析的 staged 附件（包含本次與先前成功 staged 的）

#### Scenario: parse 部分失敗但 classify 仍執行
- **WHEN** parse 階段有部分附件解析失敗，但其他帳單成功寫入
- **THEN** classify 階段仍會對所有尚未分類的交易執行分類

### Requirement: 支援排程觸發與手動觸發
系統 SHALL 支援透過 APScheduler 定時觸發 pipeline，也支援透過 CLI 或 API 手動觸發。

#### Scenario: 排程觸發 pipeline
- **WHEN** APScheduler 依設定頻率觸發 pipeline
- **THEN** 系統會執行完整的四階段 pipeline 並記錄執行結果

#### Scenario: 手動觸發 pipeline
- **WHEN** 使用者透過 CLI 命令或 API 端點手動觸發 pipeline
- **THEN** 系統會立即執行完整 pipeline，行為與排程觸發一致

### Requirement: 回傳 pipeline 執行摘要
系統 SHALL 為每次 pipeline 執行回傳結構化摘要，涵蓋各階段的處理統計。

#### Scenario: pipeline 摘要包含各階段結果
- **WHEN** 一次 pipeline 執行完成
- **THEN** 摘要至少包含：ingestion（staged/skipped/failed 數量）、parse（parsed/failed 數量）、classify（classified 數量）、notify（sent/failed 數量）與整體執行時間
