from __future__ import annotations

"""Run and observe the autonomous FOOD sandbox; place files in sandbox/inbox."""

import argparse
import queue
import sys
import threading
from pathlib import Path
from time import monotonic, sleep

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from mathematical_organism.sandbox_runtime import SandboxRuntime  # noqa: E402


def _fmt_bytes(value: float) -> str:
    for unit in ("B", "KiB", "MiB", "GiB"):
        if abs(value) < 1024.0 or unit == "GiB":
            return f"{value:.1f} {unit}" if unit != "B" else f"{int(value)} B"
        value /= 1024.0
    return f"{value:.1f} GiB"


def _view(runtime: SandboxRuntime) -> dict[str, object]:
    return runtime.observation_snapshot()


def _print_status(runtime: SandboxRuntime, started: float) -> None:
    view = _view(runtime); elapsed = max(1e-9, monotonic() - started)
    print("STATUS: RUNNING\n\nFOOD")
    print(f"  original:  {_fmt_bytes(float(view['food_original']))}\n  eaten:     {_fmt_bytes(float(view['food_eaten']))}\n  FOOD:      {_fmt_bytes(float(view['food_remaining']))}\n  inbox:     {_fmt_bytes(float(view['food_inbox_pending']))}\n  rate:      {_fmt_bytes(float(view['food_eaten']) / elapsed)}/s")
    print("\nPOPULATION")
    print(f"  alive:       {view['alive']}\n  born:        {view['born']}\n  dead:        {view['dead']}\n  generations: {view['generations']}")
    print("\nBODY")
    print(f"  avg: {float(view['body_average']):.1f}\n  max: {view['body_max']}")
    print("\nBITE")
    print(f"  avg: {_fmt_bytes(float(view['bite_average']))}\n  max: {_fmt_bytes(float(view['bite_max']))}")
    print(f"\nCORPSES: {view['corpses']}  TERRITORY RECLAIMS: {view['territory_reclaims']}  DUPLICATES: {view['duplicates']}")


def _print_orgs(runtime: SandboxRuntime) -> None:
    print("ID\tGEN\tBODY\tBITE\tRESERVE\tTERRITORY")
    for record in sorted(_view(runtime)["organisms"], key=lambda item: str(item["id"])):
        print(f"{record['id']}\t{record['generation']}\t{record['body']}\t{record['bite']}\t{float(record['reserve']):.3f}\t{record['territory']}")


def _print_org(runtime: SandboxRuntime, organism_id: str) -> None:
    record = next((item for item in _view(runtime)["organisms"] if item["id"] == organism_id), None)
    if record is None:
        print(f"unknown organism: {organism_id}"); return
    for key in ("id", "parent", "generation", "alive", "territory", "body", "atoms", "relations", "composites", "bite", "reserve", "bytes_eaten", "births", "corpse_nutrition"):
        print(f"{key}: {record[key]}")


def _print_top(runtime: SandboxRuntime) -> None:
    records = _view(runtime)["organisms"]
    for metric in ("body", "bite", "bytes_eaten", "reserve", "births"):
        leaders = sorted(records, key=lambda item: (-float(item[metric]), str(item["id"])))[:5]
        print(f"{metric}: " + ", ".join(f"{item['id']}={item[metric]}" for item in leaders))


def _print_tree(runtime: SandboxRuntime, depth: int) -> None:
    by_parent: dict[str | None, list[dict[str, object]]] = {}
    for record in _view(runtime)["organisms"]:
        by_parent.setdefault(record["parent"], []).append(record)
    def visit(parent: str | None, prefix: str, remaining: int) -> None:
        for child in sorted(by_parent.get(parent, []), key=lambda item: str(item["id"])):
            print(f"{prefix}{child['id']}")
            if remaining > 0: visit(str(child["id"]), prefix + "  ", remaining - 1)
    visit(None, "", depth)


def _handle_command(runtime: SandboxRuntime, started: float, command: str) -> bool:
    pieces = command.strip().split()
    if not pieces: return True
    name = pieces[0].lower()
    if name == "status": _print_status(runtime, started)
    elif name == "orgs": _print_orgs(runtime)
    elif name == "org" and len(pieces) == 2: _print_org(runtime, pieces[1])
    elif name == "top": _print_top(runtime)
    elif name == "tree": _print_tree(runtime, int(pieces[1]) if len(pieces) == 2 and pieces[1].isdigit() else 4)
    elif name == "food":
        view = _view(runtime); print(f"original={view['food_original']} eaten={view['food_eaten']} remaining={view['food_remaining']} inbox={view['food_inbox_pending']} duplicates={view['duplicates']}")
    elif name == "births": print(f"births={_view(runtime)['born']}")
    elif name == "deaths": print(f"deaths={_view(runtime)['dead']}")
    elif name == "corpses": print(f"corpses={_view(runtime)['corpses']}")
    elif name == "help": print("status | orgs | org <id> | top | tree [depth] | food | births | deaths | corpses | help | quit")
    elif name in {"quit", "exit"}: return False
    else: print("unknown command; use help")
    return True


def _stdin_reader(commands: "queue.SimpleQueue[str]") -> None:
    for line in sys.stdin: commands.put(line)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sandbox", type=Path, default=PROJECT_ROOT / "sandbox")
    parser.add_argument("--seconds", type=float, help="optional bounded run for automation")
    parser.add_argument("--block-size", type=int, default=65536, help="physical FOOD block size; it does not change biological bite capacity")
    parser.add_argument("--snapshot-ms", type=int, default=500)
    parser.add_argument("--interactive", action="store_true", help="accept read-only observer commands on stdin")
    args = parser.parse_args()
    runtime = SandboxRuntime(args.sandbox, block_size=args.block_size)
    started = monotonic(); last_snapshot = 0.0; max_population = 0
    commands: queue.SimpleQueue[str] = queue.SimpleQueue()
    if args.interactive or (args.seconds is None and sys.stdin.isatty()):
        threading.Thread(target=_stdin_reader, args=(commands,), daemon=True).start()
    print("SANDBOX RUNNING\nPlace binary files in sandbox/inbox/. Commands: help")
    try:
        running = True
        while running and (args.seconds is None or monotonic() - started < args.seconds):
            runtime.autonomous_step(); max_population = max(max_population, sum(organism.alive for organism in runtime.organisms))
            while not commands.empty():
                running = _handle_command(runtime, started, commands.get())
                if not running: break
            now = monotonic()
            if now - last_snapshot >= args.snapshot_ms / 1000.0:
                _print_status(runtime, started); last_snapshot = now
            sleep(0.001)
    except KeyboardInterrupt:
        pass
    view = _view(runtime)
    missing = int(view['food_original']) - int(view['food_eaten']) - int(view['food_remaining']) - int(view['food_inbox_pending'])
    print(f"\nINPUT SIZE={view['food_original']} ELAPSED={monotonic() - started:.3f}s FOOD CONSUMED={view['food_eaten']} FOOD REMAINING={view['food_remaining']} INBOX PENDING={view['food_inbox_pending']} DUPLICATES={view['duplicates']} MISSING={missing}")
    print(f"TOTAL BORN={view['born']} TOTAL DEAD={view['dead']} MAX ALIVE={max_population} MAX GENERATION={view['generations']}")
    print(f"BODY MIN/MEDIAN/MAX={view['body_min']}/{view['body_median']}/{view['body_max']} BITE MIN/MEDIAN/MAX={view['bite_min']}/{view['bite_median']}/{view['bite_max']} CORPSES={view['corpses']} TERRITORY RECLAIMS={view['territory_reclaims']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
