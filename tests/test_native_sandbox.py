from __future__ import annotations

import sys
import tempfile
import unittest
from contextlib import contextmanager
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from mathematical_organism.native_sandbox import NativeSandboxReplay  # noqa: E402
from mathematical_organism.backend import NativeBackendError  # noqa: E402
from mathematical_organism.lifecycle import LivingStructure  # noqa: E402
from mathematical_organism.sandbox_runtime import AutonomousOrganism, SandboxRuntime  # noqa: E402


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
    def __init__(self) -> None:
        self.closed = False

    @contextmanager
    def _native_transaction(self):
        yield

    @property
    def organism_ids(self) -> tuple[int, ...]:
        return ()

    def verify_material_conservation(self) -> None:
        return None

    def close(self) -> None:
        self.closed = True

    def preflight_action_traces(self, _traces: object) -> None:
        return None


class NativeSandboxOwnershipTests(unittest.TestCase):
    def test_replay_reports_missing_native_library_for_importable_initial_state(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            runtime = SandboxRuntime(Path(directory) / "sandbox")
            organism = AutonomousOrganism()
            organism.body.add_structure(
                organism.body.atoms,
                LivingStructure(65, "ATOM"),
            )
            runtime.organisms.append(organism)

            with self.assertRaises(NativeBackendError):
                NativeSandboxReplay(
                    Path(directory) / "missing-native.dll",
                    runtime,
                )

    def test_replay_rejects_dead_initial_state_without_world_corpse_import(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            runtime = SandboxRuntime(Path(directory) / "sandbox")
            organism = AutonomousOrganism()
            organism.territory_state.die()
            runtime.organisms.append(organism)
            with self.assertRaises(ValueError):
                NativeSandboxReplay(Path(directory) / "missing-native.dll", runtime)

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

    def test_failed_epoch_closes_replay_instead_of_allowing_mixed_state_retry(self) -> None:
        replay = object.__new__(NativeSandboxReplay)
        replay.runtime = _Runtime()
        replay._native_ids = {}
        replay._population = _Population()
        replay._epoch = 4
        replay._closed = False

        def fail() -> NativeSandboxEpoch:
            raise RuntimeError("synthetic differential failure")

        replay._step_impl = fail  # type: ignore[method-assign]
        with self.assertRaisesRegex(RuntimeError, "synthetic differential failure"):
            replay.step()
        self.assertTrue(replay._closed)
        self.assertTrue(replay._population.closed)
        with self.assertRaisesRegex(RuntimeError, "native sandbox replay is closed"):
            replay.step()


if __name__ == "__main__":
    unittest.main()
