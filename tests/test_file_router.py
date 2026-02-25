"""Tests for app.services.ingest.file_router — upload routing by extension."""
from __future__ import annotations

import pytest

from app.services.ingest.file_router import IngestedUploadPayload, ingest_upload_bytes


class TestIngestUploadBytesRouting:
    def test_rejects_doc_format(self):
        with pytest.raises(ValueError, match=r"\.doc"):
            ingest_upload_bytes("test.doc", b"data")

    def test_rejects_unsupported_format(self):
        with pytest.raises(ValueError, match="unsupported"):
            ingest_upload_bytes("test.txt", b"data")

    def test_rejects_xlsx(self):
        with pytest.raises(ValueError, match="unsupported"):
            ingest_upload_bytes("test.xlsx", b"data")

    def test_rejects_empty_filename(self):
        with pytest.raises(ValueError, match="unsupported"):
            ingest_upload_bytes("", b"data")

    def test_doc_error_message_chinese(self):
        """Error message should suggest converting to .docx."""
        with pytest.raises(ValueError, match="docx"):
            ingest_upload_bytes("old.doc", b"data")


class TestIngestedUploadPayload:
    def test_dataclass_fields(self):
        payload = IngestedUploadPayload(
            blocks=[],
            page_count=5,
            source_format="pdf",
            content_type="application/pdf",
            parser_version="v2",
            full_text="hello",
        )
        assert payload.page_count == 5
        assert payload.source_format == "pdf"
        assert payload.page_meta == {}
