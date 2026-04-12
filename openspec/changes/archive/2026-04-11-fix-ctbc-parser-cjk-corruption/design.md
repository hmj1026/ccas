## Context

CTBC 帳單 PDF 的商家名稱區塊是圖片化文字，pdfplumber 無法抽取，parser 走 tesseract OCR fallback。OCR 結果有三類損毀：

| 類別 | 症狀 | 可否靠後處理修 |
|---|---|---|
| A. Hyphen → 一 | `P一C` | ✅ regex 替換（ASCII 夾中 `一`）|
| B. 近形字 | `百鋼`（百貨）、`鐵包`（購物卡）| ✅ 白名單替換（有限覆蓋）|
| C. 字元截尾 | `LaLaport 全中`（台中）| ❌ 需改 OCR 本身 |

本 change 的 scope 是 A + B。C 留給後續 OCR 引擎切換的 change 處理。

## Goals / Non-Goals

**Goals:**
- 對抽樣 10 筆典型誤辨 merchant，修正後 ≥ 9 筆可讀。
- 不引入跨銀行 side effect：僅 CTBC parser 走後處理。
- 既有 OCR 空字串 fallback 行為不回歸。

**Non-Goals:**
- 不修 C 類截尾。
- 不換 OCR 引擎。
- 不動 CTBC parser 的 summary / transaction row extraction 主流程。

## Decisions

### D1：Per-bank post-processing, not shared

**選擇**：後處理 helper 放在 `ccas.parser.banks.ctbc.ocr_postprocess` 模組內，**不**放 `ccas.parser.ocr` shared module。

**理由**：各銀行 OCR 誤辨模式不同（CTBC 圖片化 merchant 欄 vs. CATHAY 部分 CID 字型），共用 helper 會引入跨銀行 regression。若未來多家共用同一規則再 refactor 到 shared。

### D2：ASCII-anchored hyphen normalization

**選擇**：regex `(?<=[A-Za-z0-9])一(?=[A-Za-z0-9])` → `-`。

**理由**：
- 只在 ASCII 字元夾中替換，避開純中文句的正常「一」字（如「統一超商」的「一」不會被動到）。
- 零 false positive 需要雙側 lookaround，保守策略優於寬鬆。

**Alternatives:**
- (A) 全域 `一 → -`：會把「統一超商」毀掉。
- (B) 以單側 anchor：仍有 `本-行` 類 false positive。

### D3：品牌白名單以 YAML 而非 Python dict

**選擇**：校正 dict 寫在 `backend/src/ccas/parser/banks/ctbc/ocr_postprocess.py` 的 module-level Python dict，**不**抽到 YAML。

**理由**：
- 初版項目 < 20 條，Python dict 可 inline review diff 最直接。
- 若超過 50 條再考慮抽到 `config/ctbc-ocr-corrections.yaml` 並走 seed 流程。
- 避免與 Change #1/#3 的 config seed 耦合（此處是 code-level constants，不是 runtime config）。

### D4：校正先做 B 後做 A

**選擇**：`normalize_ocr_merchant` 內部順序為「先白名單替換 → 後 hyphen 正規化」。

**理由**：白名單項目可能含 hyphen（例如某商家名就叫 `X-Mart`），若先做 hyphen 替換會影響白名單匹配。

## Risks / Trade-offs

- **[R1]** 白名單覆蓋不足：只能修已知錯字，新誤辨仍會出現。→ Mitigation：TDD fixture 從 E2E 抽樣 10 筆，覆蓋 ≥ 90% 後視為可接受。
- **[R2]** Hyphen regex false positive：`本行-扣繳` 中若 `-` 被辨為 `一` 且兩側是中文則不替換，可接受；若誤辨在 `A一B` 模式則會錯替換實際的「一」字。→ Mitigation：本流程僅動 ASCII-anchored 位置，純中文 context 不會被動到。
- **[R3]** 維護負擔：白名單會持續增長。→ Mitigation：若條目 > 50 再抽 YAML，本 change 不預先優化。

## Migration Plan

1. TDD RED：寫 unit test 覆蓋每條規則正反例 + integration test 對 2 份 staging PDF。
2. 新增 `ocr_postprocess.py`，實作 `normalize_ocr_merchant`。
3. 在 `ctbc_v1.py` 的 OCR merchant 取得處串接 normalize。
4. Run tests → GREEN。
5. `pipeline --bank CTBC --from parse --to parse` 重跑，抽樣 10 筆 merchant 目視驗證。
6. 無 DB migration；既有錯字 row 不回填。

## Open Questions

- **OQ1**：要不要提供一個 `scripts/reclean-ctbc-merchants.py` 對 DB 既有 row 套校正？決定：不做，留給使用者 `pipeline --from parse` 重跑。
- **OQ2**：要不要同時升級 tesseract 的 traineddata？決定：不做，避免拉大環境變動範圍；留給獨立 change。
