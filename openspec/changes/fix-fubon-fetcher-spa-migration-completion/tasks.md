## 1. TDD 前置（RED）

- [ ] 1.1 新增 `backend/tests/unit/ingestor/test_fubon_fetcher_manual_staging.py`：使用 `tmp_path` fixture 覆蓋 5 個 scenario
  - Manual staging 空 → `FetchError` 含指引訊息
  - Manual staging 含帳單月份檔名 → 精確配對並 move
  - Manual staging 僅單檔無月份 → 配對成功
  - Manual staging 多檔無月份 → `FetchError` "無法對應"
  - SPA 失敗 + manual staging 有檔 → fallback 成功
- [ ] 1.2 `cd backend && uv run pytest tests/unit/ingestor/test_fubon_fetcher_manual_staging.py -x` 確認 RED

## 2. Settings 與設定

- [ ] 2.1 在 `backend/src/ccas/config.py` 的 `Settings` 新增 `fubon_manual_staging_dir: Path = data_dir / "manual-staging" / "FUBON"`
- [ ] 2.2 `env_prefix` 支援 `FUBON_MANUAL_STAGING_DIR`
- [ ] 2.3 `.env.example` 新增範例與註解

## 3. Fetcher 改造

- [ ] 3.1 在 `backend/src/ccas/ingestor/fetcher/banks/fubon.py` 新增 `_try_manual_staging(self, billing_month: str | None) -> Path` helper
  - 列出目錄 `.pdf` 檔案
  - 先比對 filename 含 `billing_month`（格式 `YYYY-MM` 或 `YYYYMM`）
  - 退回選 mtime 最新且唯一的檔
  - 都不符 → raise `FetchError` 含指引
- [ ] 3.2 `fetch_pdf()` 重構：try HTML 解析 → except `FetchError`（僅 SPA 相關錯誤）→ `_try_manual_staging`
- [ ] 3.3 成功後把檔案 move 到 `settings.staging_dir / "FUBON" / filename`
- [ ] 3.4 重跑 1.2 → GREEN

## 4. Docker volume 檢查

- [ ] 4.1 確認 `docker-compose.yaml` 的 backend `volumes` 已包含 `./backend/data:/data`（既有）
- [ ] 4.2 無需新增 mount；在文件中說明 host 的 `./backend/data/manual-staging/FUBON/` 對應 container `/data/manual-staging/FUBON/`

## 5. 文件更新

- [ ] 5.1 `docs/user-guide.md` 新增小節「FUBON 手動下載步驟」
- [ ] 5.2 涵蓋：下載步驟、命名建議（`fubon-YYYY-MM.pdf`）、放置目錄、執行 pipeline 指令
- [ ] 5.3 troubleshooting 新增「FUBON fetch 失敗：檢查 manual staging 目錄」條目

## 6. 手動驗收

- [ ] 6.1 放一份真實 FUBON PDF 至 `backend/data/manual-staging/FUBON/fubon-2026-03.pdf`
- [ ] 6.2 `docker exec ccas-backend-1 uv run python -m ccas.pipeline --bank FUBON` 應跑完整個 pipeline
- [ ] 6.3 檔案從 manual staging 目錄消失、出現在 `staging/FUBON/`
- [ ] 6.4 `/api/bills?bank_code=FUBON` 回傳 bill row
- [ ] 6.5 前端 `/transactions?bank_code=FUBON` 看到資料

## 7. 回歸驗證

- [ ] 7.1 `cd backend && uv run pytest -k fubon -x`
- [ ] 7.2 在 `docs/e2e-user-guide-walkthrough.md` 問題 #8 狀態改 `archived`，`對應 change slug` 填 `fix-fubon-fetcher-spa-migration-completion`
- [ ] 7.3 `openspec verify fix-fubon-fetcher-spa-migration-completion` 通過
