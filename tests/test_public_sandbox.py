from __future__ import annotations

import tempfile
import unittest
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
import sys


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from mathematical_organism.cli import main
from mathematical_organism.public_sandbox import PublicSandbox, read_last_snapshot
from mathematical_organism.public_sandbox import PublicMultiprocessingSandbox
from mathematical_organism.sandbox_runtime import SandboxRuntime


class PublicSandboxTests(unittest.TestCase):
    def test_public_layout_keeps_inbox_as_the_only_input_directory(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            sandbox = PublicSandbox(Path(directory) / "sandbox")
            self.assertTrue(sandbox.layout.inbox.is_dir())
            self.assertTrue(sandbox.layout.world.is_dir())
            self.assertTrue(sandbox.layout.telemetry.is_dir())
            self.assertEqual(sandbox.runtime.inbox, sandbox.layout.inbox)

    def test_run_writes_read_only_telemetry_and_consumes_small_real_bytes(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            sandbox = PublicSandbox(Path(directory) / "sandbox", block_size=64)
            payload = bytes(range(64))
            (sandbox.layout.inbox / "sample.bin").write_bytes(payload)
            reason, view = sandbox.run(snapshot_seconds=0.001, max_seconds=2.0)
            self.assertEqual(reason, "FOOD_EXHAUSTED")
            self.assertEqual(view["food"]["consumed"], len(payload))
            self.assertEqual(view["food"]["remaining"], 0)
            self.assertEqual(view["food"]["duplicates"], 0)
            self.assertEqual(view["food"]["missing"], 0)
            persisted = read_last_snapshot(sandbox.layout.root)
            self.assertIsNotNone(persisted)
            self.assertEqual(persisted["food"]["consumed"], len(payload))  # type: ignore[index]

    def test_status_only_reads_last_telemetry_snapshot(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "sandbox"
            sandbox = PublicSandbox(root)
            sandbox.write_snapshot(termination="USER_STOP")
            before = list(sandbox.runtime.organisms)
            with redirect_stdout(StringIO()):
                self.assertEqual(main(["status", str(root)]), 0)
            self.assertEqual(before, sandbox.runtime.organisms)

    def test_public_parallel_run_never_calls_serial_population_heartbeat(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            sandbox = PublicMultiprocessingSandbox(Path(directory) / "sandbox", workers=1, block_size=64)
            (sandbox.layout.inbox / "parallel.bin").write_bytes(bytes(range(64)))
            original = SandboxRuntime.autonomous_step

            def forbidden(_self: SandboxRuntime) -> None:
                raise AssertionError("serial heartbeat entered public parallel path")

            SandboxRuntime.autonomous_step = forbidden
            try:
                reason, view = sandbox.run(snapshot_seconds=0.01, max_seconds=1.0)
            finally:
                SandboxRuntime.autonomous_step = original
            self.assertIn(reason, {"FOOD_EXHAUSTED", "USER_STOP"})
            self.assertEqual(view["runtime"]["kind"], "multiprocessing")  # type: ignore[index]
            self.assertEqual(view["runtime"]["worker_migrations"], 0)  # type: ignore[index]
            self.assertEqual(view["food"]["duplicates"], 0)  # type: ignore[index]

    def test_parallel_public_stop_joins_workers_and_observer(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            sandbox = PublicMultiprocessingSandbox(Path(directory) / "sandbox", workers=2, block_size=64)
            reason, view = sandbox.run(snapshot_seconds=0.01, max_seconds=0.10)
            self.assertEqual(reason, "USER_STOP")
            self.assertEqual(sandbox.runtime.workers_alive(), 0)
            self.assertIsNotNone(sandbox.runtime.observer_process)
            self.assertFalse(sandbox.runtime.observer_process.is_alive())  # type: ignore[union-attr]
            self.assertEqual(view["runtime"]["parent_food_rpcs"], 0)  # type: ignore[index]


if __name__ == "__main__":
    unittest.main()
