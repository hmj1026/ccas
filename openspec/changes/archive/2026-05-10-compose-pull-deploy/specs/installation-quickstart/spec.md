## ADDED Requirements

### Requirement: 純 pull 模式 compose 檔案發布

系統 SHALL 在版本庫提供 `docker/docker-compose.yml`，該檔案 SHALL 僅使用 `image:` 引用 GHCR 上的 image，**不得包含任何 `build:` 區塊**。所有 CCAS-managed service（backend、worker、scheduler、bot、frontend、proxy）的 image tag SHALL 透過 `${CCAS_VERSION:-release}` 變數解析。

#### Scenario: 使用者下載 compose 檔即可 pull

- **WHEN** 使用者在乾淨目錄僅放置 `docker/docker-compose.yml` 與對應 `.env`，執行 `docker compose pull`
- **THEN** docker SHALL 從 GHCR 成功拉取所有 service 的 image，過程不需任何原始碼

#### Scenario: 缺 CCAS_VERSION 時使用預設 release tag

- **WHEN** `.env` 未設定 `CCAS_VERSION`
- **THEN** compose SHALL 解析為 `release` tag 並成功 pull

#### Scenario: 開發者使用根目錄 compose 不受影響

- **WHEN** 開發者執行 `docker compose up`（讀取根目錄 `docker-compose.yaml`）
- **THEN** 既有 `build:` 行為 SHALL 維持不變，本機 build 流程不被破壞

### Requirement: 對外發布的 .env 範本

系統 SHALL 在版本庫提供 `docker/example.env`，作為純 pull 模式對應的 `.env` 範本。該範本 SHALL 包含啟動所需所有變數，每個變數 SHALL 標示「必填 / 選填」、附 inline 註解說明用途與安全注意事項。

#### Scenario: 使用者複製 example.env 即可填寫

- **WHEN** 使用者執行 `cp docker/example.env .env` 並填入必填變數值
- **THEN** `.env` SHALL 足以讓 `docker compose up -d` 成功啟動所有 service

#### Scenario: 範本含版本與資料路徑變數

- **WHEN** 檢視 `docker/example.env`
- **THEN** 該檔 SHALL 至少包含 `CCAS_VERSION`、`CCAS_DATA_LOCATION`、`CCAS_CONFIG_LOCATION`、`CCAS_LOG_LOCATION` 四個 immich 風格變數，每個皆有預設值與註解

### Requirement: 六步驟安裝體驗（含 Gmail 前置設定）

系統 SHALL 提供 `docs/install-quickstart.md`，描述使用者從零到啟動的六步驟流程：(0) **完成 Gmail OAuth 前置設定**（連結至 `docs/gmail-setup.md`，取得 `credentials.json`），(1) 下載 `docker-compose.yml` 與 `example.env`，(2) 複製為 `.env` 並填入必填變數（`API_TOKEN` 可留空交由 entrypoint 自動產生；Telegram 欄位填妥後會自動啟用 bot，不需要 `--profile`），(3) 放置 Gmail `credentials.json` 至 data 目錄、放置 `token.json` 或預期啟動後手動取得，(4) 執行 `docker compose pull`，(5) 執行 `docker compose up -d`，並從 `${CCAS_DATA_LOCATION}/secrets/api-token` 取得自動產生的 API token。文件 SHALL 包含每步的驗證方法（如 `docker compose ps` 預期輸出、`curl http://localhost:${CCAS_PORT}/api/health` 端點檢查）。文件 SHALL **不得**使用「一鍵安裝」「無需設定」「即裝即用」等措辭，必須誠實揭露 Gmail OAuth 為使用者必須完成的前置步驟。

#### Scenario: 步驟 0 為 Gmail 前置設定章節

- **WHEN** 檢視 `docs/install-quickstart.md`
- **THEN** 文件 SHALL 在步驟 1 之前明示 Gmail OAuth 設定為前置條件，並連結至 `docs/gmail-setup.md`

#### Scenario: 使用者依文件可在 10 分鐘內完成步驟 1-5

- **WHEN** 一名熟悉 docker 但不熟 CCAS 的使用者**已完成步驟 0**，依 install-quickstart.md 操作步驟 1-5
- **THEN** 從下載到看到 proxy 的 `/api/health` 回 200，總耗時 SHALL 不超過 10 分鐘（不計 image 下載時間）

#### Scenario: 文件含 healthcheck 驗證指令

- **WHEN** 使用者完成第 5 步
- **THEN** 文件 SHALL 提供具體驗證指令（如 `docker compose ps`、`curl http://localhost:${CCAS_PORT:-8080}/api/health`）並描述預期輸出；backend 直連 port 不再列為 troubleshooting 路徑

#### Scenario: 文件揭露 API_TOKEN 自動產生機制

- **WHEN** 使用者完成第 5 步未在 `.env` 設定 `API_TOKEN`
- **THEN** 文件 SHALL 指引使用者從 `${CCAS_DATA_LOCATION}/secrets/api-token` 取得自動產生的值，並說明該檔權限應為 0600

#### Scenario: 文件指引使用者完成首次登入

- **WHEN** 使用者完成第 5 步、服務已啟動、需要首次登入 Web UI
- **THEN** 文件 SHALL 提供具體三步驟指令片段：(1) `cat "${CCAS_DATA_LOCATION:-./data}/secrets/api-token"` 取得 token、(2) 開瀏覽器至 `http://localhost:${CCAS_PORT:-8080}/login`、(3) 將 token 貼入欄位提交，使用者 SHALL 看到 dashboard，全程不需要查看 backend log 或執行其他 docker 指令

### Requirement: Gmail OAuth 設定文件

系統 SHALL 提供 `docs/gmail-setup.md`，描述使用者於 Google Cloud Console 完成 Gmail OAuth 設定的完整步驟：(1) 建立 GCP project、(2) 啟用 Gmail API、(3) 設定 OAuth consent screen、(4) 加入 test user（自己的 Gmail 帳號）、(5) 建立 OAuth Desktop client 並下載 `credentials.json`、(6) 取得 `token.json`（CLI 或未來 Web UI 兩種方式）。文件 SHALL 包含步驟編號、預期 UI 標籤名稱、可能踩到的常見錯誤（如 `redirect_uri_mismatch`）與排查方式。

#### Scenario: 文件覆蓋完整 Cloud Console 操作

- **WHEN** 一名未操作過 GCP 的使用者依 `gmail-setup.md` 完成
- **THEN** 使用者 SHALL 取得可用的 `credentials.json` 與 `token.json`，且過程中遇到的每個 GCP 介面標籤皆對應到文件描述

#### Scenario: 文件記錄 CLI 取得 token 的限制

- **WHEN** 檢視 `gmail-setup.md` 的 CLI 取得 token 章節
- **THEN** 文件 SHALL 明示此 flow 需在 host 機器（非 container）執行，因依賴 `localhost` callback；並承諾未來 `oauth-onboarding-ui` change 將提供 Web UI 取代

### Requirement: 升級指南文件

系統 SHALL 提供 `docs/upgrade-guide.md`，描述從一個版本升級到下一版本的標準流程，至少包含：(1) 修改 `.env` 的 `CCAS_VERSION`，(2) 執行 `docker compose pull`，(3) 執行 `docker compose up -d`，(4) 觀察 alembic migration log。文件 SHALL 說明版本相容性政策（同 major 不破壞、major 升級需查 CHANGELOG）。

#### Scenario: 升級指令為單行可重複執行

- **WHEN** 使用者依升級指南執行 `docker compose pull && docker compose up -d`
- **THEN** alembic migration SHALL 自動執行，使用者資料 SHALL 完整保留，重複執行同一指令 SHALL 為冪等（不報錯、不重複 migrate）

#### Scenario: 文件記錄破壞性變更政策

- **WHEN** 檢視 upgrade-guide.md
- **THEN** 文件 SHALL 明確說明：major 版本升級可能含破壞性變更、必須先閱讀 CHANGELOG，且 minor / patch 升級保證向後相容

### Requirement: 容器啟動時自動初始化 config seed

系統 SHALL 在 `scripts/docker-entrypoint.sh` 啟動流程中，於 alembic migration 之前檢查 `${CCAS_CONFIG_LOCATION}/banks.yaml`、`bank-code-registry.yaml`、`categories.yaml` 是否存在；若任一檔不存在，SHALL 從同目錄下對應的 `*.example.yaml` 複製一份。複製動作 SHALL 在 stdout 輸出顯著的 WARN 訊息提示使用者該 config 為預設值、建議檢視。

#### Scenario: 首次啟動自動複製 config

- **WHEN** `${CCAS_CONFIG_LOCATION}` 目錄內無 `banks.yaml` 但有 `banks.example.yaml`
- **THEN** entrypoint SHALL 複製 `banks.example.yaml` 為 `banks.yaml`，stdout 輸出 `[WARN] config/banks.yaml 不存在，已從 example 複製預設值，請檢視並依需求調整`

#### Scenario: 既有 config 不被覆蓋

- **WHEN** `${CCAS_CONFIG_LOCATION}/banks.yaml` 已存在
- **THEN** entrypoint SHALL 不執行任何複製動作，既有檔案內容完整保留

#### Scenario: example 缺失時 fail-fast

- **WHEN** `banks.yaml` 與 `banks.example.yaml` 均不存在
- **THEN** entrypoint SHALL 以非零 exit code 退出，錯誤訊息指出 config 目錄掛載異常

### Requirement: Telegram bot 為選用 service

系統 SHALL 將 Telegram bot 視為預設存在但可 disabled 的 integration service。使用者未設定 `TELEGRAM_BOT_TOKEN` 時 SHALL 不影響其他 service 啟動；使用者設定 `TELEGRAM_BOT_TOKEN` 與必要 chat / allowlist 資訊後，Telegram 功能 SHALL 自動可用，不需要額外 compose profile。`docs/install-quickstart.md` SHALL 在 Telegram 段落明示「未填 token 時會 disabled；填妥後重新 `docker compose up -d` 即啟用」。

#### Scenario: 不啟用 Telegram 仍可完整使用

- **WHEN** 使用者完整跑完 quickstart 但未設定 `TELEGRAM_BOT_TOKEN`
- **THEN** backend、worker、scheduler、frontend、proxy 全數正常啟動，bot 以 disabled 狀態存在且不 crashloop，使用者可透過 Web UI 操作所有功能（除 Telegram 通知外）

#### Scenario: 填妥 Telegram 後不需 profile

- **WHEN** 使用者在 `.env` 填妥 `TELEGRAM_BOT_TOKEN`、`TELEGRAM_CHAT_ID`、`TELEGRAM_ALLOWED_CHAT_IDS` 後執行 `docker compose up -d`
- **THEN** bot SHALL 自動連線 Telegram 並可發送通知，不需要使用者執行 `docker compose --profile telegram up -d`

### Requirement: 首次登入 UX 完整路徑

`docs/install-quickstart.md` SHALL 含獨立「首次登入」章節，將 D11 自動產生的 `${CCAS_DATA_LOCATION}/secrets/api-token` 與前端 `/login` 頁串接成完整使用者旅程。文件 SHALL 涵蓋兩條路徑：(a) 使用者未在 `.env` 設定 `API_TOKEN` 時從 secrets 檔取得、(b) 使用者已自行設定 `API_TOKEN` env 時直接使用該值。兩條路徑均指向同一個 `/login` 頁。

#### Scenario: 自動產生 token 路徑有完整指令片段

- **WHEN** 使用者依文件「首次登入」章節操作、`.env` 未設定 `API_TOKEN`
- **THEN** 文件 SHALL 提供連續三步驟指令片段（取 token、開瀏覽器、貼上）並描述每步預期輸出（如 64 字元 hex 字串、`/login` 頁面截圖描述、登入後 redirect 至 dashboard）

#### Scenario: 自設 token 路徑指向同一登入頁

- **WHEN** 使用者於 `.env` 自行設定 `API_TOKEN=<custom>` 並完成 `up -d`
- **THEN** 文件 SHALL 明示「直接以 `.env` 中設定的 token 值貼到 `/login` 頁」，不需要再從 secrets 檔取得；UX 入口 SHALL 為同一 `/login` 頁

#### Scenario: 文件揭露 token 即 session 入口的設計

- **WHEN** 使用者閱讀「首次登入」章節
- **THEN** 文件 SHALL 簡述 CCAS 採「API token 即 Web UI 登入憑證」設計（無 username/password、無 admin bootstrap wizard），並轉述 `oauth-onboarding-ui` 後續 change 將提供 admin / token rotate UI

### Requirement: 誠實揭露目前仍需手動編輯的設定

`docs/install-quickstart.md` SHALL 在「設定 .env」步驟章節明示目前仍需使用者手動編輯的兩類設定：(1) `PDF_PASSWORD_*` env 變數（各銀行 PDF 解密密碼），(2) `banks.yaml` 啟用清單（停用某銀行需手動編輯該 yaml）。文件 SHALL 不使用「無需設定」「全自動」「pull 即用」等誤導措辭；UI 化承諾 SHALL 轉述至 `oauth-onboarding-ui` 後續 change。

#### Scenario: 文件明示 PDF 密碼為手動填入

- **WHEN** 使用者閱讀「設定 .env」步驟
- **THEN** 文件 SHALL 明示 `PDF_PASSWORD_*` 變數需依各使用者實際銀行 PDF 密碼填入，並提供「如何取得 PDF 密碼」連結（依各銀行帳單 PDF 規則）

#### Scenario: 文件明示 banks.yaml 啟用清單需手動編輯

- **WHEN** 使用者閱讀「設定 .env」步驟或「config」相關章節
- **THEN** 文件 SHALL 明示 `banks.yaml` 預設啟用全部支援銀行、若要停用某銀行需手動編輯該 yaml；同時轉述「未來 `oauth-onboarding-ui` change 將提供 UI 取代手動編輯」

#### Scenario: 措辭審查禁止誤導語

- **WHEN** code review `install-quickstart.md` 與 README「30 秒安裝」段落
- **THEN** 文件 SHALL 不含「一鍵安裝」「無需設定」「全自動」「pull 即用」等措辭；改為「快速安裝（已完成 Gmail 設定與 PDF 密碼後）」「30 秒啟動服務」等誠實描述
