# Proposal: fix-fubon-captcha-solver-accuracy

## Why

FUBON fetcher 的 captcha solver（EasyOCR + conf≥0.80 + length gate）在真實 pipeline 實測命中率遠低於 research-time fixture 的預估。本輪 `docker exec ccas-backend-1 uv run python -m ccas.pipeline --bank FUBON --to notify` 跑 33 筆中約 10 筆以 `captcha_retry_exhausted: 7 attempts failed` 失敗，失敗率 ~30%（預期 `(0.7)^7 = 8.2%`）。Section 11 live test 亦需將 `FUBON_CAPTCHA_MAX_RETRIES` 從預設 7 調到 15 才通過。

**根因不是參數沒調好，是模型類別錯了**：EasyOCR 是為自然場景文字 / 文件掃描訓練的通用 OCR，對 captcha 特有的噪點、線條、字符扭曲並非其強項。加重試次數或降低信心閾值都只是延後症狀、不是解法。使用者明確表態：**不再增加重試上限、不把 LLM fallback 升格為主路徑**（LLM 必須保持為最後兜底）。因此主路徑需要改用 captcha-specialized 的 OCR 引擎。

## What Changes

- **BREAKING（僅限 FUBON 內部實作）**：`ccas.ingestor.fetcher.banks.fubon.captcha` 模組的主 solver 從 EasyOCR 換成 `ddddocr`（MIT-licensed，ONNX runtime，captcha-specialized）。
- `captcha.py::solve(jpeg_bytes) -> CaptchaResult | None` 的外部介面、回傳語意、conf + length gate 行為**完全保留**，flow.py / captcha_llm.py / settings 皆不動。
- `pyproject.toml` 主依賴移除 `easyocr`、`torch`、`torchvision`（僅被 FUBON captcha 引用，無其他內部使用者）；加入 `ddddocr>=1.5.0`。`[tool.uv.sources]` / `[[tool.uv.index]]` 的 pytorch-cpu 設定可全部清除。
- `backend/Dockerfile` 移除 EasyOCR weights 預載步驟（`RUN uv run python -c "import easyocr; ..."`）。若 ddddocr 需要 model preload 則改掛其對應指令，否則直接省掉。
- 擴充 `tests/fixtures/fubon/captcha_samples/` 從 10 張到 20+ 張（現有 10 張 + 新收集 10 張），做為新 solver 的 regression baseline。
- `tests/unit/ingestor/fetcher/banks/fubon/test_captcha_gate.py` 的 `test_all_samples_gate_correctness` 斷言升級：**accepted rate ≥ 80%**（目前是 3/10 = 30%）、false positive rate = 0（accepted 的 text 必須等於檔名 ground truth）。
- **不動**：retries 預設仍是 7；conf gate 仍是 0.80；LLM fallback 仍預設 off。
- **驗證**：實跑 `docker exec ccas-backend-1 uv run python -m ccas.pipeline --bank FUBON --to notify`，`captcha_retry_exhausted` 失敗率應從 ~30% 降到 ≤ 10%。

## Capabilities

### New Capabilities
（無）

### Modified Capabilities
- `fubon-fetcher-impl`：captcha solving requirement 從「EasyOCR + conf/length gate」改為「captcha-specialized OCR（ddddocr）+ conf/length gate」。外部行為（`solve()` 簽名、gate 語意、flow 重試邏輯）不變；僅主 solver 實作替換，accepted rate 下限從「靠重試覆蓋」改為「單次命中 ≥ 80%」。

## Impact

### Affected code
- `backend/src/ccas/ingestor/fetcher/banks/fubon/captcha.py`（solver 實作替換）
- `backend/tests/unit/ingestor/fetcher/banks/fubon/test_captcha_gate.py`（斷言升級、`easyocr.Reader` mock 改成 ddddocr API）
- `backend/tests/fixtures/fubon/captcha_samples/`（新增 10+ 張 labeled samples）
- `backend/pyproject.toml`（deps + uv sources 清理）
- `backend/Dockerfile`（移除 EasyOCR preload）

### Affected deps
- **Removed**: `easyocr`, `torch==2.10.0`, `torchvision==0.25.0`（及 pytorch-cpu index 配置）
- **Added**: `ddddocr>=1.5.0`

### Affected docker artefacts
- **Image size 預期變化**：大幅縮小。EasyOCR + torch CPU 佔現行 image 的大部分（Section 9 記錄 1.82 GB 總 size），ddddocr 用 ONNX runtime，估計可減 500 MB–1 GB。實測數字在 tasks 驗證階段收集。
- **Build time**：預期縮短（少一個 torch wheel 下載 + EasyOCR model preload）。

### Affected config / runtime
- 無 env var 變更。`FUBON_CAPTCHA_MAX_RETRIES` / `FUBON_CAPTCHA_FALLBACK_LLM` / `ANTHROPIC_API_KEY` 語意與預設皆不動。
- 無 API 變更、無 DB migration、無前端影響。

### Risk
- **ddddocr 對 FUBON captcha 實測命中率若 < 80%**：B 方案（LLM fallback 預設開）使用者已否決；若發生則回退到 follow-up change「C：image preprocessing 強化」，不在本 change 範圍。
- **ddddocr license / 供應鏈**：MIT license，維護者是中國社群開發者 `sml2h3/ddddocr`。需在 tasks 階段確認 PyPI 最新版、sha 指紋、及離線模型 bundle 狀況。
- **ONNX runtime platform binary**：需確認 `linux/amd64` + `linux/arm64` 皆有 wheel（Docker multi-arch build 潛在風險）。

### Out of scope
- 調整 retries / conf gate（使用者明確拒絕）
- 把 LLM fallback 升為主路徑（使用者明確拒絕，LLM 維持 fallback）
- Image preprocessing 管線（若 ddddocr 不夠好再做）
- 自訓 CNN / 收集大量標註樣本
