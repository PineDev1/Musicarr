"""restore_backup must reject an oversized upload without buffering the
whole body first — the previous implementation called `await file.read()`
(no size limit) before checking MAX_UPLOAD_BYTES, so the cap did nothing to
bound memory use.
"""
from __future__ import annotations

import asyncio

import pytest
from fastapi import HTTPException

from app.api.backup import MAX_UPLOAD_BYTES, restore_backup


class ChunkedUploadFile:
    """Fake UploadFile that serves data in fixed-size chunks and records how
    many bytes were actually requested/consumed, so a test can prove the
    handler stopped reading once it exceeded the cap instead of reading the
    whole (huge) body."""

    def __init__(self, total_size: int, chunk_size: int = 1024 * 1024):
        self.total_size = total_size
        self.chunk_size = chunk_size
        self._served = 0
        self.max_served = 0

    async def read(self, size: int = -1) -> bytes:
        remaining = self.total_size - self._served
        if remaining <= 0:
            return b""
        take = min(size if size and size > 0 else remaining, remaining)
        self._served += take
        self.max_served = max(self.max_served, self._served)
        return b"x" * take


def test_restore_backup_rejects_oversized_upload_without_reading_it_all():
    huge = MAX_UPLOAD_BYTES * 4
    fake = ChunkedUploadFile(huge)

    with pytest.raises(HTTPException) as exc:
        asyncio.run(restore_backup(fake))  # type: ignore[arg-type]

    assert exc.value.status_code == 400
    # The handler must bail out shortly after crossing the cap, not after
    # consuming the entire (much larger) upload.
    assert fake.max_served <= MAX_UPLOAD_BYTES + fake.chunk_size
    assert fake.max_served < huge


def test_restore_backup_rejects_empty_upload():
    fake = ChunkedUploadFile(0)
    with pytest.raises(HTTPException) as exc:
        asyncio.run(restore_backup(fake))  # type: ignore[arg-type]
    assert exc.value.status_code == 400
