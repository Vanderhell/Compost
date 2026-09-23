from __future__ import annotations

import sys
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from mathematical_organism.native_sandbox import NativeSandboxReplay  # noqa: E402


class _DeadOrganism:
    name = "ORG-DEAD"
    alive = False

    def verify_material_conservation(self) -> None:
        return None


class _Runtime:
    organisms = (_DeadOrganism(),)

    def verify_world_material_conservation(self) -> None:
        return None


class _Population:
    @property
    def organism_ids(self) -> tuple[int, ...]:
        return ()

    def verify_material_conservation(self) -> None:
        return None

    def preflight_action_traces(self, _traces: object) -> None:
        return None


class NativeSandboxOwnershipTests(unittest.TestCase):
    def test_previous_epoch_corpse_handle_is_not_required_again(self) -> None:
        replay = object.__new__(NativeSandboxReplay)
        replay.runtime = _Runtime()
        replay._native_ids = {"ORG-DEAD": 17}
        replay._population = _Population()
        replay._epoch = 3
        replay._closed = False

        epoch = replay.step()

        self.assertEqual(epoch.index, 3)
        self.assertEqual(epoch.traces, ())
        self.assertEqual(epoch.snapshots, ())
        self.assertEqual(epoch.corpses, ())


if __name__ == "__main__":
    unittest.main()
