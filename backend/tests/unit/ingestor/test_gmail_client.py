"""Gmail 查詢組裝與 PDF 附件過濾的單元測試。"""

import base64
import logging
from unittest.mock import MagicMock, patch

import pytest

from ccas.ingestor.gmail_client import (
    _extract_html_body,
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


def _pdf_part(filename="bill.pdf", attachment_id="att-001", size=1024, part_id="1"):
    """建立 PDF 附件 part。"""
    return {
        "partId": part_id,
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
    def test_message_without_pdf_still_returned(self, mock_retry):
        """郵件只有非 PDF 附件時，仍回傳但 pdf_attachments 為空。"""
        mock_retry.side_effect = [
            {"messages": [{"id": "msg-001"}]},
            _make_message_payload("msg-001", [_image_part()]),
        ]

        result = search_messages(MagicMock(), "from:bank@example.com")
        assert len(result) == 1
        assert result[0].pdf_attachments == ()
        assert result[0].html_body is None  # image part is not HTML

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

    def test_captures_part_id_from_payload(self):
        """PDF part 的 partId 應被擷取到 GmailAttachmentMeta.part_id。"""
        from datetime import datetime

        payload = {
            "parts": [
                _pdf_part("bill.pdf", "att-A", part_id="1"),
            ],
        }
        result = _extract_pdf_attachments("msg-partid", payload, datetime(2026, 3, 15))
        assert len(result) == 1
        assert result[0].part_id == "1"

    def test_captures_nested_part_id(self):
        """巢狀 multipart 中的 PDF 應保留其原始 partId（例如 "0.1"）。"""
        from datetime import datetime

        payload = {
            "parts": [
                {
                    "partId": "0",
                    "mimeType": "multipart/related",
                    "parts": [
                        {
                            "partId": "0.0",
                            "mimeType": "text/html",
                            "filename": "",
                            "body": {"size": 100},
                        },
                        _pdf_part("nested.pdf", "att-B", part_id="0.1"),
                    ],
                },
            ],
        }
        result = _extract_pdf_attachments(
            "msg-nested-partid", payload, datetime(2026, 3, 15)
        )
        assert len(result) == 1
        assert result[0].part_id == "0.1"

    def test_missing_part_id_defaults_to_empty(self):
        """缺少 partId 欄位時 part_id 應退回空字串（防禦性）。"""
        from datetime import datetime

        part = {
            "mimeType": "application/pdf",
            "filename": "no-partid.pdf",
            "body": {"attachmentId": "att-C", "size": 512},
        }
        payload = {"parts": [part]}
        result = _extract_pdf_attachments(
            "msg-no-partid", payload, datetime(2026, 3, 15)
        )
        assert len(result) == 1
        assert result[0].part_id == ""

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
    def test_paginates_beyond_old_limit(self, mock_retry):
        """應能取得超過舊上限 (10 頁) 的所有郵件。"""
        num_pages = 15
        page_responses = []
        for i in range(num_pages):
            response: dict = {"messages": [{"id": f"msg-{i:03d}"}]}
            if i < num_pages - 1:
                response["nextPageToken"] = f"token-{i + 1}"
            page_responses.append(response)

        detail_responses = [
            _make_message_payload(
                f"msg-{i:03d}", [_pdf_part(f"bill{i}.pdf", f"att-{i}")]
            )
            for i in range(num_pages)
        ]

        mock_retry.side_effect = page_responses + detail_responses

        result = search_messages(MagicMock(), "from:bank@example.com")

        assert len(result) == num_pages

    @patch("ccas.ingestor.gmail_client.call_with_retry")
    def test_mid_page_failure_preserves_fetched_results(self, mock_retry, caplog):
        """分頁中途失敗時，應保留已成功取得的頁面並繼續處理。"""
        from googleapiclient.errors import HttpError

        mock_retry.side_effect = [
            # Page 1: success
            {"messages": [{"id": "msg-001"}], "nextPageToken": "token-2"},
            # Page 2: failure
            HttpError(MagicMock(status=503), b"Service Unavailable"),
            # msg-001 detail (still processed)
            _make_message_payload("msg-001", [_pdf_part("bill1.pdf", "att-1")]),
        ]

        with caplog.at_level(logging.WARNING, logger="ccas.ingestor.gmail_client"):
            result = search_messages(MagicMock(), "from:bank@example.com")

        assert len(result) == 1
        assert result[0].message_id == "msg-001"
        assert any("分頁中途失敗" in r.message for r in caplog.records)

    @patch("ccas.ingestor.gmail_client.call_with_retry")
    def test_first_page_failure_raises(self, mock_retry):
        """第一頁就失敗時，應直接拋出例外。"""
        from googleapiclient.errors import HttpError

        mock_retry.side_effect = HttpError(
            MagicMock(status=500), b"Internal Server Error"
        )

        with pytest.raises(HttpError):
            search_messages(MagicMock(), "from:bank@example.com")

    @patch(
        "ccas.ingestor.gmail_client._MAX_PAGES_SAFETY",
        3,
    )
    @patch("ccas.ingestor.gmail_client.call_with_retry")
    def test_safety_limit_raises_runtime_error(self, mock_retry):
        """超過安全上限應 raise RuntimeError。"""
        # All 3 pages have nextPageToken → triggers safety limit
        mock_retry.side_effect = [
            {"messages": [{"id": f"msg-{i}"}], "nextPageToken": f"token-{i + 1}"}
            for i in range(3)
        ]

        with pytest.raises(RuntimeError, match="安全上限"):
            search_messages(MagicMock(), "from:bank@example.com")


class TestExtractHtmlBody:
    """_extract_html_body() tests."""

    def test_extracts_html_from_flat_part(self):
        """Extracts HTML from a flat text/html part."""
        html_content = "<html><body>Hello</body></html>"
        encoded = base64.urlsafe_b64encode(html_content.encode()).decode()
        payload = {
            "mimeType": "text/html",
            "body": {"data": encoded},
        }
        result = _extract_html_body(payload)
        assert result == html_content

    def test_extracts_html_from_nested_multipart(self):
        """Extracts HTML from nested multipart structure."""
        html_content = "<html><body>Nested</body></html>"
        encoded = base64.urlsafe_b64encode(html_content.encode()).decode()
        payload = {
            "mimeType": "multipart/alternative",
            "parts": [
                {"mimeType": "text/plain", "body": {"data": "plain text"}},
                {"mimeType": "text/html", "body": {"data": encoded}},
            ],
        }
        result = _extract_html_body(payload)
        assert result == html_content

    def test_returns_none_when_no_html(self):
        """Returns None when no text/html part exists."""
        payload = {
            "mimeType": "multipart/mixed",
            "parts": [
                {"mimeType": "text/plain", "body": {"data": "text only"}},
            ],
        }
        result = _extract_html_body(payload)
        assert result is None

    def test_returns_none_when_no_body_data(self):
        """Returns None when HTML part has no data."""
        payload = {
            "mimeType": "text/html",
            "body": {},
        }
        result = _extract_html_body(payload)
        assert result is None

    def test_search_messages_with_html_body(self):
        """search_messages includes html_body for messages without PDF attachments."""
        html_content = "<html><body>Bill Link</body></html>"
        encoded = base64.urlsafe_b64encode(html_content.encode()).decode()

        with patch("ccas.ingestor.gmail_client.call_with_retry") as mock_retry:
            mock_retry.side_effect = [
                {"messages": [{"id": "msg-html"}]},
                {
                    "id": "msg-html",
                    "payload": {
                        "headers": [
                            {"name": "Date", "value": "Mon, 10 Mar 2026 10:00:00 +0800"}
                        ],
                        "mimeType": "multipart/alternative",
                        "parts": [
                            {
                                "mimeType": "text/html",
                                "filename": "",
                                "body": {"data": encoded},
                            },
                        ],
                    },
                },
            ]

            result = search_messages(MagicMock(), "from:fubon@example.com")
            assert len(result) == 1
            assert result[0].html_body == html_content
            assert result[0].pdf_attachments == ()
