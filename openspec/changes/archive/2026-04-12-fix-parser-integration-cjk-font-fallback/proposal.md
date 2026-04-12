## Why

7 家銀行的 35 個 parser integration tests 全部在本機（macOS）FAIL，原因是 CJK 字體路徑 hardcode 為 Docker Linux 路徑 `/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc`。macOS 有 CJK 字體但路徑不同（如 `/System/Library/Fonts/STHeiti Medium.ttc`）。這導致本機開發者無法驗證 parser integration tests。

## What Changes

- 在 parser integration test conftest 中建立 CJK 字體解析邏輯：嘗試多個候選路徑（Linux → macOS），無字體時 skip test
- 更新 7 個 `test_*_v1_pdf.py` 使用共用 fixture 取代 hardcoded 路徑

## Capabilities

### New Capabilities

- `test-infrastructure`: 跨平台 CJK 字體 fixture 供 parser integration tests 使用

### Modified Capabilities

（無）

## Impact

- 影響 7 個 parser integration test 檔案 + 1 個新 conftest
- 無生產程式碼變更
