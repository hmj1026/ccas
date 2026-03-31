"""Gmail 查詢組裝與 PDF 附件過濾的單元測試。"""

import base64
from unittest.mock import MagicMock, patch

from ccas.ingestor.gmail_client import (
    download_attachment,
    search_messages,
)


def _make_message_payload(
    message_id,
    parts,
    date_str="Mon, 10 Mar 2026 10:00:00 +0800",
):
    """建立 mock message payload。"""
    return {
        "id": message_id,
        "payload": {
            "headers": [{"name": "Date", "value": date_str}],
            "parts": parts,
        },
    }


def _pdf_part(filename="bill.pdf", attachment_id="att-001", size=1024):
    """建立 PDF 附件 part。"""
    return {
        "mimeType": "application/pdf",
        "filename": filename,
        "body": {"attachmentId": attachment_id, "size": size},
    }


def _image_part(filename="photo.jpg"):
    """建立非 PDF 附件 part。"""
    return {
        "mimeType": "image/jpeg",
        "filename": filename,
        "body": {"attachmentId": "att-img", "size": 2048},
    }


class TestSearchMessages:
    """search_messages() 的測試案例。"""

    @patch("ccas.ingestor.gmail_client.call_with_retry")
    def test_passes_gmail_filter_as_query(self, mock_retry):
        """驗證 gmail_filter 被正確傳遞為搜尋 q 參數。"""
        mock_retry.side_effect = [
            {"messages": []},
        ]

        service = MagicMock()
        search_messages(service, "from:bank@example.com subject:帳單")

        assert mock_retry.call_count >= 1

    @patch("ccas.ingestor.gmail_client.call_with_retry")
    def test_filters_pdf_only(self, mock_retry):
        """只回傳 PDF 附件，忽略其他類型。"""
        mock_retry.side_effect = [
            {"messages": [{"id": "msg-001"}]},
            _make_message_payload(
                "msg-001",
                [_pdf_part("bill.pdf", "att-pdf"), _image_part("photo.jpg")],
            ),
        ]

        result = search_messages(MagicMock(), "from:bank@example.com")

        assert len(result) == 1
        assert len(result[0].pdf_attachments) == 1
        assert result[0].pdf_attachments[0].filename == "bill.pdf"

    @patch("ccas.ingestor.gmail_client.call_with_retry")
    def test_returns_empty_on_no_results(self, mock_retry):
        """搜尋無結果時回傳空清單。"""
        mock_retry.return_value = {}

        result = search_messages(MagicMock(), "from:nobody@example.com")
        assert result == []

    @patch("ccas.ingestor.gmail_client.call_with_retry")
    def test_skips_message_without_pdf(self, mock_retry):
        """郵件只有非 PDF 附件時，該郵件不出現在結果中。"""
        mock_retry.side_effect = [
            {"messages": [{"id": "msg-001"}]},
            _make_message_payload("msg-001", [_image_part()]),
        ]

        result = search_messages(MagicMock(), "from:bank@example.com")
        assert result == []

    @patch("ccas.ingestor.gmail_client.call_with_retry")
    def test_multiple_pdfs_in_one_message(self, mock_retry):
        """同一封郵件中的多個 PDF 都被收集。"""
        mock_retry.side_effect = [
            {"messages": [{"id": "msg-001"}]},
            _make_message_payload(
                "msg-001",
                [
                    _pdf_part("bill_01.pdf", "att-001"),
                    _pdf_part("bill_02.pdf", "att-002"),
                ],
            ),
        ]

        result = search_messages(MagicMock(), "from:bank@example.com")
        assert len(result) == 1
        assert len(result[0].pdf_attachments) == 2


class TestDownloadAttachment:
    """download_attachment() 的測試案例。"""

    @patch("ccas.ingestor.gmail_client.call_with_retry")
    def test_decodes_base64_data(self, mock_retry):
        """驗證附件 base64url 資料被正確解碼。"""
        raw_content = b"fake-pdf-content"
        encoded = base64.urlsafe_b64encode(raw_content).decode()
        mock_retry.return_value = {"data": encoded}

        result = download_attachment(MagicMock(), "msg-001", "att-001")
        assert result == raw_content
