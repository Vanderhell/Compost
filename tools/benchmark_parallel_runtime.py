"""Small completion-style smoke benchmark for autonomous process workers."""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path
from time import monotonic

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from mathematical_organism.parallel_runtime import AutonomousMultiprocessingRuntime  # noqa: E402
from mathematical_organism.sandbox_runtime import AutonomousOrganism  # noqa: E402


def organisms() -> list[AutonomousOrganism]:
    first = AutonomousOrganism("ORG-A")
    second = first.spawn_child()
    third = second.spawn_child()
    return [first, second, third]


def run(workers: int, payload_size: int = 64 * 1024, maximum_seconds: float = 3.0) -> None:
    with tempfile.TemporaryDirectory(prefix="organism-parallel-") as directory:
        runtime = AutonomousMultiprocessingRuntime(Path(directory) / "sandbox", workers=workers, block_size=64 * 1024)
        (runtime.environment.inbox / "payload.bin").write_bytes(bytes(index & 0xFF for index in range(payload_size)))
        started = monotonic()
        runtime.start(organisms())
        while monotonic() - started < maximum_seconds:
            runtime.run_for(0.05)
            metrics = runtime.metrics()
            if metrics.food_consumed == payload_size:
                break
        runtime.shutdown()
        metrics = runtime.metrics()
        elapsed = monotonic() - started
        rate = metrics.food_consumed / (1024 * 1024) / elapsed if elapsed else 0.0
        print(
            f"workers={workers} elapsed={elapsed:.3f}s MiB/s={rate:.4f} "
            f"alive_max={metrics.max_simultaneous_organisms} births={metrics.births} "
            f"deaths={metrics.deaths} divisions={metrics.divisions} consumed={metrics.food_consumed} "
            f"duplicates={metrics.duplicates} migrations={metrics.worker_migrations}"
        )


if __name__ == "__main__":
    for count in (1, 2, 4, 8):
        run(count)
