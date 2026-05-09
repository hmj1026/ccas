## 1. Env 驗證

- [x] 1.1 建立 `scripts/check-env.sh`：從 `.env.example` 提取變數清單，區分 required/optional，逐一檢查 `.env`
- [x] 1.2 撰寫 `check-env.sh` 的手動測試案例（缺少 required、缺少 optional、檔案不存在）

## 2. 一鍵啟動（腳本模式）

- [x] 2.1 改造 `scripts/start.sh`：background 啟動 uvicorn + foreground 啟動 vite，trap SIGINT/SIGTERM 統一清理
- [x] 2.2 在 `start.sh` 啟動前呼叫 `check-env.sh`，驗證失敗則中止
- [x] 2.3 在 `start.sh` 加入 health check：輪詢 backend `/health` 和 frontend `localhost:5173`，逾時 30 秒警告

## 3. 一鍵啟動（Docker 模式）

- [x] 3.1 建立 `scripts/docker-entrypoint.sh`：執行 env 驗證 → alembic migrate → 啟動 uvicorn
- [x] 3.2 更新 `docker-compose.yaml` backend service 使用新 entrypoint

## 4. Pipeline 階段控制

- [x] 4.1 在 `pipeline/options.py` 的 `PipelineOptions` 新增 `from_stage: str | None` 和 `to_stage: str | None` 欄位
- [x] 4.2 定義 `STAGE_ORDER` 常數 tuple 於 `pipeline/orchestrator.py`
- [x] 4.3 新增 `_validate_stage_range()` 函式：驗證 from/to 合法性，回傳要執行的階段子集
- [x] 4.4 修改 `run_pipeline()` 使用階段子集而非固定五階段
- [x] 4.5 在 `pipeline/__main__.py` 新增 `--from` 和 `--to` CLI 參數
- [x] 4.6 更新 `PipelineOptions.to_dict()`/`from_dict()` 序列化新欄位
- [x] 4.7 撰寫 pipeline 階段控制的 unit tests（全範圍、部分範圍、單一階段、無效名稱、反序）

## 5. Parse 失敗結構化 logging

- [x] 5.1 修改 `parser/job.py` 的 `_process_attachment()`：失敗時 log 包含 `pdf_filename`、`bank_code`、`error_type`、`error_detail`
- [x] 5.2 `ParseError` 失敗時額外記錄 `missing_fields`
- [x] 5.3 在 `parser/registry.py` 加入 parser 選擇過程 logging（DEBUG: 每個嘗試；INFO: 最終匹配；WARNING: 全部失敗）
- [x] 5.4 撰寫 logging 的 unit tests（mock logger 驗證結構化欄位）

## 6. Seed Data 管理

- [x] 6.1 完善 `backend/scripts/seed.py`：確保可建立測試 Bill + Transaction 記錄
- [x] 6.2 新增 `--reset` flag：清除既有 seed 資料後重建

## 7. 文件重構

- [x] 7.1 建立 `docs/user-guide.md`：前置需求 → env 設定 → Gmail/Telegram → Docker 啟動 → Pipeline 執行 → 查看報表 → 故障排除
- [x] 7.2 建立 `docs/developer-guide.md`：前置需求 → clone + env → 架構總覽 → 腳本啟動 → 測試 → lint → DB migration → 貢獻指南
- [x] 7.3 刪除 `docs/beginner-setup-guide.md`
- [x] 7.4 更新 `CLAUDE.md` 中的文件引用（beginner-setup-guide → user-guide / developer-guide）
