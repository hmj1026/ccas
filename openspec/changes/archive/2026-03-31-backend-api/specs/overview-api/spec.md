## ADDED Requirements

### Requirement: 提供 Overview 摘要 API
系統 SHALL 提供 `GET /api/overview`，回傳指定月份的總消費、已繳總額、未繳總額與即將到期帳單摘要；若未提供 `month`，預設為當月。

#### Scenario: 未指定月份時回傳當月摘要
- **WHEN** 前端呼叫 `GET /api/overview` 且未帶 `month`
- **THEN** API 會回傳當月的摘要卡片資料與即將到期帳單清單

#### Scenario: 指定月份時回傳該月份摘要
- **WHEN** 前端呼叫 `GET /api/overview?month=2026-03`
- **THEN** API 會回傳 `2026-03` 的摘要資料
