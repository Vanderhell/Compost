from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from mathematical_organism.parallel_runtime import AutonomousMultiprocessingRuntime  # noqa: E402
from mathematical_organism.public_sandbox import PublicMultiprocessingSandbox  # noqa: E402
from mathematical_organism.sandbox_runtime import AutonomousOrganism  # noqa: E402
from mathematical_organism.territory import FoodTerritory  # noqa: E402


class _ExitedProcess:
    def __init__(self, exitcode: int) -> None:
        self.exitcode = exitcode

    def is_alive(self) -> bool:
        return False


class _RuntimeDouble:
    """Minimal execution host double; it contains no organism biology."""

    def __init__(
        self,
        *,
        accounting: tuple[int, int, int, int, int] = (0, 0, 0, 0, 0),
        live: dict[str, tuple[bool, FoodTerritory]] | None = None,
        worker_exit: int | None = None,
        observer_exit: int | None = None,
        start_error: Exception | None = None,
        run_error: Exception | None = None,
    ) -> None:
        self.workers = 1
        self.environment = SimpleNamespace(
            food_sources={"source": object()} if accounting[0] else {},
            corpses=[], observer=SimpleNamespace(events=[]),
        )
        self._accounting = accounting
        self.live = live if live is not None else {"ORG-ROOT": (True, FoodTerritory())}
        self.processes = [] if worker_exit is None else [_ExitedProcess(worker_exit)]
        self.observer_process = None if observer_exit is None else _ExitedProcess(observer_exit)
        self.organism_snapshots: dict[str, dict[str, object]] = {}
        self.max_simultaneous_organisms = sum(alive for alive, _ in self.live.values())
        self.births = self.deaths = self.divisions = 0
        self.environment_rpcs = self.parent_food_rpcs = self.total_live_steps = self.total_successful_bites = 0
        self.shutdown_latency = 0.0
        self.newborn_initial_placements = self.newborn_local_placements = self.newborn_remote_placements = 0
        self.worker_organisms = [set()]
        self.worker_live_steps = [0]
        self.worker_bytes_eaten = [0]
        self.material_conservation = True
        self.energy_conservation = True
        self.start_error = start_error
        self.run_error = run_error
        self.started = False
        self.shutdown_called = False

    def start(self, _organisms: object) -> None:
        self.started = True
        if self.start_error is not None:
            raise self.start_error

    def run_for(self, _seconds: float) -> None:
        if self.run_error is not None:
            raise self.run_error

    def shutdown(self) -> None:
        self.shutdown_called = True

    def food_accounting(self) -> tuple[int, int, int, int, int]:
        return self._accounting

    def metrics(self) -> SimpleNamespace:
        return SimpleNamespace(mass_conservation=True, duplicates=0, missing=0)

    def workers_alive(self) -> int:
        return 0


class PublicRuntimeFailureGateTests(unittest.TestCase):
    def _sandbox_with(self, runtime: _RuntimeDouble) -> PublicMultiprocessingSandbox:
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        sandbox = PublicMultiprocessingSandbox(Path(directory.name) / "sandbox", workers=1)
        sandbox.runtime = runtime  # type: ignore[assignment]
        return sandbox

    def test_public_termination_food_exhausted(self) -> None:
        sandbox = self._sandbox_with(_RuntimeDouble(accounting=(8, 8, 0, 0, 0)))
        reason, _view = sandbox.run(max_seconds=0.1)
        self.assertEqual(reason, "FOOD_EXHAUSTED")
        self.assertTrue(sandbox.runtime.shutdown_called)

    def test_public_termination_extinction(self) -> None:
        sandbox = self._sandbox_with(_RuntimeDouble(accounting=(8, 0, 8, 0, 0), live={}))
        reason, _view = sandbox.run(max_seconds=0.1)
        self.assertEqual(reason, "EXTINCTION")
        self.assertTrue(sandbox.runtime.shutdown_called)

    def test_public_termination_user_stop(self) -> None:
        sandbox = self._sandbox_with(_RuntimeDouble())
        reason, _view = sandbox.run(stop=lambda: True)
        self.assertEqual(reason, "USER_STOP")
        self.assertTrue(sandbox.runtime.shutdown_called)

    def test_public_termination_invariant_failure(self) -> None:
        sandbox = self._sandbox_with(_RuntimeDouble(accounting=(8, 0, 7, 0, 0)))
        reason, view = sandbox.run(max_seconds=0.1)
        self.assertEqual(reason, "INVARIANT_FAILURE")
        self.assertEqual(view["food"]["missing"], 1)

    def test_unexpected_worker_exit_is_runtime_failure(self) -> None:
        sandbox = self._sandbox_with(_RuntimeDouble(worker_exit=17))
        reason, view = sandbox.run(max_seconds=0.1)
        self.assertEqual(reason, "RUNTIME_FAILURE")
        self.assertIn("worker 0 exited unexpectedly", str(view["failure"]))
        self.assertTrue(sandbox.runtime.shutdown_called)

    def test_observer_exit_is_runtime_failure(self) -> None:
        sandbox = self._sandbox_with(_RuntimeDouble(observer_exit=0))
        reason, view = sandbox.run(max_seconds=0.1)
        self.assertEqual(reason, "RUNTIME_FAILURE")
        self.assertIn("observer exited unexpectedly", str(view["failure"]))

    def test_failed_ingest_runtime_path_is_failure_and_cleans_up(self) -> None:
        sandbox = self._sandbox_with(_RuntimeDouble(run_error=OSError("ingest commit failed")))
        reason, view = sandbox.run(max_seconds=0.1)
        self.assertEqual(reason, "RUNTIME_FAILURE")
        self.assertIn("ingest commit failed", str(view["failure"]))
        self.assertTrue(sandbox.runtime.shutdown_called)

    def test_public_worker_startup_failure_is_runtime_failure_and_cleans_up(self) -> None:
        sandbox = self._sandbox_with(_RuntimeDouble(start_error=OSError("worker start failed")))
        reason, view = sandbox.run(max_seconds=0.1)
        self.assertEqual(reason, "RUNTIME_FAILURE")
        self.assertIn("worker start failed", str(view["failure"]))
        self.assertTrue(sandbox.runtime.shutdown_called)

    def test_worker_startup_failure_joins_started_workers(self) -> None:
        class FakeProcess:
            starts = 0

            def __init__(self, *_args: object, **_kwargs: object) -> None:
                self.joined = False

            def start(self) -> None:
                type(self).starts += 1
                if type(self).starts == 2:
                    raise OSError("worker startup failed")

            def is_alive(self) -> bool:
                return False

            def join(self, timeout: float | None = None) -> None:
                del timeout
                self.joined = True

            def terminate(self) -> None:
                pass

        with tempfile.TemporaryDirectory() as directory:
            runtime = AutonomousMultiprocessingRuntime(Path(directory) / "sandbox", workers=2)
            with patch.object(runtime.context, "Process", side_effect=FakeProcess):
                with self.assertRaisesRegex(OSError, "worker startup failed"):
                    runtime.start((AutonomousOrganism("ORG-START"),))
            self.assertTrue(all(not process.is_alive() for process in runtime.processes))
            self.assertEqual(runtime.workers_alive(), 0)
            self.assertEqual(runtime.live, {})
            self.assertFalse((runtime.environment.organism_directory("ORG-START") / "ALIVE").exists())


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
