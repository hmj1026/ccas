# Secrets Management

本文件說明 CCAS 的本機 secrets 儲存、備份與 rotate 行為。

## 檔案與資料表

| 項目 | 預設位置 | 用途 |
|---|---|---|
| `master.key` | `${CCAS_DATA_LOCATION}/secrets/master.key` | Fernet 對稱金鑰，用來解密 `bank_secrets` |
| API token | `${CCAS_DATA_LOCATION}/secrets/api-token` | Web UI / API 的登入 token |
| API token version | `${CCAS_DATA_LOCATION}/secrets/api-token-version` | cookie session 失效控制 |
| Gmail token | `${CCAS_DATA_LOCATION}/token.json` | Gmail OAuth refresh token |
| `bank_secrets` | SQLite DB | 各銀行 PDF 密碼密文 |

`master.key`、API token 與 Gmail token 都不應 commit。prod compose 會把
`${CCAS_DATA_LOCATION}` 掛到容器內 `/data`。

## master.key

entrypoint 首次啟動會自動產生 `master.key`，權限為 `0600`。既有檔案不會被覆寫。

`/setup/secrets` 寫入 PDF 密碼時，後端會用 `master.key` 加密後存進 `bank_secrets`。
DB 內不會保存明文密碼。

遺失 `master.key` 後，即使 SQLite DB 還在，既有 `bank_secrets` 也無法解密。系統會明確回報
`master.key` 與加密資料不匹配，而不是把它誤判為 PDF 密碼錯誤。

## PDF 密碼來源優先序

密碼解析順序固定為：

1. `bank_secrets` DB row
2. `.env` 的 `PDF_PASSWORD_<BANK_CODE>`
3. 無密碼

因此，從 `/setup/secrets` 設定密碼後，DB 會優先於 env。刪除 DB 條目後，如果 env 仍有值，系統會 fallback 到 env。

`/setup/secrets` 的「匯入 env 密碼」只會把 env 值加密寫入 DB，不會修改 `.env`。確認 DB 生效後，可在下次維護時手動移除 `.env` 的明文密碼。

## API token rotate

在 `/setup/admin` 點「產生新 token」後：

1. 後端產生新的 32-byte hex token。
2. 覆寫 `${CCAS_DATA_LOCATION}/secrets/api-token`，權限維持 `0600`。
3. `api-token-version` 加 1。
4. 回應只顯示一次完整新 token。
5. 舊 Bearer token 與舊 cookie session 立即失效。

請先複製新 token，再按「重新登入」。若關閉頁面後忘記 token，可在主機讀取：

```bash
cat "${CCAS_DATA_LOCATION:-./data}/secrets/api-token"
```

## Gmail credentials 與 token

`/setup/gmail` 會寫入 `GMAIL_CREDENTIALS_PATH` 與 `GMAIL_TOKEN_PATH` 指向的檔案。prod 預設為：

```env
GMAIL_CREDENTIALS_PATH=/data/credentials.json
GMAIL_TOKEN_PATH=/data/token.json
```

如果透過外部網域或非預設 port 使用 OAuth，請設定 `PUBLIC_BASE_URL`，例如：

```env
PUBLIC_BASE_URL=https://ccas.example.com
```

並在 Google Cloud Console 的 OAuth client 加入：

```text
https://ccas.example.com/setup/gmail/callback
```

## 備份與還原

完整備份至少包含 `${CCAS_DATA_LOCATION}`：

```bash
docker compose -f docker-compose.yml stop
tar -czf "ccas-data-$(date +%Y%m%d-%H%M%S).tar.gz" "${CCAS_DATA_LOCATION:-./data}"
docker compose -f docker-compose.yml start
```

建議另備份 `.env`，因為它可能含 Telegram token 與 env fallback 密碼。

還原時，解壓同一份 data 目錄並使用同一份 `.env` 啟動即可。只還原 SQLite、不還原
`secrets/master.key` 會造成 DB 內的 PDF 密碼密文無法解密。
