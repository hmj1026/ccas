## Why

CCAS 目前已支援中國信託（CTBC），永豐（SINOPAC）、玉山（ESUN）、聯邦（UBOT）、台新（TAISHIN）已建立 OpenSpec 變更但尚未實作。使用者持有國泰世華銀行（Cathay United Bank）信用卡，需要將國泰世華帳單納入同一自動化管線：從 Gmail 下載 → 解密 → 解析 → 分類 → 通知。國泰世華銀行已在 `bank-code-registry.yaml` 預定義（bank_code: CATHAY, fsc_code: 013），但目前 `supported: false`。

使用者提供的國泰世華帳單郵件資訊：
- 寄件者：`service@pxbillrc01.cathaybk.com.tw`
- 主旨格式：`國泰世華銀行信用卡YYYY年M月電子帳單`
- PDF 密碼規則：身分證字號

## What Changes

- 新增 CATHAY 銀行設定至 `banks.example.yaml`（Gmail filter、parser version、is_active）
- 新增 `PDF_PASSWORD_CATHAY` 環境變數至 `.env.example`
- 在 `bank-code-registry.yaml` 將 CATHAY 標記為 `supported: true`
- 實作 `CathayV1Parser`（繼承 `BankParser`，實作 `can_parse` / `parse`）
- 在 parser registry 自動註冊 CATHAY parser
- 新增 parser 單元測試與整合測試
- 更新使用者文件說明新增銀行

## Capabilities

### New Capabilities
- `cathay-bootstrap`: 國泰世華銀行設定（Gmail filter、PDF password key、banks.yaml 設定）
- `cathay-parser`: 國泰世華銀行信用卡帳單 PDF parser（v1），解析帳單摘要與交易明細

### Modified Capabilities
_無需修改現有 spec — 現有 pipeline、ingestor、decryptor、parser registry 皆已支援多銀行，只需新增設定與 parser 實作。_

## Impact

- **Config**: `banks.example.yaml`、`.env.example`、`bank-code-registry.yaml`
- **Parser**: 新增 `backend/src/ccas/parser/banks/cathay_v1.py`，更新 `__init__.py`
- **Tests**: 新增 `tests/unit/parser/test_cathay_v1.py`、`tests/integration/parser/test_cathay_v1_pdf.py`
- **Docs**: `docs/user-guide.md` 新增國泰世華銀行設定說明
- **依賴**: 無新增外部依賴（沿用 pdfplumber、fpdf2 等既有工具）
