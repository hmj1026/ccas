"""銀行附件檔名黑名單過濾模組。

用於在 ingestion 階段早期跳過非帳單的 PDF 附件（例如永豐銀行
同郵件附帶的「繳款聯」付款憑證），避免污染 staging DB 與後續 parser 統計。
"""

from __future__ import annotations

ATTACHMENT_FILENAME_BLOCKLIST: dict[str, tuple[str, ...]] = {
    # 永豐銀行每封帳單郵件都附帶一份「繳款聯」作為付款用繳款單，
    # 與帳單內容無關，故於 ingest 直接 skip。
    "SINOPAC": ("繳款聯",),
    # 台新銀行每封帳單郵件附帶 TSB_PaymentSlip_YYYYMM.pdf 繳款明細，
    # 不包含帳單資料；保留 TSB_Creditcard_Estatement_*.pdf 帳單檔。
    "TAISHIN": ("PaymentSlip",),
    # 國泰世華每封帳單郵件附帶「國泰世華YYY年MM月信用卡繳款聯.pdf」付款憑證，
    # 與帳單內容無關，故於 ingest 直接 skip。
    "CATHAY": ("繳款聯",),
}


def should_skip_attachment(bank_code: str, filename: str) -> bool:
    """判斷某附件檔名是否命中該銀行的黑名單（substring match）。

    Args:
        bank_code: 銀行代碼（大小寫敏感，需與 BankConfig 一致）。
        filename: 附件原始檔名。

    Returns:
        True 代表應跳過該附件；False 代表正常處理。
    """
    keywords = ATTACHMENT_FILENAME_BLOCKLIST.get(bank_code)
    if not keywords:
        return False
    lower = filename.lower()
    return any(kw.lower() in lower for kw in keywords)
