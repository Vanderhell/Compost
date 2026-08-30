from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from mathematical_organism.food_sandbox import PhysicalFoodSandbox, SandboxFeedingHarness, stream_sha256  # noqa: E402


class PhysicalFoodSandboxTests(unittest.TestCase):
    REAL_PARTITION = (
        PROJECT_ROOT.parent / "cOMPOSABLE SPACE" / "esp32_build32"
        / "esp32s3_skip_space.ino.partitions_flashed.bin"
    )

    def test_partial_bites_physically_remove_ranges_and_empty_parcel(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "input.bin"
            source.write_bytes(bytes(range(16)))
            before_hash = stream_sha256(source)
            food = PhysicalFoodSandbox(source, root / "sandbox", parcel_size=16, context_overlap=2)
            first = food.claim(0, 5, skipped_regions=0)
            self.assertIsNotNone(first)
            bite, context = food.read(first)  # type: ignore[arg-type]
            self.assertEqual(bite, tuple(range(5)))
            self.assertEqual(context, 2)
            food.consume(first)  # type: ignore[arg-type]
            self.assertEqual(food.remaining, 11)
            self.assertEqual(sum(path.stat().st_size for path in food.food_dir.glob("*.food")), 11)
            second = food.claim(0, 11, skipped_regions=0)
            self.assertIsNotNone(second)
            food.consume(second)  # type: ignore[arg-type]
            self.assertEqual(food.remaining, 0)
            self.assertEqual(list(food.food_dir.glob("*.food")), [])
            food.assert_invariants()
            self.assertEqual(stream_sha256(source), before_hash)

    def test_3kib_source_is_physically_exhausted_once_only(self) -> None:
        self.assertTrue(self.REAL_PARTITION.is_file(), self.REAL_PARTITION)
        before_hash = stream_sha256(self.REAL_PARTITION)
        with tempfile.TemporaryDirectory() as directory:
            harness = SandboxFeedingHarness(self.REAL_PARTITION, Path(directory) / "sandbox", seed=0xF00D, parcel_size=64, context_overlap=2)
            harness.run()
            harness.assert_invariants()
            self.assertEqual(harness.food.metrics.bytes_consumed, 3072)
            self.assertEqual(harness.food.remaining, 0)
            self.assertEqual(harness.food.metrics.duplicate_consumption, 0)
            self.assertEqual(list(harness.food.food_dir.glob("*.food")), [])
        self.assertEqual(stream_sha256(self.REAL_PARTITION), before_hash)


if __name__ == "__main__":
    unittest.main()
