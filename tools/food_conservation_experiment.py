from __future__ import annotations

"""Run the fixed alternating-stream food-conservation measurements."""

import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from mathematical_organism.life_experiments import population_report, run_experiment  # noqa: E402


LENGTHS = (48, 96, 192, 384, 768, 1536)


def main() -> int:
    rows: list[dict[str, object]] = []
    for length in LENGTHS:
        population = run_experiment("alternating", length=length)
        report = population_report(population)
        available = float(report["total_available_nutrition"])
        rows.append({
            "length": length,
            "alive_population": report["alive"],
            "total_born": report["total_organisms_born"],
            "total_dead": report["dead"],
            "divisions": report["divisions"],
            "reserve": sum(item.reserve for item in population.alive()),
            "total_strength": sum(item.total_strength for item in population.alive()),
            "total_exposure": report["total_exposure"],
            "total_available_nutrition": available,
            "total_consumed_nutrition": report["total_consumed_nutrition"],
            "nutrition_created": report["nutrition_created"],
            "exposure_multiplier": float(report["total_exposure"]) / length,
            "nutrition_multiplier": float(report["total_consumed_nutrition"]) / available if available else 0.0,
            "conservation_holds": float(report["total_consumed_nutrition"]) <= available + 1e-12,
        })
    output = PROJECT_ROOT / "food-conservation-results.json"
    output.write_text(json.dumps(rows, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(output), "rows": rows}, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
