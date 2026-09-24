from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys
from typing import Sequence

from .backend import NativeBackend, create_backend
from .organism import MathematicalOrganism
from .public_sandbox import PublicMultiprocessingSandbox, PublicSandbox, read_last_snapshot


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run the Compost reference simulator."
    )
    parser.add_argument(
        "sequences",
        nargs="*",
        help="Input sequences; every character is one V0 symbol.",
    )
    parser.add_argument(
        "--repeat",
        type=int,
        default=1,
        help="Repeat the supplied sequence list this many times.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Print the final deterministic snapshot as JSON.",
    )
    return parser


def _legacy_main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.repeat <= 0:
        raise SystemExit("--repeat must be positive")
    sequences = args.sequences or ["ABCD", "ABCD", "XABC", "YABD"]

    organism = MathematicalOrganism()
    for _ in range(args.repeat):
        for sequence in sequences:
            result = organism.ingest(sequence)
            print(
                f"t={result.time:04d} input={sequence} raw={result.raw_count} "
                f"rule={result.adaptive_rule} nodes={result.node_count} "
                f"edges={result.transition_count} energy={result.energy_after:.6f}"
            )

    if args.json:
        print(json.dumps(_json_safe(organism.snapshot()), indent=2, sort_keys=True))
    else:
        print(f"audit_sha256={organism.audit.digest()}")
    return 0


def _fmt_bytes(value: float | int | None) -> str:
    if value is None:
        return "n/a"
    amount = float(value)
    for unit in ("B", "KiB", "MiB", "GiB"):
        if abs(amount) < 1024.0 or unit == "GiB":
            return f"{int(amount)} B" if unit == "B" else f"{amount:.2f} {unit}"
        amount /= 1024.0
    return f"{amount:.2f} GiB"


def _json_safe(value: object) -> object:
    """Convert opaque snapshot containers to deterministic JSON values."""
    if isinstance(value, bytes):
        return value.hex()
    if isinstance(value, tuple):
        return [_json_safe(item) for item in value]
    if isinstance(value, list):
        return [_json_safe(item) for item in value]
    if isinstance(value, dict):
        return {key: _json_safe(item) for key, item in value.items()}
    return value


def _print_sandbox_snapshot(snapshot: dict[str, object], *, include_organisms: bool = True, organism_limit: int | None = 16) -> None:
    food = snapshot["food"]
    population = snapshot["population"]
    body = snapshot["body"]
    energy = snapshot["energy"]
    world = snapshot["world"]
    performance = snapshot["performance"]
    prepared_remaining = int(food["remaining"])
    inbox_pending = int(food.get("inbox_pending", 0))
    total_remaining = prepared_remaining + inbox_pending
    print("\nSANDBOX")
    print("FOOD")
    print(
        f"  original:            {_fmt_bytes(food['original'])}\n"
        f"  consumed:            {_fmt_bytes(food['consumed'])}\n"
        f"  prepared remaining:  {_fmt_bytes(prepared_remaining)}\n"
        f"  inbox pending:       {_fmt_bytes(inbox_pending)}\n"
        f"  total remaining:     {_fmt_bytes(total_remaining)}\n"
        f"  accounting: original = consumed + prepared remaining + inbox pending"
    )
    print("POPULATION")
    print(f"  alive: {population['alive']}  born: {population['born']}  dead: {population['dead']}  divisions: {population['divisions']}  max generation: {population['max_generation']}")
    print("BODY")
    print(f"  min: {body['min']}  median: {body['median']}  max: {body['max']}")
    print("ENERGY")
    print(f"  reserve [min/median/max]: {energy['reserve_min']:.6f}/{energy['reserve_median']:.6f}/{energy['reserve_max']:.6f}\n  metabolic debt: {energy['metabolic_debt']:.6f}  gut backlog: {energy['gut_backlog']}")
    print("WORLD")
    print(f"  occupied territories: {world['occupied_territories']}  free territories: {world['free_territories']}  corpses: {world['corpses']}  reclaims: {world['reclaims']}")
    print("PERFORMANCE")
    print(f"  elapsed: {snapshot['elapsed_seconds']:.3f}s  rate: {performance['mib_per_second']:.3f} MiB/s  CPU: {snapshot['cpu_utilization']:.2f}  RAM: {_fmt_bytes(snapshot['ram_bytes'])}")
    if include_organisms:
        living = [organism for organism in snapshot["organisms"] if organism["alive"]]
        shown = living if organism_limit is None else living[:organism_limit]
        for organism in shown:
            print(
                f"ORG {organism['id']} parent={organism['parent']} gen={organism['generation']} "
                f"territory={organism['territory']} mass={organism['body_mass']} atoms={organism['atoms']} "
                f"relations={organism['relations']} composites={organism['composites']} reserve={organism['reserve']:.6f} "
                f"debt={organism['metabolic_debt']:.6f} gut={organism['gut']} weakest={organism['weakest_weight']} "
                f"bytes={organism['bytes_eaten']} divisions={organism['divisions']}"
            )
        if len(shown) < len(living):
            print(f"  ... {len(living) - len(shown)} additional living organisms are present in telemetry/latest.json")


def _public_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="External autonomous Compost sandbox.")
    commands = parser.add_subparsers(dest="command", required=True)
    run = commands.add_parser("run", help="run an autonomous world; add binary files to sandbox/inbox")
    run.add_argument("sandbox", type=Path)
    run.add_argument("--block-size", type=int, default=64 * 1024)
    run.add_argument("--workers", type=int, default=max(1, min(8, os.cpu_count() or 1)), help="persistent autonomous worker processes")
    run.add_argument("--backend", choices=("python", "native"), default="python")
    run.add_argument("--library", type=Path, help="native library path; required for --backend native")
    run.add_argument("--snapshot-seconds", type=float, default=0.5)
    run.add_argument("--max-seconds", type=float, help="optional observation bound; terminal reason is USER_STOP")
    status = commands.add_parser("status", help="read the last read-only telemetry snapshot")
    status.add_argument("sandbox", type=Path)
    status.add_argument("--organisms", action="store_true", help="print every living organism from the saved snapshot")
    checkpoint = commands.add_parser("checkpoint", help="run the bounded Python/native deterministic checkpoint")
    checkpoint.add_argument("payload", nargs="?", default="ABCD")
    checkpoint.add_argument("--backend", choices=("python", "native"), default="python")
    checkpoint.add_argument("--library", type=Path, help="native library path; required for --backend native")
    checkpoint.add_argument("--steps", type=int, default=1)
    checkpoint.add_argument("--json", action="store_true")
    return parser


def _public_main(argv: Sequence[str]) -> int:
    args = _public_parser().parse_args(argv)
    if args.command == "status":
        snapshot = read_last_snapshot(args.sandbox)
        if snapshot is None:
            print(f"No telemetry snapshot in {args.sandbox / 'telemetry'}.")
            return 1
        _print_sandbox_snapshot(snapshot, organism_limit=None if args.organisms else 16)
        print(f"TERMINATION: {snapshot.get('termination') or 'RUNNING'}")
        if snapshot.get("failure"):
            print(f"FAILURE: {snapshot['failure']}")
        return 0
    if args.command == "checkpoint":
        if args.steps <= 0:
            raise SystemExit("--steps must be positive")
        if args.backend == "native":
            if args.library is None:
                raise SystemExit("--library is required with --backend native")
            with create_backend("native", library=args.library) as backend:
                assert isinstance(backend, NativeBackend)
                for step in range(args.steps):
                    payload = args.payload.encode("ascii") if step == 0 else b""
                    backend.step(payload, (1.0,) * len(payload))
                result = {"backend": "native", "steps": args.steps, "snapshot": backend.snapshot()}
        else:
            backend = create_backend("python", payload=args.payload)
            for _ in range(args.steps):
                backend.population.cycle()  # type: ignore[union-attr]
            result = {"backend": "python", "steps": args.steps, "snapshot": backend.population.snapshot()}  # type: ignore[union-attr]
        if args.json:
            print(json.dumps(_json_safe(result), indent=2, sort_keys=True))
        else:
            print(f"CHECKPOINT backend={result['backend']} steps={args.steps}")
        return 0
    if args.block_size <= 0 or args.workers <= 0 or args.snapshot_seconds <= 0 or (args.max_seconds is not None and args.max_seconds <= 0):
        raise SystemExit("--block-size, --workers, --snapshot-seconds, and --max-seconds must be positive")
    if args.backend == "native":
        if args.library is None:
            raise SystemExit("--library is required with --backend native")
        if args.workers != 1:
            raise SystemExit("--backend native requires --workers 1")
        sandbox = PublicSandbox(
            args.sandbox,
            block_size=args.block_size,
            backend="native",
            library=args.library,
        )
    else:
        sandbox = PublicMultiprocessingSandbox(args.sandbox, workers=args.workers, block_size=args.block_size)
    print(f"SANDBOX RUNNING: place binary files in {sandbox.layout.inbox}")
    termination, snapshot = sandbox.run(
        snapshot_seconds=args.snapshot_seconds,
        max_seconds=args.max_seconds,
        observer=lambda view: _print_sandbox_snapshot(view),
    )
    _print_sandbox_snapshot(snapshot)
    mass = snapshot["mass"]
    food = snapshot["food"]
    energy = snapshot["energy"]
    print(
        "CONSERVATION\n"
        f"  external input={mass['input']} assimilated={mass['assimilated']} expelled={mass['external_expelled']} gut={mass['external_gut']}\n"
        f"  resorption expelled={mass['resorption_expelled']} gut={mass['resorption_gut']}\n"
        f"  food original={food['original']} consumed={food['consumed']} prepared_remaining={food['remaining']} inbox_pending={food.get('inbox_pending', 0)} total_remaining={int(food['remaining']) + int(food.get('inbox_pending', 0))} duplicates={food['duplicates']} missing={food['missing']}\n"
        f"  structural mass={mass['structural_mass']} resorbed={mass['resorbed_mass']} energy spent={energy['energy_spent']:.6f} reserve={energy['reserve_max']:.6f}"
    )
    print(f"TERMINATION: {termination}")
    if snapshot.get("failure"):
        print(f"FAILURE: {snapshot['failure']}")
    return 0 if termination in {"FOOD_EXHAUSTED", "USER_STOP", "EXTINCTION"} else 2


def main(argv: Sequence[str] | None = None) -> int:
    arguments = list(sys.argv[1:] if argv is None else argv)
    if not arguments or arguments[0] in {"-h", "--help"}:
        parser = argparse.ArgumentParser(
            description="Compost experimental sandbox and reference simulator."
        )
        commands = parser.add_subparsers(title="commands", dest="command")
        commands.add_parser("run", help="run an autonomous multiprocessing sandbox")
        commands.add_parser("status", help="read the last sandbox telemetry snapshot")
        commands.add_parser("legacy", help="run the legacy deterministic sequence simulator")
        commands.add_parser("checkpoint", help="run the bounded Python/native deterministic checkpoint")
        parser.epilog = "Use 'run SANDBOX', 'status SANDBOX', or 'checkpoint --backend python'. Legacy simulation remains available as 'legacy [SEQUENCE ...]'."
        parser.print_help()
        return 0
    if arguments and arguments[0] in {"run", "status", "checkpoint"}:
        return _public_main(arguments)
    if arguments[0] == "legacy":
        return _legacy_main(arguments[1:])
    return _legacy_main(arguments)


if __name__ == "__main__":
    raise SystemExit(main())
