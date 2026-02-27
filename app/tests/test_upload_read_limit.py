from __future__ import annotations

import asyncio
from io import BytesIO

from fastapi import UploadFile

from app.api import routes


def test_read_upload_with_limit_supports_bytesio_uploadfile() -> None:
    async def _run() -> None:
        file = UploadFile(filename="sample.pdf", file=BytesIO(b"%PDF-1.4"))
        content = await routes._read_upload_with_limit(file)
        assert content == b"%PDF-1.4"

    asyncio.run(_run())
