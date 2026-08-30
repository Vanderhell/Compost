from __future__ import annotations

"""Physical, content-neutral food sandbox for binary FILE experiments.

The sandbox copies a source into an experiment-owned directory, partitions the
copy into bounded files, and deletes consumed ranges from those files.  It is
not a new lifecycle: digestion and the post-digest lifecycle tail are the same
ones used by :mod:`mathematical_organism.food`.

Each live fragment represents one half-open original interval [start, end).
For every completed claim the invariant is
``original_bytes == consumed_bytes + sum(live fragment lengths)``.  A bite is
read only from a live fragment, digested, then removed from the sandbox; no raw
byte sequence is retained in an organism or trace.
"""

from dataclasses import dataclass
import hashlib
from pathlib import Path
import shutil
from time import perf_counter
from typing import BinaryIO

from .food import FoodNavigationState, _power_of_two_at_least
from .food_preparation import DEFAULT_PARCEL_SIZE
from .lifecycle import LifecycleEvent, MathematicalLifeOrganism, MathematicalLifePopulation, OrganismStatus


COPY_CHUNK = 64 * 1024


def stream_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while block := handle.read(COPY_CHUNK):
            digest.update(block)
    return digest.hexdigest()


@dataclass(frozen=True, slots=True)
class SandboxFragment:
    parcel: int
    start: int
    end: int
    path: Path


@dataclass(frozen=True, slots=True)
class SandboxClaim:
    parcel: int
    offset: int
    length: int
    fragment: SandboxFragment
    skipped_regions: int


@dataclass(frozen=True, slots=True)
class SandboxTrace:
    cycle: int
    organism_id: int
    parcel_id: int
    offset: int
    length: int
    remaining_file_food: int
    organism_count: int
    skipped_regions: int


@dataclass(slots=True)
class SandboxMetrics:
    parcels_created: int = 0
    parcels_deleted: int = 0
    claims: int = 0
    candidates_visited: int = 0
    regions_skipped: int = 0
    bytes_read: int = 0
    bytes_consumed: int = 0
    duplicate_consumption: int = 0
    fragmentation_peak: int = 0
    peak_working_memory: int = 0


class PhysicalFoodSandbox:
    """Experiment-owned physical food fragments, without a byte occupancy map.

    Claim state is exactly the sorted fragment intervals.  This is exact for
    partial bites and uses O(number of remaining fragments) metadata, trading
    compactness for filesystem operations.  It deliberately never alters the
    source file.
    """

    def __init__(self, source: str | Path, root: str | Path, *, parcel_size: int = DEFAULT_PARCEL_SIZE, context_overlap: int = 2) -> None:
        self.source = Path(source).resolve()
        self.root = Path(root).resolve()
        if not self.source.is_file():
            raise ValueError(f"not a regular source file: {self.source}")
        if parcel_size <= 0 or context_overlap < 0:
            raise ValueError("parcel_size must be positive and context_overlap non-negative")
        self.parcel_size = parcel_size
        self.context_overlap = context_overlap
        self.size = self.source.stat().st_size
        self.source_hash = stream_sha256(self.source)
        self.source_copy = self.root / "source" / self.source.name
        self.food_dir = self.root / "food" / self.source.name
        self.trace_dir = self.root / "traces"
        self.result_dir = self.root / "results"
        self.fragments: dict[int, list[SandboxFragment]] = {}
        self.pending: set[tuple[int, int]] = set()
        self.metrics = SandboxMetrics()
        self._prepare()

    @property
    def parcel_count(self) -> int:
        return (self.size + self.parcel_size - 1) // self.parcel_size

    @property
    def remaining(self) -> int:
        return self.size - self.metrics.bytes_consumed

    def _prepare(self) -> None:
        for directory in (self.root / "source", self.food_dir, self.trace_dir, self.result_dir):
            directory.mkdir(parents=True, exist_ok=True)
        if self.source_copy.exists() and stream_sha256(self.source_copy) != self.source_hash:
            raise ValueError("existing sandbox source copy does not match source hash")
        if not self.source_copy.exists():
            with self.source.open("rb") as source_handle, self.source_copy.open("wb") as target:
                shutil.copyfileobj(source_handle, target, COPY_CHUNK)
        with self.source_copy.open("rb") as source_handle:
            for parcel in range(self.parcel_count):
                start = parcel * self.parcel_size
                end = min(self.size, start + self.parcel_size)
                path = self.food_dir / f"parcel_{parcel:06d}.food"
                payload = source_handle.read(end - start)
                if len(payload) != end - start:
                    raise IOError("short read while preparing physical parcel")
                path.write_bytes(payload)
                self.fragments[parcel] = [SandboxFragment(parcel, start, end, path)]
                self.metrics.parcels_created += 1
        self._check_accounting()

    def _check_accounting(self) -> None:
        remaining = sum(fragment.end - fragment.start for parts in self.fragments.values() for fragment in parts)
        if self.size != self.metrics.bytes_consumed + remaining:
            raise AssertionError("physical food accounting violation")
        self.metrics.fragmentation_peak = max(self.metrics.fragmentation_peak, sum(len(parts) for parts in self.fragments.values()))

    def claim(self, parcel: int, capacity: int, *, skipped_regions: int) -> SandboxClaim | None:
        self.metrics.candidates_visited += 1
        if capacity <= 0 or parcel not in self.fragments or not self.fragments[parcel]:
            self.metrics.regions_skipped += 1
            return None
        fragment = self.fragments[parcel][0]
        length = min(capacity, fragment.end - fragment.start)
        key = (fragment.start, fragment.start + length)
        if key in self.pending:
            self.metrics.duplicate_consumption += 1
            raise AssertionError("duplicate pending food claim")
        self.pending.add(key)
        self.metrics.claims += 1
        return SandboxClaim(parcel, fragment.start, length, fragment, skipped_regions)

    def read(self, claim: SandboxClaim) -> tuple[tuple[int, ...], int]:
        """Read only one transient context|nutrition|context window from live food."""
        fragment = claim.fragment
        if not fragment.path.is_file():
            raise AssertionError("claimed fragment disappeared before digestion")
        local_start = claim.offset - fragment.start
        left = min(self.context_overlap, claim.offset)
        right = min(self.context_overlap, self.size - (claim.offset + claim.length))
        with fragment.path.open("rb") as handle:
            handle.seek(local_start)
            nutrition = handle.read(claim.length)
        if len(nutrition) != claim.length:
            raise IOError("short physical food read")
        # Read-only context comes from the sandbox's unchanged source copy.
        # It may cross a food-fragment boundary but is never nutritional food.
        with self.source_copy.open("rb") as handle:
            handle.seek(claim.offset - left)
            context = handle.read(left + right + claim.length)
        if len(context) != left + right + claim.length:
            raise IOError("short sandbox context read")
        bite = tuple(nutrition)
        self.metrics.bytes_read += len(nutrition) + len(context)
        self.metrics.peak_working_memory = max(self.metrics.peak_working_memory, len(nutrition) + len(context))
        del nutrition, context
        return bite, left + right

    def consume(self, claim: SandboxClaim) -> None:
        """Remove the digested original interval from its physical fragment file."""
        key = (claim.offset, claim.offset + claim.length)
        if key not in self.pending:
            self.metrics.duplicate_consumption += 1
            raise AssertionError("food consumed without its unique claim")
        self.pending.remove(key)
        fragment = claim.fragment
        parts = self.fragments.get(claim.parcel, [])
        if fragment not in parts:
            raise AssertionError("claimed fragment is not live")
        if not (fragment.start <= claim.offset and claim.offset + claim.length <= fragment.end):
            raise AssertionError("claim outside live physical fragment")
        local_start = claim.offset - fragment.start
        local_end = local_start + claim.length
        with fragment.path.open("rb") as handle:
            before = handle.read(local_start)
            eaten = handle.read(claim.length)
            after = handle.read()
        if len(eaten) != claim.length:
            raise IOError("short physical food consume")
        replacements: list[SandboxFragment] = []
        for start, payload in ((fragment.start, before), (claim.offset + claim.length, after)):
            if not payload:
                continue
            end = start + len(payload)
            replacement_path = self.food_dir / f"parcel_{claim.parcel:06d}.fragment_{start:012d}_{end:012d}.food"
            replacement_path.write_bytes(payload)
            replacements.append(SandboxFragment(claim.parcel, start, end, replacement_path))
        fragment.path.unlink()
        parts.remove(fragment)
        parts.extend(replacements)
        parts.sort(key=lambda item: item.start)
        if not parts:
            self.fragments.pop(claim.parcel, None)
            self.metrics.parcels_deleted += 1
        self.metrics.bytes_consumed += claim.length
        self._check_accounting()

    def assert_invariants(self) -> None:
        self._check_accounting()
        if self.pending:
            raise AssertionError("unfinished physical food claims")
        if self.metrics.duplicate_consumption:
            raise AssertionError("duplicate food consumption")
        if stream_sha256(self.source) != self.source_hash:
            raise AssertionError("source file was modified")
        if stream_sha256(self.source_copy) != self.source_hash:
            raise AssertionError("sandbox source copy changed")
        for parts in self.fragments.values():
            for fragment in parts:
                if not fragment.path.is_file() or fragment.path.stat().st_size != fragment.end - fragment.start:
                    raise AssertionError("fragment metadata differs from physical food")


class SandboxFeedingHarness:
    """Physical-food counterpart of the existing implicit feeding harness."""

    def __init__(self, source: str | Path, root: str | Path, *, seed: int = 0xF00D, parcel_size: int = 64, context_overlap: int = 2) -> None:
        self.food = PhysicalFoodSandbox(source, root, parcel_size=parcel_size, context_overlap=context_overlap)
        self.population = MathematicalLifePopulation(())
        self.population.result.available_nutrition_total = float(self.food.size)
        self.seed = seed
        self.node_count = min(65536, _power_of_two_at_least(self.food.parcel_count))
        self.navigation: dict[int, FoodNavigationState] = {}
        self.trace: list[SandboxTrace] = []
        self.navigation_time = 0.0
        self.digest_time = 0.0
        self._ensure_navigation(self.population.organisms[0])

    def _ensure_navigation(self, organism: MathematicalLifeOrganism) -> FoodNavigationState:
        return self.navigation.setdefault(organism.id, FoodNavigationState(organism.id, self.seed, self.node_count, self.food.parcel_count))

    def _claim_next(self, organism: MathematicalLifeOrganism) -> SandboxClaim | None:
        navigator = self._ensure_navigation(organism)
        skipped = 0
        attempts = max(1, self.node_count * 2)
        for _ in range(attempts):
            parcel = navigator.next_parcel()
            if parcel is None:
                skipped += 1
                continue
            claim = self.food.claim(parcel, organism.bite_limit(self.population.config), skipped_regions=skipped)
            if claim is not None:
                return claim
            skipped += 1
        return None

    def _post_digest_lifecycle(self, organism: MathematicalLifeOrganism) -> None:
        population = self.population
        population._consolidate(organism)
        population._maintain_and_resorb(organism)
        organism.age_in_cycles += 1
        if organism.status is OrganismStatus.ALIVE:
            population._divide_if_profitable(organism)
        if organism.size == 0 and organism.status is OrganismStatus.ALIVE:
            organism.status = OrganismStatus.DEAD
            organism.death_age = organism.age_in_cycles
            population.result.events.append(LifecycleEvent(organism.id, 0, "DEATH", "no living structures"))
        if organism.total_strength > organism.peak_strength:
            organism.peak_strength = organism.total_strength
            organism.peak_age = organism.age_in_cycles

    def step(self) -> None:
        for organism_id in sorted(tuple(self.population.organisms)):
            organism = self.population.organisms[organism_id]
            if organism.status is OrganismStatus.DEAD:
                continue
            started = perf_counter()
            claim = self._claim_next(organism)
            self.navigation_time += perf_counter() - started
            if claim is not None:
                bite, _context = self.food.read(claim)
                started = perf_counter()
                self.population._digest(organism, bite, tuple(1.0 for _ in bite))
                self.digest_time += perf_counter() - started
                del bite
                self.food.consume(claim)
                self.trace.append(SandboxTrace(self.population.result.cycles + 1, organism.id, claim.parcel, claim.offset, claim.length, self.food.remaining, len(self.population.alive()), claim.skipped_regions))
            self._post_digest_lifecycle(organism)
        for organism in self.population.organisms.values():
            self._ensure_navigation(organism)
        self.population.result.cycles += 1
        self.population.max_population = max(self.population.max_population, len(self.population.alive()))

    def run(self, *, max_cycles: int | None = None, progress: object | None = None) -> None:
        limit = max_cycles if max_cycles is not None else max(1, self.food.size * 2)
        while self.food.remaining and self.population.alive() and self.population.result.cycles < limit:
            self.step()
            if callable(progress):
                progress(self)
        self.food.assert_invariants()

    def assert_invariants(self) -> None:
        self.food.assert_invariants()
        if self.food.remaining:
            raise AssertionError("food remains")
        if self.food.metrics.bytes_consumed != self.food.size:
            raise AssertionError("missing food bytes")
        if self.population.result.consumed_nutrition_total > self.food.size + 1e-12:
            raise AssertionError("lifecycle nutrition exceeds physical food")
        for organism in self.population.organisms.values():
            if hasattr(organism, "payload") or hasattr(organism, "bite"):
                raise AssertionError("raw payload leaked into organism state")
