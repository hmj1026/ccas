"""跨行共用的退款 / 貸方明細偵測工具。

退款 / 回饋 / 沖銷等貸方明細在 CCAS 全系統保留為負數金額（非整筆丟棄），
利於後續對帳。各家 parser 共用此模組以避免邏輯漂移。

注意「退款」與「繳款」是不同概念：
- 退款（退款 / 退費 / 退貨 / 沖銷）= 商家退錢，保留為負數明細。
- 繳款（自動扣繳 / 付款已收到 / 自扣已入帳）= 持卡人繳清帳款，各行處理方式不一，
  不在本模組的負數化範圍內（由各 parser 自行決定保留或略過）。
"""

from __future__ import annotations

# 跨行通用退款商戶關鍵字（保守集合，只收各行皆適用的明確退款措辭）。
# 銀行專屬措辭（如永豐「永豐自扣」）由各 parser 以 ``extra_keywords`` 補充，
# 不放入共用集合，以免把其他行的正常消費誤判為退款。
GENERAL_REFUND_KEYWORDS: tuple[str, ...] = (
    "退款",
    "退費",
    "退貨",
    "沖銷",
    "取消授權",
)

# 明確標示貸方的行首符號（半形/全形負號、(-)）。
REFUND_LINE_PREFIXES: tuple[str, ...] = ("(-)", "－", "(−)")


def is_refund_merchant(merchant: str, *, extra_keywords: tuple[str, ...] = ()) -> bool:
    """Return True if the merchant name marks a refund / credit row.

    Uses ``startswith`` (not substring) so legitimate merchants that merely
    contain a keyword mid-word — e.g. 「退休俱樂部」 — are not mis-flagged.
    Banks may pass ``extra_keywords`` for their own credit wording.
    """
    stripped = merchant.lstrip()
    if not stripped:
        return False
    return stripped.startswith(GENERAL_REFUND_KEYWORDS + extra_keywords)


def parse_amount_cell(raw: str) -> int:
    """Parse an NTD amount cell into a signed integer.

    Handles the three refund encodings real bills use, without raising on
    otherwise-valid numeric input:

    - ``"-500"`` / ``"－500"`` → ``-500``
    - ``"(500)"`` / ``"（500）"`` → ``-500`` (accounting parentheses = credit)
    - ``"500"`` → ``500``

    Commas and surrounding whitespace are stripped. Raises ``ValueError`` for
    genuinely non-numeric input so callers keep their existing ``try/except``
    (which logs and skips the row).
    """
    text = raw.strip().replace(",", "")
    negative = False
    if (text.startswith("(") and text.endswith(")")) or (
        text.startswith("（") and text.endswith("）")
    ):
        negative = True
        text = text[1:-1].strip()
    if text[:1] in ("-", "－", "−"):
        negative = True
        text = text[1:].strip()
    value = int(text)
    return -value if negative else value
