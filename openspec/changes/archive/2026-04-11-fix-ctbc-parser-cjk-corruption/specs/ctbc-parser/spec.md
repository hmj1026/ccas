## ADDED Requirements

### Requirement: CTBC OCR 後處理校正商家名稱

系統 SHALL 對 CTBC parser 從 tesseract OCR 取得的商家名稱字串套用字元校正，至少涵蓋兩類：(1) ASCII 字元之間的「一」字正規化為 hyphen `-`；(2) 品牌關鍵字白名單替換（如「百鋼」→「百貨」、「鐵包」→「購物卡」等 CTBC 常見誤辨）。校正 MUST 僅影響 CTBC parser，MUST NOT 變更其他銀行 parser 或 shared OCR helper。

#### Scenario: ASCII-anchored hyphen 正規化

- **GIVEN** OCR 回傳字串 `"ICP一統一超商"` 或 `"網路家庭分期01一06"`
- **WHEN** `normalize_ocr_merchant` 處理該字串
- **THEN** 回傳值 SHALL 為 `"ICP-統一超商"` / `"網路家庭分期01-06"`

#### Scenario: 中文 context 的「一」字不被動到

- **GIVEN** OCR 回傳字串 `"統一超商門市"`
- **WHEN** `normalize_ocr_merchant` 處理該字串
- **THEN** 回傳值 SHALL 仍為 `"統一超商門市"`（「一」兩側非 ASCII，不替換）

#### Scenario: 品牌白名單替換

- **GIVEN** OCR 回傳字串 `"統一時代百鋼台北店"`
- **WHEN** `normalize_ocr_merchant` 處理該字串
- **THEN** 回傳值 SHALL 為 `"統一時代百貨台北店"`

#### Scenario: 白名單先於 hyphen 正規化

- **GIVEN** 白名單含 `"X一Mart" → "X-Mart"` 同時 hyphen 規則也會 match
- **WHEN** `normalize_ocr_merchant` 處理 `"X一Mart"`
- **THEN** 最終結果 SHALL 只命中白名單一次，不疊加雙重轉換

#### Scenario: 空字串不變

- **GIVEN** OCR fallback 回傳 `""`
- **WHEN** `normalize_ocr_merchant` 處理該字串
- **THEN** 回傳值 SHALL 仍為 `""`，且不拋例外

#### Scenario: CTBC parser 呼叫點

- **WHEN** `CtbcV1Parser.parse()` 從 OCR 取得 merchant 字串並即將構造 `TransactionItem`
- **THEN** 字串 SHALL 先經 `normalize_ocr_merchant` 處理再寫入 `TransactionItem.merchant`

#### Scenario: 其他銀行不受影響

- **WHEN** `CathayV1Parser.parse()` 處理 merchant 字串
- **THEN** `normalize_ocr_merchant` SHALL NOT 被呼叫，該字串 SHALL 不經 CTBC 專屬校正
