# CCAS API 端點驗證清單

共 26 端點，分為 9 個路由群組。本文件為 `qa-api-verify.sh` 的 SSOT。

## 回應格式

所有端點遵循統一信封：

```json
{"success": true, "data": <T>, "message": ""}
```

分頁回應額外包含：
```json
{"pagination": {"page": 1, "page_size": 20, "total": 100, "total_pages": 5}}
```

## 安全標頭

每個回應須包含（Phase 6 逐一驗證）：
- `X-Content-Type-Options: nosniff`
- `X-Frame-Options: DENY`
- `Referrer-Policy: strict-origin-when-cross-origin`
- `Content-Security-Policy: default-src 'self'; ...`（`/docs`, `/redoc`, `/openapi.json` 豁免）

## 端點總覽

### Health (1)

| Method | Path | Auth | Status | Body Check | Smoke |
|--------|------|------|--------|------------|-------|
| GET | `/health` | No | 200 | `status` == `ok` | Yes |

### Auth (3)

| Method | Path | Auth | Status | Body Check | Smoke |
|--------|------|------|--------|------------|-------|
| GET | `/api/auth/session` | No | 200 | `data.authenticated` is bool | No |
| POST | `/api/auth/session` | No | 204 | Empty body, sets HttpOnly cookie | Yes |
| DELETE | `/api/auth/session` | Yes | 204 | Empty body, clears cookie | No |

POST body: `{"token": "<API_TOKEN>"}`

### Overview (1)

| Method | Path | Auth | Status | Body Check | Smoke |
|--------|------|------|--------|------------|-------|
| GET | `/api/overview` | Yes | 200 | `data.month`, `data.total_spending` >= 0, `total_spending` == `total_paid` + `total_unpaid` | Yes |

Query: `?month=YYYY-MM`（可選，預設當月或最近有資料月份）

### Bills (4)

| Method | Path | Auth | Status | Body Check | Smoke |
|--------|------|------|--------|------------|-------|
| GET | `/api/bills` | Yes | 200 | `data` is array, `pagination` present | Yes |
| PATCH | `/api/bills/{id}` | Yes | 200 | `data.is_paid` matches request | No |
| GET | `/api/bills/{id}/transactions` | Yes | 200 | `data` is array | No |
| GET | `/api/bills/{id}/pdf` | Yes | 200/404 | Content-Type: `application/pdf` | No |

GET query: `?month=YYYY-MM&year=YYYY&bank_code=X&status=all|paid|unpaid&page=1&page_size=20`
PATCH body: `{"is_paid": true}`

### Transactions (2)

| Method | Path | Auth | Status | Body Check | Smoke |
|--------|------|------|--------|------------|-------|
| GET | `/api/transactions` | Yes | 200 | `data` is array, `pagination` present | Yes |
| GET | `/api/transactions/export` | Yes | 200 | Content-Type: `text/csv` | No |

GET query: `?month=YYYY-MM&year=YYYY&bank_code=X&category=X&q=keyword&sort=trans_date_desc&page=1&page_size=20`

### Analytics (4)

| Method | Path | Auth | Status | Body Check | Smoke |
|--------|------|------|--------|------------|-------|
| GET | `/api/analytics/years` | Yes | 200 | `data` is array of ints | No |
| GET | `/api/analytics/trend` | Yes | 200 | `data` is array with `month`, `total` | No |
| GET | `/api/analytics/categories` | Yes | 200 | `data` is array with `category`, `total` | No |
| GET | `/api/analytics/banks` | Yes | 200 | `data` is array with `bank_code`, `total` | No |

### Settings - Banks (3)

| Method | Path | Auth | Status | Body Check | Smoke |
|--------|------|------|--------|------------|-------|
| GET | `/api/settings/banks` | Yes | 200 | `data` is array, length >= 7 | No |
| POST | `/api/settings/banks` | Yes | 201 | `data.bank_code` matches request | No |
| PATCH | `/api/settings/banks/{id}` | Yes | 200 | Updated fields match | No |

POST body: `{"bank_code": "X", "bank_name": "X", "gmail_filter": "X", "active_parser_version": "v1", "is_active": true}`

### Settings - Categories (4)

| Method | Path | Auth | Status | Body Check | Smoke |
|--------|------|------|--------|------------|-------|
| GET | `/api/settings/categories` | Yes | 200 | `data` is array | No |
| POST | `/api/settings/categories` | Yes | 201 | `data.keyword` matches request | No |
| PATCH | `/api/settings/categories/{id}` | Yes | 200 | Updated fields match | No |
| DELETE | `/api/settings/categories/{id}` | Yes | 204 | Empty body | No |

### Staged Attachments (1)

| Method | Path | Auth | Status | Body Check | Smoke |
|--------|------|------|--------|------------|-------|
| GET | `/api/staged-attachments` | Yes | 200 | `data` is array, `pagination` present | No |

Query: `?status=staged,decrypted,parsed&bank_code=X&page=1&page_size=20`

### Pipeline (1)

| Method | Path | Auth | Status | Body Check | Smoke |
|--------|------|------|--------|------------|-------|
| POST | `/api/pipeline/trigger` | Yes | 200 | `data.job_id` is string | No |

POST body（可選）: `{"force": false, "bank_code": "CTBC", "year": 2024, "month": 1}`

## 錯誤回應驗證

| 場景 | Method | Path | Expected Status |
|------|--------|------|----------------|
| 無 auth header | GET | `/api/bills` | 401 |
| 無效 token | POST | `/api/auth/session` | 401 |
| 不存在的 bill | GET | `/api/bills/99999/transactions` | 404 |
| 重複 bank_code | POST | `/api/settings/banks` | 409 |
| 超出頁碼 | GET | `/api/bills?page=9999` | 200（空 data） |
| 無效參數 | GET | `/api/bills?page_size=999` | 422 |

## 擴充說明

新增端點時：
1. 在本文件對應群組新增一列
2. 標記 Smoke 欄位（Yes/No）
3. 在 `scripts/qa-api-verify.sh` 新增對應斷言
