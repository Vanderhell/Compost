from __future__ import annotations

"""Central, side-effect-free biological formulae for autonomous life."""

from dataclasses import dataclass, field
from math import ceil, floor, log, log2
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .lifecycle import LifecycleConfig, LivingStructure, MathematicalLifeOrganism


REPRODUCTION_SPLIT_MINIMUM_STRENGTH = 2.0
BYTE_RECEPTOR_COUNT = 256
BASE_RECEPTOR_MASS = BYTE_RECEPTOR_COUNT


@dataclass(frozen=True, slots=True)
class ActivityCostModel:
    """Central deterministic prices for biological work, not wall-clock time."""
    byte: float = 0.0
    digest_per_kib: float = 0.001
    reject_per_kib: float = 0.002
    resorption_per_kib: float = 0.002
    relation_created: float = 0.08
    relation_strengthened: float = 0.01
    composite_created: float = 0.12
    composite_strengthened: float = 0.02
    structural_mass_delta: float = 0.01
    resorption: float = 0.10
    division: float = 0.50
    basal_mass: float = 0.001
    settlement_base: float = 2.0
    settlement_mass_scale: float = 0.01


ACTIVITY_COSTS = ActivityCostModel()


@dataclass(slots=True)
class ActivityCounters:
    bytes_eaten: int = 0
    relations_created: int = 0
    relations_strengthened: int = 0
    composites_created: int = 0
    composites_strengthened: int = 0
    structural_mass_added: int = 0
    structural_mass_lost: int = 0
    resorption_events: int = 0
    division_events: int = 0
    processed_bytes: int = 0
    rejected_bytes: int = 0
    resorbed_processed_bytes: int = 0


@dataclass(slots=True)
class ActivityLedger:
    """Organism-owned aggregate work ledger; no structural traversal needed."""
    metabolic_debt: float = 0.0
    energy_spent: float = 0.0
    settlements: int = 0
    counters: ActivityCounters = field(default_factory=ActivityCounters)

    def add_activity(self, counters: ActivityCounters, body_mass: int, costs: ActivityCostModel = ACTIVITY_COSTS) -> float:
        self.counters.bytes_eaten += counters.bytes_eaten
        self.counters.relations_created += counters.relations_created
        self.counters.relations_strengthened += counters.relations_strengthened
        self.counters.composites_created += counters.composites_created
        self.counters.composites_strengthened += counters.composites_strengthened
        self.counters.structural_mass_added += counters.structural_mass_added
        self.counters.structural_mass_lost += counters.structural_mass_lost
        self.counters.resorption_events += counters.resorption_events
        self.counters.division_events += counters.division_events
        self.counters.processed_bytes += counters.processed_bytes
        self.counters.rejected_bytes += counters.rejected_bytes
        self.counters.resorbed_processed_bytes += counters.resorbed_processed_bytes
        delta = (
            costs.byte * counters.bytes_eaten
            + costs.digest_per_kib * (counters.processed_bytes / 1024.0)
            + costs.reject_per_kib * (counters.rejected_bytes / 1024.0)
            + costs.resorption_per_kib * (counters.resorbed_processed_bytes / 1024.0)
            + costs.relation_created * counters.relations_created
            + costs.relation_strengthened * counters.relations_strengthened
            + costs.composite_created * counters.composites_created
            + costs.composite_strengthened * counters.composites_strengthened
            + costs.structural_mass_delta * (counters.structural_mass_added + counters.structural_mass_lost)
            + costs.resorption * counters.resorption_events
            + costs.division * counters.division_events
        )
        self.metabolic_debt += delta
        return delta

    @staticmethod
    def settlement_threshold(body_mass: int, costs: ActivityCostModel = ACTIVITY_COSTS) -> float:
        return costs.settlement_base + costs.settlement_mass_scale * body_mass

    @staticmethod
    def basal_cost(body_mass: int, costs: ActivityCostModel = ACTIVITY_COSTS) -> float:
        return costs.basal_mass * body_mass


def structural_mass(strength: float) -> int:
    """Sublinear material mass of a live learned relation/composite."""
    if strength < 1.0:
        return 0
    return 1 + floor(log2(strength))


@dataclass(frozen=True, slots=True)
class ForgettingDelta:
    strength_after: float
    income_rate_after: float


@dataclass(frozen=True, slots=True)
class LazyMetabolismDelta:
    """Exact real-arithmetic composition of the existing per-epoch rule."""
    strength_after: float
    income_rate_after: float
    strength_decay_epochs: int


@dataclass(frozen=True, slots=True)
class ReproductionAssessment:
    score: float
    allowed: bool
    selected_count: int
    parent_reserve_after_cost: float


def forgetting_delta(structure: "LivingStructure", config: "LifecycleConfig") -> ForgettingDelta:
    """Exact existing lazy-forgetting rule, expressed without mutation."""
    strength = structure.strength
    if structure.income_rate <= structure.maintenance:
        strength = max(1.0, strength * config.income_decay)
    return ForgettingDelta(strength, structure.income_rate * config.income_decay)


def lazy_metabolism_delta(
    *, strength: float, income_rate: float,
    maintenance: float, income_decay: float, epochs: int,
) -> LazyMetabolismDelta:
    """Compose ``epochs`` eager maintenance/forgetting updates without looping.

    Organism-level energy settles separately; this local law decays strength
    when the *pre-decay* income is at most maintenance.  Since
    income is geometric and never increases during an unobserved interval, the
    first decay epoch is found logarithmically; all later epochs decay too.
    This is exact for the mathematical real-number recurrence.  The runtime's
    binary-float eager reference can differ only by ordinary roundoff from
    repeated multiplication, so equivalence tests use a numerical tolerance.
    """
    if epochs < 0 or maintenance < 0 or not 0 < income_decay < 1:
        raise ValueError("invalid lazy metabolism parameters")
    if epochs == 0:
        return LazyMetabolismDelta(strength, income_rate, 0)
    if income_rate <= maintenance:
        decay_epochs = epochs
    elif maintenance == 0.0:
        decay_epochs = 0
    else:
        # Find first j >= 0 such that income_rate * rho**j <= maintenance.
        first_decay_index = max(0, ceil(log(maintenance / income_rate) / log(income_decay)))
        # Correct only a possible boundary-rounding off-by-one, never by N.
        while first_decay_index > 0 and income_rate * income_decay ** (first_decay_index - 1) <= maintenance:
            first_decay_index -= 1
        while income_rate * income_decay ** first_decay_index > maintenance:
            first_decay_index += 1
        decay_epochs = max(0, epochs - first_decay_index)
    return LazyMetabolismDelta(
        max(1.0, strength * income_decay ** decay_epochs),
        income_rate * income_decay ** epochs,
        decay_epochs,
    )


def resorption_allowed(structure: "LivingStructure", organism: "MathematicalLifeOrganism", *, body_maintenance: float) -> bool:
    """The caller establishes pressure; strength one alone never triggers it."""
    del organism, body_maintenance
    return structure.strength >= 1.0


def maintenance_weakening_budget(maintenance_deficit: float, body_mass: int) -> int:
    """Whole local weakening units required by unpaid maintenance.

    A deficit is a failure to maintain, not a fuel source.  The conversion is
    deliberately monotone and deterministic.  Normalising by cached body mass
    prevents one deficit settlement from weakening every member of a large
    skeleton at once, while a positive deficit still always advances at least
    one local candidate.
    """
    if maintenance_deficit <= 0.0:
        return 0
    return max(1, ceil(maintenance_deficit / max(1, body_mass)))


def reproduction_score(organism: "MathematicalLifeOrganism", config: "LifecycleConfig", *, selected_count: int) -> float:
    """Structural maturity score; child reserve is defined to be zero."""
    del organism, config
    return float(selected_count) if selected_count >= 2 else float("-inf")


def reproduction_allowed(organism: "MathematicalLifeOrganism", config: "LifecycleConfig", *, selected_count: int) -> ReproductionAssessment:
    """Child viability is non-energetic; only parent pays division cost."""
    parent_after = organism.reserve - config.birth_cost
    score = reproduction_score(organism, config, selected_count=selected_count)
    allowed = (
        organism.size >= config.reproduction_minimum_body
        and selected_count >= 2
        and parent_after >= 0.0
    )
    return ReproductionAssessment(score, allowed, selected_count, parent_after)
