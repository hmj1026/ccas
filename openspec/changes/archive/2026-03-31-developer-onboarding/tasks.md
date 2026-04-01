## 1. Tools module setup

- [x] 1.1 Create `backend/src/ccas/tools/__init__.py` module
- [x] 1.2 Add `pyyaml` to backend dependencies

## 2. Gmail OAuth CLI tool

- [x] 2.1 Implement `GmailAuthSetupError`, `AuthPaths` dataclass
- [x] 2.2 Implement `resolve_auth_paths()` with credentials 路徑驗證
- [x] 2.3 Implement `should_generate_token()` 判斷邏輯
- [x] 2.4 Implement `generate_token()` OAuth 流程 + token 寫入
- [x] 2.5 Implement `build_parser()` + `main()` CLI entry point
- [x] 2.6 Unit tests: resolve_auth_paths (success + failure), should_generate_token, generate_token (skip + run), main (exit codes)

## 3. Bank config sync CLI tool

- [x] 3.1 Implement `BankConfigValidationError`, dataclasses (`BankRegistryEntry`, `BankConfigSpec`, `SyncSummary`)
- [x] 3.2 Implement `_load_yaml_mapping()` with YAML 驗證
- [x] 3.3 Implement `load_bank_registry()` with bank_code 唯一性檢查
- [x] 3.4 Implement `load_bank_config_specs()` with registry 交叉驗證 + 正規化
- [x] 3.5 Implement `sync_bank_configs()` async upsert with dry-run support
- [x] 3.6 Implement `build_parser()` + `main()` + `_run_cli()` CLI entry point
- [x] 3.7 Unit tests: registry loading edges, config validation edges, sync upsert/unchanged/dry-run, main exit codes

## 4. Configuration files

- [x] 4.1 Create `config/bank-code-registry.yaml` (CTBC, CATHAY, ESUN)
- [x] 4.2 Create `config/banks.example.yaml` template

## 5. Shell scripts

- [x] 5.1 Create `scripts/setup.sh` with fail-fast validation + full init flow
- [x] 5.2 Create `scripts/start.sh` with dependency check + uvicorn startup

## 6. Documentation

- [x] 6.1 Create `docs/beginner-setup-guide.md` complete onboarding guide
- [x] 6.2 Create `docs/bank-codes.md` bank code reference table
- [x] 6.3 Update `README.md` with beginner guide links + script-based startup
- [x] 6.4 Update `.env.example` with new variables + relative paths
- [x] 6.5 Fix section 11 + 14: 前端環境變數指向根目錄 `.env`（非 frontend/.env.local）
