"""Gmail API 封裝模組。

提供郵件搜尋與附件下載功能，是唯一直接呼叫
google-api-python-client 的模組。
"""

import base64
import collections.abc
import email.utils
import logging
from dataclasses import dataclass
from datetime import UTC, datetime

from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

from ccas.ingestor.retry import call_with_retry

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class GmailAttachmentMeta:
    """Gmail 附件的識別資訊與 metadata。

    Attributes:
        message_id: Gmail message ID。
        attachment_id: Gmail attachment ID（非穩定，每次 API 呼叫重生，僅用於下載）。
        part_id: Gmail MIME payload 的 partId（例 "1"、"0.1"），
            為結構性穩定識別碼，用於 staging dedupe 鍵。
        filename: 原始附件檔名。
        message_date: 郵件日期。
        size: 附件大小（bytes）。
    """

    message_id: str
    attachment_id: str
    filename: str
    message_date: datetime
    size: int
    part_id: str = ""


@dataclass(frozen=True)
class GmailMessage:
    """Gmail 郵件的識別資訊與 PDF 附件清單。

    Attributes:
        message_id: Gmail message ID。
        message_date: 郵件日期。
        pdf_attachments: 該郵件中的 PDF 附件清單。
        html_body: 郵件的 HTML 內容（僅當無 PDF 附件時填入）。
    """

    message_id: str
    message_date: datetime
    pdf_attachments: tuple[GmailAttachmentMeta, ...]
    html_body: str | None = None


def build_gmail_service(credentials: Credentials):
    """建立 Gmail API service 物件。

    Args:
        credentials: 已驗證的 OAuth Credentials。

    Returns:
        Gmail API service Resource。
    """
    return build("gmail", "v1", credentials=credentials, cache_discovery=False)


def _is_pdf_part(part: dict) -> bool:
    """判斷 MIME part 是否為 PDF 附件。"""
    mime_type = part.get("mimeType", "")
    filename = part.get("filename", "")
    if not filename:
        return False
    return mime_type == "application/pdf" or filename.lower().endswith(".pdf")


def _parse_message_date(headers: list[dict]) -> datetime:
    """從郵件 headers 解析日期。"""
    for header in headers:
        if header.get("name", "").lower() == "date":
            parsed = email.utils.parsedate_to_datetime(header["value"])
            return parsed.astimezone(UTC).replace(tzinfo=None)
    return datetime.now(UTC).replace(tzinfo=None)


_MAX_MIME_DEPTH = 10


def _collect_pdf_parts(
    message_id: str,
    part: dict,
    message_date: datetime,
    out: list[GmailAttachmentMeta],
    depth: int = 0,
) -> None:
    """遞迴搜尋 MIME part 中的 PDF 附件。

    Args:
        message_id: Gmail message ID.
        part: MIME part dict.
        message_date: 郵件日期.
        out: 收集結果的 list（原地修改）.
        depth: 目前遞迴深度.
    """
    if depth > _MAX_MIME_DEPTH:
        return

    if _is_pdf_part(part):
        body = part.get("body", {})
        attachment_id = body.get("attachmentId")
        if attachment_id:
            out.append(
                GmailAttachmentMeta(
                    message_id=message_id,
                    attachment_id=attachment_id,
                    filename=part["filename"],
                    message_date=message_date,
                    size=body.get("size", 0),
                    part_id=str(part.get("partId", "")),
                )
            )
        return

    for sub in part.get("parts", []):
        _collect_pdf_parts(message_id, sub, message_date, out, depth + 1)


def _extract_pdf_attachments(
    message_id: str, payload: dict, message_date: datetime
) -> list[GmailAttachmentMeta]:
    """從 message payload 提取 PDF 附件 metadata。"""
    attachments: list[GmailAttachmentMeta] = []
    for part in payload.get("parts", []):
        _collect_pdf_parts(message_id, part, message_date, attachments)
    return attachments


def _extract_html_body(payload: dict, depth: int = 0) -> str | None:
    """從 message payload 遞迴搜尋 HTML 內容。

    Args:
        payload: Gmail message payload（或其子 MIME part）。
        depth: 目前遞迴深度。

    Returns:
        解碼後的 HTML 字串，若找不到則回傳 None。
    """
    if depth > _MAX_MIME_DEPTH:
        return None

    mime_type = payload.get("mimeType", "")

    if mime_type == "text/html":
        body = payload.get("body", {})
        data = body.get("data")
        if data:
            return base64.urlsafe_b64decode(data).decode("utf-8", errors="replace")
        return None

    for part in payload.get("parts", []):
        result = _extract_html_body(part, depth + 1)
        if result is not None:
            return result

    return None


_MAX_PAGES_SAFETY = 100


def _iter_message_refs(
    service, gmail_filter: str
) -> collections.abc.Iterator[list[dict]]:
    """逐頁 yield Gmail message refs。

    Raises:
        RuntimeError: 分頁數超過安全上限。
    """
    page_token: str | None = None
    for _page in range(_MAX_PAGES_SAFETY):
        request_kwargs: dict = {"userId": "me", "q": gmail_filter}
        if page_token:
            request_kwargs["pageToken"] = page_token

        messages_response = call_with_retry(
            lambda kwargs=request_kwargs: (
                service.users().messages().list(**kwargs).execute()
            )
        )

        refs = messages_response.get("messages", [])
        if refs:
            yield refs
        page_token = messages_response.get("nextPageToken")
        if not page_token:
            return
    raise RuntimeError(f"Gmail 搜尋分頁超過安全上限 ({_MAX_PAGES_SAFETY} 頁)")


def search_messages(
    service,
    gmail_filter: str,
    *,
    bank_code: str | None = None,
    partial_errors: list[str] | None = None,
) -> list[GmailMessage]:
    """依 gmail_filter 搜尋 Gmail 郵件，並解析每封郵件的 PDF 附件。

    含 PDF 附件的郵件以 pdf_attachments 回傳；不含 PDF 附件的郵件
    會嘗試擷取 HTML 內容，供 web-fetch 流程使用。

    Args:
        service: Gmail API service 物件。
        gmail_filter: Gmail 搜尋語法字串。
        bank_code: 觸發此次搜尋的銀行代碼，用於分頁中途失敗時的可觀察性歸因。
        partial_errors: 若提供，分頁中途失敗（部分成功）時會 append 一筆說明，
            讓呼叫端（pipeline summary）得以揭露「有郵件因分頁失敗未處理」。

    Returns:
        符合條件的 GmailMessage 清單。
    """
    all_message_refs: list[dict] = []
    try:
        for page_refs in _iter_message_refs(service, gmail_filter):
            all_message_refs.extend(page_refs)
    except RuntimeError:
        raise  # safety limit from _iter_message_refs — must not be swallowed
    except Exception:
        if not all_message_refs:
            raise
        bank_label = bank_code or "?"
        logger.warning(
            "銀行 %s Gmail 分頁中途失敗，已取得 %d 筆訊息，繼續處理",
            bank_label,
            len(all_message_refs),
            exc_info=True,
        )
        if partial_errors is not None:
            partial_errors.append(
                f"銀行 {bank_label} Gmail 分頁中途失敗，"
                f"已取得 {len(all_message_refs)} 筆訊息，繼續處理"
            )

    if not all_message_refs:
        return []

    result: list[GmailMessage] = []

    for msg_ref in all_message_refs:
        msg_id = msg_ref["id"]
        try:
            msg_data = call_with_retry(
                lambda _id=msg_id: (
                    service.users().messages().get(userId="me", id=_id).execute()
                )
            )

            payload = msg_data.get("payload", {})
            headers = payload.get("headers", [])
            message_date = _parse_message_date(headers)

            pdf_attachments = _extract_pdf_attachments(msg_id, payload, message_date)
            html_body: str | None = None
            if not pdf_attachments:
                html_body = _extract_html_body(payload)

            result.append(
                GmailMessage(
                    message_id=msg_id,
                    message_date=message_date,
                    pdf_attachments=tuple(pdf_attachments),
                    html_body=html_body,
                )
            )
        except RuntimeError:
            raise  # safety limit from call_with_retry — must not be swallowed
        except Exception:
            # 單封郵件擷取失敗：隔離該封並繼續處理其餘郵件（與分頁中途失敗
            # 路徑對稱），避免單封失敗中止整銀行剩餘郵件。
            bank_label = bank_code or "?"
            logger.warning(
                "銀行 %s Gmail 郵件 %s 擷取失敗，已略過該封，繼續處理",
                bank_label,
                msg_id,
                exc_info=True,
            )
            if partial_errors is not None:
                partial_errors.append(
                    f"銀行 {bank_label} Gmail 郵件 {msg_id} 擷取失敗，已略過該封"
                )
            continue

    return result


def download_attachment(service, message_id: str, attachment_id: str) -> bytes:
    """下載指定 Gmail 附件的原始 bytes。

    Args:
        service: Gmail API service 物件。
        message_id: Gmail message ID。
        attachment_id: Gmail attachment ID。

    Returns:
        附件的原始 bytes。
    """
    attachment_data = call_with_retry(
        lambda: (
            service.users()
            .messages()
            .attachments()
            .get(userId="me", messageId=message_id, id=attachment_id)
            .execute()
        )
    )

    data = attachment_data["data"]
    return base64.urlsafe_b64decode(data)
