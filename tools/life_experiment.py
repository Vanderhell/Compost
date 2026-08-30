from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from mathematical_organism.life_experiments import population_report, run_experiment, sweep  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Mathematical organism lifecycle experiment")
    parser.add_argument("--scenario", default="dominant")
    parser.add_argument("--all", action="store_true", help="run every fixed environment")
    parser.add_argument("--length", type=int, default=240)
    parser.add_argument("--sweep", action="store_true")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if args.sweep:
        result = sweep()
    elif args.all:
        result = {
            name: population_report(run_experiment(name, length=args.length))
            for name in ("dominant", "two_regions", "dominant_noise", "phase_change", "alternating", "uniform_noise", "large")
        }
    else:
        result = population_report(run_experiment(args.scenario, length=args.length))
    rendered = json.dumps(result, indent=2, sort_keys=True)
    if args.output:
        args.output.write_text(rendered + "\n", encoding="utf-8")
    print(rendered)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
