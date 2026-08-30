from __future__ import annotations

"""Transparent preparation of a binary file for the FILE food-space layer.

Mathematical definition:
    For a source byte sequence ``b[0..N-1]``, preparation exposes exactly the
    same sequence.  It partitions positions into fixed physical parcels but
    does not interpret, filter, reorder, or retain the sequence.

Inputs: a seekable binary path, parcel size, and a read-only context width.
Outputs: small immutable metadata and bounded streaming reads.
Invariants: every returned nutrition byte has its original offset and value;
context has no nutritional ownership; no full-file byte copy is retained.
Complexity: O(N) streamed source hashing; O(k) for a k-byte read.
"""

from dataclasses import dataclass
import hashlib
from pathlib import Path
from typing import BinaryIO, Iterator


DEFAULT_PARCEL_SIZE = 64
HASH_CHUNK_SIZE = 64 * 1024


@dataclass(frozen=True, slots=True)
class FoodMetadata:
    """Persistent, content-neutral description of one prepared source file."""

    file_size: int
    parcel_size: int
    parcel_count: int
    last_parcel_size: int
    source_hash: str


@dataclass(frozen=True, slots=True)
class PreparedRead:
    """A transient ``context | nutrition | context`` read window."""

    offset: int
    nutrition: bytes
    left_context: bytes
    right_context: bytes

    @property
    def nutrition_length(self) -> int:
        return len(self.nutrition)

    @property
    def raw_window_size(self) -> int:
        return len(self.left_context) + len(self.nutrition) + len(self.right_context)


@dataclass(frozen=True, slots=True)
class FoodStateMemory:
    """Comparable storage estimates for exact claim-state representations."""

    byte_bitmap_bytes: int
    parcel_bitmap_bytes: int
    interval_count: int
    interval_estimated_bytes: int
    parcel_level_exact_for_partial_bites: bool


def _stream_hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while block := handle.read(HASH_CHUNK_SIZE):
            digest.update(block)
    return digest.hexdigest()


class PreparedFood:
    """A prepared file, with metadata separated from runtime food ownership."""

    def __init__(
        self,
        path: str | Path,
        *,
        parcel_size: int = DEFAULT_PARCEL_SIZE,
        context_overlap: int = 2,
    ) -> None:
        self.path = Path(path)
        if not self.path.is_file():
            raise ValueError(f"not a regular source file: {self.path}")
        if parcel_size <= 0 or context_overlap < 0:
            raise ValueError("parcel_size must be positive and context_overlap non-negative")
        size = self.path.stat().st_size
        parcel_count = (size + parcel_size - 1) // parcel_size
        self.metadata = FoodMetadata(
            file_size=size,
            parcel_size=parcel_size,
            parcel_count=parcel_count,
            last_parcel_size=0 if size == 0 else size - (parcel_count - 1) * parcel_size,
            source_hash=_stream_hash(self.path),
        )
        self.context_overlap = context_overlap

    @property
    def file_size(self) -> int:
        return self.metadata.file_size

    @property
    def parcel_size(self) -> int:
        return self.metadata.parcel_size

    @property
    def parcel_count(self) -> int:
        return self.metadata.parcel_count

    def parcel_bounds(self, parcel: int) -> tuple[int, int]:
        if not 0 <= parcel < self.parcel_count:
            raise ValueError("parcel outside prepared source")
        start = parcel * self.parcel_size
        return start, min(self.file_size, start + self.parcel_size)

    def read_window(self, handle: BinaryIO, offset: int, length: int) -> PreparedRead:
        """Stream one bounded read; returned context is observation, never food."""
        if offset < 0 or length < 0 or offset + length > self.file_size:
            raise ValueError("nutrition range outside prepared source")
        left_size = min(self.context_overlap, offset)
        right_size = min(self.context_overlap, self.file_size - offset - length)
        start = offset - left_size
        expected = left_size + length + right_size
        handle.seek(start)
        raw = handle.read(expected)
        if len(raw) != expected:
            raise IOError("short source read")
        nutrition_end = left_size + length
        result = PreparedRead(
            offset=offset,
            left_context=raw[:left_size],
            nutrition=raw[left_size:nutrition_end],
            right_context=raw[nutrition_end:],
        )
        del raw
        return result

    def iter_source_chunks(self, *, chunk_size: int = HASH_CHUNK_SIZE) -> Iterator[bytes]:
        """Yield original source bytes in bounded chunks for validation only."""
        if chunk_size <= 0:
            raise ValueError("chunk_size must be positive")
        with self.path.open("rb") as handle:
            while block := handle.read(chunk_size):
                yield block

    def state_memory(self, *, interval_count: int = 0) -> FoodStateMemory:
        """Measure representation costs; interval figures use two uint64 endpoints."""
        if interval_count < 0:
            raise ValueError("interval_count must be non-negative")
        return FoodStateMemory(
            byte_bitmap_bytes=(self.file_size + 7) // 8,
            parcel_bitmap_bytes=(self.parcel_count + 7) // 8,
            interval_count=interval_count,
            interval_estimated_bytes=interval_count * 16,
            parcel_level_exact_for_partial_bites=False,
        )


def streams_are_byte_identical(prepared: PreparedFood, *, chunk_size: int = HASH_CHUNK_SIZE) -> bool:
    """Compare prepared streaming reconstruction with its source without RAM copy."""
    with prepared.path.open("rb") as original:
        for reconstructed in prepared.iter_source_chunks(chunk_size=chunk_size):
            if original.read(len(reconstructed)) != reconstructed:
                return False
        return original.read(1) == b""
