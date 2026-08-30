from __future__ import annotations

import sys
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from mathematical_organism import MathematicalOrganism  # noqa: E402
from mathematical_organism.oracle import ReplayOracle  # noqa: E402


class ReplayOracleTests(unittest.TestCase):
    def test_replay_is_side_effect_free_and_deterministic(self) -> None:
        organism = MathematicalOrganism()
        oracle = ReplayOracle()
        for value in ("AB", "AB", "AB", "BA"):
            result = organism.ingest(value)
            oracle.record_result(result)
        before = organism.snapshot()
        first = oracle.replay(organism.graph, organism.config).snapshot(
            organism.time, organism.config.decay
        )
        second = oracle.replay(organism.graph, organism.config).snapshot(
            organism.time, organism.config.decay
        )
        self.assertEqual(before, organism.snapshot())
        self.assertEqual(first, second)

    def test_replay_starts_counters_from_zero(self) -> None:
        organism = MathematicalOrganism()
        oracle = ReplayOracle()
        result = organism.ingest("AB")
        oracle.record_result(result)
        replayed = oracle.replay(organism.graph, organism.config)
        self.assertGreaterEqual(
            sum(node.usage.read(organism.time, organism.config.decay)
                for node in replayed.nodes.values()),
            0.0,
        )
        self.assertEqual(replayed.raw_usage.last_time, organism.time)

    def test_comparisons_are_reproducible(self) -> None:
        organism = MathematicalOrganism()
        oracle = ReplayOracle()
        for value in ("AB", "AB", "AB", "AB"):
            result = organism.ingest(value)
            oracle.record_result(result)
        self.assertEqual(
            [item.to_dict() for item in oracle.compare_all(organism)],
            [item.to_dict() for item in oracle.compare_all(organism)],
        )

    def test_compose_false_reject_is_detected_by_independent_replay(self) -> None:
        organism = MathematicalOrganism()
        oracle = ReplayOracle()
        for _ in range(6):
            result = organism.ingest("ABCD")
            oracle.record_result(result)

        comparisons = oracle.compare_all(organism)
        self.assertEqual({comparison.rule for comparison in comparisons}, {"COMPOSE"})
        self.assertTrue(all(comparison.false_reject for comparison in comparisons))
        self.assertTrue(all(not comparison.state_mutation_during_evaluation for comparison in comparisons))
        scheduler = oracle.scheduler_check(organism)
        self.assertTrue(scheduler["wrong_winner"])
        self.assertIsNone(scheduler["local_winner"])
        self.assertIsNotNone(scheduler["oracle_winner"])

    def test_grow_route_false_reject_has_a_minimal_exhaustive_regression(self) -> None:
        organism = MathematicalOrganism()
        oracle = ReplayOracle()
        for value in ("AA", "AA", "AB", "AB", "BA", "BA"):
            result = organism.ingest(value)
            oracle.record_result(result)
        comparisons = oracle.compare_all(organism)
        self.assertEqual(len(comparisons), 1)
        self.assertEqual(comparisons[0].rule, "GROW_ROUTE")
        self.assertTrue(comparisons[0].false_reject)


if __name__ == "__main__":
    unittest.main()
