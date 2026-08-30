from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys
import unittest
from contextlib import redirect_stdout
from io import StringIO


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from mathematical_organism.cli import _print_sandbox_snapshot, main  # noqa: E402


def _snapshot(*, original: int, consumed: int, prepared: int, inbox: int) -> dict[str, object]:
    return {
        "food": {"original": original, "consumed": consumed, "remaining": prepared,
                 "inbox_pending": inbox, "duplicates": 0, "missing": 0},
        "population": {"alive": 0, "born": 0, "dead": 0, "divisions": 0, "max_generation": 0},
        "body": {"min": 0, "median": 0, "max": 0},
        "energy": {"reserve_min": 0.0, "reserve_median": 0.0, "reserve_max": 0.0,
                   "metabolic_debt": 0.0, "gut_backlog": 0},
        "world": {"occupied_territories": 0, "free_territories": 0, "corpses": 0, "reclaims": 0},
        "performance": {"mib_per_second": 0.0},
        "elapsed_seconds": 0.0,
        "cpu_utilization": 0.0,
        "ram_bytes": 0,
        "organisms": [],
    }


class CliPresentationGateTests(unittest.TestCase):
    def test_top_level_help_exposes_public_run_and_status(self) -> None:
        output = StringIO()
        with redirect_stdout(output):
            self.assertEqual(main(["--help"]), 0)
        text = output.getvalue()
        self.assertIn("run", text)
        self.assertIn("status", text)
        self.assertIn("legacy", text)

    def test_legacy_simulator_remains_explicitly_available(self) -> None:
        output = StringIO()
        with redirect_stdout(output):
            self.assertEqual(main(["legacy", "A"]), 0)
        self.assertIn("input=A", output.getvalue())

    def test_snapshot_displays_inbox_as_part_of_total_remaining(self) -> None:
        output = StringIO()
        with redirect_stdout(output):
            _print_sandbox_snapshot(_snapshot(original=2048, consumed=192, prepared=64, inbox=1792), include_organisms=False)
        text = output.getvalue()
        self.assertIn("prepared remaining:  64 B", text)
        self.assertIn("inbox pending:       1.75 KiB", text)
        self.assertIn("total remaining:     1.81 KiB", text)
        self.assertIn("original = consumed + prepared remaining + inbox pending", text)

    def test_module_help_exposes_public_commands_from_src_layout(self) -> None:
        environment = dict(os.environ)
        environment["PYTHONPATH"] = str(PROJECT_ROOT / "src")
        completed = subprocess.run(
            [sys.executable, "-m", "mathematical_organism", "--help"],
            cwd=PROJECT_ROOT,
            env=environment,
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertIn("run", completed.stdout)
        self.assertIn("status", completed.stdout)


if __name__ == "__main__":
    unittest.main()
