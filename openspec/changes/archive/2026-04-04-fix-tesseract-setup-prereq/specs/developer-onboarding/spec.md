## ADDED Requirements

### Requirement: Setup script 檢查 Tesseract OCR 相依性
`scripts/setup.sh` SHALL 在安裝後端依賴後，檢查 Tesseract 和 `chi_tra` Traditional Chinese 語言包是否已安裝，若未安裝則輸出明確的安裝指引並停止。

#### Scenario: Tesseract 未安裝
- **WHEN** `tesseract` 指令不在 PATH 中
- **THEN** 腳本 SHALL 停止並輸出 `[ERROR] 需要 tesseract OCR。請執行: brew install tesseract`

#### Scenario: chi_tra 語言包未安裝
- **WHEN** `tesseract` 已安裝但 `/opt/homebrew/share/tessdata/chi_tra.traineddata` 不存在
- **THEN** 腳本 SHALL 停止並輸出 `[ERROR] 需要 Tesseract Traditional Chinese 語言包。請執行: brew install tesseract-lang`

#### Scenario: Tesseract 和語言包均已安裝
- **WHEN** `tesseract` 可執行且 `chi_tra.traineddata` 存在
- **THEN** 腳本 SHALL 繼續執行後續步驟
