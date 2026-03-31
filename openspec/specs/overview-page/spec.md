# overview-page Specification

## Purpose
TBD - created by archiving change frontend-dashboard. Update Purpose after archive.
## Requirements
### Requirement: 提供本月總覽頁面
系統 SHALL 提供 Overview 頁面，顯示本月總消費、已繳總額、未繳總額與即將到期帳單摘要。

#### Scenario: 頁面載入時顯示本月摘要
- **WHEN** 使用者進入 `/overview`
- **THEN** 頁面會顯示本月摘要卡片與即將到期帳單清單

#### Scenario: 無資料時顯示空狀態
- **WHEN** 當月沒有任何帳單或交易資料
- **THEN** 頁面會顯示明確的空狀態提示，而不是空白區塊

