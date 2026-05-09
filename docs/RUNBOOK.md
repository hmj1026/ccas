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

| 服務 | 檢查指令 | 正常狀態 |
|------|---------|---------|
| backend | `curl http://localhost:8000/health` | `{"status":"ok"}` |
| scheduler | `docker compose logs scheduler --tail=20` | 顯示 scheduled jobs |
| bot | `docker compose logs bot --tail=20` | 無 ERROR 訊息 |
| redis | `docker exec ccas-redis-1 redis-cli ping` | `PONG` |

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

# 重啟 worker
docker compose -f docker-compose.yaml restart worker

# 手動觸發 pipeline
docker compose exec backend uv run python -m ccas.pipeline --bank CTBC

# 強制重新處理特定月份
docker compose exec backend uv run python -m ccas.pipeline --force --bank CTBC --year 2026 --month 3
```

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
| 繳費提醒 | 距繳費日 ≤ 7 天 | 「CTBC 帳單將於 XX/XX 到期」|

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
