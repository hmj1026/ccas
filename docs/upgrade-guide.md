# CCAS 升級指南

本文件說明從現有版本升級至新版的步驟、相容性政策與回滾建議。

> 本指南僅適用於 prod pull-only 部署（`docker/docker-compose.yml`）。dev（含原始碼）
> 升級請走 `git pull` + `docker compose up -d --build`。

---

## TL;DR — 標準升級流程

```bash
cd ~/ccas    # 你 docker-compose.yml 所在的目錄

# 1) 修改 .env 的版本
sed -i 's/^CCAS_VERSION=.*/CCAS_VERSION=v0.6.0/' .env

# 2) 拉新 image 並重啟
docker compose -f docker-compose.yml pull
docker compose -f docker-compose.yml up -d

# 3) 驗證
curl -fsS http://localhost:${CCAS_PORT:-8080}/api/health
```

**alembic migration 會在 backend 容器啟動時自動執行**（entrypoint 已內建），不需手動跑。

---

## 版本相容性政策

CCAS 採 [SemVer](https://semver.org/)：

| 升級類型 | 預期影響 | 額外步驟 |
|---|---|---|
| Patch（`v0.1.0` → `v0.1.1`） | 純 bugfix；DB schema 不動 | 無 |
| Minor（`v0.1.0` → `v0.2.0`） | 新功能；可能含 alembic migration | 升級前**備份** `${CCAS_DATA_LOCATION}` |
| Major（`v0.x.x` → `v1.0.0`） | 可能 breaking change；release notes 會明示 | 升級前**閱讀 release notes**、備份 |

每次 release 的詳細 changelog 見 [GitHub Releases](https://github.com/<owner>/ccas/releases)。

---

## v0.6.0（Minor）— 品質稽核修復（解析正確性、靜默失敗、SecretStr、API 契約）

**適用對象**：v0.5.x 升級至 v0.6.0。alembic schema 不變，但含 **API 契約變更**，
若你有自寫的 API 消費端請先閱讀下方破壞性變更。

**資料正確性（重要）**：
- 修正 **CTBC 退款記為正數消費**：兩條解析路徑此前完全不做退款負數化，退款金額
  被當成消費累加，造成對帳膨脹。升級後新解析的 CTBC 帳單退款明細會正確保留為負數
  （既有資料需 force 重解析才會更新）。
- 修正 **UBOT 應繳總額誤抓「本期最低應繳金額」**：當帳單缺特定排版錨點時 fallback
  會回傳最低應繳值而非應繳總額。
- 修正 **pipeline 靜默成功**：Gmail 分頁中途失敗等資料階段錯誤此前仍被標 SUCCEEDED、
  儀表板綠燈，導致郵件靜默遺漏。升級後任一資料階段（ingest/decrypt/parse）失敗即
  正確標 FAILED（notify 通知為盡力而為通道，單筆失敗不影響 run 狀態）。

**安全強化**：
- `TELEGRAM_BOT_TOKEN` / `API_TOKEN` 改以 `SecretStr` 處理，避免在 DEBUG repr / log
  意外洩漏；日誌 RedactingFilter 一併遮蔽。**無需改設定**。
- `API_TOKEN` 長度 < 32 時 entrypoint 會輸出**非阻斷警告**（不影響啟動）；建議改用
  ≥32 字元的高熵 token。
- 銀行密碼 API 的 `bank_code` 路徑參數加格式白名單（`^[A-Z0-9_-]{1,32}$`）。

**API 契約變更（破壞性，僅影響自寫消費端；前端不受影響）**：
- `GET /api/pipeline/runs` 分頁參數由 `limit` / `offset` 改為 `page` / `page_size`
  （與 `/api/bills`、`/api/transactions` 一致）。請改用 `?page=N&page_size=M`。
- 交易 API 新增 `installment_current` / `installment_total` 欄位（分期資訊，無分期時為
  `null`）；為新增欄位，既有消費端可忽略。
- `POST /api/transactions/{id}/note` 標記為 **deprecated**（行為不變），請改用
  `PATCH /api/transactions/{id}`；將於下個 major 移除。
- 交易 `tags` 單一元素長度上限 100 字元（超出回 422）。

**升級後**：無額外手動步驟；如需讓既有 CTBC 帳單套用退款負數化，可對該帳單執行
force 重新解析。

---

## v0.5.0（Minor）— 品質稽核修復（資料正確性、安全、架構、效能、無障礙）

**適用對象**：v0.4.x 升級至 v0.5.0。

**資料正確性（重要）**：
- 修正 classify 整批 commit 失敗時誤標 SUCCEEDED 並遺失資料
- 修正 CTBC labeled 格式跨年交易的年份判定

**新增功能**：
- **銀行網銀登入憑證可加密儲存**：FUBON `NATIONAL_ID` / `ROC_BIRTHDAY` 等可改存
  DB（Fernet + `master.key`），不再僅依賴明文環境變數；新增「設定中心 → 登入憑證」
  頁，支援一鍵將既有 env 憑證加密匯入（env 仍為 legacy fallback）
- 前端設計系統與無障礙強化：統一下拉元件（SelectField）、鍵盤可達性、表單標籤、
  展開區 aria 屬性
- 通知可靠性：預算告警補推、Gmail 逐封失敗隔離；staged 重試韌性

**安全強化**：
- `REDIS_PASSWORD` 空值在 **https 正式部署**升級為阻斷（dev http 維持警告）
- Telegram 空允許名單告警、redis-commander 加上 Basic Auth、Dockerfile `--frozen`
- SQLite 外鍵強制（`foreign_keys=ON`）+ delete 路由級聯／409 完整性

**Database 異動**：
- 新表：`bank_login_credentials`（複合主鍵 `bank_code`+`credential_key`、Fernet 密文）
- 新欄位：`budget_alerts.notified`（補推用）

**Migration 自動執行**：Alembic migration 會在 backend 容器啟動時自動執行，**無需手動操作**。

**安全相關注意**：
- **登入憑證／master.key 備份**：DB 登入憑證以 `master.key` 加密；遺失 `master.key`
  = 既有 DB 憑證無法解密。沿用 v0.4.0 的備份建議：完整備份 `${CCAS_DATA_LOCATION}`
  並**單獨保管 `master.key`**（見 [secrets-management.md](secrets-management.md)）
- **https 部署需設 `REDIS_PASSWORD`**：若 `PUBLIC_BASE_URL` 為 https 而 `REDIS_PASSWORD`
  留空，`check-env.sh` 將阻斷啟動；升級前請確認已設定

---

## v0.4.0（Minor）— 解析正確性、加密、效能

**適用對象**：v0.3.x 升級至 v0.4.0。

**新增功能**：
- 退款 / 沖銷明細統一跨行偵測（`ccas.parser.refund_utils`）
- OAuth credentials（`token.json` / `credentials.json`）**現已於磁碟上以 Fernet + `master.key` 加密存放**（非明文）
- 原子寫入保護（PDF 解密、staged 檔、機密寫入皆採 temp→`os.replace`）
- 登入端點速率限制
- 帳單估計繳款期（CTBC 特定功能）
- 交易日期快速索引優化

**Database 異動**：
- 新 index：`ix_transactions_trans_date`（交易查詢加速）
- 新欄位：`bills.due_date_estimated`（bool，區分實際期限 vs 估計期限）

**Migration 自動執行**：Alembic migration 會在 backend 容器啟動時自動執行，**無需手動操作**。

**安全相關注意**：
- **OAuth 加密金鑰備份**：v0.4.0 開始，Gmail `token.json` 與 `credentials.json` 以 `master.key` 加密寫入磁碟檔（非明文）
  - `master.key` 遺失 = 既有授權變成無法解密
  - **強烈建議**：除了定期備份 `${CCAS_DATA_LOCATION}` 整個目錄外，**務必單獨妥善保管 `master.key`**
  - 如果只備份了資料目錄但沒有 `master.key`，該備份在實災時無法復原 OAuth 授權
  - 如何備份與復原：見 [secrets-management.md](secrets-management.md) 詳細指南

---

## 升級前備份（強烈建議）

CCAS 所有狀態（SQLite、staging PDF、Gmail token、API token、master.key、redis dump）皆落在
`${CCAS_DATA_LOCATION}` 單一目錄。備份只需：

```bash
docker compose -f docker-compose.yml stop
tar -czf "ccas-backup-$(date +%Y%m%d-%H%M%S).tar.gz" data/   # 路徑為 .env 的 CCAS_DATA_LOCATION
docker compose -f docker-compose.yml start
```

> `.env` 本身建議另外備份；它可能含 PDF 密碼 fallback、Telegram token 等敏感設定。

---

## 升級到含 `/setup/*` 的版本

新版設定中心會在啟動時做三件相容性初始化：

1. 自動建立 `${CCAS_DATA_LOCATION}/secrets/master.key`（權限 0600），供 `/setup/secrets` 加密 PDF 密碼。
2. Alembic 新增 `bank_settings`、`bank_secrets`、`gmail_oauth_state` 三張表。
3. entrypoint 從既有銀行設定 seed `bank_settings`，既有 row 不覆寫。

既有部署升級後行為維持：

- `.env` 中的 `PDF_PASSWORD_<BANK>` 仍會生效；進 `/setup/secrets` 可一鍵匯入 DB，匯入後 DB 優先生效。
- 既有銀行啟用狀態會 seed 到 `bank_settings`；之後請用 `/setup/banks` 管理。
- 既有 Gmail `credentials.json` / `token.json` 路徑仍可使用；也可改到 `/setup/gmail` 重新上傳與授權。
- `API_TOKEN` 可繼續使用；若要換 token，進 `/setup/admin` rotate。rotate 後舊 token 與舊 cookie 立即失效。

`master.key` 遺失會導致既有 `bank_secrets` 無法解密。備份與復原細節見
[secrets-management.md](secrets-management.md)。

---

## 回滾流程

若升級後出問題，回滾步驟：

```bash
# 1) 停服務
docker compose -f docker-compose.yml down

# 2) 還原資料目錄（若有 schema migration，回滾 image 同時必須還原備份）
rm -rf data
tar -xzf ccas-backup-<舊時間戳>.tar.gz

# 3) 改 .env 的 CCAS_VERSION 回舊版（換成你要回滾到的版號）
sed -i 's/^CCAS_VERSION=.*/CCAS_VERSION=<舊版號>/' .env

# 4) 重新啟動
docker compose -f docker-compose.yml pull
docker compose -f docker-compose.yml up -d
```

> ⚠️ 不建議**只**回滾 image 而不還原資料：minor / major 升級若已跑了 alembic
> migration，舊版 backend 連不到新 schema，會直接 crashloop。

---

## 自動化升級（cron / scheduler）

不建議在 prod 設「自動拉 floating tag」（`CCAS_VERSION=release`）+ 自動重啟，原因：

1. minor / major 升級可能含 alembic migration 或 spec 行為變動
2. 沒事先備份就升級 = 出狀況時無路可退
3. release floating tag 在 main push 時會更新；若你沒追 commit log，可能在意外時段拉到 unfinished work

建議：在 `.env` 釘精確版號（例：`v0.4.0`），手動排定升級時段。

---

## 常見升級問題

### Q: alembic migration 卡住或失敗

```bash
docker compose -f docker-compose.yml logs backend | grep -i alembic
```

若出現 schema 衝突或 lock：先停所有 service（`down`）、還原備份、查看 release notes
是否有額外 migration 步驟。

### Q: 升級後 frontend 顯示 404 / 白屏

清除瀏覽器 cache（新 frontend image 內 bundle 檔名含 hash，但 `index.html` 可能被 cache）。

### Q: Telegram bot 沒反應

bot 會在每次重啟時重新註冊；若 token 不變、bot logs 顯示 connected 即正常。bot 不
crashloop 設計：未填 `TELEGRAM_BOT_TOKEN` 時 idle，不影響其他 service。

---

## 路徑分流提醒

- 本指南為 **prod（pull-only）** 升級；用 `docker/docker-compose.yml`
- **dev** 升級走 `git pull` + 根目錄 `docker-compose.yaml`，與本文不同
- **prod self-build 中間路徑（`docker compose -f docker-compose.yaml up -d` 跳 override）已棄用**，若你還在用該路徑，請先依本指南遷移到 prod compose
