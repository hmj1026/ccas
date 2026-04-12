## Context

Parser integration tests 用 `fpdf2` 生成 synthetic PDF 來測試各家 parser。生成中文 PDF 需要 CJK 字體。目前路徑 hardcode 為 Linux 路徑，macOS 上不存在。

## Goals / Non-Goals

**Goals:**
- 35 個 parser integration tests 在 macOS 和 Linux（Docker）上都能執行
- 無字體環境下 gracefully skip（不 FAIL）

**Non-Goals:**
- 不安裝額外字體套件
- 不改變 synthetic PDF 的內容或結構

## Decisions

1. **共用 conftest fixture** — 在 `tests/integration/parser/conftest.py` 建立 `cjk_font_path` fixture，依序嘗試候選路徑：
   - Linux: `/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc`
   - macOS: `/System/Library/Fonts/STHeiti Medium.ttc`
   - 無可用字體時 `pytest.skip("CJK font not available")`
2. **7 個 test 檔統一改用 fixture** — 移除各檔 `_CJK_FONT_PATH` 常數，改為注入 `cjk_font_path` fixture

## Risks / Trade-offs

- [Risk] macOS 字體渲染可能與 Linux 略有差異 → parser tests 只檢查 text extraction 結果，不比對像素
- [Risk] 某些 CI 環境可能無字體 → skip 而非 fail，CI 應用 Docker image 跑
