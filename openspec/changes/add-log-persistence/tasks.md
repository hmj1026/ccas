## 1. Settings 新增設定欄位

- [ ] 1.1 在 `backend/src/ccas/config.py` 的 `Settings` 類別新增 `log_dir: str = ""`、`log_file_max_bytes: int = 10_485_760`、`log_file_backup_count: int = 5` 三個欄位
- [ ] 1.2 在 `.env.example` 新增 `LOG_DIR`、`LOG_FILE_MAX_BYTES`、`LOG_FILE_BACKUP_COUNT` 說明與預設值

## 2. configure_logging() 增加 RotatingFileHandler

- [ ] 2.1 在 `backend/src/ccas/log.py` 的 `configure_logging()` 中，當 `settings.log_dir` 非空時建立 `RotatingFileHandler`
- [ ] 2.2 File handler 使用與 StreamHandler 相同的 formatter（JSON/text）和 `RedactingFilter`
- [ ] 2.3 使用 `Path(log_dir).mkdir(parents=True, exist_ok=True)` 自動建立目錄
- [ ] 2.4 新增 `log_file_prefix` 參數（預設 `"ccas"`），產生檔名 `{prefix}.log`，供多服務環境各自指定不同前綴

## 3. Scheduler 統一日誌設定

- [ ] 3.1 移除 `backend/src/ccas/scheduler/__main__.py` 的 `logging.basicConfig()` 呼叫
- [ ] 3.2 改為呼叫 `configure_logging()`，使 scheduler 與其他模組格式一致

## 4. Docker Compose 持久化配置

- [ ] 4.1 在 `docker-compose.yaml` 新增 `ccas-logs` named volume
- [ ] 4.2 在 `x-shared-env` 新增 `LOG_DIR: "/logs"`
- [ ] 4.3 所有服務（backend、worker、scheduler、bot）掛載 `ccas-logs:/logs`
- [ ] 4.4 各服務透過環境變數 `LOG_FILE_PREFIX` 設定獨立檔名（`ccas-backend`、`ccas-worker`、`ccas-scheduler`、`ccas-bot`）

## 5. 測試

- [ ] 5.1 在 `backend/tests/unit/test_log.py` 新增測試：`log_dir` 為空時不建立 file handler
- [ ] 5.2 新增測試：`log_dir` 非空時建立 `RotatingFileHandler` 並正確設定 maxBytes 和 backupCount
- [ ] 5.3 新增測試：file handler 掛載 `RedactingFilter`
- [ ] 5.4 新增測試：日誌目錄不存在時自動建立
- [ ] 5.5 新增測試：驗證 `log_file_prefix` 參數影響檔名
