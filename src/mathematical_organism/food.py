from __future__ import annotations

"""Reference FILE -> food-space adapter; it does not alter lifecycle rules.

The implicit-network adapter is a direct Python reference of its bijective
mapping layer.  It stores no graph or adjacency table.  Food ownership is a
separate bitset because exact once-only consumption is a property of the file,
not of the implicit topology.
"""

from dataclasses import dataclass, field
from pathlib import Path
from time import perf_counter
from typing import BinaryIO

from .food_preparation import DEFAULT_PARCEL_SIZE, PreparedFood
from .lifecycle import LifecycleEvent, MathematicalLifeOrganism, MathematicalLifePopulation, OrganismStatus


MASK64 = (1 << 64) - 1


def _mix64(value: int) -> int:
    value &= MASK64
    value ^= value >> 30
    value = (value * 0xBF58476D1CE4E5B9) & MASK64
    value ^= value >> 27
    value = (value * 0x94D049BB133111EB) & MASK64
    return (value ^ (value >> 31)) & MASK64


def _implicit_map(value: int, count: int, state: int) -> int:
    """Reference adapter of implicit_net.c::in_map for power-of-two ``count``."""
    if count < 4 or count > 65536 or count & (count - 1) or not 0 <= value < count:
        raise ValueError("implicit network requires a 4..65536 power-of-two domain")
    width = count.bit_length() - 1
    mixed = _mix64(state)
    result = 0
    for bit in range(width):
        destination = (bit + ((mixed >> 4) & 15)) % width
        if (mixed >> 16) & 1:
            destination = width - 1 - destination
        if (value >> bit) & 1:
            result |= 1 << destination
    return (result ^ mixed) & (count - 1)


def _power_of_two_at_least(value: int) -> int:
    return 1 << max(2, (max(1, value) - 1).bit_length())


@dataclass(slots=True)
class FoodMetrics:
    candidates_visited: int = 0
    regions_skipped: int = 0
    bytes_read: int = 0
    bytes_consumed: int = 0
    duplicate_consumption: int = 0
    peak_working_memory: int = 0


@dataclass(frozen=True, slots=True)
class FoodClaim:
    parcel: int
    offset: int
    length: int
    skipped_regions: int


@dataclass(frozen=True, slots=True)
class BiteTrace:
    organism_id: int
    generation: int
    bite_index: int
    offset: int
    length: int
    navigation_state: int
    claimed: bool
    skipped_regions: int
    digest_assimilated: float
    digest_waste: float


@dataclass(slots=True)
class FoodNavigationState:
    organism_id: int
    seed: int
    node_count: int
    parcel_count: int
    bite_index: int = 0
    round: int = 0
    index_in_round: int = 0

    @property
    def local_state(self) -> int:
        return _mix64(self.seed ^ (self.organism_id * 0x9E3779B97F4A7C15))

    def next_parcel(self) -> int | None:
        """Produce a candidate from the current round; visits do not consume food.

        The implicit mapping supplies an order only.  Its round is local state,
        so after a full trajectory the organism independently traverses another
        deterministic permutation.  A parcel remains claimable until its byte
        availability is zero; a prior visit has no semantic effect.
        """
        block, node = divmod(self.index_in_round, self.node_count)
        current_round = self.round
        self.bite_index += 1
        self.index_in_round += 1
        round_width = ((self.parcel_count + self.node_count - 1) // self.node_count) * self.node_count
        if self.index_in_round == round_width:
            self.round += 1
            self.index_in_round = 0
        round_state = self.local_state if current_round == 0 else _mix64(
            self.local_state ^ (current_round * 0xD6E8FEB86659FD93)
        )
        mapped = _implicit_map(node, self.node_count, round_state)
        parcel = block * self.node_count + mapped
        return parcel if parcel < self.parcel_count else None


class FileFoodSpace:
    """Claimable byte positions backed by a seekable file, never by a file copy."""

    def __init__(self, path: str | Path, *, parcel_size: int = DEFAULT_PARCEL_SIZE, context_overlap: int = 2) -> None:
        self.prepared = PreparedFood(path, parcel_size=parcel_size, context_overlap=context_overlap)
        self.path = self.prepared.path
        self.size = self.prepared.file_size
        self.parcel_size = self.prepared.parcel_size
        self.context_overlap = self.prepared.context_overlap
        self.parcel_count = self.prepared.parcel_count
        self._claimed = bytearray((self.size + 7) // 8)
        self.metrics = FoodMetrics()

    @property
    def remaining(self) -> int:
        return self.size - self.metrics.bytes_consumed

    def _is_claimed(self, position: int) -> bool:
        return bool(self._claimed[position >> 3] & (1 << (position & 7)))

    def _claim(self, position: int) -> None:
        mask = 1 << (position & 7)
        cell = position >> 3
        if self._claimed[cell] & mask:
            self.metrics.duplicate_consumption += 1
            raise AssertionError("duplicate food claim")
        self._claimed[cell] |= mask

    def claim(self, parcel: int, capacity: int, *, skipped_regions: int) -> FoodClaim | None:
        """Atomically claim one contiguous, previously unclaimed nutritional bite."""
        self.metrics.candidates_visited += 1
        if parcel < 0 or parcel >= self.parcel_count or capacity <= 0:
            self.metrics.regions_skipped += 1
            return None
        start = parcel * self.parcel_size
        end = min(self.size, start + self.parcel_size)
        position = start
        while position < end and self._is_claimed(position):
            position += 1
        if position == end:
            self.metrics.regions_skipped += 1
            return None
        length = 0
        while position + length < end and length < capacity and not self._is_claimed(position + length):
            length += 1
        for claimed in range(position, position + length):
            self._claim(claimed)
        self.metrics.bytes_consumed += length
        return FoodClaim(parcel, position, length, skipped_regions)

    def read(self, handle: BinaryIO, claim: FoodClaim) -> tuple[tuple[int, ...], int]:
        """Read transient context|nutrition|context; return nutrition only to DIGEST."""
        window = self.prepared.read_window(handle, claim.offset, claim.length)
        self.metrics.bytes_read += window.raw_window_size
        self.metrics.peak_working_memory = max(self.metrics.peak_working_memory, window.raw_window_size)
        nutrition = tuple(window.nutrition)
        context_bytes = len(window.left_context) + len(window.right_context)
        # Context is diagnostic-only because unchanged DIGEST has no
        # zero-nutrition context channel.  No raw window is kept in lifecycle state.
        del window
        return nutrition, context_bytes


class ImplicitFileFeedingHarness:
    """Deterministic reference feeder; organisms independently derive candidates.

    This harness invokes the existing digestion, consolidation, maintenance,
    division, and death rules verbatim.  It supplies only a claimed byte bite
    and never stores raw bytes in an organism.
    """

    def __init__(self, path: str | Path, *, seed: int = 0, parcel_size: int = 64, context_overlap: int = 2) -> None:
        self.food = FileFoodSpace(path, parcel_size=parcel_size, context_overlap=context_overlap)
        self.population = MathematicalLifePopulation(())
        self.population.result.available_nutrition_total = float(self.food.size)
        self.seed = seed
        node_count = _power_of_two_at_least(self.food.parcel_count)
        self.node_count = min(65536, node_count)
        self.navigation: dict[int, FoodNavigationState] = {}
        self.trace: list[BiteTrace] = []
        self.digest_time = 0.0
        self.navigation_time = 0.0
        self._ensure_navigation(self.population.organisms[0])

    def _ensure_navigation(self, organism: MathematicalLifeOrganism) -> FoodNavigationState:
        return self.navigation.setdefault(
            organism.id,
            FoodNavigationState(organism.id, self.seed, self.node_count, self.food.parcel_count),
        )

    def _claim_next(self, organism: MathematicalLifeOrganism) -> FoodClaim | None:
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
        """Exact non-digest tail of MathematicalLifePopulation._cycle_one."""
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
        ids = sorted(tuple(self.population.organisms))
        with self.food.path.open("rb") as handle:
            for organism_id in ids:
                organism = self.population.organisms[organism_id]
                if organism.status is OrganismStatus.DEAD:
                    continue
                started = perf_counter()
                claim = self._claim_next(organism)
                self.navigation_time += perf_counter() - started
                before_assimilated = organism.assimilated_total
                before_waste = organism.waste_total
                navigator = self._ensure_navigation(organism)
                if claim is not None:
                    bite, _context_bytes = self.food.read(handle, claim)
                    started = perf_counter()
                    self.population._digest(organism, bite, tuple(1.0 for _ in bite))
                    self.digest_time += perf_counter() - started
                    del bite
                self._post_digest_lifecycle(organism)
                self.trace.append(BiteTrace(
                    organism.id, organism.generation, navigator.bite_index,
                    claim.offset if claim else -1, claim.length if claim else 0,
                    navigator.local_state, claim is not None,
                    claim.skipped_regions if claim else 0,
                    organism.assimilated_total - before_assimilated,
                    organism.waste_total - before_waste,
                ))
        for organism in self.population.organisms.values():
            self._ensure_navigation(organism)
        self.population.result.cycles += 1
        self.population.max_population = max(self.population.max_population, len(self.population.alive()))

    def run(self, *, max_steps: int | None = None) -> None:
        limit = max_steps if max_steps is not None else max(1, self.food.size * 2)
        while self.food.remaining and self.population.alive() and self.population.result.cycles < limit:
            self.step()
        if self.food.remaining:
            raise RuntimeError("file not fully consumed before organisms died or step limit")

    def assert_invariants(self) -> None:
        if self.food.metrics.duplicate_consumption:
            raise AssertionError("duplicate nutrition")
        if self.food.metrics.bytes_consumed != self.food.size:
            raise AssertionError("missing food bytes")
        if self.population.result.consumed_nutrition_total > self.food.size + 1e-12:
            raise AssertionError("lifecycle nutrition exceeds file food")
        for organism in self.population.organisms.values():
            if hasattr(organism, "payload") or hasattr(organism, "bite"):
                raise AssertionError("raw payload leaked into organism state")

    def debug_map(self, *, width: int = 72) -> str:
        if self.food.size == 0:
            return "0 EOF"
        rows = ["0 " + "-" * width + " EOF"]
        by_organism: dict[int, list[int]] = {}
        for event in self.trace:
            if event.claimed:
                by_organism.setdefault(event.organism_id, []).append(event.offset)
        for organism_id in sorted(by_organism):
            cells = [" "] * width
            for offset in by_organism[organism_id]:
                cells[min(width - 1, offset * width // self.food.size)] = "█"
            rows.append(f"O{organism_id}: " + "".join(cells))
        return "\n".join(rows)
