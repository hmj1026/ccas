## Context

富邦 pipeline 端到端驗證後發現 7 個問題。Parser 能解析帳單摘要與交易，但遺漏 card_last4（卡號標頭未傳遞）與分期資訊（嵌在 merchant 名稱中）。Captcha OCR 使用 ddddocr 直送 raw JPEG，local gate accept rate ~90% 但 server-side accuracy 未知。Staging 路徑為 Docker 絕對路徑，本機執行找不到檔案。

## Goals / Non-Goals

**Goals:**
- Parser 正確填充 card_last4 與 installment_current/total 欄位
- Captcha OCR-only（不啟用 LLM fallback）達 80% server-side 正確率
- 保險交易正確分類
- Docker/本機環境切換時 staging 路徑不斷裂

**Non-Goals:**
- 不重構 parser 架構（維持 text-based extraction）
- 不更換 captcha OCR 引擎（維持 ddddocr）
- 不新增 Alembic migration（card_last4、installment 欄位已存在於 schema）
- 不修改 web-fetch 流程邏輯

## Decisions

### D1: Card header state tracking（parser）

**選擇**：在 `_extract_transactions_text()` 中加入 card header regex，逐行掃描時維護 `current_card_last4` 狀態，遇到卡號標頭行（如「MASTER鈦金正卡末４碼5273」）時更新狀態，後續交易行繼承該值。

**替代方案**：用 table extraction 的 header row 提取 → 富邦 PDF 不使用標準 table 格式，無法適用。

### D2: Installment extraction（parser）

**選擇**：在 merchant 文字中偵測 `(NN/MM期)` pattern，提取 installment_current 與 installment_total，並從 merchant 名稱移除該 suffix。

**替代方案**：解析下方「本筆分期尚有未到期金額」行 → 該行不含 current/total 資訊，無法取代。

### D3: Captcha 前處理 pipeline

**選擇**：在 `captcha.solve()` 呼叫 ddddocr 前加入 Pillow 前處理：灰階 → 對比增強 → 二值化（Otsu threshold）→ 降噪（median filter）。封裝為 `_preprocess(jpeg_bytes) -> bytes` 純函式。

**理由**：ddddocr 對乾淨的黑白字元辨識最佳。富邦 captcha 有彩色干擾線與漸層背景，前處理可顯著提升辨識率。

**替代方案**：
- `beta=True` 模式 → 不確定是否改善，且可能影響其他行為
- 自訓模型 → 成本過高，fixture 不足

### D4: Captcha eval harness

**選擇**：建立 `scripts/eval_captcha.py`，以 fixtures 目錄為輸入，統計 accept rate 與 ground truth accuracy。CI 不跑（fixture 含真實 captcha），但本機可手動驗證。擴充 fixture 至 ≥30 張。

### D5: Staging 路徑解析

**選擇**：`staged_path` 儲存相對於 `STAGING_DIR` 的相對路徑（如 `FUBON/xxx.pdf`），使用時以 `Path(settings.staging_dir) / staged_path` 組合。需一次性 migration script 修正既有記錄。

**替代方案**：存絕對路徑但在讀取時動態替換 prefix → 脆弱，依賴 prefix 匹配。

## Risks / Trade-offs

- **Captcha 前處理可能降低某些樣本的辨識率** → 以 eval harness 跑 A/B 對比，只在整體 accuracy 提升時合併
- **Card header regex 假陽性** → 限定格式「末４碼NNNN」+ 4 位數字驗證
- **Staging 路徑 migration** → 影響既有 staged_attachments 記錄 → 提供 idempotent script，可重複執行
- **Fixture 擴充需真實 captcha** → 需手動從富邦 SPA 收集，或在 pipeline 執行時自動儲存
