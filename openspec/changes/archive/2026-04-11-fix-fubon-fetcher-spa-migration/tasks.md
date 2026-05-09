# Tasks: fix-fubon-fetcher-spa-migration

## 1. Tests (Red)

- [x] 1.1 在 `backend/tests/unit/ingestor/fetcher/test_fubon.py` 新增 `test_can_fetch_recognizes_img_wrapped_anchor` — 使用真實 FUBON 郵件 HTML 片段（`<a href="https://fbmbill.taipeifubon.com.tw/..."><img alt="下載本期帳單(PDF)" /></a>`），斷言 `can_fetch` 回傳 `True`
- [x] 1.2 新增 `test_can_fetch_recognizes_legacy_text_anchor` — 使用舊格式 `<a href="https://mybank.taipeifubon.com.tw/...">下載帳單明細</a>`，斷言 `can_fetch` 回傳 `True`
- [x] 1.3 新增 `test_can_fetch_rejects_non_fubon_domain` — 錨點 href 指向 `https://evil.example.com`，斷言 `can_fetch` 回傳 `False`
- [x] 1.4 新增 `test_fetch_pdf_raises_spa_not_implemented` — 使用含 `fbmbill.taipeifubon.com.tw` 連結的 HTML，斷言 `fetch_pdf` 拋出 `FetchError`，訊息包含「SPA」與「尚未實作」
- [x] 1.5 執行測試，確認 RED：`./scripts/dev-test.sh tests/unit/ingestor/fetcher/test_fubon.py -v`

## 2. Implementation (Green)

- [x] 2.1 更新 `backend/src/ccas/ingestor/fetcher/banks/fubon.py` `_ALLOWED_DOMAINS`，加入 `fbmbill.taipeifubon.com.tw`
- [x] 2.2 重寫 `FubonFetcher.can_fetch()`：改為遍歷所有 `<a href="...">`，檢查 `urlparse(href).hostname` 是否在 `_ALLOWED_DOMAINS` 內
- [x] 2.3 改寫 `FubonFetcher.fetch_pdf()`：檢查 `_extract_download_url()` 回傳的網域若為 `fbmbill.taipeifubon.com.tw`，立即拋出 `FetchError("FUBON", "富邦帳單系統已遷移為 SPA + API 流程（含可能的 OTP 驗證），自動下載尚未實作；請手動下載 PDF 後放入 staging 目錄")`
- [x] 2.4 將舊的 `_attempt_download`、`_build_form_data`、`_CaptchaFailedError`、`_MAX_CAPTCHA_RETRIES`、`_DOWNLOAD_LINK_TEXT` 與 CAPTCHA 相關分支標記為 dead code 並刪除（保留 `_validate_url` 與 `_extract_download_url`）
- [x] 2.5 確認 `from ccas.ingestor.fetcher.captcha import solve_captcha` import 若不再被 FUBON 使用則一併移除（但不要刪除 `captcha.py` 模組本身）
- [x] 2.6 執行測試，確認 GREEN：`./scripts/dev-test.sh tests/unit/ingestor/fetcher/test_fubon.py -v`

## 3. Regression Check

- [x] 3.1 執行全套 backend 測試確認無其他 regression：`./scripts/dev-test.sh tests/unit/ -x`
- [x] 3.2 執行 lint：`./scripts/dev-lint.sh`
- [x] 3.3 手動執行 FUBON pipeline 確認錯誤訊息出現於 JSON summary：`cd backend && uv run python -m ccas.pipeline --bank FUBON --to ingest --force 2>&1 | head -40`

## 4. Verification (OpenSpec)

- [x] 4.1 `openspec status --change fix-fubon-fetcher-spa-migration`
- [x] 4.2 `/opsx:verify fix-fubon-fetcher-spa-migration`（三維驗證）

## 5. Archive

- [x] 5.1 `/opsx:sync fix-fubon-fetcher-spa-migration` — 合併 spec delta 到主規格
- [x] 5.2 `/opsx:archive fix-fubon-fetcher-spa-migration`
