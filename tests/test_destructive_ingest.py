from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from mathematical_organism.destructive_ingest import DestructiveFeedingHarness, StreamingDestructiveFood, sha256_file  # noqa: E402
from mathematical_organism.lifecycle import LivingStructure, OrganismStatus  # noqa: E402


class DestructiveIngestTests(unittest.TestCase):
    def _source(self, directory: Path, size: int) -> Path:
        path = directory / f"input-{size}.bin"
        with path.open("wb") as handle:
            for start in range(0, size, 65536):
                handle.write(bytes((index % 251 for index in range(start, min(size, start + 65536)))))
        return path

    def test_destructive_ingest_shrinks_source_progressively_and_conserves(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = self._source(root, 3072)
            food = StreamingDestructiveFood(source, root / "sandbox", block_size=1024)
            before = food.inbox_remaining
            event = food.ingest_next()
            self.assertIsNotNone(event)
            self.assertEqual(food.inbox_remaining, before - 1024)
            self.assertEqual(food.size, food.inbox_remaining + food.food_created)
            self.assertEqual(event.original_start, 2048)  # type: ignore[union-attr]
            self.assertEqual(event.original_end, 3072)  # type: ignore[union-attr]

    def test_failed_block_write_preserves_source_and_never_truncates_before_commit(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = self._source(root, 3072)
            food = StreamingDestructiveFood(source, root / "sandbox", block_size=1024)
            inbox_hash = sha256_file(food.inbox)
            with self.assertRaises(OSError):
                food.ingest_next(fail_before_commit=True)
            self.assertEqual(food.inbox_remaining, 3072)
            self.assertEqual(sha256_file(food.inbox), inbox_hash)
            self.assertEqual(food.food_created, 0)
            self.assertEqual(list(food.food_dir.glob("*.food")), [])

    def test_ingest_ends_empty_inbox_and_reconstructs_reference_at_3kib_1mib_10mib(self) -> None:
        for size in (3072, 1024 * 1024, 10 * 1024 * 1024):
            with self.subTest(size=size), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                source = self._source(root, size)
                food = StreamingDestructiveFood(source, root / "sandbox", block_size=1024 * 1024)
                food.ingest_all()
                self.assertFalse(food.inbox.exists())
                self.assertEqual(food.food_created, size)
                self.assertEqual(sum(path.stat().st_size for path in food.food_dir.glob("*.food")), size)
                food.validate_reconstruction()

    def test_feeding_reduces_physical_food_and_deletes_empty_blocks(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = self._source(root, 3072)
            harness = DestructiveFeedingHarness(source, root / "sandbox", block_size=64)
            before = harness.food.remaining
            harness.step()
            self.assertLess(harness.food.remaining, before)
            harness.run()
            # Random food may now cause a legitimate organism-level energy
            # extinction.  Physical accounting remains exact either way.
            self.assertEqual(harness.food.metrics.bytes_consumed + harness.food.remaining, before)
            self.assertEqual(harness.food.metrics.duplicate_consumption, 0)

    def test_body_size_controls_bite_not_strength_or_technical_buffer(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = self._source(root, 2048)
            harness = DestructiveFeedingHarness(source, root / "sandbox", block_size=2048, technical_buffer_size=1024)
            organism = harness.population.organisms[0]
            small = harness._claim_next(organism)
            self.assertEqual(small.length, 256)  # type: ignore[union-attr]
            relation = LivingStructure(("A", "B"), "RELATION", strength=1.0, maintenance=0.25)
            organism.add_structure(organism.relations, relation)
            large = harness._claim_next(organism)
            self.assertEqual(large.length, 257)  # type: ignore[union-attr]
            organism.set_strength(relation, 1_000_000.0)
            unchanged = harness._claim_next(organism)
            self.assertLess(unchanged.length, 300)  # type: ignore[union-attr]
            bite = harness.food.read(unchanged)  # type: ignore[arg-type]
            self.assertEqual(len(bite), unchanged.length)  # type: ignore[union-attr]
            self.assertGreater(harness.food.metrics.peak_technical_buffer_bytes, len(bite))

    def test_atomic_digest_defers_death_and_failure_does_not_consume_food(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = self._source(root, 64)
            harness = DestructiveFeedingHarness(source, root / "sandbox", block_size=64)
            food_before = harness.food.remaining

            def fail_digest(*_args: object) -> None:
                raise RuntimeError("digest failure")

            harness.population._digest = fail_digest  # type: ignore[method-assign]
            with self.assertRaises(RuntimeError):
                harness.step()
            self.assertEqual(harness.food.remaining, food_before)

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = self._source(root, 64)
            harness = DestructiveFeedingHarness(source, root / "sandbox", block_size=64)
            observed: list[OrganismStatus] = []

            def empty_digest(organism: object, *_args: object) -> None:
                observed.append(organism.status)  # type: ignore[attr-defined]

            harness.population._digest = empty_digest  # type: ignore[method-assign]
            harness.step()
            self.assertEqual(observed, [OrganismStatus.ALIVE])
            self.assertEqual(harness.population.organisms[0].status, OrganismStatus.DEAD)
            self.assertEqual(harness.food.metrics.bytes_consumed, 64)
            self.assertFalse(hasattr(harness.population.organisms[0], "bite"))


if __name__ == "__main__":
    unittest.main()
