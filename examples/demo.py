from __future__ import annotations

import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from mathematical_organism import MathematicalOrganism  # noqa: E402


def main() -> None:
    organism = MathematicalOrganism()
    stream = ["ABCD"] * 8 + ["XABC", "YABD"] * 8 + ["AC"] * 8

    for sequence in stream:
        result = organism.ingest(sequence)
        print(
            f"t={result.time:02d} {sequence:<4} "
            f"raw={result.raw_count} rule={result.adaptive_rule:<10} "
            f"V={result.node_count:<3} E={result.transition_count:<3}"
        )

    print(f"audit digest: {organism.audit.digest()}")


if __name__ == "__main__":
    main()

