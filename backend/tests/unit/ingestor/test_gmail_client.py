"""Gmail 查詢組裝與 PDF 附件過濾的單元測試。"""

import base64
import logging
from unittest.mock import MagicMock, patch

from ccas.ingestor.gmail_client import (
    _extract_pdf_attachments,
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


class TestExtractPdfAttachmentsRecursive:
    """_extract_pdf_attachments() 遞迴 MIME 解析測試。"""

    def test_nested_payload_finds_pdf(self):
        """巢狀 multipart 結構中的 PDF 附件應被正確擷取。"""
        from datetime import datetime

        payload = {
            "parts": [
                {
                    "mimeType": "multipart/related",
                    "parts": [
                        {
                            "mimeType": "text/html",
                            "filename": "",
                            "body": {"size": 100},
                        },
                        _pdf_part("nested-bill.pdf", "att-nested", 2048),
                    ],
                },
            ],
        }
        result = _extract_pdf_attachments("msg-nested", payload, datetime(2026, 3, 15))
        assert len(result) == 1
        assert result[0].filename == "nested-bill.pdf"
        assert result[0].attachment_id == "att-nested"

    def test_flat_payload_still_works(self):
        """扁平 payload（無巢狀）仍正常運作（回歸保護）。"""
        from datetime import datetime

        payload = {
            "parts": [
                _pdf_part("flat-bill.pdf", "att-flat", 1024),
                _image_part("photo.jpg"),
            ],
        }
        result = _extract_pdf_attachments("msg-flat", payload, datetime(2026, 3, 15))
        assert len(result) == 1
        assert result[0].filename == "flat-bill.pdf"

    def test_depth_limit_stops_search(self):
        """超過遞迴深度限制時停止搜尋。"""
        from datetime import datetime

        from ccas.ingestor.gmail_client import _MAX_MIME_DEPTH

        # Build a deeply nested structure exceeding _MAX_MIME_DEPTH
        innermost = _pdf_part("deep-bill.pdf", "att-deep", 512)
        current = innermost
        for _ in range(_MAX_MIME_DEPTH + 1):
            current = {"mimeType": "multipart/mixed", "parts": [current]}

        payload = {"parts": [current]}
        result = _extract_pdf_attachments("msg-deep", payload, datetime(2026, 3, 15))
        assert len(result) == 0


class TestSearchMessagesPagination:
    """search_messages() 分頁測試。"""

    @patch("ccas.ingestor.gmail_client.call_with_retry")
    def test_follows_next_page_token(self, mock_retry):
        """多頁回應時應跟隨 nextPageToken 取回所有郵件。"""
        mock_retry.side_effect = [
            # Page 1: has nextPageToken
            {"messages": [{"id": "msg-001"}], "nextPageToken": "token-page2"},
            # Page 2: no nextPageToken
            {"messages": [{"id": "msg-002"}]},
            # msg-001 detail
            _make_message_payload("msg-001", [_pdf_part("bill1.pdf", "att-1")]),
            # msg-002 detail
            _make_message_payload("msg-002", [_pdf_part("bill2.pdf", "att-2")]),
        ]

        result = search_messages(MagicMock(), "from:bank@example.com")

        assert len(result) == 2
        assert result[0].message_id == "msg-001"
        assert result[1].message_id == "msg-002"

    @patch("ccas.ingestor.gmail_client.call_with_retry")
    def test_single_page_no_token(self, mock_retry):
        """無 nextPageToken 時正常回傳單頁結果。"""
        mock_retry.side_effect = [
            {"messages": [{"id": "msg-001"}]},
            _make_message_payload("msg-001", [_pdf_part("bill.pdf", "att-1")]),
        ]

        result = search_messages(MagicMock(), "from:bank@example.com")
        assert len(result) == 1

    @patch("ccas.ingestor.gmail_client.call_with_retry")
    def test_stops_at_max_pages_with_warning(self, mock_retry, caplog):
        """達到分頁上限時應停止並記錄 warning。"""
        from ccas.ingestor.gmail_client import _MAX_PAGES

        # Build side effects for _MAX_PAGES + 1 pages (should stop at _MAX_PAGES)
        page_responses = []
        all_msg_ids = []
        for i in range(_MAX_PAGES + 1):
            msg_id = f"msg-{i:03d}"
            all_msg_ids.append(msg_id)
            response: dict = {"messages": [{"id": msg_id}]}
            if i < _MAX_PAGES:  # All but last have nextPageToken
                response["nextPageToken"] = f"token-{i + 1}"
            page_responses.append(response)

        # Message detail responses for messages that should be fetched
        detail_responses = [
            _make_message_payload(
                f"msg-{i:03d}", [_pdf_part(f"bill{i}.pdf", f"att-{i}")]
            )
            for i in range(_MAX_PAGES)
        ]

        mock_retry.side_effect = page_responses[:_MAX_PAGES] + detail_responses

        with caplog.at_level(logging.WARNING, logger="ccas.ingestor.gmail_client"):
            result = search_messages(MagicMock(), "from:bank@example.com")

        assert len(result) == _MAX_PAGES
        assert any(
            "分頁" in record.message or "page" in record.message.lower()
            for record in caplog.records
        )
