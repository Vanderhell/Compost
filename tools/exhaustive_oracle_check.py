from __future__ import annotations

import argparse
import hashlib
import itertools
import json
import sys
from collections import defaultdict
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from mathematical_organism import MathematicalOrganism  # noqa: E402
from mathematical_organism.oracle import ReplayOracle  # noqa: E402


IMPLEMENTED_RULES = ("GROW_ROUTE", "COMPOSE", "SPLIT", "MERGE", "PRUNE")


def _state_hash(organism: MathematicalOrganism) -> str:
    rendered = json.dumps(organism.snapshot(), sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(rendered.encode("utf-8")).hexdigest()


def run(alphabet: str = "AB", input_lengths: tuple[int, ...] = (1, 2), depth: int = 5) -> dict:
    """Exhaustively check a finite input-space; production code is never enumerated."""
    words = tuple(
        "".join(item)
        for length in input_lengths
        for item in itertools.product(alphabet, repeat=length)
    )
    counters: defaultdict[str, int] = defaultdict(int)
    max_error: defaultdict[str, float] = defaultdict(float)
    counterexamples: dict[str, list[str]] = {}
    states: set[str] = set()
    streams = 0
    invariant_failures = 0

    for stream in itertools.product(words, repeat=depth):
        streams += 1
        organism = MathematicalOrganism()
        oracle = ReplayOracle()
        for prefix_length, item in enumerate(stream, 1):
            result = organism.ingest(item)
            oracle.record_result(result)
            states.add(_state_hash(organism))
            counters[f"accepted.{result.adaptive_rule}"] += result.adaptive_rule != "KEEP"
            try:
                organism.graph.validate(organism.config)
                if result.reconstructed != tuple(item):
                    raise AssertionError("reconstruction mismatch")
                comparisons = oracle.compare_all(organism)
                scheduler = oracle.scheduler_check(organism) if comparisons else None
            except (AssertionError, ValueError):
                invariant_failures += 1
                continue

            for candidate in organism.candidates.values():
                counters[f"candidate.{candidate.kind.value}"] += 1
            for comparison in comparisons:
                rule = comparison.rule
                counters[f"eligible.{rule}"] += 1
                counters[f"local_rejected.{rule}"] += not comparison.local_accept
                counters[f"oracle_rejected.{rule}"] += not comparison.oracle_accept
                counters[f"matches.{rule}"] += comparison.local_accept == comparison.oracle_accept
                counters[f"false_accept.{rule}"] += comparison.false_accept
                counters[f"false_reject.{rule}"] += comparison.false_reject
                counters["oracle_evaluations"] += 1
                counters["oracle_disagreements"] += comparison.local_accept != comparison.oracle_accept
                counters["state_mutation_during_evaluation"] += comparison.state_mutation_during_evaluation
                max_error[rule] = max(max_error[rule], comparison.absolute_error)
                prefix = list(stream[:prefix_length])
                if comparison.local_accept != comparison.oracle_accept and (
                    rule not in counterexamples
                    or (len(prefix), tuple(prefix))
                    < (len(counterexamples[rule]), tuple(counterexamples[rule]))
                ):
                    counterexamples[rule] = prefix
            if scheduler is not None:
                counters["wrong_winner_count"] += scheduler["wrong_winner"]
                counters["wrong_tie_break_count"] += scheduler["wrong_tie_break"]

    rule_metrics = {
        rule: {
            "candidate_count": counters[f"candidate.{rule}"],
            "eligible_count": counters[f"eligible.{rule}"],
            "accepted_count": counters[f"accepted.{rule}"],
            "local_rejected_count": counters[f"local_rejected.{rule}"],
            "oracle_rejected_count": counters[f"oracle_rejected.{rule}"],
            "false_accept_count": counters[f"false_accept.{rule}"],
            "false_reject_count": counters[f"false_reject.{rule}"],
            "max_abs_delta_error": max_error[rule],
        }
        for rule in IMPLEMENTED_RULES
    }
    return {
        "profile": {"alphabet": alphabet, "input_lengths": input_lengths, "depth": depth},
        "number_of_streams": streams,
        "number_of_states": len(states),
        "candidate_count_by_rule": rule_metrics,
        "oracle_evaluations": counters["oracle_evaluations"],
        "oracle_disagreements": counters["oracle_disagreements"],
        "wrong_winner_count": counters["wrong_winner_count"],
        "wrong_tie_break_count": counters["wrong_tie_break_count"],
        "state_mutation_during_evaluation": counters["state_mutation_during_evaluation"],
        "invariant_failures": invariant_failures,
        "minimal_counterexamples": counterexamples,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Exhaustive finite replay-oracle check")
    parser.add_argument("--depth", type=int, default=5)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if args.depth <= 0:
        raise SystemExit("--depth must be positive")
    result = run(depth=args.depth)
    rendered = json.dumps(result, indent=2, sort_keys=True)
    if args.output:
        args.output.write_text(rendered + "\n", encoding="utf-8")
    print(rendered)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
