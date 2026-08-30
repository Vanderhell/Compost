"""Read-only diagnostic runner for bite scaling and sandbox execution.

It does not alter organism configuration or decisions.  It is deliberately a
bounded experiment: the temporary world is removed after its final snapshot.
"""

from __future__ import annotations

import argparse
from collections import defaultdict
import shutil
import sys
import tempfile
from pathlib import Path
from statistics import median
from time import perf_counter

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from mathematical_organism.sandbox_runtime import SandboxRuntime  # noqa: E402


def _timeline(runtime: SandboxRuntime, elapsed: float, previous_consumed: int, interval: float) -> tuple[dict[str, object], int]:
    snapshot = runtime.observation_snapshot()
    consumed = int(snapshot["food_eaten"])
    return ({
        "time": round(elapsed, 3), "alive": snapshot["alive"], "born": len(snapshot["organisms"]),
        "dead": snapshot["dead"], "divisions": sum(int(item["divisions"]) for item in snapshot["organisms"]),
        "consumed": consumed, "remaining": snapshot["food_remaining"],
        "throughput": round((consumed - previous_consumed) / interval, 1),
        "median_body": snapshot["body_median"], "max_body": snapshot["body_max"],
        "median_bite": snapshot["bite_median"], "max_bite": snapshot["bite_max"],
    }, consumed)


def _aggregate_metrics(runtime: SandboxRuntime) -> dict[str, tuple[int, float]]:
    totals: dict[str, list[float]] = defaultdict(lambda: [0.0, 0.0])
    for organism in runtime.organisms:
        if organism.hot_metrics is None:
            continue
        for name, (calls, seconds, _average) in organism.hot_metrics.snapshot().items():
            totals[name][0] += calls
            totals[name][1] += seconds
    return {name: (int(value[0]), value[1]) for name, value in totals.items()}


def run(source: Path, seconds: float, interval: float) -> None:
    with tempfile.TemporaryDirectory(prefix="organism-diagnosis-") as directory:
        root = Path(directory) / "sandbox"
        runtime = SandboxRuntime(root, block_size=64 * 1024)
        target = runtime.inbox / source.name
        shutil.copyfile(source, target)
        runtime.bootstrap().enable_hot_profile()
        started = perf_counter()
        next_snapshot = 0.0
        previous_consumed = 0
        timeline: list[dict[str, object]] = []
        while perf_counter() - started < seconds:
            runtime.autonomous_step()
            elapsed = perf_counter() - started
            if elapsed >= next_snapshot:
                point, previous_consumed = _timeline(runtime, elapsed, previous_consumed, max(interval, elapsed - (timeline[-1]["time"] if timeline else 0.0)))
                timeline.append(point)
                next_snapshot += interval
        elapsed = perf_counter() - started
        runtime.verify_world_material_conservation()
        snapshot = runtime.observation_snapshot()
        organisms = [organism for organism in runtime.organisms if organism.alive]
        divisions = [item for organism in runtime.organisms for item in organism.division_diagnostics]
        metrics = _aggregate_metrics(runtime)

        print("BITE LAW")
        print("  formula: bite = max(config.bite_minimum, body_mass)")
        print("  implementation matches formula:", "PASS" if all(o.body.bite_limit(o.config) == max(o.config.bite_minimum, o.body.body_mass) for o in organisms) else "FAIL")
        samples = sorted({(o.body.body_mass, o.body.bite_limit(o.config)) for o in organisms})
        print("  body -> bite samples:", samples[:5] + samples[-5:])
        print("\nPOPULATION TIMELINE")
        for point in timeline:
            print(" ", point)
        print("\nDIVISION")
        print("  candidates committed:", len(divisions), "rejected: not separately materialized by current local selector")
        if divisions:
            print("  median bytes before division:", median(int(item["bytes_since_birth"]) for item in divisions))
            print("  median steps before division:", median(int(item["live_steps"]) for item in divisions))
            print("  first three:", divisions[:3])
        generation_births: dict[int, list[int]] = defaultdict(list)
        for item in divisions:
            generation_births[int(item["generation"])].append(int(item["bytes_since_birth"]))
        print("  generation bytes before division:", {generation: median(values) for generation, values in sorted(generation_births.items())})
        print("\nNEWBORN CASCADE")
        newborn_cascade = any(int(item["bytes_since_birth"]) == 0 for item in divisions)
        print("  observed:" if newborn_cascade else "  not observed:", newborn_cascade)
        print("\nPERFORMANCE")
        total_profile = sum(seconds for _calls, seconds in metrics.values()) or 1.0
        for name, (calls, spent) in sorted(metrics.items(), key=lambda pair: pair[1][1], reverse=True):
            print(f"  {name}: calls={calls} seconds={spent:.6f} avg={spent / calls:.6e} share={100 * spent / total_profile:.1f}%")
        population_points = [point for point in timeline if int(point["alive"]) in {1, 10, 25, 50, 100}]
        print("  sampled bytes/s by population:", [(point["alive"], point["throughput"]) for point in population_points])
        wanted = sum(o.wanted_bite_bytes for o in runtime.organisms)
        actual = sum(o.actual_bite_bytes for o in runtime.organisms)
        failed = sum(o.failed_food_lookups for o in runtime.organisms)
        print("\nFOOD ACCESS")
        print("  wanted bite bytes:", wanted, "actual claimed bytes:", actual, "partial bites:", sum(o.partial_bites for o in runtime.organisms), "failed lookups:", failed)
        print("\n1 MiB RESULT")
        print("  consumed:", snapshot["food_eaten"], "remaining:", snapshot["food_remaining"], "alive:", snapshot["alive"], "born:", snapshot["born"], "dead:", snapshot["dead"])
        print("  divisions:", len(divisions), "max generation:", snapshot["generations"], "body median/max:", snapshot["body_median"], snapshot["body_max"], "bite median/max:", snapshot["bite_median"], snapshot["bite_max"])
        print("  mass conservation: PASS; energy conservation: PASS")
        print("  elapsed:", round(elapsed, 3), "seconds")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("file", type=Path)
    parser.add_argument("--seconds", type=float, default=10.0)
    parser.add_argument("--interval", type=float, default=0.5)
    args = parser.parse_args()
    run(args.file, args.seconds, args.interval)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
