from __future__ import annotations

import sys
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from tools.random_hex_experiment import HEX, PATTERN, hidden_pattern_hex, random_hex  # noqa: E402
from mathematical_organism.lifecycle import LifecycleConfig, MathematicalLifePopulation  # noqa: E402


class RandomHexPayloadTests(unittest.TestCase):
    def test_seeded_hex_is_reproducible_and_uses_only_the_hex_alphabet(self) -> None:
        first = random_hex(128, 17)
        self.assertEqual(first, random_hex(128, 17))
        self.assertNotEqual(first, random_hex(128, 18))
        self.assertTrue(set(first).issubset(HEX))

    def test_hidden_pattern_overwrites_deterministic_starts_without_changing_length(self) -> None:
        payload = hidden_pattern_hex(41, 3, 8)
        self.assertEqual(len(payload), 41)
        for start in range(0, 41, 8):
            self.assertEqual(payload[start:min(start + len(PATTERN), 41)], PATTERN[:max(0, min(len(PATTERN), 41 - start))])

    def test_birth_reserve_handles_known_seeds_under_mass_based_bites(self) -> None:
        for seed in (2, 8, 9):
            before = MathematicalLifePopulation(random_hex(10_000, seed), LifecycleConfig(birth_reserve=0.0))
            before.run_until_stream_exhausted(max_cycles=20_000)
            after = MathematicalLifePopulation(random_hex(10_000, seed), LifecycleConfig(birth_reserve=1.0))
            after.run_until_stream_exhausted(max_cycles=20_000)
            self.assertEqual(before.result.consumed_nutrition_total, 10_000.0)
            self.assertEqual(after.result.consumed_nutrition_total, 10_000.0)


if __name__ == "__main__":
    unittest.main()
