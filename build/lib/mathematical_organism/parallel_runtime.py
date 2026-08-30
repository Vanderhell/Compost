from __future__ import annotations

"""Persistent process workers for autonomous sandbox organisms.

Workers retain organism objects for their whole lifetime.  Requests sent to
the parent are restricted to physical sandbox operations selected locally by
an organism: ingest, a concrete FOOD block claim/read/commit, corpse storage,
and read-only ownership queries.  No organism body is returned after a bite.
"""

from dataclasses import dataclass
from hashlib import sha256
import multiprocessing as mp
from pathlib import Path
from queue import Empty
from time import monotonic, sleep
from typing import Any, Iterable

from .destructive_ingest import BlockClaim
from .sandbox_runtime import AutonomousOrganism, Corpse, SandboxRuntime
from .territory import FoodTerritory


@dataclass(frozen=True, slots=True)
class ParallelMetrics:
    workers_used: int
    max_simultaneous_organisms: int
    births: int
    deaths: int
    divisions: int
    food_consumed: int
    duplicates: int
    body_transfers: int
    worker_migrations: int
    parent_food_rpcs: int
    direct_food_operations: int
    missing: int
    file_opens: int
    stat_calls: int
    truncates: int
    bite_sizes: tuple[int, ...]
    environment_rpcs: int
    live_steps: int
    successful_bites: int
    mass_conservation: bool
    energy_conservation: bool
    newborn_initial_placements: int
    newborn_local_placements: int
    newborn_remote_placements: int
    worker_distribution: tuple[tuple[int, int, int, int], ...]


class _DirectFood:
    """Worker-local handle for direct, territory-checked physical FOOD I/O."""

    def __init__(self, root: Path, name: str, source_hash: str, block_count: int, source_size: int, block_size: int) -> None:
        self.root = root
        self.name = name
        self.source_hash = source_hash
        self.block_count = block_count
        self.source_size = source_size
        self.block_size = block_size
        self.food_dir = root / "food" / name
        self.direct_operations = 0
        self.consumed = 0
        self.duplicates = 0
        self.foreign_rejections = 0
        self.file_opens = 0
        self.stat_calls = 0
        self.truncates = 0
        self.flushes = 0
        self.fsyncs = 0
        self.bite_sizes: list[int] = []
        self._active_block_id: int | None = None
        self._active_remaining = 0
        self._active_start = 0
        self._active_handle: Any | None = None

    def _path(self, block_id: int) -> Path:
        return self.food_dir / f"block_{block_id:06d}.food"

    def _original_range(self, block_id: int) -> tuple[int, int]:
        end = self.source_size - block_id * self.block_size
        return max(0, end - self.block_size), end

    @property
    def has_active_block(self) -> bool:
        return self._active_handle is not None and self._active_remaining > 0

    def _close_active(self, *, delete: bool) -> None:
        if self._active_handle is None or self._active_block_id is None:
            return
        path = self._path(self._active_block_id)
        self._active_handle.close()
        self._active_handle = None
        if delete:
            path.unlink()
            self.direct_operations += 1
        self._active_block_id = None
        self._active_remaining = 0
        self._active_start = 0

    def close(self) -> None:
        """Release a cached descriptor without changing physical FOOD."""
        self._close_active(delete=False)

    def _open_block(self, block_id: int) -> bool:
        path = self._path(block_id)
        if not path.is_file():
            return False
        self.stat_calls += 1
        remaining = path.stat().st_size
        if remaining <= 0:
            return False
        self._active_handle = path.open("r+b")
        self.file_opens += 1
        self._active_block_id = block_id
        self._active_remaining = remaining
        self._active_start = self._original_range(block_id)[0]
        return True

    def claim_active(self, capacity: int, territory: FoodTerritory) -> BlockClaim | None:
        if not self.has_active_block or self._active_block_id is None:
            return None
        if not territory.owns_block(self.source_hash, self._active_block_id):
            self.foreign_rejections += 1
            self._close_active(delete=False)
            return None
        length = min(capacity, self._active_remaining)
        return BlockClaim(self._active_block_id, self._active_start + self._active_remaining - length, length, 0)

    def claim(self, block_id: int, capacity: int, *, skipped_regions: int, territory: FoodTerritory | None = None) -> BlockClaim | None:
        if territory is None or not territory.owns_block(self.source_hash, block_id):
            self.foreign_rejections += 1
            return None
        active = self.claim_active(capacity, territory)
        if active is not None:
            return active
        path = self._path(block_id)
        if capacity <= 0 or not self._open_block(block_id):
            return None
        return self.claim_active(capacity, territory)

    def read(self, claim: BlockClaim) -> tuple[int, ...]:
        if claim.block_id != self._active_block_id or self._active_handle is None or self._active_remaining < claim.length:
            raise IOError("owned FOOD block changed before direct read")
        self._active_handle.seek(self._active_remaining - claim.length)
        payload = self._active_handle.read(claim.length)
        if len(payload) != claim.length:
            raise IOError("short direct FOOD bite read")
        self.direct_operations += 1
        return tuple(payload)

    def consume(self, claim: BlockClaim) -> None:
        if claim.block_id != self._active_block_id or self._active_handle is None:
            self.duplicates += 1
            raise AssertionError("direct consume without active owned FOOD block")
        if claim.original_offset + claim.length != self._active_start + self._active_remaining:
            self.duplicates += 1
            raise AssertionError("non-tail or duplicate direct FOOD consume")
        new_size = self._active_remaining - claim.length
        self._active_handle.truncate(new_size)
        self.direct_operations += 1
        self.truncates += 1
        self.consumed += claim.length
        self.bite_sizes.append(claim.length)
        self._active_remaining = new_size
        if new_size == 0:
            self._close_active(delete=True)


class _RemoteObserver:
    def __init__(self, environment: "_WorkerEnvironment") -> None:
        self.environment = environment

    def observe(self, kind: str, organism_id: str | None = None, detail: str = "") -> None:
        self.environment.notify("observe", kind, organism_id, detail)


class _WorkerEnvironment:
    """Environment facade used by one worker; biology remains in the caller."""

    def __init__(self, worker_id: int, root: Path, requests: Any, replies: Any) -> None:
        self.worker_id = worker_id
        self.root = root
        self._requests = requests
        self._replies = replies
        self._sequence = 0
        self._foods: dict[str, _DirectFood] = {}
        self.observer = _RemoteObserver(self)
        self.newborns: list[AutonomousOrganism] = []
        self._telemetry_steps = 0
        self._bite_events = 0

    def request(self, operation: str, *payload: object) -> Any:
        sequence = self._sequence
        self._sequence += 1
        self._requests.put((self.worker_id, sequence, operation, payload))
        reply_sequence, ok, value = self._replies.get()
        if reply_sequence != sequence:
            raise RuntimeError("worker received an out-of-order environment reply")
        if not ok:
            raise RuntimeError(value)
        return value

    def notify(self, operation: str, *payload: object) -> None:
        """One-way observer telemetry; it never delays a biological bite."""
        self._requests.put((self.worker_id, None, operation, payload))

    @property
    def food_sources(self) -> dict[str, _DirectFood]:
        if not self._foods:
            self.refresh_food_sources()
        return self._foods

    def refresh_food_sources(self) -> None:
        descriptors = self.request("food_sources")
        for name, source_hash, block_count, source_size, block_size in descriptors:
            food = self._foods.get(name)
            if food is None or food.source_hash != source_hash or food.block_count != block_count:
                food = _DirectFood(self.root, name, source_hash, block_count, source_size, block_size)
                self._foods[name] = food

    def activate(self, organism: AutonomousOrganism) -> None:
        # Telemetry is sampled and one-way; live ownership changes use the
        # explicit methods below, never this hot-path sample.
        self._telemetry_steps += 1
        if self._telemetry_steps % 128 == 0:
            self.notify("state", self.worker_id, self._organism_snapshot(organism))

    @staticmethod
    def _organism_snapshot(organism: AutonomousOrganism) -> dict[str, object]:
        return {
            "id": organism.name, "parent": organism.parent_name,
            "generation": organism.body.generation, "alive": organism.alive,
            "territory": organism.territory_state.territory.path,
            "body_mass": organism.body.body_mass, "body": organism.body.size,
            "atoms": len(organism.body.atoms), "relations": len(organism.body.relations),
            "composites": len(organism.body.composites),
            "bite": organism.body.bite_limit(organism.config),
            "reserve": organism.body.reserve, "metabolic_debt": organism.activity_ledger.metabolic_debt,
            "gut": organism.gut_mass, "weakest_weight": organism.weakest_weight,
            "bytes_eaten": organism.body.consumed_total, "divisions": organism.body.children_created,
            "corpse_nutrition": organism.biomass_consumed,
        }

    def note_bite(self, organism_id: str, bite_size: int) -> None:
        """Sample only; never create per-bite request/reply traffic."""
        self._bite_events += 1
        if self._bite_events % 128 == 0:
            self.notify("observe", "ORG_BITE", organism_id, str(bite_size))

    def ingest_one_available(self, organism: AutonomousOrganism) -> None:
        self.request("ingest", organism.name)
        self.refresh_food_sources()

    def has_active_food(self) -> bool:
        return any(food.has_active_block for food in self._foods.values())

    def take_corpse_energy(self, territory: FoodTerritory, capacity: int, organism_id: str) -> float:
        return self.request("take_corpse", territory.path, capacity, organism_id)

    def add_corpse(self, corpse: Corpse, organism_id: str | None = None) -> None:
        self.request("add_corpse", corpse.territory.path, corpse.remaining_energy, organism_id)

    def is_territory_unoccupied(self, territory: FoodTerritory, *, excluding: AutonomousOrganism | None = None) -> bool:
        return self.request("territory_unoccupied", territory.path, excluding.name if excluding else None)

    def register_child(self, parent: AutonomousOrganism, child: AutonomousOrganism) -> None:
        # A newborn has no prior worker ownership.  The parent process makes
        # one deterministic initial placement; existing organisms never take
        # this route again.
        target = self.request(
            "birth", self.worker_id, parent.name, parent.territory_state.territory.path,
            child.name, child.territory_state.territory.path, child,
        )
        if int(target) == self.worker_id:
            self.newborns.append(child)

    def release_territory(self, organism_id: str, territory: FoodTerritory) -> None:
        self.request("release_territory", organism_id, territory.path)

    def update_territory(self, organism_id: str, territory: FoodTerritory) -> None:
        self.request("update_territory", organism_id, territory.path)

    def direct_metrics(self) -> tuple[int, int, int, int, int, int, tuple[int, ...]]:
        for food in self._foods.values():
            food.close()
        return (
            sum(food.consumed for food in self._foods.values()),
            sum(food.direct_operations for food in self._foods.values()),
            sum(food.duplicates for food in self._foods.values()),
            sum(food.file_opens for food in self._foods.values()),
            sum(food.stat_calls for food in self._foods.values()),
            sum(food.truncates for food in self._foods.values()),
            tuple(size for food in self._foods.values() for size in food.bite_sizes),
        )


def _worker_main(worker_id: int, root: str, requests: Any, replies: Any, control: Any, initial: list[AutonomousOrganism]) -> None:
    """One OS process retaining all assigned organism bodies locally."""
    environment = _WorkerEnvironment(worker_id, Path(root), requests, replies)
    organisms = {organism.name: organism for organism in initial}

    def handle_control() -> bool:
        """Install newborns locally or stop; neither action changes biology."""
        while True:
            try:
                command = control.get_nowait()
            except Empty:
                return False
            if command == "STOP":
                return True
            kind, child = command
            if kind == "NEWBORN":
                organisms[child.name] = child
    try:
        while True:
            if handle_control():
                return
            progressed = False
            for organism in tuple(organisms.values()):
                if handle_control():
                    return
                if not organism.alive:
                    continue
                progressed = True
                environment.activate(organism)
                organism.live_step(environment)
                environment.activate(organism)
                for child in environment.newborns:
                    organisms[child.name] = child
                environment.newborns.clear()
            if not progressed:
                sleep(0.002)
    finally:
        material_ok = True
        energy_ok = True
        snapshots = []
        for organism in organisms.values():
            try:
                organism.verify_material_conservation()
            except AssertionError:
                material_ok = False
            # Energy is organism-level state.  Its settlement checks belong
            # to the biological ledger, not to a legacy compatibility alias.
            snapshots.append(environment._organism_snapshot(organism))
        environment.request(
            "worker_summary", worker_id, material_ok, energy_ok,
            sum(organism.live_steps for organism in organisms.values()),
            sum(organism.successful_bites for organism in organisms.values()),
            sum(organism.body.consumed_total for organism in organisms.values()), snapshots,
        )
        consumed, operations, duplicates, opens, stats, truncates, bites = environment.direct_metrics()
        environment.request("direct_metrics", consumed, operations, duplicates, opens, stats, truncates, bites)


def _observer_main(events: Any, control: Any) -> None:
    """One-way telemetry sink.  It deliberately has no environment handle."""
    while True:
        try:
            if control.get_nowait() == "STOP":
                return
        except Empty:
            pass
        try:
            events.get(timeout=0.05)
        except Empty:
            continue


class AutonomousMultiprocessingRuntime:
    """Execution host only; organisms keep all mutable biological state in workers."""

    def __init__(self, root: str | Path, *, workers: int = 1, block_size: int = 64, inbox: str | Path | None = None) -> None:
        if workers <= 0:
            raise ValueError("workers must be positive")
        self.environment = SandboxRuntime(root, block_size=block_size, inbox=inbox)
        self.workers = workers
        self.context = mp.get_context("spawn")
        self.requests = self.context.Queue()
        self.replies = [self.context.Queue() for _ in range(workers)]
        self.controls = [self.context.Queue() for _ in range(workers)]
        self.observer_events = self.context.Queue()
        self.observer_control = self.context.Queue()
        self.observer_process: mp.Process | None = None
        self.processes: list[mp.Process] = []
        self.live: dict[str, tuple[bool, FoodTerritory]] = {}
        self.max_simultaneous_organisms = 0
        self.births = 0
        self.deaths = 0
        self.divisions = 0
        self.body_transfers = 0
        self.parent_food_rpcs = 0
        self.direct_food_operations = 0
        self.direct_food_consumed = 0
        self.direct_duplicates = 0
        self.file_opens = 0
        self.stat_calls = 0
        self.truncates = 0
        self.bite_sizes: list[int] = []
        self.environment_rpcs = 0
        self.total_live_steps = 0
        self.total_successful_bites = 0
        self.material_conservation = True
        self.energy_conservation = True
        self.organism_snapshots: dict[str, dict[str, object]] = {}
        self.shutdown_latency = 0.0
        self.organism_workers: dict[str, int] = {}
        self.worker_organisms: list[set[str]] = [set() for _ in range(workers)]
        self.newborn_initial_placements = 0
        self.newborn_local_placements = 0
        self.newborn_remote_placements = 0
        self.worker_live_steps = [0 for _ in range(workers)]
        self.worker_bytes_eaten = [0 for _ in range(workers)]

    @staticmethod
    def _worker_for(name: str, count: int) -> int:
        return int.from_bytes(sha256(name.encode("utf-8")).digest()[:8], "big") % count

    def start(self, organisms: Iterable[AutonomousOrganism]) -> None:
        if self.processes:
            raise RuntimeError("workers are already running")
        assignments: list[list[AutonomousOrganism]] = [[] for _ in range(self.workers)]
        initial_names: list[str] = []
        for organism in organisms:
            worker_id = self._worker_for(organism.name, self.workers)
            assignments[worker_id].append(organism)
            self.organism_workers[organism.name] = worker_id
            self.worker_organisms[worker_id].add(organism.name)
            self.body_transfers += 1  # initial placement only
            # Ownership exists before any worker can inspect/reclaim a
            # sibling territory.  This is environment state, not a lifecycle
            # decision or a per-bite organism transfer.
            self.live[organism.name] = (organism.alive, organism.territory_state.territory)
            if organism.alive:
                self.environment.mark_organism_alive(organism.name)
                initial_names.append(organism.name)
        self.max_simultaneous_organisms = sum(alive for alive, _ in self.live.values())
        try:
            for worker_id, initial in enumerate(assignments):
                process = self.context.Process(
                    target=_worker_main,
                    args=(worker_id, str(self.environment.root), self.requests, self.replies[worker_id], self.controls[worker_id], initial),
                    daemon=False,
                )
                process.start()
                self.processes.append(process)
            observer = self.context.Process(
                target=_observer_main,
                args=(self.observer_events, self.observer_control),
                daemon=False,
            )
            observer.start()
            self.observer_process = observer
        except Exception:
            # Startup is transactional at the execution boundary: a failed
            # worker or observer start leaves no earlier worker running.
            self.shutdown()
            for name in initial_names:
                marker = self.environment.organism_directory(name)
                alive_marker = marker / "ALIVE"
                if alive_marker.exists():
                    alive_marker.unlink()
                try:
                    marker.rmdir()
                except OSError:
                    pass
            self.live.clear()
            self.organism_workers.clear()
            for assigned in self.worker_organisms:
                assigned.clear()
            self.processes.clear()
            self.observer_process = None
            raise

    def _reply(self, worker_id: int, sequence: int, value: Any = None, error: Exception | None = None) -> None:
        self.replies[worker_id].put((sequence, error is None, value if error is None else f"{type(error).__name__}: {error}"))

    def _least_loaded_worker(self) -> int:
        """Deterministic newborn placement; existing bodies are never moved."""
        return min(range(self.workers), key=lambda worker_id: (len(self.worker_organisms[worker_id]), worker_id))

    def _handle(self, operation: str, payload: tuple[object, ...]) -> Any:
        environment = self.environment
        if operation == "food_sources":
            return tuple((name, food.source_hash, food.block_count, food.size, food.block_size) for name, food in sorted(environment.food_sources.items()))
        if operation == "ingest":
            environment.ingest_one_available(str(payload[0]))
            return None
        if operation == "state":
            _worker_id, record = payload
            name = str(record["id"])
            alive = bool(record["alive"])
            path = record["territory"]
            self.live[name] = (alive, FoodTerritory(tuple(path)))  # type: ignore[arg-type]
            self.organism_snapshots[name] = dict(record)
            self.max_simultaneous_organisms = max(self.max_simultaneous_organisms, sum(alive for alive, _ in self.live.values()))
            return None
        if operation == "worker_summary":
            _worker_id, material_ok, energy_ok, live_steps, bites, bytes_eaten, snapshots = payload
            self.material_conservation = self.material_conservation and bool(material_ok)
            self.energy_conservation = self.energy_conservation and bool(energy_ok)
            self.total_live_steps += int(live_steps)
            self.total_successful_bites += int(bites)
            self.worker_live_steps[int(_worker_id)] = int(live_steps)
            self.worker_bytes_eaten[int(_worker_id)] = int(bytes_eaten)
            for record in snapshots:  # type: ignore[union-attr]
                copied = dict(record)
                copied["worker"] = int(_worker_id)
                self.organism_snapshots[str(record["id"])] = copied
            return None
        if operation == "territory_unoccupied":
            path, excluding = payload
            target = FoodTerritory(tuple(path))  # type: ignore[arg-type]
            return not any(name != excluding and alive and territory.overlaps(target) for name, (alive, territory) in self.live.items())
        if operation == "add_corpse":
            path, energy, _organism_id = payload
            self.environment.add_corpse(Corpse(FoodTerritory(tuple(path)), float(energy)))  # type: ignore[arg-type]
            return None
        if operation == "take_corpse":
            path, capacity, organism_id = payload
            return environment.take_corpse_energy(FoodTerritory(tuple(path)), int(capacity), str(organism_id))  # type: ignore[arg-type]
        if operation == "birth":
            source_worker, parent, parent_path, child, path, newborn = payload
            source_worker = int(source_worker)
            target_worker = self._least_loaded_worker()
            # Queue delivery is the sole child state transfer.  If it cannot
            # be queued remotely, retaining the newborn on its birth worker
            # is a successful local placement, never a ghost child.
            if target_worker != source_worker:
                try:
                    self.controls[target_worker].put(("NEWBORN", newborn))
                except Exception:
                    target_worker = source_worker
            self.live[str(parent)] = (True, FoodTerritory(tuple(parent_path)))  # type: ignore[arg-type]
            self.live[str(child)] = (True, FoodTerritory(tuple(path)))  # type: ignore[arg-type]
            self.organism_workers[str(child)] = target_worker
            self.worker_organisms[target_worker].add(str(child))
            self.newborn_initial_placements += 1
            if target_worker == source_worker:
                self.newborn_local_placements += 1
            else:
                self.newborn_remote_placements += 1
            self.births += 1
            self.divisions += 1
            self.environment.mark_organism_alive(str(child))
            self.max_simultaneous_organisms = max(self.max_simultaneous_organisms, sum(alive for alive, _ in self.live.values()))
            return target_worker
        if operation == "release_territory":
            organism_id, path = payload
            self.live[str(organism_id)] = (False, FoodTerritory(tuple(path)))  # type: ignore[arg-type]
            worker = self.organism_workers.get(str(organism_id))
            if worker is not None:
                self.worker_organisms[worker].discard(str(organism_id))
            self.deaths += 1
            self.environment.mark_organism_dead(str(organism_id))
            return None
        if operation == "update_territory":
            organism_id, path = payload
            alive, _ = self.live[str(organism_id)]
            self.live[str(organism_id)] = (alive, FoodTerritory(tuple(path)))  # type: ignore[arg-type]
            return None
        if operation == "direct_metrics":
            consumed, operations, duplicates, opens, stats, truncates, bites = payload
            self.direct_food_consumed += int(consumed)
            self.direct_food_operations += int(operations)
            self.direct_duplicates += int(duplicates)
            self.file_opens += int(opens)
            self.stat_calls += int(stats)
            self.truncates += int(truncates)
            self.bite_sizes.extend(int(size) for size in bites)
            return None
        if operation == "observe":
            kind, organism_id, detail = payload
            environment.observer.observe(str(kind), organism_id if organism_id is None else str(organism_id), str(detail))
            self.observer_events.put((kind, organism_id, detail))
            if kind == "ORG_DEATH":
                self.deaths += 1
            return None
        raise ValueError(f"unknown worker operation: {operation}")

    def run_for(self, seconds: float) -> None:
        deadline = monotonic() + seconds
        while monotonic() < deadline:
            try:
                worker_id, sequence, operation, payload = self.requests.get(timeout=0.01)
            except Empty:
                continue
            self.environment_rpcs += 1
            try:
                value = self._handle(operation, payload)
                if sequence is not None:
                    self._reply(worker_id, sequence, value)
            except Exception as error:  # return environment errors to originating organism only
                if sequence is not None:
                    self._reply(worker_id, sequence, error=error)

    def shutdown(self) -> None:
        started = monotonic()
        for control in self.controls:
            try:
                control.put("STOP")
            except Exception:
                # Continue with bounded join/terminate cleanup even if a
                # control queue was part of the startup/runtime failure.
                pass
        deadline = monotonic() + 2.0
        while any(process.is_alive() for process in self.processes) and monotonic() < deadline:
            try:
                worker_id, sequence, operation, payload = self.requests.get(timeout=0.01)
            except Empty:
                continue
            self.environment_rpcs += 1
            try:
                value = self._handle(operation, payload)
                if sequence is not None:
                    self._reply(worker_id, sequence, value)
            except Exception as error:
                if sequence is not None:
                    self._reply(worker_id, sequence, error=error)
        for process in self.processes:
            process.join(timeout=0.1)
            if process.is_alive():
                process.terminate()
                process.join(timeout=0.5)
        if self.observer_process is not None:
            try:
                self.observer_control.put("STOP")
            except Exception:
                pass
            self.observer_process.join(timeout=0.5)
            if self.observer_process.is_alive():
                self.observer_process.terminate()
                self.observer_process.join(timeout=0.5)
        self.shutdown_latency = monotonic() - started

    def food_accounting(self) -> tuple[int, int, int, int, int]:
        """Physical FOOD accounting without inspecting worker-owned bodies."""
        sources = self.environment.food_sources
        # A raw inbox file is already physical input before an organism has
        # performed its first ingest request.  Count unregistered files here;
        # once ingest registers a source, its ``size`` replaces this term.
        # This makes ingest a transfer from inbox to FOOD, never new input.
        unregistered = sum(
            path.stat().st_size
            for path in self.environment.inbox.iterdir()
            if path.is_file() and path.name not in sources
        )
        original = sum(food.size for food in sources.values()) + unregistered
        inbox = sum(food.inbox_remaining for food in sources.values()) + unregistered
        remaining = sum(path.stat().st_size for path in self.environment.food.rglob("*.food"))
        consumed = original - inbox - remaining
        return original, consumed, remaining, inbox, self.direct_duplicates

    def workers_alive(self) -> int:
        return sum(process.is_alive() for process in self.processes)

    def metrics(self) -> ParallelMetrics:
        original, consumed, remaining, inbox_remaining, duplicates = self.food_accounting()
        missing = original - inbox_remaining - remaining - self.direct_food_consumed
        return ParallelMetrics(
            self.workers,
            self.max_simultaneous_organisms,
            self.births,
            self.deaths,
            self.divisions,
            consumed,
            duplicates,
            self.body_transfers,
            0,  # Bodies are placed once; children remain where they are born.
            self.parent_food_rpcs,
            self.direct_food_operations,
            missing,
            self.file_opens,
            self.stat_calls,
            self.truncates,
            tuple(self.bite_sizes),
            self.environment_rpcs,
            self.total_live_steps,
            self.total_successful_bites,
            self.material_conservation,
            self.energy_conservation,
            self.newborn_initial_placements,
            self.newborn_local_placements,
            self.newborn_remote_placements,
            tuple((worker_id, len(self.worker_organisms[worker_id]), self.worker_live_steps[worker_id], self.worker_bytes_eaten[worker_id]) for worker_id in range(self.workers)),
        )

    def __enter__(self) -> "AutonomousMultiprocessingRuntime":
        return self

    def __exit__(self, *_: object) -> None:
        self.shutdown()
