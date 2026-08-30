from __future__ import annotations

"""Administrative, read-only-observer shell around the autonomous sandbox.

This module deliberately owns no biological policy.  It can start and stop an
existing :class:`SandboxRuntime`, add raw files to its inbox, and remove an
entire experiment only while it is stopped.
"""

from dataclasses import dataclass
import hashlib
from pathlib import Path
import random
import shutil
import threading
from time import monotonic, sleep

from .sandbox_runtime import AutonomousOrganism, SandboxRuntime


def _copy_stream(source: Path, target: Path, chunk_size: int = 64 * 1024) -> None:
    with source.open("rb") as reader, target.open("xb") as writer:
        while chunk := reader.read(chunk_size):
            writer.write(chunk)


def _unique_target(directory: Path, name: str) -> Path:
    candidate = directory / name
    suffix = 1
    while candidate.exists():
        candidate = directory / f"{Path(name).stem}_{suffix}{Path(name).suffix}"
        suffix += 1
    return candidate


@dataclass(frozen=True, slots=True)
class GeneratedFood:
    path: Path
    size: int
    seed: int


class CompostController:
    """Experiment administration; organisms retain the autonomous life loop."""

    def __init__(self, root: str | Path = "sandbox", *, block_size: int = 4096) -> None:
        self.runtime = SandboxRuntime(root, block_size=block_size)
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._started_at: float | None = None

    @property
    def root(self) -> Path:
        return self.runtime.root

    @property
    def running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def add_organisms(self, count: int) -> list[AutonomousOrganism]:
        """Administrative bootstrap only; no learned state is seeded."""
        if count <= 0:
            raise ValueError("organism count must be positive")
        if self.running:
            raise RuntimeError("stop ecosystem before adding bootstrap organisms")
        created: list[AutonomousOrganism] = []
        root = self.runtime.bootstrap()
        if not self.runtime.organisms[:-1]:
            created.append(root)
        while len(created) < count:
            # The shallowest live branch produces a deterministic, disjoint
            # bootstrap partition without giving any organism learned matter.
            parent = min(
                (item for item in self.runtime.organisms if item.alive),
                key=lambda item: (len(item.territory_state.territory.path), item.name),
            )
            child = parent.spawn_child()
            self.runtime.register_child(parent, child)
            created.append(child)
        self.runtime.sync_organism_markers()
        return created

    def add_real_path(self, source: str | Path) -> list[Path]:
        if self.running:
            # Insertion itself is safe while active: it is only an external
            # environmental change, discovered later by autonomous organisms.
            pass
        source_path = Path(source)
        if not source_path.exists():
            raise FileNotFoundError(source_path)
        files = [source_path] if source_path.is_file() else sorted(path for path in source_path.rglob("*") if path.is_file())
        copied: list[Path] = []
        for file in files:
            target = _unique_target(self.runtime.inbox, file.name)
            _copy_stream(file, target)
            copied.append(target)
        return copied

    def generate_food(self, size: int, *, seed: int = 12345, name: str | None = None) -> GeneratedFood:
        if size < 0:
            raise ValueError("food size must be non-negative")
        target = _unique_target(self.runtime.inbox, name or f"generated_{size}_{seed}.bin")
        generator = random.Random(seed)
        remaining = size
        with target.open("xb") as handle:
            while remaining:
                count = min(64 * 1024, remaining)
                handle.write(generator.randbytes(count))
                remaining -= count
        return GeneratedFood(target, size, seed)

    def start(self) -> None:
        if self.running:
            return
        self.runtime.bootstrap()
        self.runtime.sync_organism_markers()
        self._stop.clear()
        self._started_at = monotonic()

        def loop() -> None:
            while not self._stop.is_set():
                self.runtime.autonomous_step()
                sleep(0.001)

        self._thread = threading.Thread(target=loop, name="compost-autonomous-runtime", daemon=False)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join()
            if self._thread.is_alive():
                raise RuntimeError("sandbox runtime did not stop")
        self.runtime.sync_organism_markers()

    def snapshot(self) -> dict[str, object]:
        view = self.runtime.observation_snapshot()
        view["running"] = self.running
        view["elapsed"] = max(0.0, monotonic() - self._started_at) if self._started_at is not None else 0.0
        view["food_missing"] = int(view["food_original"]) - int(view["food_eaten"]) - int(view["food_remaining"]) - int(view["food_inbox_pending"])
        return view

    def food_by_source(self) -> list[dict[str, object]]:
        return [
            {"name": name, "size": food.size, "consumed": food.metrics.bytes_consumed, "remaining": food.remaining}
            for name, food in sorted(self.runtime.food_sources.items())
        ]

    def family_tree(self, depth: int = 4) -> list[tuple[int, str]]:
        children: dict[str | None, list[AutonomousOrganism]] = {}
        for organism in self.runtime.organisms:
            children.setdefault(organism.parent_name, []).append(organism)
        output: list[tuple[int, str]] = []
        def visit(parent: str | None, level: int) -> None:
            if level > depth:
                return
            for child in sorted(children.get(parent, []), key=lambda item: item.name):
                output.append((level, child.name))
                visit(child.name, level + 1)
        visit(None, 0)
        return output

    def delete_organisms(self, mode: str, organism_id: str | None = None) -> int:
        if self.running:
            raise RuntimeError("stop ecosystem before deleting organisms")
        if mode == "dead":
            selected = [item for item in self.runtime.organisms if not item.alive]
        elif mode == "one":
            selected = [item for item in self.runtime.organisms if item.name == organism_id]
        elif mode == "all":
            selected = list(self.runtime.organisms)
        else:
            raise ValueError("unknown organism delete mode")
        for organism in selected:
            marker = self.runtime.organism_directory(organism.name)
            if marker.exists():
                shutil.rmtree(marker)
            self.runtime.organisms.remove(organism)
        return len(selected)

    def delete_food(self, mode: str) -> None:
        if self.running:
            raise RuntimeError("stop ecosystem before deleting food")
        if mode in {"inbox", "all"}:
            for path in self.runtime.inbox.iterdir():
                if path.is_file():
                    path.unlink()
        if mode in {"prepared", "all"}:
            if self.runtime.food.exists():
                shutil.rmtree(self.runtime.food)
            self.runtime.food.mkdir(parents=True, exist_ok=True)
            self.runtime.food_sources.clear()
        if mode not in {"inbox", "prepared", "all"}:
            raise ValueError("unknown food delete mode")

    def clear(self, mode: str) -> None:
        if self.running:
            raise RuntimeError("stop ecosystem before clearing sandbox")
        if mode == "food":
            self.delete_food("all")
        elif mode == "dead":
            self.delete_organisms("dead")
            for path in self.runtime.corpses_dir.glob("*"):
                if path.is_file():
                    path.unlink()
            self.runtime.corpses.clear()
        elif mode == "organisms":
            self.delete_organisms("all")
            self.runtime.corpses.clear()
        elif mode == "traces":
            for directory in (self.runtime.traces, self.runtime.results):
                if directory.exists():
                    shutil.rmtree(directory)
                directory.mkdir(parents=True, exist_ok=True)
        elif mode == "everything":
            for directory in (self.runtime.inbox, self.runtime.food, self.runtime.organisms_dir, self.runtime.corpses_dir, self.runtime.traces, self.runtime.results):
                if directory.exists():
                    shutil.rmtree(directory)
                directory.mkdir(parents=True, exist_ok=True)
            self.runtime.food_sources.clear()
            self.runtime.organisms.clear()
            self.runtime.corpses.clear()
        else:
            raise ValueError("unknown clear mode")
