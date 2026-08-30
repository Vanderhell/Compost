from __future__ import annotations

"""Run autonomous organisms in persistent worker processes.

Drop files into sandbox/inbox while the process is running; no input argument
is required.
"""

import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from mathematical_organism.parallel_runtime import AutonomousMultiprocessingRuntime
from mathematical_organism.sandbox_runtime import AutonomousOrganism


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--sandbox", default="sandbox")
    parser.add_argument("--workers", type=int, default=1)
    parser.add_argument("--seconds", type=float, default=10.0)
    arguments = parser.parse_args()
    runtime = AutonomousMultiprocessingRuntime(arguments.sandbox, workers=arguments.workers)
    runtime.start((AutonomousOrganism(),))
    try:
        runtime.run_for(arguments.seconds)
    finally:
        runtime.shutdown()
    metrics = runtime.metrics()
    print(f"workers={metrics.workers_used} max_alive={metrics.max_simultaneous_organisms} births={metrics.births} deaths={metrics.deaths}")
    print(f"food_consumed={metrics.food_consumed} duplicates={metrics.duplicates} body_transfers={metrics.body_transfers}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
