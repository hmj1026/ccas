## ADDED Requirements

### Requirement: Notify stage 單個帳單失敗不影響後續帳單
`run_notify_job()` SHALL 確保在單個帳單通知失敗並 rollback session 後，後續帳單仍能繼續處理，不因 ORM lazy loading 問題而 crash。

#### Scenario: 第一個帳單通知失敗，後續帳單繼續處理
- **WHEN** 第一個帳單的 `send_message` 拋出 exception
- **THEN** `run_notify_job()` SHALL 在 summary.failed_count 記錄該失敗
- **THEN** 後續帳單 SHALL 繼續嘗試發送，不拋出 `MissingGreenlet` exception
