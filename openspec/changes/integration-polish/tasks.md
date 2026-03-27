## 1. 共用例外階層

- [ ] 1.1 在 `core/exceptions.py` 定義 `CcasError(Exception)` 基底類別，包含 `message` 與可選 `context` 欄位
- [ ] 1.2 定義各模組子類別：`IngestError`、`DecryptError`、`ParseError`、`ClassifyError`、`NotifyError`，均繼承 `CcasError`
- [ ] 1.3 統一所有子類別的錯誤訊息格式（`[ModuleName] <描述>: <原因>`）
- [ ] 1.4 新增例外階層的單元測試，驗證繼承關係、`context` 欄位保存與訊息格式

## 2. 結構化日誌

- [ ] 2.1 在 `core/logging.py` 實作 `JsonFormatter`，輸出包含 `timestamp`、`level`、`logger`、`message` 的 JSON 格式日誌
- [ ] 2.2 實作 `RedactingFilter(logging.Filter)`，在輸出前以 `[REDACTED]` 遮罩 OAuth token、密碼與 credentials 路徑
- [ ] 2.3 提供 `configure_logging(level, format)` 入口函式，從 `Settings` 讀取 `log_level` 與 `log_format`，並將 filter 掛載至 root handler
- [ ] 2.4 在 `Settings` 新增 `log_level: str`（預設 `"INFO"`）與 `log_format: str`（預設 `"json"`）欄位
- [ ] 2.5 新增 `JsonFormatter` 輸出格式、`RedactingFilter` 遮罩行為、以及 `configure_logging` 整合的單元測試

## 3. 端對端 Pipeline 測試

- [ ] 3.1 建立 `tests/e2e/` 目錄，新增 pytest fixture，以 in-memory SQLite 資料庫初始化完整 DB schema
- [ ] 3.2 新增 E2E 測試：mock Gmail API 回傳包含 PDF 附件的候選郵件，驗證 staging record 正確建立（`status = staged`）
- [ ] 3.3 新增 E2E 測試：mock 解密流程成功，驗證 staging status 轉換至 `decrypted`
- [ ] 3.4 新增 E2E 測試：mock 解析流程成功，驗證 staging status 轉換至 `parsed`，並確認 `bills` 與 `transactions` 記錄正確建立
- [ ] 3.5 新增 E2E 測試：mock Telegram API 呼叫，驗證通知已送出且包含正確的帳單摘要資訊

## 4. 錯誤路徑測試

- [ ] 4.1 新增 E2E 測試：單一附件解密失敗（`status = decrypt_failed`），驗證同批次其他附件的解析流程不受中斷
- [ ] 4.2 新增 E2E 測試：單一附件解析失敗（`status = parse_failed`），驗證分類與通知流程繼續處理其餘已成功解析的帳單
- [ ] 4.3 新增 E2E 測試：Telegram 通知呼叫失敗，驗證錯誤被記錄至日誌，且整體 pipeline 不因此失敗
- [ ] 4.4 新增單元測試：驗證各模組在拋出模組專屬例外（`IngestError`、`DecryptError` 等）時，錯誤訊息格式符合規範

## 5. 整合驗證清單

- [ ] 5.1 確認所有模組（`ingestor`、`parser`、`classifier`、`notifier`、`core`）均可在無副作用的情況下正常 import
- [ ] 5.2 確認所有 Alembic migration 可從零套用至最新版本（`alembic upgrade head`）並無錯誤
- [ ] 5.3 確認 `uv run pytest` 全套測試通過，且覆蓋率達 80% 以上
- [ ] 5.4 確認 `uv run ruff check .` 與 `uv run pyright` 均無錯誤或警告
