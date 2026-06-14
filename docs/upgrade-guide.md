# CCAS 升級指南

本文件說明從現有版本升級至新版的步驟、相容性政策與回滾建議。

> 本指南僅適用於 prod pull-only 部署（`docker/docker-compose.yml`）。dev（含原始碼）
> 升級請走 `git pull` + `docker compose up -d --build`。

---

## TL;DR — 標準升級流程

```bash
cd ~/ccas    # 你 docker-compose.yml 所在的目錄

# 1) 修改 .env 的版本
sed -i 's/^CCAS_VERSION=.*/CCAS_VERSION=v0.3.0/' .env

# 2) 拉新 image 並重啟
docker compose -f docker-compose.yml pull
docker compose -f docker-compose.yml up -d

# 3) 驗證
curl -fsS http://localhost:${CCAS_PORT:-8080}/api/health
```

**alembic migration 會在 backend 容器啟動時自動執行**（entrypoint 已內建），不需手動跑。

---

## 版本相容性政策

CCAS 採 [SemVer](https://semver.org/)：

| 升級類型 | 預期影響 | 額外步驟 |
|---|---|---|
| Patch（`v0.1.0` → `v0.1.1`） | 純 bugfix；DB schema 不動 | 無 |
| Minor（`v0.1.0` → `v0.2.0`） | 新功能；可能含 alembic migration | 升級前**備份** `${CCAS_DATA_LOCATION}` |
| Major（`v0.x.x` → `v1.0.0`） | 可能 breaking change；release notes 會明示 | 升級前**閱讀 release notes**、備份 |

每次 release 的詳細 changelog 見 [GitHub Releases](https://github.com/<owner>/ccas/releases)。

---

## 升級前備份（強烈建議）

CCAS 所有狀態（SQLite、staging PDF、Gmail token、API token、master.key、redis dump）皆落在
`${CCAS_DATA_LOCATION}` 單一目錄。備份只需：

```bash
docker compose -f docker-compose.yml stop
tar -czf "ccas-backup-$(date +%Y%m%d-%H%M%S).tar.gz" data/   # 路徑為 .env 的 CCAS_DATA_LOCATION
docker compose -f docker-compose.yml start
```

> `.env` 本身建議另外備份；它可能含 PDF 密碼 fallback、Telegram token 等敏感設定。

---

## 升級到含 `/setup/*` 的版本

新版設定中心會在啟動時做三件相容性初始化：

1. 自動建立 `${CCAS_DATA_LOCATION}/secrets/master.key`（權限 0600），供 `/setup/secrets` 加密 PDF 密碼。
2. Alembic 新增 `bank_settings`、`bank_secrets`、`gmail_oauth_state` 三張表。
3. entrypoint 從既有銀行設定 seed `bank_settings`，既有 row 不覆寫。

既有部署升級後行為維持：

- `.env` 中的 `PDF_PASSWORD_<BANK>` 仍會生效；進 `/setup/secrets` 可一鍵匯入 DB，匯入後 DB 優先生效。
- 既有銀行啟用狀態會 seed 到 `bank_settings`；之後請用 `/setup/banks` 管理。
- 既有 Gmail `credentials.json` / `token.json` 路徑仍可使用；也可改到 `/setup/gmail` 重新上傳與授權。
- `API_TOKEN` 可繼續使用；若要換 token，進 `/setup/admin` rotate。rotate 後舊 token 與舊 cookie 立即失效。

`master.key` 遺失會導致既有 `bank_secrets` 無法解密。備份與復原細節見
[secrets-management.md](secrets-management.md)。

---

## 回滾流程

若升級後出問題，回滾步驟：

```bash
# 1) 停服務
docker compose -f docker-compose.yml down

# 2) 還原資料目錄（若有 schema migration，回滾 image 同時必須還原備份）
rm -rf data
tar -xzf ccas-backup-<舊時間戳>.tar.gz

# 3) 改 .env 的 CCAS_VERSION 回舊版（換成你要回滾到的版號）
sed -i 's/^CCAS_VERSION=.*/CCAS_VERSION=<舊版號>/' .env

# 4) 重新啟動
docker compose -f docker-compose.yml pull
docker compose -f docker-compose.yml up -d
```

> ⚠️ 不建議**只**回滾 image 而不還原資料：minor / major 升級若已跑了 alembic
> migration，舊版 backend 連不到新 schema，會直接 crashloop。

---

## 自動化升級（cron / scheduler）

不建議在 prod 設「自動拉 floating tag」（`CCAS_VERSION=release`）+ 自動重啟，原因：

1. minor / major 升級可能含 alembic migration 或 spec 行為變動
2. 沒事先備份就升級 = 出狀況時無路可退
3. release floating tag 在 main push 時會更新；若你沒追 commit log，可能在意外時段拉到 unfinished work

建議：在 `.env` 釘精確版號（例：`v0.3.0`），手動排定升級時段。

---

## 常見升級問題

### Q: alembic migration 卡住或失敗

```bash
docker compose -f docker-compose.yml logs backend | grep -i alembic
```

若出現 schema 衝突或 lock：先停所有 service（`down`）、還原備份、查看 release notes
是否有額外 migration 步驟。

### Q: 升級後 frontend 顯示 404 / 白屏

清除瀏覽器 cache（新 frontend image 內 bundle 檔名含 hash，但 `index.html` 可能被 cache）。

### Q: Telegram bot 沒反應

bot 會在每次重啟時重新註冊；若 token 不變、bot logs 顯示 connected 即正常。bot 不
crashloop 設計：未填 `TELEGRAM_BOT_TOKEN` 時 idle，不影響其他 service。

---

## 路徑分流提醒

- 本指南為 **prod（pull-only）** 升級；用 `docker/docker-compose.yml`
- **dev** 升級走 `git pull` + 根目錄 `docker-compose.yaml`，與本文不同
- **prod self-build 中間路徑（`docker compose -f docker-compose.yaml up -d` 跳 override）已棄用**，若你還在用該路徑，請先依本指南遷移到 prod compose
