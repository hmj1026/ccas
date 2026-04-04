## Context

CCAS 目前僅使用 `StreamHandler` 將日誌輸出至 stdout。容器重啟後日誌即消失，無法追溯 pipeline 失敗、認證異常等事件。此外 scheduler 模組使用 `logging.basicConfig()` 繞過統一的 `configure_logging()`，格式與其他模組不一致。

現有架構：
- `backend/src/ccas/log.py`: `configure_logging()` → 單一 `StreamHandler`，支援 JSON/text 格式
- `backend/src/ccas/config.py`: `Settings` 類別，`log_level` 和 `log_format` 兩個日誌設定項
- `backend/src/ccas/scheduler/__main__.py`: 直接呼叫 `logging.basicConfig()`
- `docker-compose.yaml`: 無 logs volume，日誌隨容器生命週期消失

## Goals / Non-Goals

**Goals:**
- 日誌同時寫入 stdout 和檔案，容器重啟後可回溯
- 檔案自動 rotation 避免磁碟空間無限成長
- 統一所有模組（API、worker、scheduler、bot）使用 `configure_logging()`
- Docker 環境下 logs 透過 named volume 持久化
- 設定項可透過環境變數調整，不需重新建置映像

**Non-Goals:**
- 不做集中式 log aggregation（ELK、Loki 等）
- 不做 log DB 表或查詢 API
- 不變更現有 JSON/text 格式邏輯或 `RedactingFilter`
- 不做 log shipping 到外部服務

## Decisions

### D1: 使用 `RotatingFileHandler`（非 `TimedRotatingFileHandler`）

以檔案大小做 rotation（預設 10 MB / 5 份 = 最大 ~60 MB）。理由：
- 大小型 rotation 行為可預測，避免低流量日不切割、高流量日單檔過大
- 標準庫內建，零依賴

### D2: File handler 共用既有 formatter 和 filter

`RotatingFileHandler` 掛載與 `StreamHandler` 相同的 `JsonFormatter`/`TextFormatter` 和 `RedactingFilter`，確保機敏資訊遮罩在檔案中同樣生效。

### D3: 新增 3 個 Settings 欄位

| 欄位 | 環境變數 | 預設值 | 說明 |
|------|---------|--------|------|
| `log_dir` | `LOG_DIR` | `""` (空字串=停用) | 日誌目錄路徑 |
| `log_file_max_bytes` | `LOG_FILE_MAX_BYTES` | `10485760` (10 MB) | 單檔上限 |
| `log_file_backup_count` | `LOG_FILE_BACKUP_COUNT` | `5` | 保留備份數 |

`log_dir` 為空字串時不建立 file handler，行為與目前完全相同（向後相容）。

### D4: 日誌檔名固定為 `ccas.log`

放在 `log_dir` 下。Rotation 產生 `ccas.log.1`, `ccas.log.2`...。不以日期命名，簡化管理。

### D5: Scheduler 改用 `configure_logging()`

移除 `scheduler/__main__.py` 的 `logging.basicConfig()` 呼叫，改為 `configure_logging()`。

### D6: Docker volume 配置

```yaml
volumes:
  ccas-logs:

# 所有服務加入
volumes:
  - ccas-logs:/logs

# shared-env 加入
LOG_DIR: "/logs"
```

## Risks / Trade-offs

| 風險 | 緩解 |
|------|------|
| 多 container 同時寫同一 volume 下的 `ccas.log` 會衝突 | 每個服務寫入獨立檔案：以 service name 區分（`ccas-backend.log`、`ccas-worker.log` 等），透過程式自動偵測或環境變數 `LOG_FILE_PREFIX` 控制 |
| `log_dir` 目錄不存在時 handler 建立失敗 | `configure_logging()` 中使用 `Path.mkdir(parents=True, exist_ok=True)` 自動建立 |
| Rotation 中途程序崩潰可能損壞日誌檔 | `RotatingFileHandler` 已有內建 lock 機制；單一寫入者模式下風險極低 |
| 本地開發預設不啟用（`LOG_DIR=""`），需手動設定 | 符合預期：本地開發看 stdout 即可，Docker 環境透過 shared-env 統一配置 |
