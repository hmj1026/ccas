## ADDED Requirements

### Requirement: master.key Fernet 加密金鑰自動產生與保存

系統 SHALL 在 `${CCAS_DATA_LOCATION}/secrets/master.key` 維護一份 Fernet 對稱加密金鑰（32-byte URL-safe base64）。entrypoint 啟動時 SHALL 偵測該檔不存在則 `cryptography.fernet.Fernet.generate_key()` 產生並寫入、權限 0600、stdout INFO log；存在時不覆寫。Backend、worker、scheduler、bot 四服務 SHALL 從同一份 master.key 載入加密能力。

#### Scenario: 首次啟動自動產生

- **WHEN** 全新部署、`${CCAS_DATA_LOCATION}/secrets/` 目錄無 `master.key`
- **THEN** entrypoint SHALL 產生新 Fernet key、寫入該檔權限 0600、stdout 印 `[INFO] 已自動產生 master.key（首次啟動）`

#### Scenario: 既有 master.key 不覆寫

- **WHEN** master.key 已存在
- **THEN** entrypoint SHALL 直接讀取載入、不覆寫該檔；後續 backend / worker / scheduler / bot 啟動 SHALL 用同一把 key

#### Scenario: master.key 權限檢查

- **WHEN** entrypoint 偵測 master.key 權限非 0600
- **THEN** SHALL stdout 印 WARN（如 `[WARN] master.key 權限為 0644，建議修正為 0600`），但不阻止啟動（避免使用者掛載權限受限環境時無法啟動）

#### Scenario: master.key 與 data 同備份

- **WHEN** 使用者 `tar` 備份 `${CCAS_DATA_LOCATION}` 目錄、在新機器解壓 + `up -d`
- **THEN** 系統 SHALL 用同一把 master.key 解密既有 bank_secrets、PDF 解密成功；不需要使用者額外備份其他檔案

### Requirement: bank_secrets 表 Fernet 加密儲存

系統 SHALL 新增 `bank_secrets` 表（`bank_code` PK、`encrypted_password` text、`created_at`、`updated_at`），密碼欄位 SHALL 為 Fernet 加密 + base64 encoded ciphertext。Backend SHALL 提供 `MasterKeyManager.encrypt(plaintext) -> str` 與 `decrypt(ciphertext) -> str` 兩個方法，封裝 Fernet 操作。

#### Scenario: 寫入時加密

- **WHEN** `PUT /api/setup/secrets/ctbc` body `{password: "12345"}`
- **THEN** 系統 SHALL 呼叫 `MasterKeyManager.encrypt("12345")`、UPSERT `bank_secrets.bank_code='ctbc'`、`encrypted_password` 為 base64 ciphertext；DB 直查該欄位 SHALL 看不到 `12345` 明文

#### Scenario: 讀取時解密

- **WHEN** decryptor 階段需要 ctbc 密碼、bank_secrets 有 row
- **THEN** 系統 SHALL 用 master.key 呼叫 `MasterKeyManager.decrypt(encrypted_password)` 取得明文、傳遞給 PDF decryption library；明文 SHALL 不寫入 log（既有 RedactingFilter 保留）

#### Scenario: master.key 不匹配時錯誤訊息明確

- **WHEN** 使用者誤刪 master.key、entrypoint 自動產生新 key、bank_secrets 仍有舊密文
- **THEN** decryptor 嘗試解密 SHALL raise `MasterKeyMismatchError`、錯誤訊息含「master.key 與加密資料不匹配，請確認 `${CCAS_DATA_LOCATION}` 完整備份還原」、不誤導為「PDF 密碼錯誤」

### Requirement: 密碼解析優先序 DB > env > 無

`backend/src/ccas/decryptor/passwords.py` SHALL 依序嘗試取得 bank PDF 解密密碼：(1) `bank_secrets` 表有 row → Fernet 解密、(2) `Settings.bank_passwords[code]`（env `PDF_PASSWORD_<CODE>`）→ 直接使用、(3) 無 → 回 None / raise NoPasswordConfiguredError。

#### Scenario: DB 有 secret 優先 env

- **WHEN** ctbc 在 DB 設定密碼 `db_pwd`、env 設定 `PDF_PASSWORD_CTBC=env_pwd`
- **THEN** decryptor SHALL 用 `db_pwd`，env 值不被讀取

#### Scenario: DB 無 row 用 env

- **WHEN** esun 在 DB 無 row、env 設定 `PDF_PASSWORD_ESUN=env_pwd`
- **THEN** decryptor SHALL 用 `env_pwd`

#### Scenario: 兩處皆無

- **WHEN** taishin 在 DB 無 row、env 也未設定 `PDF_PASSWORD_TAISHIN`
- **THEN** decryptor SHALL fallback 為「嘗試無密碼解密」（既有行為），失敗時記錄 `manual_review_needed`

### Requirement: GET /api/setup/secrets 不洩漏明文

系統 SHALL 提供 `GET /api/setup/secrets` 端點，回傳每銀行的密碼來源狀態，**不**回傳任何密碼明文或 ciphertext。Response 每項 SHALL 含 `bank_code`、`has_db_secret`、`has_env_secret`、`effective_source`（`db` / `env` / `none`）。

#### Scenario: response 不含明文

- **WHEN** 前端呼叫 `GET /api/setup/secrets`
- **THEN** response body SHALL 不含任何 `PDF_PASSWORD_*` 值或 `encrypted_password` 內容；grep response 應無實際密碼字串

#### Scenario: 來源 badge 正確

- **WHEN** ctbc 在 DB 有 secret、env 也有
- **THEN** response SHALL 為 `{bank_code: "ctbc", has_db_secret: true, has_env_secret: true, effective_source: "db"}`

#### Scenario: 既無設定的銀行也列出

- **WHEN** 系統有 7 個銀行、僅 3 個設了密碼
- **THEN** response SHALL 含全部 7 項，4 個 `effective_source: "none"`，提示使用者哪些銀行尚未設定

### Requirement: PUT/DELETE /api/setup/secrets 寫入與移除

系統 SHALL 提供 `PUT /api/setup/secrets/{code}` body `{password: str}` 寫入加密密碼、`DELETE /api/setup/secrets/{code}` 移除 DB row（env fallback 仍生效）。寫入 SHALL UPSERT、`updated_at` 更新；刪除 SHALL 不影響 env。

#### Scenario: PUT 為 UPSERT 語意

- **WHEN** 前端對既有 ctbc 條目重新 PUT 新密碼
- **THEN** 系統 SHALL UPDATE 而非 INSERT 失敗、`encrypted_password` 為新值的 ciphertext、`updated_at` 更新

#### Scenario: DELETE 不影響 env fallback

- **WHEN** ctbc 同時在 DB 與 env 有設定，使用者 DELETE DB row
- **THEN** `bank_secrets.code='ctbc'` SHALL 被刪除、env `PDF_PASSWORD_CTBC` 不變、後續 decryptor 呼叫 SHALL fallback 到 env

### Requirement: POST /api/setup/secrets/import-from-env 一鍵匯入

系統 SHALL 提供 `POST /api/setup/secrets/import-from-env` 端點，掃描 `Settings.bank_passwords`（既有 env `PDF_PASSWORD_*` 解析結果）、對每個「env 有但 DB 無」的條目 UPSERT bank_secrets。Response SHALL 為 `{imported: int, skipped_already_in_db: int, env_total: int}`。**不**修改或刪除 env 設定。

#### Scenario: 首次匯入

- **WHEN** env 有 5 個密碼、DB 全空、前端呼叫 import-from-env
- **THEN** 系統 SHALL 對 5 個 bank UPSERT、回 `{imported: 5, skipped_already_in_db: 0, env_total: 5}`、env 設定保留

#### Scenario: 部分 DB 已有 row 時 skip

- **WHEN** env 有 5 個、DB 已有 ctbc + esun
- **THEN** import SHALL 對其餘 3 個 UPSERT、回 `{imported: 3, skipped_already_in_db: 2, env_total: 5}`、ctbc/esun DB row 不變

#### Scenario: env 為空時冪等

- **WHEN** env 無 `PDF_PASSWORD_*` 設定、前端呼叫 import-from-env
- **THEN** 系統 SHALL 回 `{imported: 0, skipped_already_in_db: 0, env_total: 0}`、不報錯

### Requirement: /setup/secrets 前端頁面

系統 SHALL 提供 `frontend/src/pages/setup/secrets.tsx`，路由 `/setup/secrets`。頁面 SHALL 為表格（bank_code / 來源 badge / 「設定密碼」按鈕 / 「刪除 DB 條目」按鈕）。頁面頂部 SHALL 永久顯示 master.key 備份警告 banner。若偵測到 env-only 條目存在，頁面 SHALL 顯示「匯入 env 密碼」橫幅含一鍵按鈕。

#### Scenario: 來源 badge 三色

- **WHEN** 表格載入
- **THEN** `effective_source: "db"` 顯示綠 badge、`"env"` 顯示黃 badge、`"none"` 顯示灰 badge；hover SHALL 顯示 tooltip「DB 優先 env」說明

#### Scenario: 設定密碼對話框

- **WHEN** 使用者點某銀行「設定密碼」按鈕
- **THEN** 系統 SHALL 彈出 dialog 含 input type=password、提交呼叫 `PUT /api/setup/secrets/{code}`、成功後 toast「密碼已加密儲存」並重新載入列表

#### Scenario: 刪除確認含明確後果

- **WHEN** 使用者點「刪除 DB 條目」
- **THEN** confirm dialog SHALL 明示「刪除後若 env 仍設定 SHALL fallback 生效；否則該銀行 PDF 解密 SHALL 失敗（記為 manual_review_needed）」

#### Scenario: master.key warning 永久顯示

- **WHEN** 使用者進入 `/setup/secrets`
- **THEN** 頁面頂部 SHALL 顯示橘色 warning banner：「master.key 是備份的關鍵，請定期備份 `${CCAS_DATA_LOCATION}` 目錄。遺失 master.key 將永久失去解密能力」、不可關閉

#### Scenario: import-from-env 橫幅條件式顯示

- **WHEN** 列表中存在至少一個 `has_env_secret: true && has_db_secret: false` 條目
- **THEN** 頁面頂部 SHALL 顯示藍色 banner「偵測到 N 個 env 密碼尚未匯入 DB，是否一鍵匯入？」含「立即匯入」按鈕；匯入完成後 banner 消失
