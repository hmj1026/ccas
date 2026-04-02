## Context

CCAS 本地部署目前需要手動開兩個終端機分別啟動 backend 和 frontend，`.env` 驗證散落在 `setup.sh`（嚴格）和 `config.py`（寬鬆）之間不一致。Pipeline 只支援全量執行或 `--force` 強制重跑全部，無法指定階段。文件只有一份混合對象的新手指南。CTBC parser 的 ROC 格式將商戶名稱預設為空字串，但實際 PDF 中消費明細載要欄位是可提取的文字。

現有架構：
- 啟動：`scripts/start.sh`（只啟動 backend）+ `cd frontend && pnpm dev`（手動）
- Pipeline：5 階段循序執行（ingest → decrypt → parse → classify → notify），`PipelineOptions` 為 frozen dataclass
- CTBC parser：兩種格式（labeled/ROC），ROC 格式用 regex 逐行解析，merchant 欄位硬編碼 `""`
- 日誌：`JsonFormatter` + `RedactingFilter`，各模組用 `logging.getLogger(__name__)`

## Goals / Non-Goals

**Goals:**
- 開發者一條命令啟動 backend + frontend，啟動後自動 health check
- 使用者一條 `docker-compose up` 完成全部服務啟動
- 獨立 env 驗證命令，可被啟動腳本和 Docker entrypoint 呼叫
- Pipeline 支援 `--from`/`--to` 階段控制，可接續或只做單一範圍
- CTBC ROC 格式正確提取商戶名稱
- Parse 失敗有結構化 log（PDF 檔名、欄位、原因）
- 文件分為開發者版和使用者版

**Non-Goals:**
- 不引入 process manager（PM2、supervisord）或新的外部依賴
- 不改變 pipeline 的循序執行架構（不做並行化）
- 不修改資料庫 schema
- 不重寫整個 parser 框架，只修正 CTBC ROC 格式的商戶提取邏輯
- 不做 production deployment 自動化（本次只涵蓋本地開發/使用）

## Decisions

### D1: 一鍵啟動（腳本模式）— shell background + trap

改造 `scripts/start.sh`：background 啟動 uvicorn，foreground 啟動 vite dev server，`trap` SIGINT/SIGTERM 統一清理子程序。啟動後用 `curl` 輪詢 `/health` 和 `http://localhost:5173` 確認服務就緒。

**替代方案**：使用 `concurrently`（npm）或 `honcho`（Python）。
**否決原因**：增加外部依賴，且 shell trap 足夠簡單可靠。

### D2: 一鍵啟動（Docker 模式）— entrypoint wrapper

在 `docker-compose.yaml` 的 backend service 加入 `entrypoint` wrapper script，啟動前先執行 env 驗證。frontend service 已有 health check。使用者只需 `docker-compose up`。

**替代方案**：在 Dockerfile 的 CMD 中做驗證。
**否決原因**：entrypoint wrapper 更靈活，可獨立測試。

### D3: Env 驗證 — 獨立 `scripts/check-env.sh`

新增 `scripts/check-env.sh`，從 `.env.example` 提取所有 `KEY=` 行作為必要變數清單，逐一檢查 `.env` 是否存在。輸出缺漏列表並以非零 exit code 退出。可被 `start.sh`、`setup.sh`、Docker entrypoint 呼叫。

區分兩級變數：
- **REQUIRED**（缺少則 exit 1）：`API_TOKEN`、`TELEGRAM_BOT_TOKEN`、`TELEGRAM_CHAT_ID`
- **OPTIONAL**（缺少僅警告）：`LOG_LEVEL`、`REDIS_URL`、`VITE_API_BASE` 等有 default 的變數

**識別方式**：`.env.example` 中有值的為 optional（有預設），無值（`KEY=`）的為 required。

### D4: Pipeline 階段控制 — `--from`/`--to` 參數

在 `PipelineOptions` 新增 `from_stage: str | None` 和 `to_stage: str | None`。

定義階段順序常數：
```python
STAGE_ORDER: tuple[str, ...] = ("ingest", "decrypt", "parse", "classify", "notify")
```

`orchestrator.py` 中 `run_pipeline()` 根據 from/to 計算要執行的階段子集。未指定時預設全部執行（向後相容）。

`--force` 語意不變：在選定範圍內的 ingest 階段強制重新下載，parse 階段強制重新解析。

CLI 範例：
```bash
python -m ccas.pipeline --from decrypt --to classify   # 只跑 decrypt → parse → classify
python -m ccas.pipeline --from parse --force            # 從 parse 跑到 notify，強制重新解析
python -m ccas.pipeline --to parse                      # 只跑 ingest → decrypt → parse
```

**替代方案**：`--stage X --only`（只跑單一階段）。
**否決原因**：`--from`/`--to` 更靈活，能表達範圍；單一階段等同 `--from X --to X`。

### D5: CTBC 商戶名稱提取 — 修正 ROC regex 解析

目前 ROC 格式的 regex 只匹配數字欄位（日期、金額、卡號、幣別），商戶名稱文字在同一行或相鄰行但未被捕獲。

修正方式：擴展 `_extract_roc_transactions()` 的解析邏輯，在匹配交易數字行後，向前或向後搜尋相鄰的文字行作為 merchant name。具體策略需根據 pdfplumber 提取的文字佈局決定（消費明細載要欄位的文字位置）。

`TransactionItem.merchant` 從硬編碼 `""` 改為提取到的文字，提取失敗時 fallback 為 `""`（不影響整體 parse 流程）。

### D6: Parse 失敗結構化 logging

在 `parser/job.py` 的 `_process_attachment()` 中增強 error logging：
- 每次 parse 嘗試記錄：parser 名稱、bank_code、PDF 檔名
- 失敗時記錄：缺失欄位、錯誤類型、完整 traceback
- Parser 選擇過程記錄：registry 嘗試了哪些 parser、哪個匹配成功

使用 `logger.error()` 的 `extra` dict 傳遞結構化欄位，`JsonFormatter` 自動序列化。

### D7: 文件結構

| 文件 | 對象 | 內容 |
|------|------|------|
| `docs/user-guide.md` | 使用者（非開發者） | 前置需求 → env 設定 → Gmail/Telegram 設定 → 啟動（Docker）→ 執行 pipeline → 查看報表 → 故障排除。每步附完整指令。 |
| `docs/developer-guide.md` | 開發者 | 前置需求 → clone + env → 架構總覽 → 啟動（腳本模式）→ 測試 → lint → DB migration → 貢獻指南 |

`docs/beginner-setup-guide.md` 刪除。`CLAUDE.md` 中的文件引用更新。

### D8: Seed data 管理

完善現有 `backend/scripts/seed.py`，確保可透過 `uv run python backend/scripts/seed.py` 快速建立測試資料（bills + transactions）。加入 `--reset` flag 清除再重建。

## Risks / Trade-offs

| Risk | Mitigation |
|------|-----------|
| CTBC 商戶名稱在不同月份 PDF 中佈局不一致 | fallback 為空字串，不影響整體 parse；增加 logging 便於後續修正 |
| `start.sh` background 子程序管理在不同 shell 中行為差異 | 使用 POSIX-compatible trap + wait，避免 bash-only 語法 |
| `--from`/`--to` 跳過前置階段但 DB 無對應資料 | 文件說明：跳過 ingest 時需確保 staging 中已有 PDF；各階段空輸入時回傳零計數不報錯 |
| 刪除 beginner-setup-guide.md 為 breaking change | 新文件涵蓋所有原有內容，CLAUDE.md 同步更新引用 |
| env 驗證腳本的必要變數清單可能與 `config.py` 不同步 | 以 `.env.example` 為 SSOT，`config.py` 的 Pydantic 驗證為第二道防線 |
