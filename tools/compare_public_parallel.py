"""Run the public CLI path with identical real input and worker counts."""

from __future__ import annotations

from contextlib import redirect_stdout
from io import StringIO
import shutil
import sys
import tempfile
from pathlib import Path
from time import monotonic

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from mathematical_organism.public_sandbox import PublicMultiprocessingSandbox  # noqa: E402


def run(source: Path, seconds: float = 3.0) -> None:
    for workers in (1, 2, 4, 8):
        with tempfile.TemporaryDirectory(prefix=f"organism-public-{workers}-") as directory:
            root = Path(directory) / "sandbox"
            inbox = root / "inbox"
            inbox.mkdir(parents=True)
            shutil.copyfile(source, inbox / source.name)
            sandbox = PublicMultiprocessingSandbox(root, workers=workers)
            # PREPARE is explicitly excluded from the active-runtime timer.
            while not sandbox.runtime.environment.food_sources or any(
                food.inbox_remaining for food in sandbox.runtime.environment.food_sources.values()
            ):
                sandbox.runtime.environment.ingest_one_available("benchmark-prepare")
            sandbox.started_at = monotonic()
            started = monotonic()
            with redirect_stdout(StringIO()):
                _reason, snapshot = sandbox.run(max_seconds=seconds, snapshot_seconds=10.0)
            actual = monotonic() - started
            food = snapshot["food"]
            population = snapshot["population"]
            runtime = snapshot["runtime"]
            print({
                "workers": workers, "requested_seconds": seconds, "actual_seconds": round(actual, 3),
                "consumed": food["consumed"], "remaining": food["remaining"],
                "throughput_mib_s": round((float(food["consumed"]) / (1024 * 1024)) / actual, 6),
                "alive": population["alive"], "born": population["born"], "dead": population["dead"],
                "divisions": population["divisions"], "max_generation": population["max_generation"],
                "live_steps": runtime["live_steps"], "successful_bites": runtime["successful_bites"],
                "environment_rpcs": runtime["environment_rpcs"], "parent_food_rpcs": runtime["parent_food_rpcs"],
                "shutdown_latency_seconds": round(float(runtime["shutdown_latency_seconds"]), 6),
                "worker_migrations": runtime["worker_migrations"], "duplicates": food["duplicates"],
                "missing": food["missing"], "mass_conservation": snapshot["accounting"]["mass_conservation"],
                "energy_conservation": snapshot["accounting"]["energy_conservation"],
                "newborn_local": runtime["newborn_local_placements"],
                "newborn_remote": runtime["newborn_remote_placements"],
                "worker_distribution": runtime["worker_distribution"],
            })


if __name__ == "__main__":
    run(Path(sys.argv[1]))
