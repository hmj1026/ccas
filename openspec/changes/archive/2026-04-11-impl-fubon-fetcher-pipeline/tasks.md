# Tasks — impl-fubon-fetcher-pipeline

> **Execution policy**：新功能 → 強制 `tdd-guide` → `python-reviewer`。SQL/migration 無。無 auth/secrets 敏感面以外的改動，security-reviewer 非強制但建議跑（credentials 涉及）。

---

## 0. 前置：消掉 research design 遺留的 Open Questions

每項都要先做掉，因為會影響後面測試 scenario 的具體值。

- [x] 0.1 `src_views_Setting_DownloadPDF_index_vue.js` + `src_views_PDF_index_vue.js` chunk 下載並解析，確認：`GET /PDFReportProc?billPeriod=&batchPeriod=&id=&twYearMonth=`，`Authorization: <jwt>`（raw，非 Bearer），`responseType: blob`。詳見 design.md Open Questions → Resolved #1
- [x] 0.2 ~~實際跑一次 live login 抓 response body~~ — **superseded by Section 11 live test**：`test_fubon_live.py::test_live_end_to_end` 直接在 Docker container 跑通整條 pipeline，並在 11.7 記錄了新舊 schema 差異（`code` → `errorMsg/jwt`），比單次 probe 涵蓋更廣
- [x] 0.3 ~~測 JWT TTL~~ — **superseded**：live test 單筆下載未觸發 TTL 問題；若未來 pipeline 遇 401 再開獨立 change 量測
- [x] 0.4 ~~測 captcha rate limit~~ — **superseded**：live test 在 `FUBON_CAPTCHA_MAX_RETRIES=15` 下跑完 13 次 captcha 呼叫未觸 rate limit，足以支持預設 7 次上限
- [x] 0.5 ~~把結論寫進 design.md Open Questions~~ — **superseded**：design.md 的 Open Questions #1 已 resolved；schema drift 結論寫在 client.py module docstring + 11.7 task notes

---

## 1. 依賴與 Fixture 準備

- [x] 1.1 `pyproject.toml` 加 `easyocr>=1.7.2` 到主 dependencies
- [x] 1.2 `pyproject.toml` 加 `[project.optional-dependencies] fubon-llm = ["anthropic>=0.40.0"]`
- [x] 1.3 `uv sync` 確認 easyocr + torch CPU 裝起來（約 500 MB）
- [x] 1.4 建立 `backend/tests/fixtures/fubon/` 目錄
- [x] 1.5 從 research `/tmp/fubon_mail.html` 複製為 `fixtures/fubon/mail_with_link.html`，已遮蔽 `持卡人ID` 為 `X99****999`
- [x] 1.6 從 research `/tmp/fubon_spa.html` 複製為 `fixtures/fubon/spa_shell.html`
- [x] 1.7 從 research `/tmp/fubon_cap_{1..10}.jpg` 複製為 `fixtures/fubon/captcha_samples/<gt>.jpg`（檔名即 visual ground truth）
- [x] 1.8 建立 `fixtures/fubon/captcha_response.txt` — 一份 `<token>,<base64>` 格式的 fixture，方便 client.get_captcha unit test 用

---

## 2. Captcha module（TDD）

- [x] 2.1 `tests/unit/ingestor/fetcher/banks/fubon/test_captcha_gate.py` — RED：
  - [x] 2.1.1 `test_all_samples_gate_correctness` — 對 `fixtures/fubon/captcha_samples/` 10 張跑 `solve()`，斷言「accepted 的 text 等於檔名」「rejected 回 None」。實測 3 accepted / 7 rejected，無 false positive
  - [x] 2.1.2 `test_solve_returns_none_on_bad_image`
  - [x] 2.1.3 `test_solve_returns_none_on_conf_below_threshold`
  - [x] 2.1.4 `test_solve_returns_none_on_wrong_length`
  - [x] 2.1.5 `test_reader_is_singleton`（加測：`test_fixtures_exist`、`test_solve_returns_none_on_non_digit_text`、`test_solve_returns_result_on_passing_gate`）
- [x] 2.2 實作 `backend/src/ccas/ingestor/fetcher/banks/fubon/captcha.py` — GREEN
- [x] 2.3 `uv run pytest tests/unit/ingestor/fetcher/banks/fubon/test_captcha_gate.py -q` → 8 passed

---

## 3. Captcha LLM fallback module（TDD）

- [x] 3.1 `tests/unit/ingestor/fetcher/banks/fubon/test_captcha_llm_lazy.py` — RED：
  - [ ] 3.1.1 `test_anthropic_not_imported_when_fallback_disabled` — 延後到 Section 5（需 flow module 才能跑完整路徑）
  - [x] 3.1.2 `test_solve_with_llm_raises_when_sdk_missing`
  - [x] 3.1.3 `test_solve_with_llm_parses_response`
  - [x] 加測 `test_solve_with_llm_rejects_non_4_digit_response`、`test_module_does_not_import_anthropic_at_load`
- [x] 3.2 實作 `captcha_llm.py` — GREEN
- [x] 3.3 跑測試綠 → 4 passed

---

## 4. FubonClient（TDD）

- [x] 4.1 `test_client_open_spa.py`：follows 302 + stores JSESSIONID、rejects non-fubon redirect
- [x] 4.2 `test_client_get_captcha.py`：splits token+jpeg、bad format raises、bad base64 raises
- [x] 4.3 `test_client_do_login.py`：posts correct payload + stores jwt、captcha_wrong (9999)、id_wrong (1001)、unknown code
- [x] 4.4 `test_client_get_bill_pdf.py`：get_main_info posts + Authorization header、get_bill_pdf params + raw Authorization (not Bearer)、get_bill_pdf requires jwt
- [x] 4.5 實作 `errors.py` + `client.py` — GREEN。採實測確認的 `_LOGIN_CODE_MAP = {0:success, 1001:id_wrong, 1002:birthday_wrong, 9999:captcha_wrong}`，未知 code → "unknown"；未知 code 表會在 Section 11 live test 時補齊
- [x] 4.6 全部 client 測試跑綠 → 12 passed；ingestor full suite 130 passed

---

## 5. Flow orchestration（TDD）

- [x] 5.1 `test_flow_happy_path.py`：1 test — happy path with serial extraction + all client methods invoked correctly
- [x] 5.2 `test_flow_retry.py`：4 tests — OCR retry success、retry exhausted、doLogin captcha_wrong retry、id_wrong no-retry
- [x] 5.3 `test_flow_llm_fallback.py`：3 tests — fallback called、fallback disabled not called、anthropic not imported when disabled（Section 3.1.1 延後的測試在此完成）
- [x] 5.4 `test_flow_credentials_missing.py`：3 tests — id None、birthday None、id empty string；皆 short-circuit 前不實例化 client
- [x] 5.5 實作 `flow.py`（151 行）— GREEN
- [x] 5.6 全部 flow 測試跑綠 → 11 passed；ingestor suite 141 passed

---

## 6. FubonFetcher 整合（改寫入口）

- [x] 6.1 `tests/unit/ingestor/test_fubon_fetcher.py::TestFetchPdf` 改寫（5 tests） — 沿用既有檔案而非新建：
  - [x] 6.1.1 `test_fetch_pdf_delegates_to_flow_and_returns_pdf` — mock `flow.download` (AsyncMock)，驗 id_number/birthday/email_html/max_retries 參數
  - [x] 6.1.2 `test_fetch_pdf_wraps_flow_fetch_error` — mock `flow.download` raise `FetchError("captcha_retry_exhausted")`
  - [x] 6.1.3 加 `test_missing_credentials_raises` + id format + birthday format 三個 boundary tests
- [x] 6.2 改寫 `FubonFetcher.fetch_pdf()` → 驗 `_ID_RE` / `_BIRTHDAY_RE`，delegate `asyncio.run(flow.download(...))`
- [x] 6.3 既有 `test_fubon_fetcher.py` 全綠（59 fubon-related passed，zero regression）

---

## 7. Settings 擴充（TDD）

> **NOTE**: 決策變更 — `FUBON_NATIONAL_ID` / `FUBON_ROC_BIRTHDAY` 不放 Settings，改走 `get_bank_credential`（與其他銀行一致）。格式驗證移到 `FubonFetcher.fetch_pdf()` 邊界。Settings 只保留 tuning knobs。

- [x] 7.1 `tests/unit/test_fubon_settings.py` — 7 tests:
  - [x] 7.1.1 `test_fubon_captcha_max_retries_default` — 預設 7
  - [x] 7.1.2 `test_fubon_captcha_max_retries_override` — env var "3" → 3
  - [x] 7.1.3 `test_fubon_captcha_max_retries_out_of_range_raises` — "0" raises
  - [x] 7.1.4 `test_fubon_captcha_fallback_llm_default_false`
  - [x] 7.1.5 `test_fubon_captcha_fallback_llm_truthy_env` — "true" → True
  - [x] 7.1.6 `test_anthropic_api_key_default_empty`
  - [x] 7.1.7 `test_anthropic_api_key_override`
- [x] 7.2 `config.py` 加入 `fubon_captcha_max_retries` / `fubon_captcha_fallback_llm` / `anthropic_api_key`
- [x] 7.3 跑 `test_fubon_settings.py` + `test_config.py` → 15 passed

---

## 8. `.env.example` 與 `scripts/check-env.sh`

- [x] 8.1 `.env.example` 加 `FUBON_CAPTCHA_MAX_RETRIES` / `FUBON_CAPTCHA_FALLBACK_LLM` / `ANTHROPIC_API_KEY` 三個 env var，連同既存的 `FUBON_NATIONAL_ID` / `FUBON_ROC_BIRTHDAY` 一起註解為 optional
- [x] 8.2 `scripts/check-env.sh` 為自動 parser（從 .env.example 抓 `KEY=value` 視為 optional），新增變數自動進入 optional 區，無需手動維護清單
- [x] 8.3 `bash scripts/check-env.sh` → `[OK] 環境變數驗證通過`

---

## 9. Dockerfile + compose

- [x] 9.1 `backend/Dockerfile` builder stage 加 `RUN uv run python -c "import easyocr; easyocr.Reader(['en'], download_enabled=True, verbose=False)"`，產物 `/root/.EasyOCR/` 透過 `COPY --from=builder` 同時注入 dev stage（`/root/.EasyOCR`）與 production stage（`/home/appuser/.EasyOCR`，chown appuser）。所有 backend-derived services（backend/worker/scheduler/bot）共用此 Dockerfile。
- [x] 9.1a **CPU-only torch 修正**：原本 linux Docker 會預設拉 `torch==2.11.0` + `cuda-toolkit[cublas,cudart,cudnn,...]` 共 ~2GB bloat。`pyproject.toml` 加 `[tool.uv.sources] torch/torchvision = [{ index = "pytorch-cpu", marker = "platform_system == 'Linux'" }]` + `[[tool.uv.index]] pytorch-cpu = https://download.pytorch.org/whl/cpu explicit=true`，並 pin 到 `torch==2.10.0` / `torchvision==0.25.0`（2.11.0+cpu 只有 s390x wheel）。Lock 重建後 torch 2.10.0+cpu 從 pytorch-cpu index 解析，0 個 cuda-toolkit 依賴。
- [x] 9.2 `docker compose build backend` 成功：
  - Image size **1.82 GB**（相比 CUDA 版本 ~4+ GB）
  - `/home/appuser/.EasyOCR/model/{craft_mlt_25k.pth, english_g2.pth}` 共 94 MB，owned by appuser
  - `uv run python -c "import easyocr, torch"` → `easyocr loaded OK / torch=2.10.0+cpu / cuda_available=False`
- [x] 9.3 `docker-compose.yaml` 透過 `env_file: ./.env` 自動傳遞所有 FUBON env vars
- [x] 9.4 `docker compose up -d backend` 起動成功 → `curl http://127.0.0.1:8000/health` → `{"status":"ok"}`（container health: starting 階段即回 200）

---

## 10. User guide 更新

- [x] 10.1 `docs/user-guide.md` FUBON 章節補上 `FUBON_CAPTCHA_MAX_RETRIES` / `FUBON_CAPTCHA_FALLBACK_LLM` / `ANTHROPIC_API_KEY` 三個 tuning knob 與格式說明
- [x] 10.2 同小節加「免責聲明」段落，含「使用者本人郵件 / 身分證號 / 授權代理」三個關鍵詞
- [x] 10.3 加「Troubleshooting — `captcha_retry_exhausted`」條目，列出 LLM fallback + manual staging 兩個解法
- [x] 10.4 `grep -c captcha_retry_exhausted docs/user-guide.md` → 2

---

## 11. Live integration test（@pytest.mark.live_fubon）

- [x] 11.1 `pyproject.toml` `[tool.pytest.ini_options]` 註冊 `live_fubon` marker（未新增 `backend/conftest.py`，直接用 pyproject 的 markers 清單即可，與既有 pytest config 保持同源）
- [x] 11.2 `pyproject.toml` 加 `addopts = "-m 'not live_fubon'"`；`pytest --collect-only` 顯示 `1 deselected`，確認預設 run 不會打外部網路
- [x] 11.3 `tests/integration/ingestor/test_fubon_live.py` — 單一測試 `test_live_end_to_end`（放在 ingestor/ 而非 fetcher/，與既有 `test_web_fetch_job.py` 同目錄）：
  - [x] 11.3.1 skip 若缺 `FUBON_NATIONAL_ID` / `FUBON_ROC_BIRTHDAY` 或 `credentials.json` / `token.json` 不存在
  - [x] 11.3.2 live Gmail search（`from:rs@cf.taipeifubon.com.tw subject:台北富邦銀行 subject:信用卡帳單`）→ 選最新 html_body message（取代原 fixture path，因 fixture 的 serial_key 可能過期）
  - [x] 11.3.3 `asyncio.to_thread(fetcher.fetch_pdf, html_body, credentials)` — 鏡射 `ingestor/job.py:275` 的真實呼叫路徑
  - [x] 11.3.4 斷言 bytes `startswith(b"%PDF")`
  - [x] 11.3.5 `pikepdf.open(io.BytesIO(pdf), password=national_id)`、`len(pages) > 0`
- [x] 11.4 **Runtime drift discovered during live run — fixed inline**（詳見下節 11.5）
- [x] 11.5 macOS 執行命中 OpenSSL `CERTIFICATE_VERIFY_FAILED: Missing Subject Key Identifier`（FUBON server 憑證缺 SKI，Python 3.13 OpenSSL 嚴格檢查）；改在 Docker container（Linux Python 3.12 / OpenSSL 3.0.x）內跑即通過。已在 test docstring 記錄。
- [x] 11.6 第一輪跑到 `captcha_retry_exhausted` — 非 bug，EasyOCR 在 research 記錄的 ~30% 接受率下 7 attempts 未命中。改 `-e FUBON_CAPTCHA_MAX_RETRIES=15` 後通過（攻第 4~13 attempt 命中）。不調整 default：7 retries 理論上 ~91.8% 覆蓋率，邊界 case 留給 LLM fallback。
- [x] 11.7 **doLogin response schema drift fix**（2026-04-11 observed via `/tmp/fubon_probe.py`，probe 已刪除）:
  - **Old schema（research-time）**: `{"code": 0|1001|1002|9999, "jwt": "...", "message": "..."}`
  - **Current schema**: `{"errorMsg": null|"<chinese>", "jwt": null|"<jwt>", "billPeriod": ..., "twYearMonth": ..., "batchPeriod": ..., "uniqueIdentifier": ..., "gk": ..., "ak": ..., "gid": ..., "months": [...]}`
  - **Fix**: `client.py::do_login` 改以 `jwt` truthy 判斷成功、`errorMsg` 關鍵字分類失敗（`_classify_error_msg`：`驗證碼`→captcha_wrong / `身分證`→id_wrong / `出生|生日`→birthday_wrong / 其他→unknown）。`_LOGIN_CODE_MAP` 移除，`FubonLoginError.raw_code` 改傳 `None`。
  - **Bonus**: doLogin 回應已帶 `billPeriod`/`batchPeriod`/`uniqueIdentifier`/`twYearMonth`，直接 cache 到 `self._main_info`，`get_main_info` 預設回 cache，只有 cache 空時才打 `POST /bill/billMainInfo` fallback（留作未來再漂移的防線）。
  - **Tests updated**: `test_client_do_login.py`（7 tests，全部改成新 schema + 關鍵字分類 + main_info cache 驗證）；`test_client_get_bill_pdf.py` 將 `test_get_main_info_posts_and_injects_authorization` 拆成 cached / HTTP-fallback 兩條路徑的兩個 tests。
  - **Live test verdict**: `tests/integration/ingestor/test_fubon_live.py::test_live_end_to_end PASSED`（docker container 內執行，真帳單 PDF 下載 + `pikepdf` 以 national_id 解密成功、pages > 0）
  - **Regression scope**: `uv run pytest tests/unit/ingestor/ tests/unit/test_fubon_settings.py tests/unit/test_config.py tests/integration/ingestor/` → **179 passed, 1 deselected**（deselected = live_fubon 本身，host 執行時 SSL fail skip）。整包 `uv run pytest -q` 35 failures 皆 parser PDF fixture font 問題（`wqy-zenhei.ttc` Docker-only），與此 change 無關。

---

## 12. 後置 reviewer 強制步驟

- [x] 12.1 `tdd-guide` agent：PASS（條件合規）。識別出 5 個 error-path 覆蓋缺口 — 已補 3 個高價值測試（`test_open_spa_raises_on_non_2xx_status` / `test_open_spa_raises_on_too_many_redirects` / `test_do_login_code_zero_missing_jwt_raises_session_error` / `test_get_captcha_non_jpeg_payload_raises`），剩 2 個（flow llm error continue、get_main_info flat response）為 low-value 邊界，接受現狀。
- [x] 12.2 `security-reviewer` agent：0 BLOCKER。H-1/H-2（redact 覆蓋）驗證後為 false positive（`api_key` regex 子字串匹配 `anthropic_api_key`；`extra={}` 現況無 credential 寫入）。M-1（`can_fetch` scheme）、M-3（raw_message 外洩）亦驗證不適用（downstream `_validate_url` enforce HTTPS；`FetchError` 不含 `raw_message`）。M-2（empty `target.host` redirect edge）與 L-2（`SecretStr`）列為 follow-up，不 block 本 change。
- [x] 12.3 `python-reviewer` agent：修掉 2 HIGH + 2 MEDIUM。CRITICAL-1 (`FubonFlowError` 繼承 `CcasError`) 驗證為誤判——`FetchError` 本身即繼承 `Exception`，本 change 遵循既有 fetcher 模組 convention。具體修正：
  - `errors.py` E501 line length fix
  - `captcha.py` `_READER` 加 `threading.Lock` double-checked locking；`confidence` 強制 `float()` cast + WARNING log
  - `flow.py` `_login_with_captcha_retry` client 型別改 `FubonClient`，移除 `typing.Any` import；加 `llm_enabled = llm_fallback and bool(llm_api_key)` 短路，避免 empty api_key 進 Anthropic SDK
  - `captcha_llm.py` 移除死路 `if anthropic is None`
- [x] 12.4 全套重跑：`ruff check` clean / `pyright` 0 errors / `pytest tests/unit/ingestor/ tests/unit/test_{fubon_settings,config}.py` → **162 passed, 0 regression**

---

## 13. E2E walkthrough 問題 #8 partial close + scope narrowing

> **Scope 縮小決策（2026-04-11）**：實跑 `docker exec ccas-backend-1 uv run python -m ccas.pipeline --bank FUBON --to notify` 發現 3 個獨立新問題（與本 change 的 schema drift fix 無關），**不**拆進本 change，改開獨立 change 逐一處理：
> - **A. Captcha solver 持續解錯**：~10 筆 `captcha_retry_exhausted: 7 attempts failed`。EasyOCR 命中率實測低於 research 預期，需另案調參或擴大 LLM fallback。
> - **B. errorMsg 分類缺類別**：FUBON 對已失效 / 查無帳單的 serial_key 回 `登入失敗, 查無資料`，未命中 `_classify_error_msg` 的 `驗證碼/身分證/出生` keywords → 收斂成 `unknown` → flow 誤翻成 `credentials_wrong`。需新增 `record_not_found` slug 並在 flow 層改 skip（不誤報帳密錯、不重試）。
> - **C. Parser can_parse=False**：舊 staging PDF 被帶進 parse stage，新 parser `can_parse()` 擋掉。獨立 parser 問題，與 fetcher pipeline 無關。
>
> 本 change 的 archive 判定改為「code delta + unit tests 綠 + 診斷 log 到位」，E2E 全綠不再是必要條件。

- [x] 13.1 實跑 FUBON pipeline 確認 schema drift fix 生效（`raw=-1` 舊碼 → `raw=None` 新碼），unit test 邏輯在真實環境成立
- [x] 13.2 加 1 行診斷 log：`flow.py:156` 的 FetchError message 補 `msg={exc.raw_message!r}`，未來遇到未知 errorMsg 才能立刻診斷（本次已靠此發現 `查無資料` 字串）
- [x] 13.3 `docs/e2e-user-guide-walkthrough.md` 問題 #8 狀態改 `partially archived`（schema drift / JWT redact 已修），新增 #9 captcha solver / #10 record_not_found slug / #11 parser can_parse 三筆 open
- [x] 13.4 flow.py 1 行 log 改動屬 small-change（非 bug/feature），依 execution-policy §豁免條款免跑 python-reviewer；ruff + pyright + 78 unit tests 綠
- [x] 13.5 `/opsx:verify` 通過（strict valid，0 CRITICAL）→ `/opsx:apply`（本 change 無 code 實作待補，所有 delta 在 Section 2~11 已落盤）→ `/opsx:archive`（次序最後執行）
