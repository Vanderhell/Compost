from __future__ import annotations

import sys
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from mathematical_organism import MathematicalOrganism, OrganismConfig  # noqa: E402
from mathematical_organism.model import (  # noqa: E402
    END_ID,
    START_ID,
    NodeKind,
)


class OrganismCoreTests(unittest.TestCase):
    def test_raw_fallback_reconstructs_first_input(self) -> None:
        organism = MathematicalOrganism()
        result = organism.ingest("AB")
        self.assertEqual(result.reconstructed, ("A", "B"))
        self.assertEqual(result.raw_count, 2)
        self.assertEqual(set(organism.graph.atom_index), {"A", "B"})

    def test_empty_input_is_rejected(self) -> None:
        organism = MathematicalOrganism()
        with self.assertRaises(ValueError):
            organism.ingest("")

    def test_repeated_route_becomes_representable(self) -> None:
        organism = MathematicalOrganism()
        organism.ingest("AB")
        second = organism.ingest("AB")
        third = organism.ingest("AB")
        self.assertEqual(second.adaptive_rule, "GROW_ROUTE")
        self.assertEqual(third.raw_count, 0)
        self.assertEqual(third.reconstructed, ("A", "B"))

    def test_repetition_does_not_duplicate_atoms(self) -> None:
        organism = MathematicalOrganism()
        for _ in range(10):
            organism.ingest("ABBA")
        atoms = [
            node for node in organism.graph.nodes.values() if node.kind is NodeKind.ATOM
        ]
        self.assertEqual(len(atoms), 2)
        self.assertEqual({node.yield_symbols for node in atoms}, {("A",), ("B",)})

    def test_repetition_can_create_composite(self) -> None:
        organism = MathematicalOrganism()
        for _ in range(16):
            organism.ingest("ABCD")
        composites = [
            node
            for node in organism.graph.nodes.values()
            if node.kind is NodeKind.COMPOSITE
        ]
        self.assertTrue(composites)
        self.assertTrue(any(len(node.yield_symbols) > 1 for node in composites))
        organism.graph.validate(organism.config)

    def test_every_committed_mutation_lowers_energy(self) -> None:
        organism = MathematicalOrganism()
        for item in ["ABCD"] * 12 + ["XABC", "YABD"] * 8:
            organism.ingest(item)
        for record in organism.audit.records:
            if record.adaptive_rule == "KEEP":
                continue
            self.assertLess(
                record.energy_after["total"], record.energy_before["total"]
            )

    def test_deterministic_replay(self) -> None:
        stream = ["ABCD"] * 10 + ["XABC", "YABD"] * 6 + ["AC"] * 5
        first = MathematicalOrganism()
        second = MathematicalOrganism()
        for item in stream:
            first.ingest(item)
            second.ingest(item)
        self.assertEqual(first.snapshot(), second.snapshot())
        self.assertEqual(first.audit.digest(), second.audit.digest())

    def test_budget_falls_back_to_raw(self) -> None:
        config = OrganismConfig(max_nodes=2, alphabet_limit=2)
        organism = MathematicalOrganism(config)
        for _ in range(4):
            result = organism.ingest("ABCD")
        self.assertLessEqual(len(organism.graph.nodes), 2)
        self.assertGreater(result.raw_count, 0)
        organism.graph.validate(config)

    def test_context_split_creates_semantic_children(self) -> None:
        organism = MathematicalOrganism()
        graph = organism.graph
        ids = {symbol: graph.add_atom(symbol, 0)[0] for symbol in "XABCYD"}
        composite_id, _ = graph.add_composite(ids["A"], ids["B"], 0)
        composite = graph.nodes[composite_id]
        composite.usage.add(16.0, 0, organism.config.decay)
        composite.observe_context(ids["X"], ids["C"], 8.0, 0, organism.config.decay)
        composite.observe_context(ids["Y"], ids["D"], 8.0, 0, organism.config.decay)
        for source, target in (
            (ids["X"], composite_id),
            (composite_id, ids["C"]),
            (ids["Y"], composite_id),
            (composite_id, ids["D"]),
        ):
            graph.add_transition(
                source, target, 0, initial_usage=8.0, decay=organism.config.decay
            )

        applied = organism.stabilize(max_steps=1)
        instances = [
            node
            for node in organism.graph.nodes.values()
            if node.kind is NodeKind.INSTANCE and node.semantic_id == composite_id
        ]
        self.assertEqual(applied, 1)
        self.assertEqual(len(instances), 2)
        self.assertFalse(organism.graph.nodes[composite_id].routable)
        self.assertTrue(all(node.yield_symbols == ("A", "B") for node in instances))

    def test_equivalent_instances_can_merge(self) -> None:
        organism = MathematicalOrganism()
        graph = organism.graph
        ids = {symbol: graph.add_atom(symbol, 0)[0] for symbol in "XABC"}
        semantic_id, _ = graph.add_composite(ids["A"], ids["B"], 0)
        semantic = graph.nodes[semantic_id]
        semantic.routable = False
        first = graph.add_instance(semantic_id, 0)
        second = graph.add_instance(semantic_id, 0)
        for instance_id in (first, second):
            instance = graph.nodes[instance_id]
            instance.usage.add(4.0, 0, organism.config.decay)
            instance.observe_context(ids["X"], ids["C"], 4.0, 0, organism.config.decay)
            graph.add_transition(
                ids["X"], instance_id, 0, initial_usage=4.0, decay=organism.config.decay
            )
            graph.add_transition(
                instance_id, ids["C"], 0, initial_usage=4.0, decay=organism.config.decay
            )

        applied = organism.stabilize(max_steps=1)
        self.assertEqual(applied, 1)
        self.assertTrue(organism.graph.nodes[semantic_id].routable)
        self.assertNotIn(first, organism.graph.nodes)
        self.assertNotIn(second, organism.graph.nodes)

    def test_unused_composite_can_be_pruned(self) -> None:
        organism = MathematicalOrganism()
        graph = organism.graph
        left = graph.add_atom("A", 0)[0]
        right = graph.add_atom("B", 0)[0]
        composite, _ = graph.add_composite(left, right, 0)
        applied = organism.stabilize(max_steps=1)
        self.assertEqual(applied, 1)
        self.assertNotIn(composite, organism.graph.nodes)

    def test_boundary_transitions_are_valid(self) -> None:
        organism = MathematicalOrganism()
        organism.ingest("A")
        organism.ingest("A")
        atom = organism.graph.atom_index["A"]
        self.assertIn((START_ID, atom), organism.graph.transitions)
        self.assertIn((atom, END_ID), organism.graph.transitions)


if __name__ == "__main__":
    unittest.main()

