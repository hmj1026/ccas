## Context

`categories` 表的資料唯一來源是 `/api/settings/categories` CRUD — 沒有 YAML seed，也沒有 CLI。新環境 `bank_configs` 已由 Change #1 自動 seed，但分類規則仍需使用者逐筆建；user-guide 沒提到這件事，結果 E2E 跑完 3348 筆交易全部 `未分類`。

`bank_configs` 的 idempotent CLI 設計（`../config/banks.yaml` → `created/updated/unchanged` diff + UPSERT）是現成 pattern，可以直接複用於 categories。

## Goals / Non-Goals

**Goals:**
- 新 clone 的 Docker stack，`docker compose up -d backend` 後 `categories` 表非空且涵蓋至少 8 個主要分類。
- 重啟 container 不重複寫入；YAML 更新後 restart 能同步新規則。
- Host 路徑（`scripts/setup.sh`）行為與 container 一致，使用同一條命令 `uv run python -m ccas.tools.categories --apply`，僅靠 `BANK_CONFIG_DIR` 切路徑。
- 既有已由 API 新增的 row 不被粗暴清掉（只對 YAML 中存在的 keyword 做 UPSERT，不對額外 row 做 DELETE）。

**Non-Goals:**
- 不引入多國語系分類。
- 不做 ML-based 分類或 fallback。
- 不改 classifier engine 的最長匹配演算法。

## Decisions

### D1：YAML schema 與 `banks.yaml` 對齊，但獨立檔案

**選擇**：`config/categories.yaml` 作為獨立檔，不與 `banks.yaml` 合併。

```yaml
categories:
  - category: 餐飲
    keywords:
      - 星巴克
      - 麥當勞
      - 肯德基
      - 摩斯
      - 必勝客
  - category: 交通
    keywords:
      - 悠遊卡
      - 高鐵
      - 台鐵
      - Uber
      - 計程車
```

**理由**：
- 關注點分離：銀行設定與分類規則變動頻率不同，合檔會造成 diff 噪音。
- 與 `bank-code-registry.yaml` 已是獨立檔的既有慣例一致。

**Alternatives:**
- (A) 內嵌進 `banks.yaml`：違反關注點分離。
- (B) 寫成 JSON：YAML 更適合人類編輯 keyword list。

### D2：Seed 寫入策略 — YAML SSOT，但不刪 extra row

**選擇**：CLI apply 只對 YAML 中出現的 `(keyword, category)` 組合做 UPSERT。DB 中額外存在的 row（使用者透過 API 自訂的）**保留不動**。

**理由**：
- 使用者可透過設定頁新增個人化 keyword，若 seed 跑一次就清光會造成資料遺失。
- YAML 控制「預設分類基線」，API 控制「個人化擴充」，兩者職責分離。

**Alternatives:**
- (A) Apply 時清空表再 insert：破壞使用者資料。
- (B) Apply 時不覆寫既有 keyword：無法透過 YAML 修正既有 keyword 的分類（例如把「麥當勞」從「餐飲」改成「外食」）。

### D3：Category 表 schema 不加 source 欄位

**選擇**：保留現 schema，不加 `source` 欄位區分「seed」與「user」。

**理由**：
- D2 的策略不需知道來源；YAML 中出現就 UPSERT，不出現就不動。
- schema 改動會觸發 migration、影響 API、增加測試負擔，對本 change 不必要。
- 若未來需要「reset to seed defaults」功能再補 source column。

### D4：Entrypoint 與 bank_configs 同步走 fast-fail

**選擇**：`scripts/docker-entrypoint.sh` 於 `bank_configs --apply` 之後直接串 `categories --apply`，任一失敗即 exit 非零。

```sh
log_info "Seeding categories from /config/..."
uv run python -m ccas.tools.categories --apply || {
  log_error "categories seed failed"
  exit 1
}
```

**理由**：與 bank_configs 同層處理，container 啟動 contract 一致。

## Risks / Trade-offs

- **[R1]** YAML 中的 keyword 品質決定首次使用體驗：過少→分類覆蓋率低；過多→衝突與誤分類增加。→ Mitigation：初版只收錄明確商家字樣（含品牌名），避免泛詞（「餐廳」、「店」等容易誤命中）。
- **[R2]** 使用者手動新增的 keyword 與 YAML 同 keyword 但不同 category 會衝突：YAML apply 時 UPSERT 會覆蓋使用者自訂值。→ Mitigation：在 user-guide troubleshooting 明述「YAML 為 SSOT，改 keyword 分類請優先改 YAML」。
- **[R3]** 分類效果可能讓使用者困惑為什麼某商家沒分到：→ Mitigation：`/transactions` 顯示 `未分類` 即是訊號，使用者可透過設定頁新增；不在本 change 範圍解決。

## Migration Plan

1. 寫 `categories.yaml`（初版 keyword set）。
2. 新增 `ccas.tools.categories` CLI（對 `bank_configs.py` 做結構同構 clone）。
3. 更新 entrypoint + setup.sh。
4. 本機 `docker compose down -v && docker compose up -d backend`；確認 logs 中 seed 成功、`sqlite3 ... "SELECT COUNT(*) FROM categories"` > 0。
5. 重跑 `pipeline --from classify --to classify`，抽樣檢查 `/api/transactions?category=餐飲` 有資料。
6. 無需 DB migration。

## Open Questions

- **OQ1**：初版 categories.yaml 納入幾類？決定：8 類起步（餐飲、交通、購物、娛樂、帳單水電、訂閱服務、超商、咖啡），後續 change 擴充。
- **OQ2**：是否同步做 reclassify 自動觸發？決定：不做；由 pipeline `--from classify` 或 `/api/bills/{id}/reclassify` 手動觸發，避免 seed 時引入長時間 side-effect。
