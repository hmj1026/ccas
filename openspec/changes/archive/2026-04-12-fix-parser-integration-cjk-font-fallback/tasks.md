## 1. 建立共用 fixture

- [x] 1.1 在 `tests/integration/parser/conftest.py` 新增 `cjk_font_path` fixture（候選路徑 + skip fallback）

## 2. 更新 7 個 parser integration tests

- [x] 2.1 更新 `test_ctbc_v1_pdf.py`：移除 `_CJK_FONT_PATH`，改用 `cjk_font_path` fixture
- [x] 2.2 更新 `test_sinopac_v1_pdf.py`
- [x] 2.3 更新 `test_esun_v1_pdf.py`
- [x] 2.4 更新 `test_ubot_v1_pdf.py`
- [x] 2.5 更新 `test_cathay_v1_pdf.py`
- [x] 2.6 更新 `test_taishin_v1_pdf.py`
- [x] 2.7 更新 `test_fubon_v1_pdf.py`

## 3. 驗證

- [x] 3.1 本機（macOS）`uv run pytest tests/integration/parser/ -q` — 76 tests PASS
- [x] 3.2 ruff check + format 無 error
