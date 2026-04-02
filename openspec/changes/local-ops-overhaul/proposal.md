## Why

CCAS 本地部署流程分散在多個腳本與終端機，pipeline 只支援全量重跑或 `--force` 強制重新下載/解析，缺乏階段級控制。文件僅有一份混合對象的新手指南，開發者與使用者的需求未分離。此外 CTBC 真實帳單的消費名稱可直接提取但目前被忽略，parse 失敗時也缺少結構化 log 協助排查。

## What Changes

### 啟動與環境
- 新增獨立 env 驗證腳本（`scripts/check-env.sh`），檢查 `.env` 所有必要變數，輸出缺漏警告
- 改造 `scripts/start.sh` 為一鍵啟動：同時啟動 backend (uvicorn) + frontend (vite dev)，啟動後自動 health check
- 優化 Docker Compose 流程：啟動前自動執行 env 驗證，使用者只需 `docker-compose up`
- 啟動後自動檢查 backend `/health` + frontend 是否回應正常

### Pipeline 彈性
- 新增 `--from <stage>` 參數：從指定階段開始執行到最後（預設從 ingest 開始）
- 新增 `--to <stage>` 參數：執行到指定階段停止（預設到 notify 結束）
- `--from` 和 `--to` 可組合使用，例如 `--from decrypt --to classify`
- `--force` 與階段控制配合：只重置指定範圍內的階段資料

### Parser 改進
- CTBC ROC 格式：提取消費明細載要欄位中的商戶名稱文字（不再預設空字串）
- Parse 失敗時輸出結構化 log：包含 PDF 檔名、失敗階段、缺失欄位、錯誤原因
- Parser 格式選擇過程加入 logging（哪個 parser 被嘗試、哪個匹配成功）

### 文件重構
- **BREAKING**: 刪除 `docs/beginner-setup-guide.md`
- 新增 `docs/user-guide.md`：使用者操作手冊，每步驟附完整指令
- 新增 `docs/developer-guide.md`：開發者環境設定、架構說明、貢獻指南

### 資料管理
- 完善 seed data 命令，提供快速建立/重置測試資料的能力

## Capabilities

### New Capabilities
- `local-dev-startup`: 一鍵啟動腳本（腳本模式 + Docker 模式）、env 驗證、startup health check
- `env-validation`: 獨立環境變數檢查命令，可被啟動腳本或 Docker entrypoint 呼叫
- `user-guide`: 使用者操作文件，面向非開發者，明確步驟指令
- `developer-guide`: 開發者環境設定、架構總覽、貢獻指南

### Modified Capabilities
- `pipeline-orchestration`: 新增 `--from`/`--to` 階段控制參數，per-stage force 語意
- `ctbc-parser`: ROC 格式商戶名稱提取（消費明細載要欄位文字提取）
- `error-handling-patterns`: parse 失敗結構化 logging（PDF 檔名、欄位、原因）

## Impact

- **Scripts**: `scripts/start.sh` 行為改變（從只啟動 backend → 同時啟動 frontend）；新增 `scripts/check-env.sh`
- **Pipeline CLI**: 新增 `--from`/`--to` 參數，不影響既有 `--force`/`--bank`/`--year`/`--month` 語意
- **Database**: 無 schema 變更
- **Docker**: `docker-compose.yaml` 加入 env 驗證 entrypoint，不影響現有 service 定義
- **文件**: beginner-setup-guide.md 刪除為 **breaking change**，CLAUDE.md 需更新文件引用
- **Parser**: ctbc_v1 output 變更（merchant 欄位從空字串 → 實際值），下游 classify 和 API 受益
- **Dependencies**: 無新增外部依賴
