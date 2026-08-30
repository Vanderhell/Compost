from __future__ import annotations

"""Streaming, destructive FILE -> FOOD storage adapter.

This module owns only experiment storage.  It deliberately does not change
lifecycle policy, affinity, digestion, division, or reserve arithmetic.

An input is first copied into a disposable inbox and an immutable reference.
Ingest then transfers one tail block at a time.  The block is fsync'd and
verified before the inbox is truncated, so each committed operation conserves
``original_size == inbox_remaining + food_created``.
"""

from dataclasses import dataclass
import hashlib
import os
from pathlib import Path
import shutil
from time import perf_counter

from .food import FoodNavigationState, _power_of_two_at_least
from .lifecycle import LifecycleEvent, MathematicalLifeOrganism, MathematicalLifePopulation, OrganismStatus


CHUNK_SIZE = 64 * 1024


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(CHUNK_SIZE):
            digest.update(chunk)
    return digest.hexdigest()


def _copy_stream(source: Path, target: Path) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    with source.open("rb") as source_handle, target.open("wb") as target_handle:
        shutil.copyfileobj(source_handle, target_handle, CHUNK_SIZE)
        target_handle.flush()
        os.fsync(target_handle.fileno())


@dataclass(frozen=True, slots=True)
class FoodBlock:
    block_id: int
    original_start: int
    original_end: int
    path: Path


@dataclass(frozen=True, slots=True)
class BlockClaim:
    block_id: int
    original_offset: int
    length: int
    skipped_regions: int


@dataclass(frozen=True, slots=True)
class IngestEvent:
    block_id: int
    original_start: int
    original_end: int
    inbox_remaining: int
    food_created: int


@dataclass(slots=True)
class DestructiveStorageMetrics:
    blocks_created: int = 0
    blocks_deleted: int = 0
    filesystem_operations: int = 0
    bytes_created: int = 0
    bytes_consumed: int = 0
    bytes_read: int = 0
    claims: int = 0
    candidates_visited: int = 0
    regions_skipped: int = 0
    duplicate_consumption: int = 0
    peak_working_memory: int = 0
    peak_raw_bite_bytes: int = 0
    peak_technical_buffer_bytes: int = 0


class StreamingDestructiveFood:
    """Physical food blocks produced by tail-truncating a disposable inbox."""

    def __init__(self, source: str | Path, sandbox: str | Path, *, block_size: int = 1024 * 1024, technical_buffer_size: int = 64 * 1024, logical_name: str | None = None, inbox_is_source: bool = False) -> None:
        self.source = Path(source).resolve()
        self.sandbox = Path(sandbox).resolve()
        if not self.source.is_file() or block_size <= 0 or technical_buffer_size <= 0:
            raise ValueError("source must be regular and block/buffer sizes positive")
        self.logical_name = logical_name or self.source.name
        self.inbox_is_source = inbox_is_source
        self.reference_dir = self.sandbox.parent / "reference"
        self.inbox_dir = self.sandbox / "inbox"
        self.food_dir = self.sandbox / "food" / self.logical_name
        self.trace_dir = self.sandbox / "traces"
        self.result_dir = self.sandbox / "results"
        self.reference = self.reference_dir / self.logical_name
        self.inbox = self.source if inbox_is_source else self.inbox_dir / self.logical_name
        self.size = self.source.stat().st_size
        self.source_hash = sha256_file(self.source)
        self.block_size = block_size
        self.technical_buffer_size = technical_buffer_size
        self.blocks: dict[int, FoodBlock] = {}
        self.metrics = DestructiveStorageMetrics()
        self.ingest_events: list[IngestEvent] = []
        self._initialize_copies()

    @property
    def inbox_remaining(self) -> int:
        return self.inbox.stat().st_size if self.inbox.exists() else 0

    @property
    def food_created(self) -> int:
        return self.metrics.bytes_created

    @property
    def remaining(self) -> int:
        return self.food_created - self.metrics.bytes_consumed

    @property
    def block_count(self) -> int:
        return (self.size + self.block_size - 1) // self.block_size

    def _initialize_copies(self) -> None:
        for directory in (self.reference_dir, self.inbox_dir, self.food_dir, self.trace_dir, self.result_dir):
            directory.mkdir(parents=True, exist_ok=True)
        targets = (self.reference,) if self.inbox_is_source else (self.reference, self.inbox)
        for target in targets:
            if target.exists() and sha256_file(target) != self.source_hash:
                raise ValueError(f"existing {target} does not match source hash")
            if not target.exists():
                _copy_stream(self.source, target)
        self._check_ingest_conservation()

    def _check_ingest_conservation(self) -> None:
        if self.size != self.inbox_remaining + self.food_created:
            raise AssertionError("inbox/food ingest conservation violated")

    def ingest_next(self, *, fail_before_commit: bool = False) -> IngestEvent | None:
        """Commit one tail block, or fail before truncation without data loss."""
        remaining = self.inbox_remaining
        if not remaining:
            return None
        start = max(0, remaining - self.block_size)
        length = remaining - start
        block_id = len(self.ingest_events)
        temporary = self.food_dir / f"block_{block_id:06d}.tmp"
        final = self.food_dir / f"block_{block_id:06d}.food"
        with self.inbox.open("rb") as inbox_handle:
            inbox_handle.seek(start)
            payload = inbox_handle.read(length)
        if len(payload) != length:
            raise IOError("short inbox tail read")
        self.metrics.peak_working_memory = max(self.metrics.peak_working_memory, len(payload))
        digest = hashlib.sha256(payload).hexdigest()
        try:
            with temporary.open("xb") as food_handle:
                food_handle.write(payload)
                food_handle.flush()
                os.fsync(food_handle.fileno())
            self.metrics.filesystem_operations += 1
            if temporary.stat().st_size != length or sha256_file(temporary) != digest:
                raise IOError("unverified food block")
            if fail_before_commit:
                raise OSError("injected failure before block commit")
            temporary.replace(final)
            self.metrics.filesystem_operations += 1
            with self.inbox.open("r+b") as inbox_handle:
                inbox_handle.truncate(start)
                inbox_handle.flush()
                os.fsync(inbox_handle.fileno())
            self.metrics.filesystem_operations += 1
        except Exception:
            if temporary.exists():
                temporary.unlink()
            raise
        finally:
            del payload
        block = FoodBlock(block_id, start, remaining, final)
        self.blocks[block_id] = block
        self.metrics.blocks_created += 1
        self.metrics.bytes_created += length
        event = IngestEvent(block_id, start, remaining, self.inbox_remaining, self.food_created)
        self.ingest_events.append(event)
        self._check_ingest_conservation()
        return event

    def ingest_all(self, progress: object | None = None) -> None:
        while event := self.ingest_next():
            if callable(progress):
                progress(event)
        if self.inbox.exists():
            self.inbox.unlink()
            self.metrics.filesystem_operations += 1
        if self.food_created != self.size:
            raise AssertionError("incomplete destructive ingest")
        self.validate_reconstruction()

    def validate_reconstruction(self) -> None:
        """Test-only deterministic reconstruction ordered by original offsets."""
        digest = hashlib.sha256()
        expected = 0
        for block in sorted(self.blocks.values(), key=lambda item: item.original_start):
            if block.original_start != expected or not block.path.is_file():
                raise AssertionError("food blocks do not cover the original file exactly")
            with block.path.open("rb") as handle:
                while chunk := handle.read(CHUNK_SIZE):
                    digest.update(chunk)
            expected = block.original_end
        if expected != self.size or digest.hexdigest() != sha256_file(self.reference):
            raise AssertionError("food reconstruction differs from reference")

    def claim(self, block_id: int, capacity: int, *, skipped_regions: int, territory: object | None = None) -> BlockClaim | None:
        self.metrics.candidates_visited += 1
        if territory is not None and not territory.owns_block(self.source_hash, block_id):
            self.metrics.regions_skipped += 1
            return None
        block = self.blocks.get(block_id)
        if block is None or capacity <= 0:
            self.metrics.regions_skipped += 1
            return None
        available = block.original_end - block.original_start
        length = min(capacity, available)
        if not length:
            self.metrics.regions_skipped += 1
            return None
        self.metrics.claims += 1
        return BlockClaim(block_id, block.original_end - length, length, skipped_regions)

    def read(self, claim: BlockClaim) -> tuple[int, ...]:
        """Return only a biological bite; a larger disk buffer is not consumed.

        The storage read may contain up to ``technical_buffer_size`` bytes,
        but only its final ``claim.length`` bytes leave this method.  Thus the
        lifecycle sees exactly ``max(B_min, organism.size)`` bytes at most.
        """
        block = self.blocks[claim.block_id]
        available = block.original_end - block.original_start
        buffered = min(self.technical_buffer_size, available)
        with block.path.open("rb") as handle:
            handle.seek(available - buffered)
            technical = handle.read(buffered)
        if len(technical) != buffered:
            raise IOError("short food bite read")
        payload = technical[-claim.length:]
        self.metrics.bytes_read += len(technical)
        self.metrics.peak_technical_buffer_bytes = max(self.metrics.peak_technical_buffer_bytes, len(technical))
        self.metrics.peak_raw_bite_bytes = max(self.metrics.peak_raw_bite_bytes, len(payload))
        self.metrics.peak_working_memory = max(self.metrics.peak_working_memory, len(technical))
        bite = tuple(payload)
        del payload, technical
        return bite

    def consume(self, claim: BlockClaim) -> None:
        """After DIGEST, remove the claimed tail by O(1) file truncation."""
        block = self.blocks.get(claim.block_id)
        if block is None or claim.original_offset + claim.length != block.original_end:
            self.metrics.duplicate_consumption += 1
            raise AssertionError("non-tail or duplicate food consume")
        new_end = block.original_end - claim.length
        with block.path.open("r+b") as handle:
            handle.truncate(new_end - block.original_start)
            handle.flush()
            os.fsync(handle.fileno())
        self.metrics.filesystem_operations += 1
        self.metrics.bytes_consumed += claim.length
        if new_end == block.original_start:
            block.path.unlink()
            self.metrics.filesystem_operations += 1
            self.metrics.blocks_deleted += 1
            del self.blocks[block.block_id]
        else:
            self.blocks[block.block_id] = FoodBlock(block.block_id, block.original_start, new_end, block.path)
        if sum(item.original_end - item.original_start for item in self.blocks.values()) != self.remaining:
            raise AssertionError("food consumption accounting violated")


class DestructiveFeedingHarness:
    """Existing lifecycle fed from destructively-truncated physical blocks."""

    def __init__(self, source: str | Path, sandbox: str | Path, *, seed: int = 0xF00D, block_size: int = 1024 * 1024, technical_buffer_size: int = 64 * 1024, ingest_progress: object | None = None) -> None:
        self.food = StreamingDestructiveFood(source, sandbox, block_size=block_size, technical_buffer_size=technical_buffer_size)
        self.food.ingest_all(progress=ingest_progress)
        self.population = MathematicalLifePopulation(())
        self.population.result.available_nutrition_total = float(self.food.size)
        self.seed = seed
        self.node_count = min(65536, _power_of_two_at_least(self.food.block_count))
        self.navigation: dict[int, FoodNavigationState] = {}
        self.navigation_time = 0.0
        self.digest_time = 0.0
        self.body_sizes: list[int] = []
        self.bite_sizes: list[int] = []
        self._ensure_navigation(self.population.organisms[0])

    def _ensure_navigation(self, organism: MathematicalLifeOrganism) -> FoodNavigationState:
        return self.navigation.setdefault(organism.id, FoodNavigationState(organism.id, self.seed, self.node_count, self.food.block_count))

    def _claim_next(self, organism: MathematicalLifeOrganism) -> BlockClaim | None:
        state = self._ensure_navigation(organism)
        skipped = 0
        for _ in range(max(1, self.node_count * 2)):
            block_id = state.next_parcel()
            if block_id is not None:
                claim = self.food.claim(block_id, organism.bite_limit(self.population.config), skipped_regions=skipped)
                if claim is not None:
                    return claim
            skipped += 1
        return None

    def _tail(self, organism: MathematicalLifeOrganism) -> None:
        self.population._consolidate(organism)
        self.population._maintain_and_resorb(organism)
        organism.age_in_cycles += 1
        if organism.status is OrganismStatus.ALIVE:
            self.population._divide_if_profitable(organism)
        if organism.size == 0 and organism.status is OrganismStatus.ALIVE:
            organism.status = OrganismStatus.DEAD
            organism.death_age = organism.age_in_cycles
            self.population.result.events.append(LifecycleEvent(organism.id, 0, "DEATH", "no living structures"))

    def step(self) -> None:
        for organism_id in sorted(tuple(self.population.organisms)):
            organism = self.population.organisms[organism_id]
            if organism.status is OrganismStatus.DEAD:
                continue
            started = perf_counter()
            claim = self._claim_next(organism)
            self.navigation_time += perf_counter() - started
            if claim is not None:
                # Snapshot before DIGEST: strength has no influence here.
                self.body_sizes.append(organism.size)
                self.bite_sizes.append(claim.length)
                bite = self.food.read(claim)
                try:
                    started = perf_counter()
                    self.population._digest(organism, bite, tuple(1.0 for _ in bite))
                    self.digest_time += perf_counter() - started
                except Exception:
                    # No consume commit: claimed bytes remain physical FOOD.
                    raise
                else:
                    # Commit occurs only after the complete DIGEST succeeds.
                    self.food.consume(claim)
                finally:
                    del bite
            self._tail(organism)
        for organism in self.population.organisms.values():
            self._ensure_navigation(organism)
        self.population.result.cycles += 1
        self.population.max_population = max(self.population.max_population, len(self.population.alive()))

    def run(self, *, max_cycles: int | None = None) -> None:
        limit = max_cycles if max_cycles is not None else max(1, self.food.size * 2)
        while self.food.remaining and self.population.alive() and self.population.result.cycles < limit:
            self.step()

    def assert_invariants(self) -> None:
        if self.food.inbox_remaining or self.food.remaining or self.food.metrics.duplicate_consumption:
            raise AssertionError("destructive food did not finish exactly once")
        if self.population.result.consumed_nutrition_total > self.food.size + 1e-12:
            raise AssertionError("nutrition exceeds physical food")
