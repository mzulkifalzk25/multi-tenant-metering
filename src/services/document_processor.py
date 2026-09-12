"""Fans a Job out into WorkUnitSpecs and executes the work for one unit.

Metadata extraction (page/frame counts) is read through an injectable
:class:`FileMetadataReaderProtocol` so unit tests can exercise the fan-out
logic without real PDF/video files on disk; :class:`FilesystemMetadataReader`
is the production implementation, using only the standard library.
"""

from __future__ import annotations

import asyncio
import re
import struct
from pathlib import Path
from typing import Protocol

from src.entities.job import Job
from src.entities.work_unit import WorkUnit
from src.services.llm_service import LLMServiceProtocol, NullLLMService
from src.shared.constants import VIDEO_FRAME_SAMPLE_INTERVAL_SECONDS, FileType, WorkUnitType
from src.shared.errors import DocumentProcessingError, UnsupportedFileTypeError
from src.use_cases.protocols import WorkUnitSpec

_PDF_PAGE_PATTERN = re.compile(rb"/Type\s*/Page(?!s)")


class FileMetadataReaderProtocol(Protocol):
    def read_pdf_page_count(self, file_path: str) -> int:
        ...

    def read_video_duration_seconds(self, file_path: str) -> float:
        ...


class FilesystemMetadataReader:
    """Best-effort metadata extraction using only the standard library."""

    def read_pdf_page_count(self, file_path: str) -> int:
        data = Path(file_path).read_bytes()
        count = len(_PDF_PAGE_PATTERN.findall(data))
        return max(count, 1)

    def read_video_duration_seconds(self, file_path: str) -> float:
        data = Path(file_path).read_bytes()
        duration = _read_mp4_duration_seconds(data)
        if duration is None:
            raise DocumentProcessingError(f"Could not determine video duration for {file_path}")
        return duration


def _read_mp4_duration_seconds(data: bytes) -> float | None:
    """Walk top-level ISO BMFF boxes looking for moov/mvhd to read duration."""
    offset = 0
    while offset + 8 <= len(data):
        box_size = int.from_bytes(data[offset : offset + 4], "big")
        box_type = data[offset + 4 : offset + 8]
        if box_size < 8:
            break
        if box_type == b"moov":
            duration = _find_mvhd_duration(data[offset + 8 : offset + box_size])
            if duration is not None:
                return duration
        offset += box_size
    return None


def _find_mvhd_duration(moov_data: bytes) -> float | None:
    offset = 0
    while offset + 8 <= len(moov_data):
        box_size = int.from_bytes(moov_data[offset : offset + 4], "big")
        box_type = moov_data[offset + 4 : offset + 8]
        if box_size < 8:
            break
        if box_type == b"mvhd":
            payload = moov_data[offset + 8 : offset + box_size]
            version = payload[0]
            if version == 1:
                timescale = struct.unpack(">I", payload[20:24])[0]
                duration = struct.unpack(">Q", payload[24:32])[0]
            else:
                timescale = struct.unpack(">I", payload[12:16])[0]
                duration = struct.unpack(">I", payload[16:20])[0]
            return duration / timescale if timescale else None
        offset += box_size
    return None


class DocumentProcessor:
    def __init__(
        self,
        metadata_reader: FileMetadataReaderProtocol | None = None,
        llm_service: LLMServiceProtocol | None = None,
    ) -> None:
        self._metadata_reader = metadata_reader or FilesystemMetadataReader()
        self._llm_service = llm_service or NullLLMService()

    async def expand(self, job: Job) -> list[WorkUnitSpec]:
        if job.file_type == FileType.PDF:
            page_count = await asyncio.to_thread(
                self._metadata_reader.read_pdf_page_count, job.file_path
            )
            return [WorkUnitSpec(WorkUnitType.PAGE, n) for n in range(page_count)]

        if job.file_type == FileType.IMAGE:
            return [WorkUnitSpec(WorkUnitType.IMAGE, 0)]

        if job.file_type == FileType.VIDEO:
            duration_seconds = await asyncio.to_thread(
                self._metadata_reader.read_video_duration_seconds, job.file_path
            )
            frame_count = max(int(duration_seconds // VIDEO_FRAME_SAMPLE_INTERVAL_SECONDS) + 1, 1)
            return [WorkUnitSpec(WorkUnitType.FRAME, n) for n in range(frame_count)]

        raise UnsupportedFileTypeError(f"Unsupported file type: {job.file_type}")

    async def process_unit(self, job: Job, work_unit: WorkUnit) -> None:
        await self._llm_service.analyze(job, work_unit)
