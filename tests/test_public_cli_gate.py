from __future__ import annotations

"""External-user CLI checks: installed package, clean cwd, no source-path injection."""

import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


PROJECT_ROOT = Path(__file__).resolve().parents[1]


class PublicCliGateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls._temporary = tempfile.TemporaryDirectory()
        cls.root = Path(cls._temporary.name)
        cls.venv = cls.root / "venv"
        subprocess.run([sys.executable, "-m", "venv", str(cls.venv)], check=True, capture_output=True, text=True)
        cls.python = cls.venv / ("Scripts/python.exe" if sys.platform == "win32" else "bin/python")
        subprocess.run(
            [str(cls.python), "-m", "pip", "install", "--no-deps", str(PROJECT_ROOT)],
            check=True,
            capture_output=True,
            text=True,
        )
        cls.cwd = cls.root / "external-user-cwd"
        cls.cwd.mkdir()

    @classmethod
    def tearDownClass(cls) -> None:
        cls._temporary.cleanup()

    def command(self, *arguments: str, timeout: float = 20.0) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [str(self.python), "-m", "mathematical_organism", *arguments],
            cwd=self.cwd,
            capture_output=True,
            text=True,
            timeout=timeout,
        )

    def test_help_and_status_without_a_sandbox_need_no_repository_cwd(self) -> None:
        help_result = self.command("--help")
        self.assertEqual(help_result.returncode, 0, help_result.stderr)
        self.assertIn("run", help_result.stdout)
        self.assertIn("status", help_result.stdout)

        absent = self.command("status", "never-created")
        self.assertEqual(absent.returncode, 1)
        self.assertIn("No telemetry snapshot", absent.stdout)

    def test_new_empty_sandbox_can_run_and_be_queried_repeatedly(self) -> None:
        sandbox = "empty-sandbox"
        first = self.command("run", sandbox, "--workers", "1", "--snapshot-seconds", "0.05", "--max-seconds", "0.15")
        self.assertEqual(first.returncode, 0, first.stderr)
        root = self.cwd / sandbox
        for name in ("inbox", "world", "telemetry"):
            self.assertTrue((root / name).is_dir())
        for _ in range(2):
            status = self.command("status", sandbox)
            self.assertEqual(status.returncode, 0, status.stderr)
            self.assertIn("TERMINATION: USER_STOP", status.stdout)

    def test_zero_small_and_multiple_binary_files_are_accepted_by_public_run(self) -> None:
        sandbox = self.cwd / "binary-sandbox"
        inbox = sandbox / "inbox"
        inbox.mkdir(parents=True)
        (inbox / "empty.bin").write_bytes(b"")
        (inbox / "small.bin").write_bytes(bytes(range(64)))
        (inbox / "second.bin").write_bytes(bytes(range(32)))
        result = self.command("run", str(sandbox), "--workers", "1", "--snapshot-seconds", "0.05", "--max-seconds", "3.0", timeout=30.0)
        self.assertIn(result.returncode, {0, 2}, result.stderr)
        snapshot = json.loads((sandbox / "telemetry" / "latest.json").read_text(encoding="utf-8"))
        self.assertEqual(snapshot["food"]["duplicates"], 0)
        self.assertEqual(snapshot["food"]["missing"], 0)
        self.assertEqual(snapshot["food"]["original"], 96)

    def test_corrupted_telemetry_is_an_external_failure_not_an_import_failure(self) -> None:
        sandbox = self.cwd / "corrupt-sandbox"
        telemetry = sandbox / "telemetry"
        telemetry.mkdir(parents=True)
        (telemetry / "latest.json").write_text("{not valid json", encoding="utf-8")
        result = self.command("status", str(sandbox))
        self.assertNotEqual(result.returncode, 0)
        self.assertNotIn("ModuleNotFoundError", result.stderr)


if __name__ == "__main__":
    unittest.main()
