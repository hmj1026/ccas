# CCAS 升級指南

本文件說明從現有版本升級至新版的步驟、相容性政策與回滾建議。

> **prod pull-only**（`docker/docker-compose.yml`）用下方「標準升級流程」。
> **dev（含原始碼 + Compose）** 走 `git pull` + `docker compose up -d --build`。
> **非 Docker**（uv + supervisord，無 Compose）走「非 Docker（uv + supervisord）升級」。

---

## TL;DR — 標準升級流程

```bash
cd ~/ccas    # 你 docker-compose.yml 所在的目錄

# 1) 修改 .env 的版本
sed -i 's/^CCAS_VERSION=.*/CCAS_VERSION=v0.8.5/' .env

# 2) 拉新 image 並重啟
docker compose -f docker-compose.yml pull
docker compose -f docker-compose.yml up -d

# 3) 驗證
curl -fsS http://localhost:${CCAS_PORT:-8080}/api/health
```

**alembic migration 會在 backend 容器啟動時自動執行**（entrypoint 已內建），不需手動跑。

---

## TL;DR — 非 Docker（uv + supervisord）升級

適用於沒有 Docker、以 `uv` 與 `host-services.sh --driver=supervisord` 常駐
api／worker／scheduler 的 host。Redis 啟動方式見
[`non-docker-agent-host.md`](non-docker-agent-host.md)（systemd、Homebrew，或
systemd-less `redis-server --daemonize`）。MCP PID 回收見
[`mcp-installation.md`](mcp-installation.md)。

```bash
cd /path/to/ccas
git fetch --tags
git checkout v0.8.5    # 改成目標 tag

cd backend
uv sync --frozen --extra supervisor
cd ..

# Redis：systemd / brew / daemonize，見 non-docker-agent-host.md
./scripts/host-services.sh --driver=supervisord install all
./scripts/host-services.sh --driver=supervisord smoke all

# MCP 由 host 管理；Restart 不夠，必須先殺殘留行程再重接
pgrep -af 'ccas-mcp-logging-wrapper|ccas-mcp'
pkill -f 'ccas-mcp-logging-wrapper|ccas-mcp' || true
# 然後在 MCP client Restart 或重新 Add：
# uv run --directory /absolute/path/to/ccas/backend ccas-mcp
# 依序：tools/list → get_payment_due → pipeline_status（timestamp 須帶 Z）
```

無 systemd 時 Redis 與 supervisord 重開機後都不會自己起來；開機 checklist 見
[`non-docker-agent-host.md`](non-docker-agent-host.md) 與
[`non-docker-host-services.md`](non-docker-host-services.md)。
`host-services.sh` 不會跑 alembic；有 schema 變更時先在 `backend/` 執行
`uv run alembic upgrade head`。v0.8.5 無資料庫 schema 變更。

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

## v0.8.5（Patch）— 2026-09-14 — systemd-less Redis 與 MCP 行程回收運維手冊強化

**適用對象**：v0.8.4 升級至 v0.8.5。無資料庫 schema 變更，不需執行 migration。

**運維手冊與非 Docker 部署強化**：
- 針對無 systemd 之 host 環境補齊 `redis-server --daemonize yes` 啟動路徑與重開機 checklist。
- 補充非 Docker MCP host 升級後之殘留行程回收（`pkill -f`）與重連驗證 SOP。
- 同步主幹版本與發布分支。

**升級後**：pull-only Docker 部署請使用 `CCAS_VERSION=v0.8.5`；非 Docker 環境請依手冊執行行程回收與重啟。

---

## v0.8.4（Patch）— 2026-09-14 — FUBON 驗證碼閘門與 CI 穩定性修正

**適用對象**：v0.8.3 升級至 v0.8.4。無資料庫 schema 變更，不需執行 migration。

**驗證碼與 CI**：
- FUBON 驗證碼評估器同時檢查最低接受率、辨識正確率與 false positive，避免樣本幾乎全被拒絕時仍因「接受樣本 100% 正確」而錯誤通過。
- 將真實 ONNX 驗證碼 fixture gate 保留在專用 integration job，並固定 CI runner／CPU 拓撲以降低模型執行環境差異造成的誤報。
- 正式 OCR confidence gate 維持不變。

**升級後**：pull-only Docker 部署請使用 `CCAS_VERSION=v0.8.4`。

---

## v0.8.3（Patch）— 2026-09-14 — Dockerfile 動態版號構建修復與發布對齊

**適用對象**：v0.8.1 或 v0.8.2 升級至 v0.8.3。無資料庫 schema 變更，不需執行 migration。

**Docker 部署與構建**：
- 修復 `backend/Dockerfile` 在 `builder` 階段缺少 `src/` 導致 Hatchling 解析動態版號失敗的問題。
- 整合 v0.8.2 之 Agent MCP datetime UTC RFC3339 `Z` 格式與跨層 metadata 一致性。

**升級後**：pull-only Docker 部署請使用 `CCAS_VERSION=v0.8.3`。

---

## v0.8.2（Patch）— 2026-09-14 — Agent MCP datetime contract 與版本 metadata 修正

**適用對象**：v0.8.1 升級至 v0.8.2。無資料庫 schema 變更，不需執行 migration。

**Agent MCP／CLI**：
- Agent DTO 的 datetime 統一以 UTC RFC3339 `Z` suffix 輸出，既有 SQLite naive timestamp
  在讀取時視為 UTC。
- MCP、CLI 與 API runtime metadata 使用同一個 package version source，serverInfo
  version 對齊 `0.8.2`。

**Host troubleshooting**：
- 若 host 顯示 MCP connected／tools=6，但 tools/call 在 JSON-RPC 前回報
  `Not connected`，或 Restart 後仍跑舊碼，請依
  [`mcp-installation.md`](mcp-installation.md) 殺掉殘留 PID 再 Add／Restart。
- 若 host 已收到 response 但回報 `-32602 date-time`，請確認已升級至 v0.8.2 並走
  同一份 PID 回收 SOP；不要只 Restart。

**升級後**：pull-only Docker 部署請使用 `CCAS_VERSION=v0.8.2`；非 Docker MCP host
  不需 Redis 才能查詢，但升級後必須回收 MCP 子行程，見
  [`mcp-installation.md`](mcp-installation.md)。

---

## v0.8.1（Patch）— 2026-09-14 — Supervisord 宿主常駐驅動、API 服務管理與 Agent 規格同步

**適用對象**：v0.8.0 升級至 v0.8.1。無資料庫 schema 變更，不含破壞性變更。

**非 Docker 宿主常駐服務（Host Services）**：
- **Supervisord 常駐驅動**：新增第三種常駐驅動 `supervisord`，為無 systemd user bus 的 Linux 環境（如容器化或限制 init 的 host）提供第一方 fallback。純 Python 實作、無需 root 權限。
- **API 服務常駐管理**：`supervisord` 驅動正式納入 `api` (uvicorn) 服務管理，提供正式 production 啟動參數與 HTTP readiness smoke check。
- **統一驅動契約架構**：重構 `host-services.sh` 平台邏輯為統一的 driver 契約（`systemd`、`launchd`、`supervisord`），各自宣告能力並提供完整生命週期操作（install、uninstall、status、restart、is_running）。

**OpenSpec 規格與索引同步**：
- **Agent 規格歸檔**：同步已歸檔之 `agent-cli-interface`、`agent-mcp-interface` 與 `reconciliation-identity` 規格文件，補齊 stdio MCP / CLI 唯讀介面與對帳查詢規格。
- **GitNexus 索引**：同步最新程式碼拓撲分析指標。

**升級後**：pull-only Docker 部署請使用 `CCAS_VERSION=v0.8.1`，無資料庫 migration；非 Docker 部署如需使用 supervisord 可參考 `docs/non-docker-host-services.md`。

---

## v0.8.0（Minor）— 2026-09-13 — 帳單解析管線強化、結構化詮釋資料與資料庫遷移

**適用對象**：v0.7.1 升級至 v0.8.0。包含 alembic migration（`d4e7f2a1b9c3_add_bill_parse_metadata`），不含破壞性變更。升級前建議備份 `${CCAS_DATA_LOCATION}`。

**帳單解析管線（Bill Parsing Pipeline）**：
- **三層解析與信心度管理**：提供 Rules 規則引擎、OCR 文字辨識與選用 LLM 參考輔助三層架構，具備確定性（deterministic）信心度評估與跨視角回退機制。
- **解析結果合約與 Schema**：新增 `schemas/bill_parse_result.schema.json` 結構契約與驗證工具，規範各層解析來源與結構化資料。
- **Golden Fixtures 測試覆蓋**：新增 rules-only、ocr-fallback、llm-assisted、low-confidence 與 failed 等完整 golden 測試案例。

**資料庫與儲存**：
- **帳單詮釋資料（Metadata）**：`bills` 資料表新增 `parse_source`、`parse_confidence` 與 `parse_metadata` 欄位，由 migration 自動補齊既有資料預設值。

**驗證碼與穩定度**：
- **FUBON 驗證碼辨識**：進一步收緊並微調 FUBON 驗證碼信心度閘門，消除 CI 與正式環境的偶發邊界問題。

**升級後**：pull-only Docker 部署請使用 `CCAS_VERSION=v0.8.0`，容器啟動時 entrypoint 會自動執行資料庫 migration。

---

## v0.7.1（Patch）— 2026-09-13 — FUBON 驗證碼測試與非 Docker 維運補強

**適用對象**：v0.7.0 升級至 v0.7.1。無資料庫 schema 變更，不含破壞性變更。

**MCP 與維運**：
- **MCP 錯誤契約**：工具執行錯誤維持 `isError=true` 與 JSON `TextContent`，不再把錯誤 payload 放入成功 `structuredContent` schema。
- **非 Docker background services**：新增 worker／scheduler 的 Linux systemd user service 與 macOS launchd 管理腳本，包含 restart 與 smoke check；此路徑使用主機 Redis。
- **Docker Redis**：Docker Compose 部署仍使用 Compose 管理的 Redis container，無需安裝 host Redis。

**FUBON 驗證碼**：
- 新增 deterministic HTTP/OCR/retry/PDF end-to-end 測試。
- 將 45 個 CAPTCHA fixture 的辨識率 gate 納入 CI，最低門檻維持 80%。

**升級後**：pull-only Docker 部署請使用 `CCAS_VERSION=v0.7.1`，不需要手動執行資料庫 migration。

---

## v0.7.0（Minor）— 2026-09-12 — Agent CLI 與 MCP 唯讀介面、對帳架構與管線狀態升級

**適用對象**：v0.6.2 升級至 v0.7.0。包含 alembic migration（`b72e619af430_add_pipeline_terminal_reason`），不含破壞性變更。

**Agent CLI 與 MCP 伺服器**：
- **唯讀介面**：新增 `ccas agent` CLI 指令與標準 Model Context Protocol (MCP) 伺服器，支援外部代理讀取帳單、交易、預算與管線狀態。
- **對帳與領域語彙 (ADR 0001)**：建立外部代理與 Notion 信任邊界架構決策紀錄，導入穩定識別鍵 (Reconciliation identity) 機制。
- **安裝與整合指南**：新增 `docs/mcp-installation.md` 提供完整 MCP 設定與使用指引。

**管線與資料庫**：
- **管線終止原因追蹤**：Alembic 遷移新增 `pipeline_runs.terminal_reason` 欄位，精準記錄管線終止、失敗或中止原因。

**Harness 與規格對齊**：
- **DHPK 執行期對齊**：移除已追蹤的失效 Codex 技能符號連結，全面對齊 DHPK v0.58.0 執行期規格並加入防禦性測試。

**升級後**：容器啟動時自動套用 alembic migration，無額外手動步驟。

---

## v0.6.2（Patch）— 2026-09-10 — 架構圖資更新、Agent 協作規範與忽略規則維護

**適用對象**：v0.6.1 升級至 v0.6.2。alembic schema 不變，不含破壞性變更。

**規格與架構圖資**：
- **架構地圖與現行實作總覽**：新增 `docs/CODEMAPS/current-implementation.md` 現行實作總覽，並全面更新整體架構地圖與領域上下文 (`CONTEXT.md`)。
- **模組深度規格**：歸檔 `deepen-codebase-architecture`，並新增 Gmail 連線管理、帳單收取流程 (Intake)、Pipeline 生命週期與交易編輯深度規格。
- **開發指南對齊**：更新開發手冊、Runbook 與 README，統一對齊測試覆蓋率門檻與部署設定。

**Agent 與 Harness 維護**：
- **Agent 規範配置**：配置 Agent 協作規範、議題追蹤指引與更新規格配置。
- **忽略規則調整**：精細化 `.gitignore` 配置，忽略外部安裝之 Agent 技能與工具生成目錄（`.agents/skills/`、`.agent/`、`.codex/`、`.cursor/`），保留倉庫外掛描述檔。

**升級後**：無額外手動步驟。

---

## v0.6.1（Patch）— 2026-07-15 — 功能增強與架構重構

**適用對象**：v0.6.0 升級至 v0.6.1。alembic schema 不變，不含破壞性變更。

**功能增強與修復**：
- **交易編輯與 Hook 機制**：前端實作交易編輯功能，支援編輯備註與標籤，並加入 Hook 觸發更新。
- **Gmail 連線管理 API**：後端實作 Gmail 連線狀態監控與 API 設定路由，增強對 Gmail 連線健康狀態的控制。
- **系統初始化腳本**：支援在本地設定檔缺失時，由 `setup.sh` 自動複製範本檔案，降低新環境的佈署門檻。

**架構重構與優化**：
- **Pipeline 生命週期管理**：抽離與重構 Pipeline 任務狀態管理，增強狀態轉移時的防禦性邏輯。
- **Parser 職責重構**：抽離 Ingestor/Parser 職責，明確區分帳單下載/收取 (Intake) 與解析 (Parse) 的責任邊界，並增加其單元測試覆蓋率。
- **依賴套件更新**：替換遭 yanked 的 `pydantic-extra-types` 並升級 `pyright` 靜態分析工具。

**升級後**：無額外手動步驟。

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

- **prod（pull-only）**：`docker/docker-compose.yml`，用本文件開頭的標準升級流程
- **dev Compose**：`git pull` + 根目錄 `docker-compose.yaml`，與 prod 不同
- **非 Docker uv + supervisord**：用本文件「非 Docker（uv + supervisord）升級」；
  Redis 與 MCP PID 回收分別以 agent-host、mcp-installation 為 SSOT
- **prod self-build 中間路徑（`docker compose -f docker-compose.yaml up -d` 跳 override）已棄用**，若你還在用該路徑，請先依本指南遷移到 prod compose
