from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from mathematical_organism import (  # noqa: E402
    LifecycleConfig,
    MathematicalLifePopulation,
    MathematicalOrganism,
    canonical_bytes,
    canonical_digest,
    canonical_state,
)


class CanonicalStateTests(unittest.TestCase):
    def test_fixture_replays_have_stable_digests(self) -> None:
        fixture_path = PROJECT_ROOT / "tests" / "fixtures" / "canonical_replays.json"
        fixtures = json.loads(fixture_path.read_text(encoding="utf-8"))
        for fixture in fixtures:
            config = LifecycleConfig(**fixture["config"])
            first = MathematicalLifePopulation(fixture["payload"], config)
            second = MathematicalLifePopulation(fixture["payload"], config)
            first.run(max_cycles=fixture["cycles"])
            second.run(max_cycles=fixture["cycles"])
            self.assertEqual(canonical_digest(first), canonical_digest(second), fixture["name"])
            self.assertEqual(canonical_bytes(first), canonical_bytes(second), fixture["name"])

    def test_snapshot_is_immutable_and_excludes_observational_identity(self) -> None:
        organism = MathematicalOrganism()
        organism.ingest("AB")
        state = canonical_state(organism)
        self.assertIsInstance(state, tuple)
        self.assertNotIn("0x", repr(state))
        before = canonical_digest(organism)
        organism.audit.records.clear()
        self.assertEqual(before, canonical_digest(organism))

    def test_canonical_digest_repeats_for_legacy_and_lifecycle_models(self) -> None:
        legacy = MathematicalOrganism()
        for item in ("AB", "AB", "BA", "AB"):
            legacy.ingest(item)
        lifecycle = MathematicalLifePopulation("ABAB", LifecycleConfig(birth_reserve=10.0))
        lifecycle.run(max_cycles=6)
        self.assertEqual(canonical_digest(legacy), canonical_digest(legacy))
        self.assertEqual(canonical_digest(lifecycle), canonical_digest(lifecycle))


if __name__ == "__main__":
    unittest.main()
