## Context

CCAS 的初始化流程涉及多個外部服務（Gmail OAuth、Telegram Bot）與內部設定（bank_configs、DB migration），新開發者需要手動執行 5+ 個步驟才能讓系統跑起來。目前沒有統一的入口或驗證機制，錯誤時也缺少明確指引。

已有的基礎設施：
- `ccas.config` 透過 pydantic-settings 從 `.env` 讀取所有環境變數
- `ccas.ingestor.auth` 已有 Gmail token 載入與 refresh 邏輯
- `ccas.storage.models.BankConfig` 已有 SQLAlchemy model
- Alembic migration 已建立完整 schema

## Goals / Non-Goals

**Goals:**
- 提供 `python -m ccas.tools.gmail_auth` 產生本地 OAuth token
- 提供 `python -m ccas.tools.bank_configs` 從 YAML 同步銀行設定到 DB
- 提供 `scripts/setup.sh` 一次性初始化（fail-fast，每步有明確錯誤訊息）
- 提供 `scripts/start.sh` 日常啟動
- 維護 `config/bank-code-registry.yaml` 作為 bank_code 的唯一權威來源
- 提供完整新手文件，從 clone 到前後端跑通

**Non-Goals:**
- 不提供 Docker-based 初始化（未來可加）
- 不自動申請 Gmail/Telegram 憑證（需人工操作）
- 不修改既有 `ccas.ingestor.auth` 的 token refresh 邏輯
- 不引入 GUI 或 interactive prompts（純 CLI + 腳本）

## Decisions

### D1: CLI 工具放在 `ccas.tools` 子模組

**選擇**: 新建 `backend/src/ccas/tools/` 模組，每個工具一個檔案。
**替代方案**: 放在 `scripts/` 作為獨立 Python 腳本。
**理由**: 放在 package 內可以直接 import ccas 的 config、models、auth 模組，且能用 `python -m ccas.tools.xxx` 執行，不需要處理 sys.path。

### D2: YAML 作為銀行設定的宣告式來源

**選擇**: 用 `config/banks.yaml` + `config/bank-code-registry.yaml` 兩層 YAML。
**替代方案**: 直接用 CLI flags 或 API endpoint 建立 bank_configs。
**理由**: YAML 可 version control、可 review、可複製。registry 作為 SSOT 防止使用者自創 bank_code。兩層分離讓 registry 由 repo 維護，banks.yaml 由使用者自訂。

### D3: Shell 腳本而非 Python CLI 作為頂層 orchestrator

**選擇**: `scripts/setup.sh` 和 `scripts/start.sh` 用 bash 撰寫。
**替代方案**: 用 Python click/typer CLI 統一入口。
**理由**: 腳本需要 source `.env`、呼叫 `uv sync`、`alembic upgrade head` 等 shell 操作，bash 最直接。fail-fast 語意 (`set -euo pipefail`) 適合線性初始化流程。

### D4: bank_configs sync 預設 dry-run

**選擇**: `--apply` flag 才真的寫入 DB，預設只做預覽。
**理由**: 防止使用者在 YAML 設定錯誤時意外覆蓋 DB 資料。setup.sh 先 dry-run 預覽再 --apply 寫入。

### D5: gmail_auth 複用既有 GMAIL_SCOPES

**選擇**: 從 `ccas.ingestor.auth.GMAIL_SCOPES` import scope 常數。
**理由**: 確保 CLI 工具與 runtime 使用相同的 OAuth scope，避免授權範圍不一致。

## Risks / Trade-offs

- **[bank-code-registry 維護成本]** 新增銀行需同時更新 registry YAML + docs/bank-codes.md → 用文件明確記載流程，未來可考慮自動產生 docs
- **[Shell 腳本跨平台]** bash 腳本在 Windows 原生環境無法執行 → 目標使用者預期使用 WSL/macOS/Linux，README 已標示前置需求
- **[pyyaml 新依賴]** 新增 runtime dependency → pyyaml 是成熟穩定的 library，風險極低
- **[OAuth 需要瀏覽器]** gmail_auth 在 headless 環境無法完成 OAuth → 文件說明需要桌面環境，server-only 環境需手動複製 token.json
