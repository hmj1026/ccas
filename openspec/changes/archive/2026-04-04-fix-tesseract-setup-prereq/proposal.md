## Why

CTBC 信用卡 PDF 帳單的文字無法直接由 pdfplumber 提取（中文字型編碼問題），parser 因此回退到 OCR（Tesseract）。但 Tesseract Traditional Chinese 語言包（`chi_tra.traineddata`）並不在標準 `tesseract` homebrew 安裝中，需要額外安裝 `tesseract-lang`。`setup.sh` 和 `check-env.sh` 未檢查此依賴，導致 parse stage 靜默失敗並輸出混亂的 TesseractError traceback。

## What Changes

- `scripts/check-env.sh` 加入 Tesseract 與 `chi_tra` 語言包的存在性檢查
- `scripts/setup.sh` 在 tesseract/tesseract-lang 未安裝時輸出明確的安裝指引
- `docs/developer-guide.md` 加入 Tesseract 相依性說明

## Capabilities

### New Capabilities
<!-- 無 -->

### Modified Capabilities
- `developer-onboarding`: setup.sh 加入 tesseract 相依性檢查

## Impact

- `scripts/setup.sh` — 加入 tesseract 與 chi_tra 的 preflight check
- `scripts/check-env.sh` — 加入 tesseract 與 chi_tra 的存在性驗證
