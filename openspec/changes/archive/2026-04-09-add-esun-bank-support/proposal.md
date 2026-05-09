## Why

CCAS 目前僅支援中國信託（CTBC）信用卡帳單，永豐（SINOPAC）正在開發中。使用者持有玉山銀行（E.SUN）信用卡，需要將玉山帳單納入同一自動化管線：從 Gmail 下載 → 解密 → 解析 → 分類 → 通知。玉山銀行已在 `bank-code-registry.yaml` 預定義（bank_code: ESUN, fsc_code: 808），但目前 `supported: false`。

## What Changes

- 新增 ESUN 銀行設定至 `banks.example.yaml`（Gmail filter、parser version、is_active）
- 新增 `PDF_PASSWORD_ESUN` 環境變數至 `.env.example`
- 在 `bank-code-registry.yaml` 將 ESUN 標記為 `supported: true`
- 實作 `EsunV1Parser`（繼承 `BankParser`，實作 `can_parse` / `parse`）
- 在 parser registry 自動註冊 ESUN parser
- 新增玉山銀行常見消費分類關鍵字 seed data
- 新增 parser 單元測試與整合測試
- 更新使用者文件說明新增銀行

## Capabilities

### New Capabilities
- `esun-bootstrap`: 玉山銀行設定（Gmail filter、PDF password key、banks.yaml 設定、seed data）
- `esun-parser`: 玉山銀行信用卡帳單 PDF parser（v1），解析帳單摘要與交易明細

### Modified Capabilities
_無需修改現有 spec — 現有 pipeline、ingestor、decryptor、parser registry 皆已支援多銀行，只需新增設定與 parser 實作。_

## Impact

- **Config**: `banks.example.yaml`、`.env.example`、`bank-code-registry.yaml`
- **Parser**: 新增 `backend/src/ccas/parser/banks/esun_v1.py`，`__init__.py` 已預留 import
- **Tests**: 新增 `tests/unit/parser/test_esun_v1.py`、`tests/integration/parser/test_esun_v1_pdf.py`
- **Seed**: 可能新增或擴充分類關鍵字
- **Docs**: `docs/user-guide.md` 新增玉山銀行設定說明
- **依賴**: 無新增外部依賴（沿用 PyPDF、pdfplumber 等既有工具）
- **Email**: subject 格式 `玉山銀行2026年02月信用卡電子帳單`，sender `estatement@esunbank.com`
