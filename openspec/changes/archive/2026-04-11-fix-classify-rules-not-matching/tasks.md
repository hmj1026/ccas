## 1. TDD 前置（RED）

- [x] 1.1 新增 `backend/tests/integration/tools/test_categories_seed.py`，覆蓋 5 個 scenario：
  - apply 空表 → `created=N unchanged=0`
  - apply 重跑 → `created=0 unchanged=N`
  - YAML 改單一 keyword 分類 → `updated=1`
  - 使用者自訂 row（不在 YAML）→ 不被動到
  - `BANK_CONFIG_DIR` 環境變數優先於 hard-coded default、被顯式 `--config` flag 覆蓋
- [x] 1.2 `cd backend && uv run pytest tests/integration/tools/test_categories_seed.py -x` 確認 RED

## 2. 建立 categories.yaml（初版）

- [x] 2.1 新增 `config/categories.yaml`，至少 8 類：餐飲、交通、購物、娛樂、帳單水電、訂閱服務、超商、咖啡
- [x] 2.2 每類至少 5 個明確商家/品牌 keyword（避免泛詞）
- [x] 2.3 Schema `categories: [{category, keywords: [...]}]`

## 3. 建立 ccas.tools.categories CLI

- [x] 3.1 新增 `backend/src/ccas/tools/categories.py`，結構對齊 `bank_configs.py`：`build_parser()`、`main()`、`apply_categories()` 三段
- [x] 3.2 `--config` default 採 dynamic callable：讀 `BANK_CONFIG_DIR` env → `{env}/categories.yaml`；未設則 `../config/categories.yaml`
- [x] 3.3 實作 diff-based UPSERT：以 `(keyword)` 為唯一鍵，比對 YAML 與 DB；YAML 有 DB 無 → INSERT；YAML 有 DB 有但 category 不同 → UPDATE；YAML 有 DB 有且相同 → unchanged；DB 有 YAML 無 → **不動**（D2 策略）
- [x] 3.4 輸出 `created=X updated=Y unchanged=Z` 到 stdout
- [x] 3.5 支援 `--dry-run`：跑 diff 但不 commit
- [x] 3.6 重跑 1.2 測試 → GREEN

## 4. Docker Entrypoint 串接

- [x] 4.1 `scripts/docker-entrypoint.sh` 在 `bank_configs --apply` 之後新增 `categories --apply`，fast-fail 同策略
- [ ] 4.2 `docker compose down -v && docker compose up -d backend` 驗證 logs 顯示 `categories seed: created=N unchanged=0`
- [ ] 4.3 `docker exec ccas-backend-1 sqlite3 /data/ccas.db "SELECT COUNT(*) FROM categories;"` 回傳 > 30

## 5. Host Setup 同步

- [x] 5.1 `scripts/setup.sh` 在 `bank_configs --apply` 行之後新增 `categories --apply`
- [ ] 5.2 Host 直接執行 `scripts/setup.sh` 驗證 `categories` 非空

## 6. 文件更新

- [x] 6.1 `docs/user-guide.md` 故障排除章節新增「分類全部為未分類」條目
- [x] 6.2 條目包含 `docker compose restart backend` 與 `docker exec ccas-backend-1 uv run python -m ccas.tools.categories --apply` 兩種做法
- [x] 6.3 說明 YAML 為 SSOT，若修改 keyword 分類應優先改 YAML

## 7. 回歸驗證

- [x] 7.1 全 suite：`cd backend && uv run pytest -x`
- [ ] 7.2 重跑 `docker exec ccas-backend-1 uv run python -m ccas.pipeline --from classify --to classify`，抽樣查 `/api/transactions?category=餐飲` 有資料
- [x] 7.3 在 `docs/e2e-user-guide-walkthrough.md` 問題 #3 狀態改 `archived`，`對應 change slug` 填 `fix-classify-rules-not-matching`
- [x] 7.4 `openspec verify fix-classify-rules-not-matching` 通過
