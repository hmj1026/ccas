# api-auth Specification

## Purpose
TBD - created by archiving change backend-api. Update Purpose after archive.
## Requirements
### Requirement: 所有業務 API 需通過 Bearer Token 認證
系統 SHALL 在 `/api` 命名空間下的所有端點加入 Bearer Token 認證 middleware；Token 值從環境變數 `API_TOKEN` 讀取。

#### Scenario: 帶有效 Token 的請求正常通過
- **WHEN** 請求的 `Authorization` header 帶有 `Bearer <valid_token>`
- **THEN** 請求正常轉發到對應的路由處理

#### Scenario: 缺少 Token 的請求被拒絕
- **WHEN** 請求未包含 `Authorization` header
- **THEN** API 回傳 `401 Unauthorized`

#### Scenario: Token 無效的請求被拒絕
- **WHEN** 請求的 `Authorization` header 帶有無效的 Token
- **THEN** API 回傳 `401 Unauthorized`

#### Scenario: `/health` 端點不需認證
- **WHEN** 請求呼叫 `GET /health`
- **THEN** 無論是否帶有 Token，都會正常回應

