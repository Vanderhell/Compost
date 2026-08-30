from __future__ import annotations

"""Implicit, disjoint FOOD territories for autonomous organisms.

Ownership is a pure function of a food address and a territory path.  No
byte-to-organism table, claim winner, or lifecycle scheduler is required.
"""

from dataclasses import dataclass
from hashlib import sha256
from typing import Iterable


MASK64 = (1 << 64) - 1


def _mix64(value: int) -> int:
    value &= MASK64
    value ^= value >> 30
    value = (value * 0xBF58476D1CE4E5B9) & MASK64
    value ^= value >> 27
    value = (value * 0x94D049BB133111EB) & MASK64
    return (value ^ (value >> 31)) & MASK64


def address_bit(address: int, depth: int) -> int:
    """Stable implicit partition bit for non-negative FOOD address ``address``."""
    if address < 0 or depth < 0:
        raise ValueError("food address and territory depth must be non-negative")
    return _mix64(address ^ ((depth + 1) * 0x9E3779B97F4A7C15)) & 1


def food_block_key(file_id: str, block_index: int) -> int:
    """Stable 64-bit address for an entire physical FOOD block."""
    if block_index < 0:
        raise ValueError("block index must be non-negative")
    material = file_id.encode("utf-8") + b"\0" + block_index.to_bytes(8, "big")
    return int.from_bytes(sha256(material).digest()[:8], "big")


@dataclass(frozen=True, slots=True)
class FoodTerritory:
    """A prefix in the implicit binary partition tree of the food address space."""

    path: tuple[int, ...] = ()

    def __post_init__(self) -> None:
        if any(bit not in (0, 1) for bit in self.path):
            raise ValueError("a territory path contains only binary branches")

    def contains(self, address: int) -> bool:
        return all(address_bit(address, depth) == bit for depth, bit in enumerate(self.path))

    def split(self) -> tuple["FoodTerritory", "FoodTerritory"]:
        return FoodTerritory(self.path + (0,)), FoodTerritory(self.path + (1,))

    def owns_block(self, file_id: str, block_index: int) -> bool:
        """Whole-block ownership; byte offsets never influence this decision."""
        return self.contains(food_block_key(file_id, block_index))

    def overlaps(self, other: "FoodTerritory") -> bool:
        shared = min(len(self.path), len(other.path))
        return self.path[:shared] == other.path[:shared]


OrganismId = tuple[int, ...]


def child_id(parent_id: OrganismId, local_birth_counter: int) -> OrganismId:
    """Globally unique tree ID derived solely from a parent's local birth count."""
    if local_birth_counter < 0:
        raise ValueError("local birth counter must be non-negative")
    return parent_id + (local_birth_counter,)


@dataclass(slots=True)
class AutonomousTerritoryState:
    """The territory portion of one autonomous organism's mutable state."""

    organism_id: OrganismId
    territory: FoodTerritory = FoodTerritory()
    local_birth_counter: int = 0
    alive: bool = True

    def divide_territory(self) -> "AutonomousTerritoryState":
        """Give parent D0 and an immediately autonomous child D1."""
        if not self.alive:
            raise RuntimeError("dead organism cannot divide a territory")
        parent_domain, child_domain = self.territory.split()
        child = AutonomousTerritoryState(
            organism_id=child_id(self.organism_id, self.local_birth_counter),
            territory=child_domain,
        )
        self.local_birth_counter += 1
        self.territory = parent_domain
        return child

    def die(self) -> None:
        """Leave territory unoccupied; its food remains physically untouched."""
        self.alive = False


def assert_disjoint_live_territories(states: Iterable[AutonomousTerritoryState]) -> None:
    live = [state for state in states if state.alive]
    for index, first in enumerate(live):
        for second in live[index + 1:]:
            if first.territory.overlaps(second.territory):
                raise AssertionError(f"overlapping live territories: {first.organism_id}, {second.organism_id}")


def owner_of(address: int, states: Iterable[AutonomousTerritoryState]) -> AutonomousTerritoryState | None:
    """Return the sole live owner of an address, or None for unoccupied food."""
    owners = [state for state in states if state.alive and state.territory.contains(address)]
    if len(owners) > 1:
        raise AssertionError("food address has more than one live territory owner")
    return owners[0] if owners else None


def owner_of_block(file_id: str, block_index: int, states: Iterable[AutonomousTerritoryState]) -> AutonomousTerritoryState | None:
    """Whole-block counterpart of :func:`owner_of`."""
    return owner_of(food_block_key(file_id, block_index), states)


def territory_digest(territory: FoodTerritory) -> str:
    """Stable diagnostic identity; it has no role in territory ownership."""
    return sha256(bytes(territory.path)).hexdigest()
