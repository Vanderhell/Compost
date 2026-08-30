from __future__ import annotations

import sys
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from mathematical_organism.territory import (  # noqa: E402
    AutonomousTerritoryState,
    FoodTerritory,
    assert_disjoint_live_territories,
    child_id,
    food_block_key,
    owner_of,
    owner_of_block,
)


class FoodTerritoryTests(unittest.TestCase):
    def test_root_owns_complete_food_space(self) -> None:
        root = AutonomousTerritoryState((0,))
        self.assertTrue(all(root.territory.contains(address) for address in range(256)))

    def test_division_partitions_territory_exactly_and_child_is_autonomous(self) -> None:
        parent = AutonomousTerritoryState((0,))
        child = parent.divide_territory()
        self.assertTrue(child.alive)
        self.assertEqual(child.organism_id, (0, 0))
        assert_disjoint_live_territories((parent, child))
        for address in range(512):
            self.assertEqual(parent.territory.contains(address) + child.territory.contains(address), 1)

    def test_deeper_division_preserves_parent_union_without_overlap(self) -> None:
        root = AutonomousTerritoryState((0,))
        first_child = root.divide_territory()
        grandchild = first_child.divide_territory()
        states = (root, first_child, grandchild)
        assert_disjoint_live_territories(states)
        for address in range(1024):
            self.assertEqual(sum(state.territory.contains(address) for state in states), 1)

    def test_every_food_byte_has_at_most_one_live_owner_independent_of_worker_assignment(self) -> None:
        root = AutonomousTerritoryState((0,))
        right = root.divide_territory()
        right_child = right.divide_territory()
        states = (root, right, right_child)
        reordered_worker_assignment = (right_child, root, right)
        for address in range(2048):
            self.assertEqual(owner_of(address, states).organism_id, owner_of(address, reordered_worker_assignment).organism_id)  # type: ignore[union-attr]

    def test_organism_cannot_claim_outside_territory(self) -> None:
        left, right = FoodTerritory().split()
        left_address = next(address for address in range(512) if left.contains(address))
        self.assertFalse(right.contains(left_address))

    def test_local_child_ids_are_deterministic_and_do_not_need_global_allocator(self) -> None:
        self.assertEqual(child_id((4, 2), 7), (4, 2, 7))
        first = AutonomousTerritoryState((9,))
        second = AutonomousTerritoryState((9,))
        self.assertEqual(first.divide_territory().organism_id, second.divide_territory().organism_id)

    def test_dead_territory_is_unoccupied_and_food_is_not_lost(self) -> None:
        root = AutonomousTerritoryState((0,))
        child = root.divide_territory()
        address = next(address for address in range(512) if child.territory.contains(address))
        self.assertEqual(owner_of(address, (root, child)), child)
        child.die()
        self.assertIsNone(owner_of(address, (root, child)))
        self.assertTrue(child.territory.contains(address))

    def test_each_block_has_one_owner_and_bytes_share_that_owner(self) -> None:
        root = AutonomousTerritoryState((0,))
        right = root.divide_territory()
        right_child = right.divide_territory()
        states = (root, right, right_child)
        for block in range(2048):
            owner = owner_of_block("firmware-A", block, states)
            self.assertIsNotNone(owner)
            self.assertTrue(owner.territory.owns_block("firmware-A", block))  # type: ignore[union-attr]
            # All offsets in the block use the same block key, not their byte address.
            self.assertEqual(food_block_key("firmware-A", block), food_block_key("firmware-A", block))

    def test_block_partition_is_disjoint_stable_and_reasonably_balanced(self) -> None:
        root = AutonomousTerritoryState((0,))
        right = root.divide_territory()
        right_child = right.divide_territory()
        states = (root, right, right_child)
        counts = {state.organism_id: 0 for state in states}
        for block in range(4096):
            owner = owner_of_block("future-file", block, states)
            self.assertIsNotNone(owner)
            counts[owner.organism_id] += 1  # type: ignore[union-attr]
            self.assertEqual(owner, owner_of_block("future-file", block, tuple(reversed(states))))
        # Expected shares are 1/2, 1/4, 1/4.  A broad deterministic bound
        # detects pathological hashing without treating finite sampling as proof.
        self.assertTrue(1600 < counts[root.organism_id] < 2500)
        self.assertTrue(700 < counts[right.organism_id] < 1400)
        self.assertTrue(700 < counts[right_child.organism_id] < 1400)

    def test_dead_territory_blocks_become_unoccupied(self) -> None:
        root = AutonomousTerritoryState((0,))
        child = root.divide_territory()
        block = next(index for index in range(1024) if child.territory.owns_block("dead-owner", index))
        child.die()
        self.assertIsNone(owner_of_block("dead-owner", block, (root, child)))


if __name__ == "__main__":
    unittest.main()
