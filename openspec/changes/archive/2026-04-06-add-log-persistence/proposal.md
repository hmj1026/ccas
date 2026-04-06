## Why

目前 CCAS 的 logging 僅輸出至 stdout（`StreamHandler`），容器重啟或回收後日誌即消失，無法事後追蹤 pipeline 失敗原因、API 認證異常或排程任務執行歷程。在排查生產問題時只能依賴即時觀察，缺乏可回溯的日誌紀錄。此外 scheduler 模組使用 `basicConfig()` 繞過統一的 `configure_logging()`，造成格式不一致。

## What Changes

- 在 `configure_logging()` 中新增 `RotatingFileHandler`，將日誌同時寫入檔案
- 新增設定項：`LOG_DIR`（日誌目錄）、`LOG_FILE_MAX_BYTES`（單檔上限）、`LOG_FILE_BACKUP_COUNT`（保留份數）
- Docker Compose 掛載 logs volume，確保日誌在容器重啟後持久保存
- 修正 scheduler 模組改用 `configure_logging()` 統一日誌設定
- 提供 log rotation 機制避免磁碟空間無限成長

## Capabilities

### New Capabilities
- `log-persistence`: 涵蓋日誌檔案持久化、rotation 策略、目錄管理及 Docker volume 配置

### Modified Capabilities
- `docker-deployment`: 新增 logs volume mount 至所有服務
- `app-config`: 新增 LOG_DIR、LOG_FILE_MAX_BYTES、LOG_FILE_BACKUP_COUNT 設定項
- `developer-onboarding`: .env.example 新增日誌相關變數說明

## Impact

- **程式碼**: `backend/src/ccas/log.py`（核心變更）、`backend/src/ccas/config.py`（新設定項）、`backend/src/ccas/scheduler/__main__.py`（統一日誌設定）
- **基礎設施**: `docker-compose.yaml`（新增 volume）、`.env.example`（新增變數）
- **測試**: `backend/tests/unit/test_log.py` 需新增 file handler 與 rotation 測試
- **依賴**: 無新增外部依賴，使用 Python 標準庫 `logging.handlers`
