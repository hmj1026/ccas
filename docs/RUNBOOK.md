# CCAS Operational Runbook

此文件供正式環境維運使用。初次部署請先閱讀 [部署指南](deployment-guide.md)。

## 服務健康檢查

### 快速狀態確認

```bash
# 全部服務狀態
docker compose -f docker-compose.yaml ps

# Backend API
curl -s http://localhost:8000/health
# 預期回應: {"status":"ok"}

# Redis 可用性
docker compose -f docker-compose.yaml exec redis redis-cli ping
# 預期回應: PONG
```

### 逐服務檢查

<!-- AUTO-GENERATED: healthchecks — 由 docker/docker-compose.yml 抽出 -->

| 服務 | 檢查指令 | 正常狀態 |
|------|---------|---------|
| backend | `curl http://localhost:8000/health` | `{"status":"ok"}` |
| worker | `docker compose exec worker uv run rq info -u $REDIS_URL --raw -Q` | rc=0、列出 queue（rq 2.x 已無 `--quiet` flag） |
| scheduler | `docker compose exec scheduler test -f /data/scheduler-heartbeat && find /data/scheduler-heartbeat -mmin -1 \| grep -q .` | rc=0；heartbeat 檔 60s 內須更新 |
| bot | `docker compose logs bot --tail=20` | 無 ERROR 訊息 |
| redis | `docker exec ccas-redis-1 redis-cli ping` | `PONG` |
| frontend | `curl -I http://localhost:8080/` | `200 OK`（nginx 靜態 SPA） |

> Scheduler 主程式週期寫入 `SCHEDULER_HEARTBEAT_PATH=/data/scheduler-heartbeat`；若 healthcheck 反覆失敗，先檢查 scheduler container 的 stdout，再確認 `/data` volume 是否可寫入。

<!-- /AUTO-GENERATED -->

## 服務監控指標

### Redis 工作佇列

```bash
# 佇列深度與 worker 狀態
docker compose exec worker uv run rq info --url redis://redis:6379/0

# 查看特定 job
docker compose exec worker uv run rq job <job-id> --url redis://redis:6379/0
```

關注點：
- `queued` 數量持續增加 → worker 可能卡住
- `failed` 數量增加 → pipeline 出現錯誤，需查 logs

### Backend Logs

```bash
# 即時 logs（JSON 格式）
docker compose -f docker-compose.yaml logs -f backend

# 過濾 ERROR
docker compose -f docker-compose.yaml logs backend 2>&1 | grep '"level":"ERROR"'

# 過濾特定時間範圍
docker compose -f docker-compose.yaml logs backend --since=1h
```

若設定了 `LOG_DIR`，日誌同步寫入檔案：

```bash
# 檔案日誌位置（容器內，對應 host 的 ./logs/）
docker compose exec backend ls /logs/

# 讀取最新日誌
docker compose exec backend tail -f /logs/ccas.log
```

## 常見問題速查

### Pipeline 不執行 / 卡住

**症狀：** 排程到期但 pipeline 未執行，或 job 停在 `queued`

```bash
# 確認 worker 是否存活
docker compose ps worker

# 重啟 worker（rq 2.x 已不再支援 --quiet，預設 healthcheck 改用 `rq info --raw -Q`）
docker compose -f docker-compose.yaml restart worker

# 手動觸發 pipeline
docker compose exec backend uv run python -m ccas.pipeline --bank CTBC

# 強制重新處理特定月份
docker compose exec backend uv run python -m ccas.pipeline --force --bank CTBC --year 2026 --month 3
```

**從 UI 觸發與追蹤（pipeline-operations-center）：**

```bash
# 列出最近執行紀錄（status filter 可用 queued / running / succeeded / failed / cancelled）
curl -s -H "Authorization: Bearer $API_TOKEN" \
  "http://localhost:8000/api/pipeline/runs?limit=10"

# 查看單一 run 的 stage_summary（含 processed / total / errors）
curl -s -H "Authorization: Bearer $API_TOKEN" \
  "http://localhost:8000/api/pipeline/runs/<run_id>"

# 經 API 觸發（等同前端 /operations 頁）
curl -s -X POST -H "Authorization: Bearer $API_TOKEN" -H "Content-Type: application/json" \
  -d '{"bank_codes":["CTBC"],"force":true}' \
  "http://localhost:8000/api/pipeline/trigger"
```

> `pipeline_runs` 表記錄 stage_summary（JSON），由 `pipeline.progress.stage_finished()` 寫入；前端 `/operations` 頁短輪詢同一資料。

### SQLite database is locked / busy timeout

**症狀：** logs 出現 `sqlite3.OperationalError: database is locked` 或 pipeline stage 進度卡住但無明顯錯誤

**內建保護**（PR #6 / #11，2026-05-10 後）：
- 每個 SQLAlchemy connection 開啟時自動設 `PRAGMA busy_timeout=30000`（30 秒），避免 scheduler heartbeat / worker / backend GET 多寫者瞬間衝突
- `DbProgressReporter.stage_finished()` 對 `database is locked` 自動重試 3 次，backoff 0.1 / 0.5 / 2 秒（`pipeline/progress.py:_STAGE_FINISHED_*`）

**若仍頻繁出現**：
```bash
# 確認沒有外部 sqlite3 / sqlite-web 持鎖
docker compose ps sqlite-web        # dev-tools profile
docker compose exec backend lsof /data/ccas.db | head

# 確認 WAL 模式仍生效（應看到 -wal / -shm 檔）
docker compose exec backend ls -la /data/ccas.db*

# 切回 single-writer 重啟（暫時性紓困，會丟掉 in-flight RQ jobs）
docker compose -f docker-compose.yaml restart worker scheduler bot
```

如果是 schema migration 期間，請先 `docker compose stop worker scheduler bot` 讓 backend 獨佔 alembic upgrade，完成後再 start 其他服務。

### Gmail OAuth Token 過期

**症狀：** ingest 階段失敗，logs 顯示 `invalid_grant` 或 `Token has been expired`

```bash
# 確認 token 存在
docker compose exec backend ls /data/credentials.json /data/token.json

# 在本機重新執行 OAuth 流程
./scripts/setup.sh   # 選擇 Gmail 認證步驟

# 將新 token 複製到 volume
docker cp backend/data/token.json ccas-backend-1:/data/token.json
```

**或透過 Setup Wizard（前端 `/setup/gmail`）：**

1. 上傳 Google client secret JSON → `POST /api/setup/gmail/credentials`
2. 取得授權 URL → `GET /api/setup/gmail/authorize`
3. 完成授權後由 `GET /api/setup/gmail/callback` 自動寫回 token
4. 確認狀態 → `GET /api/setup/gmail/status`

`gmail_oauth_state` 表存放 PKCE state，redirect URI 由 `gmail_oauth_redirect_uri` 控制（local / docker / prod 各自的 PUBLIC_BASE_URL）。

### Redis 連線失敗

**症狀：** backend logs 顯示 `ConnectionError: Error 111 connecting to redis`

```bash
# 確認 Redis 容器
docker compose ps redis

# 重啟 Redis（注意：會清空記憶體中的 job queue）
docker compose -f docker-compose.yaml restart redis

# 確認 REDIS_URL 設定
grep REDIS_URL .env
```

### Backend 無法啟動 / Migration 失敗

**症狀：** backend 容器反覆重啟，logs 顯示 migration error

```bash
# 查看詳細錯誤
docker compose logs backend --tail=50

# 手動執行 migration
docker compose exec backend uv run alembic upgrade head

# 查看 migration 狀態
docker compose exec backend uv run alembic current
```

### API_TOKEN 找不到 / Web UI 無法登入

**症狀：** 不知道 API token 是什麼，或 `${CCAS_DATA_LOCATION}/secrets/api-token` 不存在

**內建行為**：entrypoint 在 backend 首啟時會自動生成 32-byte token 並落地至 `${CCAS_DATA_LOCATION}/secrets/api-token`（檔案權限 0600）。`.env` 不需設 `API_TOKEN`；若顯式設為空字串會被驗證腳本擋下。

```bash
# 1) 直接讀取自動生成的 token
docker compose exec backend cat /data/secrets/api-token

# 2) 從 host 端讀（CCAS_DATA_LOCATION 對應路徑）
cat "${CCAS_DATA_LOCATION:-./data}/secrets/api-token"

# 3) 不見時：確認 secrets 目錄寫入權限正常
docker compose exec backend ls -la /data/secrets/
docker compose exec backend stat /data/secrets/

# 4) 強制重新生成：刪除檔案後重啟 backend
docker compose exec backend rm /data/secrets/api-token
docker compose -f docker-compose.yaml restart backend
docker compose exec backend cat /data/secrets/api-token
```

> token 同時是 Web UI 登入憑證與 Bearer 認證；revoke 後請更新所有外部腳本與 reverse proxy。

### OCR 功能缺失

**症狀：** logs 顯示 `tesseract OCR 未安裝`，merchant 欄位空白

```bash
# 確認使用 production image（非 dev）
docker compose -f docker-compose.yaml build --no-cache backend

# 驗證 OCR 可用性
docker compose exec backend python -c \
  "from ccas.parser.ocr import is_ocr_available; print('OCR:', is_ocr_available())"
```

### FUBON Web-Fetch 失敗 / Captcha LLM Fallback 問題

**症狀：** ingest 階段 FUBON 失敗，logs 顯示 `CaptchaError`、`LoginError` 或 `anthropic` 相關錯誤

```bash
# 確認 FUBON 相關設定
grep FUBON .env
grep ANTHROPIC_API_KEY .env

# 查看 FUBON 詳細 logs
docker compose logs backend 2>&1 | grep -i fubon

# 若 FUBON_CAPTCHA_FALLBACK_LLM=true，確認 Anthropic API key 已設定
docker compose exec backend python -c \
  "from ccas.config import get_settings; s=get_settings(); print('anthropic key set:', bool(s.anthropic_api_key))"

# 停用 LLM fallback，回到純 OCR 模式（排查用）
# 編輯 .env: FUBON_CAPTCHA_FALLBACK_LLM=false
docker compose -f docker-compose.yaml restart backend
```

**常見原因：**
- `FUBON_NATIONAL_ID` / `FUBON_ROC_BIRTHDAY` 未填或格式錯誤（ROC 生日需 7 碼，例 `0881010`）
- `FUBON_CAPTCHA_FALLBACK_LLM=true` 但 `ANTHROPIC_API_KEY` 未設定 → LLM fallback 無法啟動
- 驗證碼重試超過 `FUBON_CAPTCHA_MAX_RETRIES`（預設 7）→ pipeline 放棄，需 manual staging
- SPA 自動化失敗時，可將 PDF 手動放入 `FUBON_MANUAL_STAGING_DIR`，下次 ingest 自動拾取

## 日誌分析

### JSON Log 格式

```json
{"timestamp":"2026-04-07T10:00:00","level":"INFO","message":"...","module":"..."}
```

常用過濾：

```bash
# 只看 ERROR
docker compose logs backend | python3 -c "
import sys, json
for line in sys.stdin:
    try:
        obj = json.loads(line)
        if obj.get('level') in ('ERROR', 'CRITICAL'):
            print(line.strip())
    except: pass
"

# 最近 100 行 pipeline 活動
docker compose logs backend --tail=100 | grep pipeline
```

### 排程器 Logs

```bash
docker compose logs scheduler --tail=50
```

正常輸出應包含每次排程執行的時間戳與結果。

## 回滾程序

### 應用程式版本回滾

```bash
# 確認要回滾的版本
git log --oneline -10

# 切換到目標版本
git checkout <commit-hash>

# 重建並重啟服務
docker compose -f docker-compose.yaml up --build -d
```

### 資料庫 Migration 回滾

```bash
# 查看 migration 歷史
docker compose exec backend uv run alembic history

# 回滾一個版本
docker compose exec backend uv run alembic downgrade -1

# 回滾到指定版本
docker compose exec backend uv run alembic downgrade <revision-id>
```

**注意：** downgrade 可能遺失資料。回滾前務必先備份。

### 緊急備份

```bash
# 備份資料庫（從 bind mount ./backend/data/）
mkdir -p backups
cp backend/data/ccas.db backups/ccas-$(date +%Y%m%d-%H%M%S).db

echo "Backup saved to backups/"
```

## Telegram 告警

CCAS Telegram Bot 傳送的通知類型：

| 告警類型 | 觸發條件 | 範例訊息 |
|---------|---------|---------|
| 帳單摘要 | Pipeline notify 階段完成 | 月結帳單金額、待繳項目 |
| 繳費提醒 | 距繳費日符合 `reminder_settings.days_before`（預設 `[3, 1]`） | 「CTBC 帳單將於 XX/XX 到期」|
| 預算超標 | `BudgetAlert` 觸發（current ≥ `alert_threshold_percent`） | 「Total / 餐飲 月度預算已達 85%」|

> 提醒策略可在前端 `/settings/reminders` 逐張帳單覆寫；預算與門檻在 `/settings/budgets` 維護。Backend dispatch：scheduler 週期性查表 → bot send → 寫入 `payment_reminders` 與 `budget_alerts`。

若需暫停 Telegram 通知（例如維護期間）：

```bash
# 方法 1：移除 TELEGRAM_BOT_TOKEN（重啟後生效）
# 編輯 .env，清空 TELEGRAM_BOT_TOKEN=
docker compose -f docker-compose.yaml restart bot

# 方法 2：停止 bot 服務
docker compose -f docker-compose.yaml stop bot
```

恢復通知：

```bash
docker compose -f docker-compose.yaml start bot
```
