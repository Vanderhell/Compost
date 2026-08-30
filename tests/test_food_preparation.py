from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from mathematical_organism.food_preparation import PreparedFood, streams_are_byte_identical  # noqa: E402
from mathematical_organism.food import FileFoodSpace  # noqa: E402


class FoodPreparationTests(unittest.TestCase):
    def _prepared(self, data: bytes, *, parcel_size: int = 64, context_overlap: int = 2) -> tuple[tempfile.TemporaryDirectory[str], PreparedFood]:
        directory = tempfile.TemporaryDirectory()
        path = Path(directory.name) / "input.bin"
        path.write_bytes(data)
        return directory, PreparedFood(path, parcel_size=parcel_size, context_overlap=context_overlap)

    def test_empty_and_single_byte_metadata_are_exact(self) -> None:
        directory, empty = self._prepared(b"")
        self.addCleanup(directory.cleanup)
        self.assertEqual((empty.metadata.file_size, empty.metadata.parcel_count, empty.metadata.last_parcel_size), (0, 0, 0))
        self.assertTrue(streams_are_byte_identical(empty))
        directory, single = self._prepared(b"\xA7", parcel_size=64, context_overlap=3)
        self.addCleanup(directory.cleanup)
        self.assertEqual((single.metadata.file_size, single.metadata.parcel_count, single.metadata.last_parcel_size), (1, 1, 1))
        with single.path.open("rb") as handle:
            window = single.read_window(handle, 0, 1)
        self.assertEqual(window.nutrition, b"\xA7")
        self.assertEqual((window.left_context, window.right_context), (b"", b""))

    def test_boundaries_partial_parcel_and_context_preserve_raw_values(self) -> None:
        source = bytes(range(256)) + b"\xA7\xF3\x00"
        directory, prepared = self._prepared(source, parcel_size=64, context_overlap=3)
        self.addCleanup(directory.cleanup)
        self.assertEqual(prepared.metadata.last_parcel_size, 3)
        self.assertTrue(streams_are_byte_identical(prepared, chunk_size=17))
        with prepared.path.open("rb") as handle:
            window = prepared.read_window(handle, 63, 2)
        self.assertEqual(window.left_context, source[60:63])
        self.assertEqual(window.nutrition, source[63:65])
        self.assertEqual(window.right_context, source[65:68])
        self.assertEqual(prepared.parcel_bounds(4), (256, 259))

    def test_large_file_is_validated_in_streaming_chunks(self) -> None:
        source = bytes(range(256)) * 4096
        directory, prepared = self._prepared(source, parcel_size=1024)
        self.addCleanup(directory.cleanup)
        self.assertEqual(prepared.metadata.file_size, 1 << 20)
        self.assertEqual(prepared.metadata.parcel_count, 1024)
        self.assertTrue(streams_are_byte_identical(prepared))
        state = prepared.state_memory(interval_count=prepared.parcel_count)
        self.assertEqual(state.byte_bitmap_bytes, (1 << 20) // 8)
        self.assertFalse(state.parcel_level_exact_for_partial_bites)
        self.assertLess(state.interval_estimated_bytes, state.byte_bitmap_bytes)
        fragmented = prepared.state_memory(interval_count=prepared.metadata.file_size)
        self.assertGreater(fragmented.interval_estimated_bytes, state.byte_bitmap_bytes)

    def test_prepared_parcel_allows_several_exact_partial_bites(self) -> None:
        directory, prepared = self._prepared(b"ABCDEFGH", parcel_size=4, context_overlap=1)
        self.addCleanup(directory.cleanup)
        food = FileFoodSpace(prepared.path, parcel_size=4, context_overlap=1)
        first = food.claim(0, 1, skipped_regions=0)
        second = food.claim(0, 3, skipped_regions=0)
        third = food.claim(1, 4, skipped_regions=0)
        self.assertEqual((first.offset, first.length), (0, 1))  # type: ignore[union-attr]
        self.assertEqual((second.offset, second.length), (1, 3))  # type: ignore[union-attr]
        self.assertEqual((third.offset, third.length), (4, 4))  # type: ignore[union-attr]
        with prepared.path.open("rb") as handle:
            self.assertEqual(food.read(handle, second)[0], tuple(b"BCD"))  # type: ignore[arg-type]
        self.assertEqual(food.metrics.bytes_consumed, prepared.file_size)
        self.assertEqual(food.metrics.duplicate_consumption, 0)


if __name__ == "__main__":
    unittest.main()
