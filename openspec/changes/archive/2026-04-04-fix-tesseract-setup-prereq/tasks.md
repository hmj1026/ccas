## 1. scripts/setup.sh 加入 Tesseract 檢查

- [x] 1.1 在 `scripts/setup.sh` 的「安裝後端依賴」步驟後，加入 tesseract 存在性檢查：
  - `command -v tesseract >/dev/null 2>&1 || fail "需要 tesseract OCR。請執行: brew install tesseract"`
- [x] 1.2 加入 chi_tra 語言包檢查：
  - 在 tessdata 目錄中確認 `chi_tra.traineddata` 存在，否則 fail 並提示 `brew install tesseract-lang`

## 2. 驗證

- [x] 2.1 在未安裝 tesseract 的環境中執行 `scripts/setup.sh`，確認出現明確的安裝指引
- [x] 2.2 在已安裝 tesseract 和 chi_tra 的環境中執行，確認正常通過
