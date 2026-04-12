# Design: fix-fubon-captcha-solver-accuracy

## Context

`fubon-fetcher-impl` change 上線後，Section 11 live test 需將 `FUBON_CAPTCHA_MAX_RETRIES` 從 7 調到 15 才通過。本輪（2026-04-11）完整 pipeline 實跑 33 筆 FUBON 信件，約 10 筆以 `captcha_retry_exhausted: 7 attempts failed` 失敗（~30%），遠高於 research-time fixture 預估的 8.2%。

Captcha 模組架構（現行）：

```
flow.py::_login_with_captcha_retry
    └─> captcha.solve(jpeg) -> CaptchaResult | None     # primary path (EasyOCR)
        └─> (rejected) captcha_llm.solve_with_llm()     # optional fallback
```

現行主 solver `captcha.py` 使用 **EasyOCR** + 後置 gate（conf ≥ 0.80、長度 = 4、全數字）。`_READER` 為 process-level singleton，lazy init，受 `threading.Lock` 保護。Gate 語意：任何不合格直接回 None，由 flow 層 burn 一個 retry slot 並 refetch。

使用者對修復方向的硬性約束（本設計必須遵守）：

1. **不加重試上限**（症狀治療、非根因修復）
2. **不調 conf gate**（降閾值會引入 false positive，反而更慢）
3. **不把 LLM fallback 升為主路徑**（LLM 必須保持為最後兜底；成本/隱私/外部依賴考量）

## Goals / Non-Goals

**Goals:**
- 主 solver 的單次命中率（accepted rate）從 ~30% 提升到 ≥ 80%，以 `tests/fixtures/fubon/captcha_samples/` 20+ 張 labeled sample 為 regression baseline
- 完整 pipeline 實跑 `captcha_retry_exhausted` 失敗率從 ~30% 降到 ≤ 10%
- `captcha.py::solve(jpeg_bytes) -> CaptchaResult | None` 外部介面、gate 語意、回傳契約**零變動**（flow.py / captcha_llm.py / test_flow_* 一行不改）
- Docker image 大小不增加；若能順勢縮小更好
- 外部依賴變動對 supply chain 有明確審查紀錄（license、maintainer、sha）

**Non-Goals:**
- 調整 `FUBON_CAPTCHA_MAX_RETRIES` 預設值
- 調整 conf gate `_MIN_CONF = 0.80`
- 更動 `FUBON_CAPTCHA_FALLBACK_LLM` 預設或語意
- 自訓 captcha CNN / 收集 100+ 標註樣本
- Image preprocessing 管線（列為 follow-up，不在本 change）
- 多 OCR 引擎 ensemble（例：兩家 OCR 同時跑、取共識）

## Decisions

### D1. 主 solver 換成 `ddddocr`

**Decision**: 用 `ddddocr`（MIT license，作者 `sml2h3`，GitHub > 10k stars）取代 EasyOCR 作為 FUBON captcha 的主 OCR 引擎。

**Rationale**:
- ddddocr 是 **captcha-specialized** CNN 模型，訓練資料集本身就是各式 captcha（含扭曲、噪點、粘連、干擾線）。對 4 位數字這類低複雜度 captcha，社群 benchmark 通常 90%+。
- 使用 ONNX runtime 推論，模型 bundle ~30 MB（含在 wheel 內），remote download 不需（EasyOCR 需下載 `craft_mlt_25k.pth` + `english_g2.pth` ~94 MB）。
- API 簡單：`ocr.classification(image_bytes) -> str`，直接對映到我們 `solve()` 內部。
- 沒有 torch 依賴，拔掉 easyocr 的同時可一併移除 `torch==2.10.0` + `torchvision==0.25.0` + pytorch-cpu index 設定。

**Alternatives considered**:

- **PaddleOCR**：更強、支援 CJK，但安裝體積 ~1 GB，Paddle runtime 同樣是重量級框架。Over-kill for 4 digits。
- **Tesseract**：傳統 OCR，對 captcha 噪點扛不住（社群實測普遍 < 50%）。否決。
- **自訓 CNN（captcha_trainer / cnn_ocr）**：需要 50+ 標註樣本、GPU 訓練 pipeline、模型檔入 repo。樣本收集成本高，且每次 FUBON 換 captcha 樣式都要重訓。列為最後手段。
- **Image preprocessing + 保留 EasyOCR**：治標（可能 30%→60%），上限受模型類別限制，且 opencv 參數需要長期維護。若 ddddocr 實測結果仍不夠好，再當 follow-up。
- **升格 LLM fallback 為主路徑**：使用者明確否決。

### D2. 完全保留 `captcha.py` 的外部介面

**Decision**: 替換 solver 只動 `captcha.py` 內部。保留：
- `def solve(jpeg_bytes: bytes) -> CaptchaResult | None`
- `@dataclass(frozen=True) CaptchaResult(text: str, confidence: float)`
- 後置 gate：`len == 4`、`isdigit()`、`confidence >= _MIN_CONF`
- Process-level singleton + `threading.Lock` double-checked init

**Rationale**:
- flow.py / captcha_llm.py / test_flow_* 完全不需改動，change 爆炸半徑最小
- Gate 邏輯仍有價值：ddddocr 理論上不會回非 4 digits，但後置檢查是安全網
- `CaptchaResult.confidence`: ddddocr 本身的 `classification()` 不直接回 confidence；我們用 `with_probability=True` 取得 per-char confidence 陣列，取 `min()` 作為 aggregate confidence 給 gate 用

**Alternatives considered**:
- 整個模組重寫成 `captcha_v2.py`：過度工程。
- 把 gate 拿掉因為 ddddocr 更準：降低安全性，不值得。

### D3. Fixture 擴充策略

**Decision**: 把 `tests/fixtures/fubon/captcha_samples/` 從 10 張擴充到 20+ 張，新增樣本沿用「檔名 = ground truth」命名（`{4-digit}.jpg`）。新樣本從 live captcha 拉取（用 `FubonClient.get_captcha()` 存檔 + 手動肉眼標註）。

**Rationale**:
- 10 張樣本統計力道不足（3/10 = 30% 的 CI 區間非常寬）
- 20+ 張可以支撐「accepted rate ≥ 80%」的 regression 斷言
- 不需要 100+ 樣本——我們只要驗證「solver 夠用」，不是訓練模型

**Acceptance gate upgrade**:
- 現行 `test_all_samples_gate_correctness`: accepted 的 text 必須等於檔名（無 false positive），rejected 允許任意數量
- 新斷言：**accepted rate ≥ 80%**（即 20 張中至少 16 張 accept），false positive rate = 0（不容忍錯誤答案）

### D4. Dependency 清理

**Decision**: 從 `pyproject.toml` 主依賴移除 `easyocr`、`torch`、`torchvision`；清除 `[tool.uv.sources]` 的 torch/torchvision 條目與 `[[tool.uv.index]] pytorch-cpu`。加入 `ddddocr`。

**Rationale**:
- `rg -l "easyocr|import torch" src/ tests/` 結果只命中 `captcha.py` + `test_captcha_gate.py`。無其他內部使用者，安全移除。
- Dockerfile builder stage 的 EasyOCR preload `RUN uv run python -c "import easyocr; ..."` 可整行刪除。ddddocr 模型 bundle 在 wheel 內，無須預載。
- 預期 Docker image 大小從 1.82 GB 減到 ~800 MB–1 GB（實測數字在 tasks 階段收集）

**Risk**: ddddocr 的 onnxruntime dependency 在 `linux/arm64` 是否有 pre-built wheel？需 tasks 階段用 `uv pip compile` + `docker buildx build --platform linux/amd64,linux/arm64` 驗證。

### D5. Confidence 來源與 gate 一致性

**Decision**: ddddocr `classification(image, probability=True)` 回傳 `{text: str, probabilities: list, charset: list, confidence: float}`，其中 `confidence` 已是 library 端聚合後的 aggregate confidence（CTC 解碼後的整體分數）。我們直接採用 `confidence`：
1. 呼叫 `classification(jpeg, probability=True)` 取 `text` 與 `confidence`
2. 套用現行 gate：`len == 4` + `isdigit()` + `confidence >= 0.80`
3. `probabilities` 不直接使用（CTC 時序長度 ≠ 字符數，手動 aggregate 無益）

**Rationale**:
- ddddocr 內建 `confidence` 語意與實作文件一致，省掉自製 aggregation 的維護成本
- **實測驗證**（Section 0/1 階段，現行 10 張 fixture）：accept rate = 9/10 = 90%，false positive = 0（唯一誤識 `4450→r450` 被 `isdigit()` gate 正確拒絕），所有 accepted 樣本 `confidence` 均 ≥ 0.988，0.80 閾值有充足安全邊際
- 0.80 閾值沿用：ddddocr 的 softmax 分佈比 EasyOCR 尖銳很多（實測 >0.95 普遍），不需調整

**Alternatives considered**:
- 自製 `min(per_char_probs)` aggregation：`probabilities` 是 CTC 時序輸出（長度 19）不是 4-字 per-char；映射回字符位需額外 CTC decoder，得不償失
- 換閾值（0.6 或 0.9）：本 change 不動 gate 參數

## Risks / Trade-offs

| Risk | Mitigation |
|---|---|
| ddddocr 對 FUBON 實測命中率仍 < 80% | Tasks 階段先跑 fixture regression；若 fail 就 open follow-up change 做 image preprocessing 補強（D1 alternatives 已列為後手） |
| ddddocr 是中國社群單人專案，supply chain 信任度較低 | Tasks 階段 (a) 釘 exact version + sha256 (b) 檢查 PyPI 維護者歷史 (c) audit upstream GitHub 最近 release + issue flow (d) 若風險過高回退 PaddleOCR |
| ONNX runtime 在 arm64 Docker 無 wheel | Tasks 階段用 `docker buildx --platform linux/arm64` 驗證；若失敗記錄於本 change 並評估後退 |
| ddddocr 回傳 confidence 語意與 EasyOCR 不同，導致既有 gate 行為改變 | D5 的 `min()` aggregation + 20+ fixture regression test 鎖住行為 |
| 新 solver 對 `solve()` 內部錯誤類型改變，呼叫端 `except Exception` broad catch 不捕捉 | `captcha.py:61` 已用 `except Exception:  # noqa: BLE001`，涵蓋 broad types；保留 |
| PyTorch 移除後 Dockerfile CPU-only index 設定殘留造成 uv sync 錯誤 | Tasks 階段同步清 `[tool.uv.sources]` + `[[tool.uv.index]]`，並跑一次乾淨 `uv sync` |

## Migration Plan

本 change 對外部 API / DB / frontend 零影響，部署策略單純：

1. **Build**：`docker compose build backend` 會自動拉 ddddocr wheel（含 ONNX model bundle），image rebuild 完成
2. **Deploy**：`docker compose up -d backend` 重啟 backend container
3. **Verify**：
   - `docker exec ccas-backend-1 uv run python -c "import ddddocr; print(ddddocr.__version__)"` 應成功
   - `docker exec ccas-backend-1 uv run pytest tests/unit/ingestor/fetcher/banks/fubon/test_captcha_gate.py -q` 應綠
   - `docker exec ccas-backend-1 uv run python -m ccas.pipeline --bank FUBON --to notify` 應顯著減少 `captcha_retry_exhausted`
4. **Rollback**: `git revert <commit>` + `docker compose build backend` + restart。無 DB migration、無 state 變更，可瞬時回退。

## Open Questions

| # | Question | 如何解答 | Status |
|---|---|---|---|
| 1 | ddddocr 當前穩定版本號？ | `pip download ddddocr` → `1.6.1`（py3-none-any，MIT，author sml2h3） | **resolved** |
| 2 | ddddocr 對 FUBON 舊 fixture（10 張）的 accept rate 是多少？ | 實測 `classification(probability=True)` → **9/10 = 90%，FP=0** | **resolved** |
| 3 | onnxruntime 在 `linux/arm64` 有 pre-built wheel 嗎？ | 確認 `onnxruntime-1.24.4-cp312-cp312-manylinux_2_27_aarch64.manylinux_2_28_aarch64.whl` 存在（amd64 亦有） | **resolved** |
| 4 | 新 fixture 從哪裡拉？直接在 live container 跑 `client.get_captcha()` 存 jpeg + 手動標註？ | baseline 已達標，fixture 擴充改列為 nice-to-have；仍保留在 tasks 中以強化 regression 統計力 | deferred |
| 5 | ddddocr 的 classification API 的 `probability=True` 回傳結構？ | `{text, probabilities(CTC 時序), charset, confidence(aggregate float)}`；採用 `confidence` 不自製 aggregation | **resolved** |
