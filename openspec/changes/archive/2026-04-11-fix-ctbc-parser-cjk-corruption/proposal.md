## Why

E2E walkthrough 問題 #2：CTBC 真實 PDF 經 parser → tesseract OCR 提取商家名稱後，DB 中的 `merchant` 欄位大量出現字元損毀，導致：

- 分類無法命中（classifier keyword 無法 match「統一時代百鋼台北店」、「ICP一統一超商 斷體」）
- 使用者在前端 `/transactions?bank_code=CTBC` 閱讀困難
- 部分 row 商家名只剩半截（`LaLaport 全中`，應為 `LaLaport 台中`）

從 `SELECT DISTINCT merchant FROM transactions LIMIT 20` 抽樣可見三類典型損毀：

1. **Hyphen 誤辨**：商戶名中的 `-` 被 tesseract 辨為 `一`
   - `ICP-統一超商` → `ICP一統一超商`
   - `網路家庭分期01-06` → `網路家庭分期01一06`
   - `Pi-拍賣` → `Pi一拍孚基`
2. **近形字誤辨**：單字視覺近似被錯置
   - `百貨` → `百鋼`
   - `家樂福-購物卡EDC-自` → `家樂福一鐵包EDC一自`、`家樂福一錢包EDC一自`
3. **字元截尾**：商戶名尾端字被切掉
   - `LaLaport 台中` → `LaLaport 全中`
   - `統一時代百貨台北店` → `統一時代百鋼台北店`

（註：CTBC PDF 的商家名稱區塊是圖片化文字，必須經 OCR。既有 spec `parser-ocr` 已允許 OCR fallback 空字串，但沒規範 OCR 後處理品質。）

## What Changes

- **新增 `backend/src/ccas/parser/banks/ctbc/ocr_postprocess.py`**：集中 CTBC 特有的 OCR 字元校正邏輯：
  - Hyphen 正規化：當 `一` 位於 ASCII letter/digit 之間（如 `P一C`、`01一06`），替換為 `-`
  - 品牌白名單替換 dict：`"百鋼" → "百貨"`、`"鐵包" → "購物卡"`（初版覆蓋抽樣出的 10 組高頻誤辨，後續可持續擴充）
  - `normalize_ocr_merchant(raw: str) -> str` 為唯一入口
- **修改 `backend/src/ccas/parser/banks/ctbc_v1.py`**：在 OCR 取得 merchant 字串後呼叫 `normalize_ocr_merchant`；不動 OCR 本身調用流程。
- **新增 `backend/tests/unit/parser/test_ctbc_ocr_postprocess.py`**：TDD 覆蓋每條校正規則的正反例。
- **新增 `backend/tests/integration/parser/test_ctbc_v1_ocr_regression.py`**：從 `backend/data/staging/CTBC/` 挑 2 份真實 PDF 做 golden assertion（merchant 不再含 `一` 夾在 ASCII 字元中、不再含白名單中的已知錯字）。
- **更新 OCR 訓練資料（可選）**：若白名單覆蓋率 < 80% 則補 `-c tessedit_char_whitelist` 或切換 `--oem` 模式（延後 decision，視 TDD 結果）。

**非範圍**：
- 不更換 OCR 引擎（tesseract → PaddleOCR 等）。
- 不處理全字截尾問題（需 OCR 本身解，後續獨立 change）。
- 不動 pdfplumber 對非圖片文字區塊的 text extraction。

## Capabilities

### New Capabilities

無。

### Modified Capabilities

- `ctbc-parser`：新增 OCR 後處理要求；現有 OCR fallback 空字串規則不變，但在 OCR 成功回傳字串時 SHALL 套用字元校正。
- `parser-ocr`：補充通用後處理（hyphen 正規化）歸屬於 per-bank parser 的權責，不納入 shared OCR helper（避免跨銀行 side effect）。

## Impact

- **程式**：`backend/src/ccas/parser/banks/ctbc/ocr_postprocess.py`（新）、`backend/src/ccas/parser/banks/ctbc_v1.py`
- **測試**：`backend/tests/unit/parser/test_ctbc_ocr_postprocess.py`、`backend/tests/integration/parser/test_ctbc_v1_ocr_regression.py`
- **相容性**：對既有已寫入 DB 的錯字 row 不做 retro-fix；使用者若想清理需手動重跑 `pipeline --bank CTBC --from parse`
- **風險**：白名單覆蓋有限，只能減少已知誤辨；新出現的誤辨需後續 PR 補。
