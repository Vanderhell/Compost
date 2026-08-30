from __future__ import annotations

import itertools
import sys
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from mathematical_organism import MathematicalOrganism  # noqa: E402
from mathematical_organism.model import DecayedCounter  # noqa: E402
from mathematical_organism.representation import find_best_representation  # noqa: E402


class ReferenceProperties(unittest.TestCase):
    def test_exact_representation_for_all_small_sequences(self) -> None:
        organism = MathematicalOrganism()
        for symbol in "AB":
            organism.graph.add_atom(symbol, 0)
        for length in range(1, 4):
            for symbols in itertools.product("AB", repeat=length):
                plan = find_best_representation(
                    organism.graph, symbols, 0, organism.config
                )
                self.assertEqual(plan.reconstruct(organism.graph), symbols)

    def test_lazy_decay_matches_closed_form_without_touching_other_counters(self) -> None:
        counter = DecayedCounter(value=7.0, last_time=3)
        self.assertEqual(counter.read(3, 0.5), 7.0)
        self.assertEqual(counter.read(8, 0.5), 7.0 * (0.5**5))
        self.assertEqual(counter.last_time, 3)
        counter.touch(8, 0.5)
        self.assertEqual(counter.last_time, 8)
        self.assertEqual(counter.value, 7.0 * (0.5**5))


if __name__ == "__main__":
    unittest.main()
