## Why

富邦是唯一完全阻塞的銀行：33 封電子帳單信全部 `FetchError("SPA + 尚未實作")`，FUBON bills=0 / tx=0（見 `docs/e2e-user-guide-walkthrough.md` 問題 #8）。前置 research change `research-fubon-web-fetch-pipeline` 已完成：還原完整 HTTP flow、找出所有 API 端點與 payload schema、對 captcha 辨識跑過 POC 實測（Tesseract 40%、EasyOCR + conf-gate 50% + 7 retry → 99.2%）。本 change 依據 research design 落地實作。

## What Changes

- 新增 `backend/src/ccas/ingestor/fetcher/banks/fubon/` 子套件：
  - `client.py`：`httpx.AsyncClient` session wrapper（cookie jar + JWT + interceptor）
  - `captcha.py`：EasyOCR 辨識 + `conf ≥ 0.80 && len == 4` gate
  - `captcha_llm.py`（可選）：Claude API fallback，預設關閉
  - `flow.py`：Step 1~6 pipeline（redirect → SPA shell → captcha → doLogin → billInfo → PDF）
- 改寫 `FubonFetcher.fetch_pdf()`：從現行 `raise FetchError("SPA + 尚未實作")` 改為呼叫 `flow.download(...)`
- `Settings` 加四個 env：
  - `FUBON_ID_NUMBER`（身分證號大寫）
  - `FUBON_BIRTHDAY`（民國 7 碼）
  - `FUBON_CAPTCHA_MAX_RETRIES`（預設 7）
  - `FUBON_CAPTCHA_FALLBACK_LLM`（預設 `0`）
- `pyproject.toml` 新增 `easyocr` 依賴（含 torch CPU）
- `Dockerfile` / `scripts/docker-entrypoint.sh`：build 階段預下載 EasyOCR 權重烘進 image，避免 runtime 下載
- `.env.example`、`docs/user-guide.md`：加新 env vars 說明 + 法遵免責聲明（「本自動化流程僅下載使用者本人郵件中的帳單連結、使用使用者本人身分證號登入，屬使用者授權代理」）
- **BREAKING**（僅對 FUBON 使用者）：需要在 `.env` 填 `FUBON_ID_NUMBER` + `FUBON_BIRTHDAY` 才能成功下載；未填則 fetcher 明確 raise `FetchError("missing FUBON credentials")`，不走舊的「SPA 未實作」訊息

## Capabilities

### New Capabilities

無全新 capability — 本 change 是把既有 capability 的「尚未實作」填實。

### Modified Capabilities

- `fubon-fetcher-impl`：`fetch_pdf` requirement 從「拋出 FetchError 說 SPA 尚未實作」改為「完成完整下載流程，支援 captcha OCR + 重試 + 可選 LLM fallback + 手動 staging 最終 fallback」
- `env-validation`：新增 4 個 FUBON env vars 的驗證（必填 / 格式 / 預設值）
- `docker-deployment`：Dockerfile build 階段 pre-warm EasyOCR 權重
- `user-guide`：FUBON 章節補上 credential 設定步驟與法遵免責聲明

## Impact

- **Code**：
  - 新增：`backend/src/ccas/ingestor/fetcher/banks/fubon/{client,captcha,captcha_llm,flow}.py`
  - 改寫：`backend/src/ccas/ingestor/fetcher/banks/fubon/__init__.py`（`FubonFetcher.fetch_pdf`）
  - 擴充：`backend/src/ccas/config.py`（Settings + env vars）
- **Tests**：
  - 新增 unit：`tests/unit/ingestor/fetcher/banks/fubon/test_{client,captcha,flow}.py`，用 research 抓下的 fixture（`fubon_mail.html`、`fubon_spa.html`、`fubon_cap_*.jpg`）mock HTTP
  - 新增 integration：`tests/integration/fetcher/test_fubon_live.py`，`@pytest.mark.live_fubon` marker，CI skip
- **Dependencies**：
  - 新：`easyocr`（含 `torch` CPU wheel，約 500 MB image 增量）
  - 可選：`anthropic` SDK（只在 `FUBON_CAPTCHA_FALLBACK_LLM=1` 時載入；走 lazy import）
- **Docker image size**：+500 MB（torch CPU + easyocr 模型權重）
- **Runtime**：首次 `Reader()` 初始化約 1~2 秒；之後每張 captcha 辨識 < 200ms（CPU）
- **Risk**：
  - 富邦改 captcha 樣式會讓 EasyOCR 掉準確率 → 有 LLM fallback + manual staging 兜底
  - `server_token` 若綁 IP → Docker host network 要穩定
  - Captcha 重抽 rate limit 未實測 → impl 要加 `asyncio.sleep(0.3)` between retries
- **Downstream**：FUBON 成為第 7 家可 end-to-end 跑通的銀行，`docs/e2e-user-guide-walkthrough.md` 問題 #8 可關閉
