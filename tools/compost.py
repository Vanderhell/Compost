from __future__ import annotations

"""Interactive administrative console for the persistent COMPOST sandbox."""

import sys
from pathlib import Path
from statistics import median
from time import sleep

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from mathematical_organism.compost import CompostController  # noqa: E402


def _bytes(value: float) -> str:
    for unit in ("B", "KiB", "MiB", "GiB"):
        if value < 1024 or unit == "GiB":
            return f"{int(value)} B" if unit == "B" else f"{value:.1f} {unit}"
        value /= 1024
    return f"{value:.1f} GiB"


def _print_menu() -> None:
    print("\nMATHEMATICAL ORGANISM — COMPOST\n\n[1] Start ecosystem\n[2] Stop ecosystem\n\n[3] Add organisms\n[4] Add food\n\n[5] Live view\n[6] Organisms\n[7] Food\n[8] Family tree\n[9] Corpses\n[10] Results\n\n[11] Delete organisms\n[12] Delete food\n[13] Clear sandbox\n\n[0] Exit")


def print_live_view(controller: CompostController) -> None:
    view = controller.snapshot()
    elapsed = max(1e-9, float(view["elapsed"]))
    records = list(view["organisms"])
    masses = [int(item["body_mass"]) for item in records]
    bites = [int(item["bite"]) for item in records]
    print("\n================================================\nCOMPOST — " + ("RUNNING" if view["running"] else "STOPPED"))
    print("\nFOOD")
    print(f"  inbox:     {_bytes(float(view['food_inbox_pending']))}\n  prepared: {_bytes(float(view['food_remaining']))}\n  consumed:  {_bytes(float(view['food_eaten']))}\n  rate:      {_bytes(float(view['food_eaten']) / elapsed)}/s")
    print("\nPOPULATION")
    print(f"  alive: {view['alive']}\n  born: {view['born']}\n  dead: {view['dead']}\n  max generation: {view['generations']}")
    print("\nBODY MASS")
    print(f"  min: {min(masses, default=0)}\n  median: {median(masses) if masses else 0}\n  max: {max(masses, default=0)}")
    print("\nBITE")
    print(f"  min: {_bytes(min(bites, default=0))}\n  median: {_bytes(float(median(bites)) if bites else 0)}\n  max: {_bytes(max(bites, default=0))}")
    print("\nSKELETON")
    print(f"  relations: {view['relations']}\n  composites: {view['composites']}")
    print(f"\nCORPSES\n  count: {view['corpses']}\n  energy: {float(view['corpse_energy']):.3f}")
    events = controller.runtime.observer.events[-4:]
    if events:
        print("\nLAST EVENTS")
        for event in events:
            print(f"  {event.kind} {event.organism_id or ''} {event.detail}".rstrip())
    print("================================================")


def _print_organisms(controller: CompostController) -> None:
    print("ID\tSTATE\tGEN\tBODY\tBITE\tRESERVE\tTERRITORY")
    for record in sorted(controller.snapshot()["organisms"], key=lambda item: str(item["id"])):
        state = "ACTIVE" if record["alive"] else "DEAD"
        print(f"{record['id']}\t{state}\t{record['generation']}\t{record['body_mass']}\t{record['bite']}\t{float(record['reserve']):.3f}\t{record['territory']}")


def _print_organism_detail(controller: CompostController, organism_id: str) -> None:
    record = next((item for item in controller.snapshot()["organisms"] if item["id"] == organism_id), None)
    if record is None:
        print(f"unknown organism: {organism_id}")
        return
    for key in ("id", "parent", "generation", "alive", "territory", "body_mass", "bite", "reserve", "atoms", "relations", "composites", "bytes_eaten", "corpse_nutrition", "births"):
        print(f"{key}: {record[key]}")


def _print_food(controller: CompostController) -> None:
    view = controller.snapshot()
    print(f"TOTAL INPUT={view['food_original']} INBOX={view['food_inbox_pending']} PREPARED={view['food_remaining']} CONSUMED={view['food_eaten']} DUPLICATES={view['duplicates']} MISSING={view['food_missing']}")
    for item in controller.food_by_source():
        percentage = 100.0 * float(item['consumed']) / max(1, int(item['size']))
        print(f"{item['name']} {item['size']} B {percentage:.1f}% consumed")


def main() -> int:
    controller = CompostController(PROJECT_ROOT / "sandbox")
    while True:
        _print_menu(); choice = input("> ").strip()
        try:
            if choice == "0":
                controller.stop(); return 0
            if choice == "1": controller.start(); print("ecosystem started")
            elif choice == "2": controller.stop(); print("ecosystem stopped")
            elif choice == "3": print(f"created {len(controller.add_organisms(int(input('Number of organisms: '))))} organisms")
            elif choice == "4":
                mode = input("[1] real file/directory [2] generated food: ").strip()
                if mode == "1": print("added", *controller.add_real_path(input("Path: ")))
                elif mode == "2":
                    size = int(input("Food size in bytes: ")); seed = int(input("Seed [12345]: ") or "12345")
                    generated = controller.generate_food(size, seed=seed); print(f"Generated: size={_bytes(generated.size)} seed={generated.seed}")
            elif choice == "5":
                seconds = float(input("Live view seconds [0 = Ctrl+C]: ") or "0")
                try:
                    if seconds <= 0:
                        while True:
                            print_live_view(controller); sleep(0.4)
                    else:
                        remaining = seconds
                        while remaining > 0:
                            print_live_view(controller); sleep(min(0.4, remaining)); remaining -= 0.4
                except KeyboardInterrupt:
                    print("live view stopped")
            elif choice == "6":
                _print_organisms(controller)
                organism_id = input("Organism ID for detail [Enter to return]: ").strip()
                if organism_id:
                    _print_organism_detail(controller, organism_id)
            elif choice == "7": _print_food(controller)
            elif choice == "8":
                for level, name in controller.family_tree(int(input("Depth [4]: ") or "4")): print("  " * level + name)
            elif choice == "9":
                for corpse in controller.runtime.corpses: print(f"{corpse.source_organism_id} territory=D{''.join(map(str, corpse.territory.path))} energy={corpse.remaining_energy:.3f}")
            elif choice == "10":
                view = controller.snapshot()
                print(f"INPUT={view['food_original']} CONSUMED={view['food_eaten']} REMAINING={view['food_remaining']} DUPLICATES={view['duplicates']} MISSING={view['food_missing']}")
                print(f"INITIAL/LIVE/BORN/DEAD=not persisted/{view['alive']}/{view['born']}/{view['dead']} MAX GENERATION={view['generations']} ELAPSED={float(view['elapsed']):.3f}s")
            elif choice == "11": controller.delete_organisms({"1":"dead", "2":"one", "3":"all"}.get(input("[1] dead [2] one [3] all: "), "invalid"), input("ID: ") or None)
            elif choice == "12": controller.delete_food({"1":"inbox", "2":"prepared", "3":"all"}.get(input("[1] inbox [2] prepared [3] all: "), "invalid"))
            elif choice == "13": controller.clear({"1":"food", "2":"dead", "3":"organisms", "4":"traces", "5":"everything"}.get(input("[1] food [2] dead+corpses [3] organisms [4] traces/results [5] everything: "), "invalid"))
        except (OSError, RuntimeError, ValueError) as error:
            print(f"error: {error}")


if __name__ == "__main__":
    raise SystemExit(main())
