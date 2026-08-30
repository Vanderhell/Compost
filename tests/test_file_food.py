from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))
sys.path.insert(0, str(PROJECT_ROOT))

from mathematical_organism.food import FileFoodSpace, FoodNavigationState, ImplicitFileFeedingHarness  # noqa: E402
from mathematical_organism.lifecycle import LivingStructure, MathematicalLifeOrganism, OrganismStatus  # noqa: E402
from tools.create_food_fixture import fixture_bytes  # noqa: E402


class FileFoodTests(unittest.TestCase):
    REAL_PARTITION = (
        PROJECT_ROOT.parent / "cOMPOSABLE SPACE" / "esp32_build32"
        / "esp32s3_skip_space.ino.partitions_flashed.bin"
    )

    def _fixture(self) -> tuple[tempfile.TemporaryDirectory[str], Path]:
        directory = tempfile.TemporaryDirectory()
        path = Path(directory.name) / "fixture.bin"
        path.write_bytes(fixture_bytes())
        return directory, path

    def test_file_food_is_complete_once_only_and_deterministic(self) -> None:
        directory, path = self._fixture()
        self.addCleanup(directory.cleanup)
        first = ImplicitFileFeedingHarness(path, seed=0xF00D)
        try:
            first.run()
        except RuntimeError:
            pass  # a zero-energy extinction is biological, not food loss
        second = ImplicitFileFeedingHarness(path, seed=0xF00D)
        try:
            second.run()
        except RuntimeError:
            pass
        self.assertEqual(first.food.metrics.bytes_consumed + first.food.remaining, path.stat().st_size)
        self.assertEqual(first.food.metrics.duplicate_consumption, 0)
        self.assertEqual(
            [(event.organism_id, event.offset, event.length, event.claimed) for event in first.trace],
            [(event.organism_id, event.offset, event.length, event.claimed) for event in second.trace],
        )

    def test_context_overlap_is_read_but_not_nutrition_and_raw_does_not_leak(self) -> None:
        directory, path = self._fixture()
        self.addCleanup(directory.cleanup)
        harness = ImplicitFileFeedingHarness(path, seed=0xF00D, context_overlap=3)
        try:
            harness.run()
        except RuntimeError:
            pass
        self.assertGreater(harness.food.metrics.bytes_read, harness.food.metrics.bytes_consumed)
        for organism in harness.population.organisms.values():
            self.assertFalse(hasattr(organism, "payload"))
            self.assertFalse(hasattr(organism, "bite"))

    def test_birth_gets_its_own_navigation_state_without_releasing_food(self) -> None:
        directory, path = self._fixture()
        self.addCleanup(directory.cleanup)
        harness = ImplicitFileFeedingHarness(path, seed=0xF00D)
        root = harness.population.organisms[0]
        root.reserve = 20.0
        root.atoms["A"] = LivingStructure("A", "ATOM", strength=12.0, maintenance=0.25, evidence=12.0, income_rate=3.0)
        root.atoms["B"] = LivingStructure("B", "ATOM", strength=12.0, maintenance=0.25, evidence=12.0, income_rate=3.0)
        root.relations[("A", "B")] = LivingStructure(("A", "B"), "RELATION", strength=2.0, maintenance=0.5, evidence=2.0, income_rate=1.0)
        harness.population._divide_if_profitable(root)
        harness.step()
        self.assertGreater(len(harness.population.result.births), 0)
        for birth in harness.population.result.births:
            self.assertIn(birth.child_id, harness.navigation)
            self.assertNotEqual(
                harness.navigation[birth.parent_id].local_state,
                harness.navigation[birth.child_id].local_state,
            )
        self.assertGreater(harness.food.metrics.bytes_consumed, 0)

    def test_death_does_not_release_unclaimed_food(self) -> None:
        directory, path = self._fixture()
        self.addCleanup(directory.cleanup)
        harness = ImplicitFileFeedingHarness(path, seed=0xF00D)
        harness.step()
        consumed_before_death = harness.food.metrics.bytes_consumed
        root = harness.population.organisms[0]
        root.status = OrganismStatus.DEAD
        successor = MathematicalLifeOrganism(1, None, 0, 0, 0)
        harness.population.organisms[1] = successor
        harness.step()
        self.assertGreater(harness.food.metrics.bytes_consumed, consumed_before_death)
        self.assertEqual(harness.food.metrics.duplicate_consumption, 0)

    def test_partial_parcel_is_revisited(self) -> None:
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        path = Path(directory.name) / "one-parcel.bin"
        path.write_bytes(b"ABCD")
        food = FileFoodSpace(path, parcel_size=4)
        navigation = FoodNavigationState(0, 0xF00D, 4, 1)
        claims = []
        while len(claims) < 4:
            parcel = navigation.next_parcel()
            if parcel is not None:
                claim = food.claim(parcel, 1, skipped_regions=0)
                if claim is not None:
                    claims.append(claim)
        self.assertGreaterEqual(navigation.round, 3)
        self.assertEqual([claim.offset for claim in claims], [0, 1, 2, 3])
        self.assertEqual(food.remaining, 0)

    def test_multiple_bites_empty_one_parcel(self) -> None:
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        path = Path(directory.name) / "one-parcel.bin"
        path.write_bytes(b"ABCDEFGH")
        food = FileFoodSpace(path, parcel_size=8)
        claims = [food.claim(0, 3, skipped_regions=0) for _ in range(3)]
        self.assertEqual([(claim.offset, claim.length) for claim in claims if claim], [(0, 3), (3, 3), (6, 2)])
        self.assertEqual(food.remaining, 0)

    def test_multiple_organisms_share_parcel_without_duplicate(self) -> None:
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        path = Path(directory.name) / "shared.bin"
        path.write_bytes(b"ABCD")
        food = FileFoodSpace(path, parcel_size=4)
        first = food.claim(0, 2, skipped_regions=0)
        second = food.claim(0, 2, skipped_regions=0)
        self.assertEqual((first.offset, first.length), (0, 2))  # type: ignore[union-attr]
        self.assertEqual((second.offset, second.length), (2, 2))  # type: ignore[union-attr]
        self.assertEqual(food.metrics.duplicate_consumption, 0)

    def test_navigation_wraps_to_next_round(self) -> None:
        navigation = FoodNavigationState(7, 0xF00D, 4, 4)
        first_round = [navigation.next_parcel() for _ in range(4)]
        self.assertEqual(navigation.round, 1)
        second_round = [navigation.next_parcel() for _ in range(4)]
        self.assertEqual(navigation.round, 2)
        self.assertEqual(sorted(first_round), [0, 1, 2, 3])
        self.assertEqual(sorted(second_round), [0, 1, 2, 3])

    def test_each_round_covers_all_blocks_of_a_large_food_space(self) -> None:
        navigation = FoodNavigationState(7, 0xF00D, 4, 6)
        first_round = [navigation.next_parcel() for _ in range(8)]
        self.assertEqual(navigation.round, 1)
        self.assertEqual(sorted(parcel for parcel in first_round if parcel is not None), list(range(6)))

    def test_food_exhaustion_only_when_all_bytes_claimed(self) -> None:
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        path = Path(directory.name) / "food.bin"
        path.write_bytes(b"ABCDE")
        food = FileFoodSpace(path, parcel_size=4)
        self.assertEqual(food.claim(0, 1, skipped_regions=0).length, 1)  # type: ignore[union-attr]
        self.assertGreater(food.remaining, 0)
        self.assertIsNotNone(food.claim(0, 3, skipped_regions=0))
        self.assertIsNotNone(food.claim(1, 1, skipped_regions=0))
        self.assertEqual(food.remaining, 0)

    def test_real_3kib_regression_consumes_all_food(self) -> None:
        self.assertTrue(self.REAL_PARTITION.is_file(), self.REAL_PARTITION)
        harness = ImplicitFileFeedingHarness(self.REAL_PARTITION, seed=0xF00D, parcel_size=64, context_overlap=2)
        harness.run()
        harness.assert_invariants()
        self.assertEqual(harness.food.metrics.bytes_consumed, 3072)
        self.assertEqual(harness.food.remaining, 0)
        self.assertEqual(harness.food.metrics.duplicate_consumption, 0)


if __name__ == "__main__":
    unittest.main()
