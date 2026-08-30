from __future__ import annotations

"""Minimal external process wrapper for the autonomous sandbox.

This module owns directories, periodic observation, and termination reporting.
It deliberately delegates every biological action to ``SandboxRuntime`` and
never inspects a snapshot to make a biological decision.
"""

from dataclasses import dataclass
import json
import os
from pathlib import Path
import statistics
import sys
from time import monotonic, process_time, sleep
from typing import Callable

from .sandbox_runtime import SandboxRuntime
from .sandbox_runtime import AutonomousOrganism
from .parallel_runtime import AutonomousMultiprocessingRuntime
from .territory import FoodTerritory


TERMINATION_REASONS = {
    "FOOD_EXHAUSTED",
    "EXTINCTION",
    "USER_STOP",
    "INVARIANT_FAILURE",
    "RUNTIME_FAILURE",
}


def _rss_bytes() -> int | None:
    """Best-effort read-only process RSS without an extra dependency."""
    if sys.platform != "win32":
        return None
    try:
        import ctypes
        from ctypes import wintypes

        class Counters(ctypes.Structure):
            _fields_ = [
                ("cb", wintypes.DWORD), ("PageFaultCount", wintypes.DWORD),
                ("PeakWorkingSetSize", ctypes.c_size_t), ("WorkingSetSize", ctypes.c_size_t),
                ("QuotaPeakPagedPoolUsage", ctypes.c_size_t), ("QuotaPagedPoolUsage", ctypes.c_size_t),
                ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t), ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
                ("PagefileUsage", ctypes.c_size_t), ("PeakPagefileUsage", ctypes.c_size_t),
            ]

        counters = Counters(); counters.cb = ctypes.sizeof(Counters)
        process = ctypes.windll.kernel32.GetCurrentProcess()
        if ctypes.windll.psapi.GetProcessMemoryInfo(process, ctypes.byref(counters), counters.cb):
            return int(counters.WorkingSetSize)
    except Exception:
        return None
    return None


def _median(values: list[float]) -> float:
    return statistics.median(values) if values else 0.0


@dataclass(frozen=True, slots=True)
class SandboxLayout:
    root: Path
    inbox: Path
    world: Path
    telemetry: Path


class PublicSandbox:
    """Filesystem-only public boundary around one autonomous world."""

    def __init__(self, root: str | Path, *, block_size: int = 64 * 1024) -> None:
        base = Path(root)
        self.layout = SandboxLayout(base, base / "inbox", base / "world", base / "telemetry")
        for directory in (self.layout.inbox, self.layout.world, self.layout.telemetry):
            directory.mkdir(parents=True, exist_ok=True)
        self.runtime = SandboxRuntime(self.layout.world, block_size=block_size, inbox=self.layout.inbox)
        self.started_at = monotonic()
        self.started_cpu = process_time()
        self.max_alive = 0
        self.peak_gut = 0
        self.food_seen = False

    @property
    def snapshot_path(self) -> Path:
        return self.layout.telemetry / "latest.json"

    def _free_territories(self) -> int:
        """Observer-only count of immediately reclaimable sibling territories."""
        count = 0
        for organism in self.runtime.organisms:
            if not organism.alive:
                continue
            path = organism.territory_state.territory.path
            if not path:
                continue
            sibling = FoodTerritory(path[:-1] + (1 - path[-1],))
            if self.runtime.is_territory_unoccupied(sibling, excluding=organism):
                count += 1
        return count

    def snapshot(self, *, termination: str | None = None, failure: str | None = None) -> dict[str, object]:
        view = self.runtime.observation_snapshot()
        organisms = list(view["organisms"])
        elapsed = max(0.0, monotonic() - self.started_at)
        cpu_seconds = max(0.0, process_time() - self.started_cpu)
        food_original = int(view["food_original"])
        food_eaten = int(view["food_eaten"])
        food_remaining = int(view["food_remaining"])
        food_inbox = int(view["food_inbox_pending"])
        missing = food_original - food_eaten - food_remaining - food_inbox
        alive = [item for item in organisms if item["alive"]]
        flows = [organism.material_flow for organism in self.runtime.organisms]
        debt = [float(item["metabolic_debt"]) for item in organisms]
        reserve = [float(item["reserve"]) for item in organisms]
        gut = [int(item["gut"]) for item in organisms]
        result = {
            "termination": termination,
            "failure": failure,
            "elapsed_seconds": elapsed,
            "cpu_seconds": cpu_seconds,
            "cpu_utilization": (cpu_seconds / elapsed) if elapsed else 0.0,
            "ram_bytes": _rss_bytes(),
            "food": {
                "original": food_original,
                "consumed": food_eaten,
                "remaining": food_remaining,
                "inbox_pending": food_inbox,
                "duplicates": int(view["duplicates"]),
                "missing": missing,
            },
            "population": {
                "alive": int(view["alive"]), "born": len(organisms), "dead": int(view["dead"]),
                "divisions": sum(int(item["divisions"]) for item in organisms),
                "max_generation": int(view["generations"]), "max_alive": self.max_alive,
            },
            "body": {"min": int(view["body_min"]), "median": view["body_median"], "max": int(view["body_max"])},
            "energy": {
                "reserve_min": min(reserve, default=0.0), "reserve_median": _median(reserve), "reserve_max": max(reserve, default=0.0),
                "metabolic_debt": sum(debt), "gut_backlog": sum(gut), "energy_spent": sum(item.energy_spent for item in (organism.activity_ledger for organism in self.runtime.organisms)),
            },
            "world": {
                "occupied_territories": len(alive), "free_territories": self._free_territories(),
                "corpses": int(view["corpses"]), "reclaims": int(view["territory_reclaims"]),
            },
            "performance": {"mib_per_second": (food_eaten / (1024 * 1024)) / elapsed if elapsed else 0.0},
            "mass": {
                "input": sum(flow.input_mass for flow in flows), "assimilated": sum(flow.assimilated_mass for flow in flows),
                "expelled": sum(flow.expelled_mass for flow in flows), "gut_remaining": sum(organism.gut_mass for organism in self.runtime.organisms),
                "external_expelled": sum(flow.external_expelled_mass for flow in flows),
                "resorption_expelled": sum(flow.resorption_expelled_mass for flow in flows),
                "external_gut": sum(flow.gut_mass_by_origin(organism.gut_queue, "external") for flow, organism in zip(flows, self.runtime.organisms)),
                "resorption_gut": sum(flow.gut_mass_by_origin(organism.gut_queue, "resorption") for flow, organism in zip(flows, self.runtime.organisms)),
                "peak_gut": self.peak_gut,
                "structural_mass": sum(organism.body.body_mass for organism in self.runtime.organisms),
                "resorbed_mass": sum(flow.resorbed_mass for flow in flows),
            },
            "organisms": organisms,
        }
        return result

    def write_snapshot(self, *, termination: str | None = None, failure: str | None = None) -> dict[str, object]:
        snapshot = self.snapshot(termination=termination, failure=failure)
        temporary = self.snapshot_path.with_suffix(".tmp")
        temporary.write_text(json.dumps(snapshot, sort_keys=True, indent=2), encoding="utf-8")
        os.replace(temporary, self.snapshot_path)
        return snapshot

    def step(self) -> None:
        self.runtime.autonomous_step()
        self.max_alive = max(self.max_alive, sum(organism.alive for organism in self.runtime.organisms))
        self.peak_gut = max(self.peak_gut, sum(organism.gut_mass for organism in self.runtime.organisms))
        if self.runtime.food_sources:
            self.food_seen = True

    def natural_termination(self) -> str | None:
        snapshot = self.snapshot()
        food = snapshot["food"]
        if self.food_seen and int(food["inbox_pending"]) == 0 and int(food["remaining"]) == 0:
            return "FOOD_EXHAUSTED"
        if self.food_seen and int(snapshot["population"]["alive"]) == 0:
            return "EXTINCTION"
        if int(food["duplicates"]) or int(food["missing"]):
            return "INVARIANT_FAILURE"
        return None

    def run(
        self,
        *,
        snapshot_seconds: float = 0.5,
        max_seconds: float | None = None,
        stop: Callable[[], bool] | None = None,
        observer: Callable[[dict[str, object]], None] | None = None,
    ) -> tuple[str, dict[str, object]]:
        """Run only the environment heartbeat until a visible terminal reason."""
        last_snapshot = 0.0
        termination = "USER_STOP"
        failure: str | None = None
        try:
            while True:
                if stop is not None and stop():
                    termination = "USER_STOP"; break
                if max_seconds is not None and monotonic() - self.started_at >= max_seconds:
                    termination = "USER_STOP"; break
                self.step()
                natural = self.natural_termination()
                if natural is not None:
                    termination = natural; break
                now = monotonic()
                if now - last_snapshot >= snapshot_seconds:
                    view = self.write_snapshot()
                    if observer is not None:
                        observer(view)
                    last_snapshot = now
                sleep(0.001)
        except KeyboardInterrupt:
            termination = "USER_STOP"
        except AssertionError as error:
            termination = "INVARIANT_FAILURE"
            failure = str(error) or error.__class__.__name__
        except Exception as error:
            termination = "RUNTIME_FAILURE"
            failure = f"{error.__class__.__name__}: {error}"
        if termination != "RUNTIME_FAILURE":
            for organism in self.runtime.organisms:
                try:
                    organism.verify_material_conservation()
                except AssertionError as error:
                    termination = "INVARIANT_FAILURE"
                    failure = f"{organism.name}: {str(error) or error.__class__.__name__}"
                    break
            if termination != "INVARIANT_FAILURE":
                try:
                    self.runtime.verify_world_material_conservation()
                except AssertionError as error:
                    termination = "INVARIANT_FAILURE"
                    failure = str(error) or error.__class__.__name__
        final = self.write_snapshot(termination=termination, failure=failure)
        self.runtime.sync_organism_markers()
        return termination, final


class PublicMultiprocessingSandbox:
    """Public observer wrapper for worker-local autonomous organisms.

    The parent only services environment RPC and writes eventual snapshots;
    it never invokes an organism's lifecycle method.
    """

    def __init__(self, root: str | Path, *, workers: int = 1, block_size: int = 64 * 1024) -> None:
        base = Path(root)
        self.layout = SandboxLayout(base, base / "inbox", base / "world", base / "telemetry")
        for directory in (self.layout.inbox, self.layout.world, self.layout.telemetry):
            directory.mkdir(parents=True, exist_ok=True)
        self.runtime = AutonomousMultiprocessingRuntime(
            self.layout.world, workers=workers, block_size=block_size, inbox=self.layout.inbox,
        )
        self.started_at = monotonic()
        self.started_cpu = process_time()
        self.food_seen = False
        self.initial_population = 1
        self.max_alive = 1

    @property
    def snapshot_path(self) -> Path:
        return self.layout.telemetry / "latest.json"

    def snapshot(self, *, termination: str | None = None, failure: str | None = None) -> dict[str, object]:
        original, consumed, remaining, inbox, duplicates = self.runtime.food_accounting()
        elapsed = max(0.0, monotonic() - self.started_at)
        cpu_seconds = max(0.0, process_time() - self.started_cpu)
        records = list(self.runtime.organism_snapshots.values())
        alive_count = sum(alive for alive, _territory in self.runtime.live.values())
        self.max_alive = max(self.max_alive, self.runtime.max_simultaneous_organisms, alive_count)
        bodies = [int(record["body_mass"]) for record in records]
        bites = [int(record["bite"]) for record in records]
        reserve = [float(record["reserve"]) for record in records]
        debt = [float(record["metabolic_debt"]) for record in records]
        gut = [int(record["gut"]) for record in records]
        missing = original - consumed - remaining - inbox
        return {
            "termination": termination, "failure": failure,
            "elapsed_seconds": elapsed, "cpu_seconds": cpu_seconds,
            "cpu_utilization": cpu_seconds / elapsed if elapsed else 0.0,
            "ram_bytes": _rss_bytes(),
            "runtime": {"kind": "multiprocessing", "workers": self.runtime.workers,
                        "environment_rpcs": self.runtime.environment_rpcs,
                        "parent_food_rpcs": self.runtime.parent_food_rpcs,
                        "worker_migrations": 0, "live_steps": self.runtime.total_live_steps,
                        "successful_bites": self.runtime.total_successful_bites,
                        "shutdown_latency_seconds": self.runtime.shutdown_latency,
                        "newborn_initial_placements": self.runtime.newborn_initial_placements,
                        "newborn_local_placements": self.runtime.newborn_local_placements,
                        "newborn_remote_placements": self.runtime.newborn_remote_placements,
                        "worker_distribution": [
                            {"worker": worker_id, "living": len(self.runtime.worker_organisms[worker_id]),
                             "live_steps": self.runtime.worker_live_steps[worker_id],
                             "bytes_eaten": self.runtime.worker_bytes_eaten[worker_id]}
                            for worker_id in range(self.runtime.workers)
                        ]},
            "food": {"original": original, "consumed": consumed, "remaining": remaining,
                     "inbox_pending": inbox, "duplicates": duplicates, "missing": missing},
            "population": {"alive": alive_count, "born": self.initial_population + self.runtime.births,
                           "dead": self.runtime.deaths, "divisions": self.runtime.divisions,
                           "max_generation": max((int(record["generation"]) for record in records), default=0),
                           "max_alive": self.max_alive},
            "body": {"min": min(bodies, default=0), "median": _median(bodies), "max": max(bodies, default=0)},
            "bite": {"min": min(bites, default=0), "median": _median(bites), "max": max(bites, default=0)},
            "energy": {"reserve_min": min(reserve, default=0.0), "reserve_median": _median(reserve),
                       "reserve_max": max(reserve, default=0.0), "metabolic_debt": sum(debt),
                       "gut_backlog": sum(gut), "energy_spent": 0.0},
            "world": {"occupied_territories": alive_count, "free_territories": 0,
                      "corpses": len(self.runtime.environment.corpses),
                      "reclaims": sum(event.kind == "TERRITORY_RECLAIM" for event in self.runtime.environment.observer.events)},
            "performance": {"mib_per_second": (consumed / (1024 * 1024)) / elapsed if elapsed else 0.0},
            "mass": {"input": 0, "assimilated": 0, "expelled": 0, "gut_remaining": sum(gut),
                     "external_expelled": 0, "resorption_expelled": 0, "external_gut": 0,
                     "resorption_gut": 0, "peak_gut": 0, "structural_mass": sum(bodies), "resorbed_mass": 0},
            "accounting": {"mass_conservation": self.runtime.material_conservation,
                           "energy_conservation": self.runtime.energy_conservation},
            "organisms": records,
        }

    def write_snapshot(self, *, termination: str | None = None, failure: str | None = None) -> dict[str, object]:
        snapshot = self.snapshot(termination=termination, failure=failure)
        temporary = self.snapshot_path.with_suffix(".tmp")
        temporary.write_text(json.dumps(snapshot, sort_keys=True, indent=2), encoding="utf-8")
        os.replace(temporary, self.snapshot_path)
        return snapshot

    def _natural_termination(self) -> str | None:
        original, consumed, remaining, inbox, duplicates = self.runtime.food_accounting()
        if self.runtime.environment.food_sources:
            self.food_seen = True
        if self.food_seen and inbox == 0 and remaining == 0:
            return "FOOD_EXHAUSTED"
        if self.food_seen and not any(alive for alive, _territory in self.runtime.live.values()):
            return "EXTINCTION"
        if duplicates or original - consumed - remaining - inbox:
            return "INVARIANT_FAILURE"
        # A worker or observer is expected to live until this wrapper begins
        # shutdown.  Any earlier exit is a runtime failure, including an
        # unexpected clean exit that would otherwise hide lost execution.
        if any(process.exitcode is not None for process in self.runtime.processes):
            return "RUNTIME_FAILURE"
        observer = self.runtime.observer_process
        if observer is not None and observer.exitcode is not None:
            return "RUNTIME_FAILURE"
        return None

    def _runtime_failure_detail(self) -> str | None:
        """Return an observer-only explanation for an unexpected process exit."""
        for worker_id, process in enumerate(self.runtime.processes):
            if process.exitcode is not None:
                return f"worker {worker_id} exited unexpectedly with code {process.exitcode}"
        observer = self.runtime.observer_process
        if observer is not None and observer.exitcode is not None:
            return f"observer exited unexpectedly with code {observer.exitcode}"
        return None

    def run(self, *, snapshot_seconds: float = 0.5, max_seconds: float | None = None,
            stop: Callable[[], bool] | None = None,
            observer: Callable[[dict[str, object]], None] | None = None) -> tuple[str, dict[str, object]]:
        last_snapshot = 0.0
        termination = "USER_STOP"
        failure: str | None = None
        try:
            self.runtime.start((AutonomousOrganism(),))
            while True:
                elapsed = monotonic() - self.started_at
                if stop is not None and stop():
                    break
                if max_seconds is not None and elapsed >= max_seconds:
                    break
                # This only services environment requests for a bounded slice;
                # no parent-side organism loop exists here.
                self.runtime.run_for(min(0.05, max_seconds - elapsed) if max_seconds is not None else 0.05)
                natural = self._natural_termination()
                if natural is not None:
                    termination = natural
                    if termination == "RUNTIME_FAILURE":
                        failure = self._runtime_failure_detail()
                    break
                now = monotonic()
                if now - last_snapshot >= snapshot_seconds:
                    view = self.write_snapshot()
                    if observer is not None:
                        observer(view)
                    last_snapshot = now
        except KeyboardInterrupt:
            pass
        except Exception as error:
            termination = "RUNTIME_FAILURE"
            failure = f"{type(error).__name__}: {error}"
        finally:
            self.runtime.shutdown()
        metrics = self.runtime.metrics()
        if termination != "RUNTIME_FAILURE" and not metrics.mass_conservation:
            termination, failure = "INVARIANT_FAILURE", "worker material conservation failed"
        if termination != "RUNTIME_FAILURE" and (metrics.duplicates or metrics.missing):
            termination, failure = "INVARIANT_FAILURE", "physical FOOD accounting failed"
        final = self.write_snapshot(termination=termination, failure=failure)
        return termination, final


def read_last_snapshot(root: str | Path) -> dict[str, object] | None:
    path = Path(root) / "telemetry" / "latest.json"
    if not path.is_file():
        return None
    return json.loads(path.read_text(encoding="utf-8"))
