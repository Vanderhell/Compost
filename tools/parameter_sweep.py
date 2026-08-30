from __future__ import annotations

import itertools
import json
import sys
from dataclasses import replace
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from mathematical_organism import MathematicalOrganism, OrganismConfig  # noqa: E402
from mathematical_organism.oracle import ReplayOracle  # noqa: E402


def run() -> list[dict[str, float | int | bool]]:
    """Small falsification sweep; it searches no production topology."""
    rows: list[dict[str, float | int | bool]] = []
    for raw_cost, node_cost, entropy_cost in itertools.product(
        (4.0, 8.0, 12.0), (0.25, 0.75, 1.50), (0.5, 1.5, 3.0)
    ):
        config = replace(
            OrganismConfig(),
            raw_cost=raw_cost,
            node_cost=node_cost,
            context_entropy_cost=entropy_cost,
        )
        organism = MathematicalOrganism(config)
        oracle = ReplayOracle()
        for _ in range(6):
            result = organism.ingest("ABCD")
            oracle.record_result(result)
        comparisons = oracle.compare_all(organism)
        rows.append(
            {
                "raw_cost": raw_cost,
                "node_cost": node_cost,
                "context_entropy_cost": entropy_cost,
                "eligible_compose": len(comparisons),
                "false_reject": any(item.false_reject for item in comparisons),
                "false_accept": any(item.false_accept for item in comparisons),
                "max_abs_delta_error": max((item.absolute_error for item in comparisons), default=0.0),
            }
        )
    return rows


def main() -> int:
    rows = run()
    print(json.dumps(rows, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
