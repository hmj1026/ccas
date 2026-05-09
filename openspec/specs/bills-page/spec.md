# bills-page Specification

## Purpose
TBD - created by archiving change frontend-dashboard. Update Purpose after archive.
## Requirements
### Requirement: 提供帳單列表與狀態管理頁面
系統 SHALL 提供 Bills 頁面，列出帳單資料，並支援依月份與付款狀態篩選。

#### Scenario: 篩選帳單列表
- **WHEN** 使用者在 `/bills` 頁面切換月份或付款狀態
- **THEN** 頁面會只顯示符合條件的帳單資料

### Requirement: 支援付款狀態切換與 PDF 連結
系統 SHALL 在 Bills 頁面提供付款狀態切換控制與 PDF 檔案連結。

#### Scenario: 切換帳單為已繳
- **WHEN** 使用者在 Bills 頁面將某張帳單標記為已繳
- **THEN** 頁面會送出更新請求並在成功後顯示最新狀態

#### Scenario: 開啟帳單 PDF 連結
- **WHEN** 某張帳單具有可用的 PDF 檔案路徑或連結
- **THEN** 頁面會提供可點擊的 PDF 連結供使用者開啟

