## 緣由 (Why)

CCAS 的所有功能模組（gmail-ingestor、parser-engine、keyword-classifier、telegram-bot、frontend-dashboard）已在各自的 change 中獨立定義，但目前缺乏覆蓋完整流程的端對端測試、統一的例外階層、以及結構化日誌策略。在進入正式使用前，需要一個整合收尾 change，確保各模組串接無誤、錯誤能跨模組正確傳遞、日誌可觀測且不洩漏機敏資訊。

## 變更內容 (What Changes)

- 新增端對端測試套件，以 mocked 外部服務（Gmail API、Telegram API）搭配真實 SQLite 資料庫，驗證從 inbox 到通知的完整流程
- 定義共用例外階層（`CcasError` 基底類別與各模組子類別），統一跨模組錯誤訊息格式
- 新增結構化日誌策略：模組層級 logger、JSON 格式輸出、機敏資訊遮罩過濾器
- 補齊 staging 狀態機的完整生命週期測試（`staged -> decrypted -> parsed` 與錯誤分支）
- 新增整合驗證清單，確保所有模組可正常匯入、所有 migration 可正常套用、測試覆蓋率達標

## 能力範圍 (Capabilities)

### 新增能力 (New Capabilities)
- `e2e-pipeline-tests`: 以 mocked 外部服務搭配真實資料庫執行全流程端對端測試，驗證各 staging 狀態轉換與最終產出
- `error-handling-patterns`: 定義共用例外階層與結構化日誌策略，提供跨模組一致的錯誤處理與可觀測性基礎

### 修改能力 (Modified Capabilities)
(無 -- 沒有既有 capability 的 requirement 被修改)

## 影響範圍 (Impact)

- **測試**: `tests/e2e/`（新增端對端測試套件）
- **後端模組**: `core/exceptions.py`（新增共用例外階層）、`core/logging.py`（新增結構化日誌設定）
- **跨模組**: 所有現有模組需採用統一 logger 與例外類別
- **設定**: `Settings` 新增 `log_level` 與 `log_format` 欄位
