"""Gmail API 封裝模組。

提供郵件搜尋與附件下載功能，是唯一直接呼叫
google-api-python-client 的模組。
"""

import base64
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
        attachment_id: Gmail attachment ID。
        filename: 原始附件檔名。
        message_date: 郵件日期。
        size: 附件大小（bytes）。
    """

    message_id: str
    attachment_id: str
    filename: str
    message_date: datetime
    size: int


@dataclass(frozen=True)
class GmailMessage:
    """Gmail 郵件的識別資訊與 PDF 附件清單。

    Attributes:
        message_id: Gmail message ID。
        message_date: 郵件日期。
        pdf_attachments: 該郵件中的 PDF 附件清單。
    """

    message_id: str
    message_date: datetime
    pdf_attachments: tuple[GmailAttachmentMeta, ...]


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
    return datetime.utcnow()


def _extract_pdf_attachments(
    message_id: str, payload: dict, message_date: datetime
) -> list[GmailAttachmentMeta]:
    """從 message payload 提取 PDF 附件 metadata。"""
    attachments: list[GmailAttachmentMeta] = []
    parts = payload.get("parts", [])

    for part in parts:
        if not _is_pdf_part(part):
            continue

        body = part.get("body", {})
        attachment_id = body.get("attachmentId")
        if not attachment_id:
            continue

        attachments.append(
            GmailAttachmentMeta(
                message_id=message_id,
                attachment_id=attachment_id,
                filename=part["filename"],
                message_date=message_date,
                size=body.get("size", 0),
            )
        )

    return attachments


def search_messages(service, gmail_filter: str) -> list[GmailMessage]:
    """依 gmail_filter 搜尋 Gmail 郵件，並解析每封郵件的 PDF 附件。

    Args:
        service: Gmail API service 物件。
        gmail_filter: Gmail 搜尋語法字串。

    Returns:
        符合條件的 GmailMessage 清單，每個 message 只包含 PDF 附件。
        不含 PDF 附件的郵件會被過濾掉。
    """
    messages_response = call_with_retry(
        lambda: service.users()
        .messages()
        .list(userId="me", q=gmail_filter)
        .execute()
    )

    message_ids = messages_response.get("messages", [])
    if not message_ids:
        return []

    result: list[GmailMessage] = []

    for msg_ref in message_ids:
        msg_id = msg_ref["id"]
        msg_data = call_with_retry(
            lambda _id=msg_id: service.users()
            .messages()
            .get(userId="me", id=_id)
            .execute()
        )

        payload = msg_data.get("payload", {})
        headers = payload.get("headers", [])
        message_date = _parse_message_date(headers)

        pdf_attachments = _extract_pdf_attachments(msg_id, payload, message_date)
        if not pdf_attachments:
            continue

        result.append(
            GmailMessage(
                message_id=msg_id,
                message_date=message_date,
                pdf_attachments=tuple(pdf_attachments),
            )
        )

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
        lambda: service.users()
        .messages()
        .attachments()
        .get(userId="me", messageId=message_id, id=attachment_id)
        .execute()
    )

    data = attachment_data["data"]
    return base64.urlsafe_b64decode(data)
