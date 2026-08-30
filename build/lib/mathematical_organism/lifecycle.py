from __future__ import annotations

"""Deterministic reference population with data-as-food semantics.

The model stores only living symbolic structures and aggregate evidence.  A
payload belongs to the environment: after a bite is digested an organism keeps
no bite, position list, or raw event history.
"""

from collections import defaultdict, deque
from dataclasses import dataclass, field
from enum import Enum
from typing import Iterable, Sequence

from .biology_rules import BASE_RECEPTOR_MASS, BYTE_RECEPTOR_COUNT, forgetting_delta, resorption_allowed, structural_mass


Pair = tuple[str, str]


class OrganismStatus(str, Enum):
    ALIVE = "ALIVE"
    DEAD = "DEAD"


@dataclass(frozen=True, slots=True)
class LifecycleConfig:
    bite_minimum: int = 1
    atom_income: float = 1.0
    relation_income: float = 0.80
    composite_income: float = 1.10
    atom_maintenance: float = 0.25
    relation_maintenance: float = 0.50
    composite_maintenance: float = 0.30
    atom_formation_cost: float = 0.35
    relation_formation_cost: float = 1.25
    consolidation_formation_cost: float = 1.50
    birth_cost: float = 1.0
    division_horizon: float = 8.0
    boundary_ratio_limit: float = 0.15
    income_decay: float = 0.80
    novelty_affinity: float = 0.25
    # Bootstrap reserve belongs only to an initially created organism.  A
    # division child is explicitly born with reserve zero.
    birth_reserve: float = 1.0
    # Metabolism is charged per deterministic volume of digested food, never
    # per I/O bite.  A body-sized interval makes a larger body pay after it has
    # processed proportionally more work; the minimum prevents a zero/one-node
    # bootstrap from being charged once for every byte.
    metabolic_minimum_work: int = 64
    reproduction_minimum_body: int = 32

    def validate(self) -> None:
        positive = (
            self.bite_minimum,
            self.atom_income,
            self.relation_income,
            self.composite_income,
            self.atom_maintenance,
            self.relation_maintenance,
            self.composite_maintenance,
            self.atom_formation_cost,
            self.relation_formation_cost,
            self.consolidation_formation_cost,
            self.birth_cost,
            self.division_horizon,
            self.metabolic_minimum_work,
            self.reproduction_minimum_body,
        )
        if any(value <= 0 for value in positive):
            raise ValueError("lifecycle parameters must be positive")
        if not 0 < self.boundary_ratio_limit < 1:
            raise ValueError("boundary_ratio_limit must be in (0, 1)")
        if not 0 < self.income_decay < 1:
            raise ValueError("income_decay must be in (0, 1)")
        if self.novelty_affinity <= 0:
            raise ValueError("novelty_affinity must be positive")
        if self.birth_reserve < 0:
            raise ValueError("birth_reserve must be non-negative")


@dataclass(slots=True)
class LivingStructure:
    key: str | Pair
    kind: str
    strength: float = 0.0
    maintenance: float = 0.0
    evidence: float = 0.0
    income_rate: float = 0.0
    # Relation/composite references are symbolic skeleton links, never raw
    # payload.  A tuple permits later n-ary members without changing storage.
    members: tuple[object, ...] = ()
    # Prepared for exact lazy metabolism.  It is not used to change the eager
    # global resorption schedule until an equivalent global event model exists.
    last_metabolic_epoch: int = 0

    def feed(self, amount: float) -> None:
        """Apply real-use gain to learned evidence, never to energy."""
        self.strength += amount
        self.evidence += 1.0
        self.income_rate += amount


@dataclass(frozen=True, slots=True)
class BirthEvent:
    """Immutable observation emitted after an already-approved division.

    These fields are audit data only.  They are captured from the same state
    transition used by the lifecycle model and take no part in eligibility,
    scheduling, or energy/reserve calculations.
    """

    birth_index: int
    parent_id: int
    child_id: int
    data_position: int
    parent_generation: int
    parent_size_before: int
    parent_total_strength: float
    parent_reserve: float
    candidate_region: tuple[str, ...]
    boundary_strength: float
    child_generation: int
    child_size_at_birth: int
    child_total_strength: float
    child_reserve: float
    parent_size_after: int
    parent_strength_after: float
    parent_reserve_after: float
    next_parent_bite: int
    next_child_bite: int
    # Backward-compatible aggregate accounting fields.
    child_size: int
    reserve_before: float
    reserve_after: float
    reason: str


@dataclass(frozen=True, slots=True)
class LifecycleEvent:
    organism_id: int
    position: int
    kind: str
    detail: str


@dataclass(slots=True)
class MathematicalLifeOrganism:
    id: int
    parent_id: int | None
    birth_position: int
    generation: int
    cursor: int
    atoms: dict[str, LivingStructure] = field(default_factory=dict)
    relations: dict[Pair, LivingStructure] = field(default_factory=dict)
    composites: dict[Pair, LivingStructure] = field(default_factory=dict)
    # The byte alphabet is a fixed sensory substrate.  It is not learned
    # evidence and contributes only the explicit base term M_A.
    receptors: tuple[int, ...] = field(default_factory=lambda: tuple(range(BYTE_RECEPTOR_COUNT)))
    activated_receptors: set[int] = field(default_factory=set)
    body_mass: int = BASE_RECEPTOR_MASS
    # The sole authoritative energy store of a living organism.  Structures
    # carry evidence and mass only; they never own or transfer reserve.
    reserve: float = 0.0
    # These aggregates are an optimisation for the autonomous DIGEST path.
    # They have a lazy reference rebuild because a few legacy tests construct
    # structures directly.  The public total_* properties remain the exact
    # full-scan reference views.
    maintenance_cache: float = 0.0
    resource_cache_valid: bool = False
    age_in_cycles: int = 0
    consumed_total: int = 0
    assimilated_total: int = 0
    waste_total: int = 0
    nutrition_consumed_total: float = 0.0
    children_created: int = 0
    status: OrganismStatus = OrganismStatus.ALIVE
    peak_strength: float = 0.0
    peak_age: int = 0
    first_consolidation_age: int | None = None
    death_age: int | None = None

    @property
    def size(self) -> int:
        return len(self.atoms) + len(self.relations) + len(self.composites)

    @property
    def total_strength(self) -> float:
        return sum(item.strength for item in self._structures())

    def ensure_resource_cache(self) -> None:
        if not self.resource_cache_valid:
            self.maintenance_cache = sum(item.maintenance for item in self._structures())
            self.resource_cache_valid = True

    def cached_maintenance(self) -> float:
        self.ensure_resource_cache()
        return self.maintenance_cache

    def adjust_reserve(self, delta: float) -> None:
        """Apply an organism-level energy delta; structures are never payers."""
        self.reserve = max(0.0, self.reserve + delta)

    def refresh_resource_cache(self) -> None:
        self.resource_cache_valid = False
        self.ensure_resource_cache()

    @property
    def assimilation_ratio(self) -> float:
        return self.assimilated_total / self.consumed_total if self.consumed_total else 0.0

    @property
    def exposure_total(self) -> int:
        """Number of symbols seen; ``consumed_total`` retains its public meaning."""
        return self.consumed_total

    def bite_limit(self, config: LifecycleConfig) -> int:
        return max(config.bite_minimum, self.body_mass)

    def activate_receptor(self, symbol: object) -> bool:
        """Record exposure of a canonical byte receptor without learned weight."""
        if isinstance(symbol, int) and 0 <= symbol < BYTE_RECEPTOR_COUNT:
            self.activated_receptors.add(symbol)
            return True
        return False

    def full_body_mass(self) -> int:
        """Reference recalculation used by tests; never needed on the bite path."""
        return BASE_RECEPTOR_MASS + sum(structural_mass(item.strength) for item in self.relations.values()) + sum(structural_mass(item.strength) for item in self.composites.values())

    def verify_body_mass(self) -> None:
        if self.body_mass != self.full_body_mass():
            raise AssertionError("incremental body mass diverged from skeleton")

    def _tracks_mass(self, structure: LivingStructure) -> bool:
        return structure.kind in {"RELATION", "COMPOSITE"}

    def add_structure(self, collection: dict, structure: LivingStructure) -> None:
        collection[structure.key] = structure
        if self._tracks_mass(structure):
            self.body_mass += structural_mass(structure.strength)
        if self.resource_cache_valid:
            self.maintenance_cache += structure.maintenance

    def remove_structure(self, collection: dict, key: object) -> LivingStructure:
        structure = collection.pop(key)
        if self._tracks_mass(structure):
            self.body_mass -= structural_mass(structure.strength)
        if self.resource_cache_valid:
            self.maintenance_cache -= structure.maintenance
        return structure

    def set_strength(self, structure: LivingStructure, new_strength: float) -> None:
        old_mass = structural_mass(structure.strength) if self._tracks_mass(structure) else 0
        structure.strength = new_strength
        if self._tracks_mass(structure):
            self.body_mass += structural_mass(structure.strength) - old_mass

    def _structures(self) -> Iterable[LivingStructure]:
        yield from self.atoms.values()
        yield from self.relations.values()
        yield from self.composites.values()

    def clone_region(self, atom_names: set[str], *, child_id: int, birth_position: int) -> "MathematicalLifeOrganism":
        """Move a connected region into a child; evidence is transferred, never copied."""
        # Compatibility for manually constructed test/reference skeletons;
        # normal lifecycle mutation maintains the cache incrementally.
        self.body_mass = self.full_body_mass()
        child = MathematicalLifeOrganism(
            id=child_id,
            parent_id=self.id,
            birth_position=birth_position,
            generation=self.generation + 1,
            cursor=birth_position,
        )
        for atom in sorted(atom_names):
            child.atoms[atom] = self.atoms.pop(atom)
        for collection, child_collection in ((self.relations, child.relations), (self.composites, child.composites)):
            for pair in sorted(list(collection)):
                if pair[0] in atom_names and pair[1] in atom_names:
                    child.add_structure(child_collection, self.remove_structure(collection, pair))
        self.verify_body_mass()
        child.verify_body_mass()
        return child


@dataclass(slots=True)
class PopulationResult:
    cycles: int = 0
    cycles_at_stream_end: int | None = None
    alive_at_stream_end: int | None = None
    births: list[BirthEvent] = field(default_factory=list)
    events: list[LifecycleEvent] = field(default_factory=list)
    available_nutrition_total: float = 0.0
    consumed_nutrition_total: float = 0.0
    nutrition_created_total: float = 0.0


class MathematicalLifePopulation:
    """Single-thread logical reference; ID order defines scheduling, not CPU timing."""

    def __init__(self, payload: str | Sequence[str], config: LifecycleConfig | None = None) -> None:
        self.payload = tuple(payload) if isinstance(payload, str) else tuple(payload)
        if any(not isinstance(symbol, str) or not symbol for symbol in self.payload):
            raise TypeError("payload symbols must be non-empty strings")
        self.config = config or LifecycleConfig()
        self.config.validate()
        root = MathematicalLifeOrganism(0, None, 0, 0, 0, reserve=self.config.birth_reserve)
        self.organisms: dict[int, MathematicalLifeOrganism] = {0: root}
        self.next_id = 1
        self.max_population = 1
        self.result = PopulationResult(available_nutrition_total=float(len(self.payload)))
        self._nutrition_remaining = [1.0] * len(self.payload)

    def alive(self) -> list[MathematicalLifeOrganism]:
        return [item for item in self.organisms.values() if item.status is OrganismStatus.ALIVE]

    def cycle(self) -> None:
        """Advance one deterministic logical cycle with conserved food allocation.

        Organisms expose their next bite before lifecycle work.  They compete
        only for the finite nutrition of absolute payload positions they see;
        subsequent lifecycle work remains in deterministic ID order.
        """
        organism_ids = sorted(tuple(self.organisms))
        planned_bites = self._allocate_nutrition(organism_ids)
        for organism_id in organism_ids:
            organism = self.organisms[organism_id]
            if organism.status is OrganismStatus.ALIVE:
                self._cycle_one(organism, planned_bites.get(organism_id))
        self.result.cycles += 1
        self.max_population = max(self.max_population, len(self.alive()))

    def run(self, *, max_cycles: int, settle_cycles: int = 0) -> None:
        if max_cycles < 0 or settle_cycles < 0:
            raise ValueError("cycle limits must be non-negative")
        for _ in range(max_cycles):
            if not self.alive():
                break
            self.cycle()
        self.settle(settle_cycles)

    def run_until_stream_exhausted(self, *, max_cycles: int) -> None:
        """Run while at least one living organism still has unseen environment data."""
        for _ in range(max_cycles):
            if not any(item.status is OrganismStatus.ALIVE and item.cursor < len(self.payload) for item in self.organisms.values()):
                break
            self.cycle()
        else:
            raise RuntimeError("stream was not exhausted within max_cycles")
        self.result.cycles_at_stream_end = self.result.cycles
        self.result.alive_at_stream_end = len(self.alive())

    def settle(self, cycles: int) -> None:
        if cycles < 0:
            raise ValueError("cycles must be non-negative")
        for _ in range(cycles):
            if not self.alive():
                break
            self.cycle()

    def _cycle_one(
        self,
        organism: MathematicalLifeOrganism,
        planned_bite: tuple[tuple[str, ...], tuple[float, ...]] | None,
    ) -> None:
        if planned_bite is not None:
            bite, nutrition = planned_bite
            organism.cursor += len(bite)
            self._digest(organism, bite, nutrition)
        self._consolidate(organism)
        self._maintain_and_resorb(organism)
        organism.age_in_cycles += 1
        if organism.status is OrganismStatus.ALIVE:
            self._divide_if_profitable(organism)
        if organism.size == 0 and organism.status is OrganismStatus.ALIVE:
            organism.status = OrganismStatus.DEAD
            organism.death_age = organism.age_in_cycles
            self.result.events.append(LifecycleEvent(organism.id, organism.cursor, "DEATH", "no living structures"))
        if organism.total_strength > organism.peak_strength:
            organism.peak_strength = organism.total_strength
            organism.peak_age = organism.age_in_cycles

    def _allocate_nutrition(self, organism_ids: Sequence[int]) -> dict[int, tuple[tuple[str, ...], tuple[float, ...]]]:
        """Allocate Q(position)=1 once among simultaneous positive-affinity exposures.

        A non-empty organism's affinity is the strength of the matching atom;
        an empty bootstrap organism has affinity one.  Shares are proportional
        to affinity.  ID order breaks ties, and the final claimant receives the
        floating residual, so recorded nutrition cannot exceed availability.
        """
        planned: dict[int, tuple[int, tuple[str, ...]]] = {}
        claimants: dict[int, list[tuple[int, float]]] = defaultdict(list)
        exposed_positions: set[int] = set()
        for organism_id in organism_ids:
            organism = self.organisms[organism_id]
            if organism.status is OrganismStatus.DEAD or organism.cursor >= len(self.payload):
                continue
            end = min(len(self.payload), organism.cursor + organism.bite_limit(self.config))
            bite = self.payload[organism.cursor:end]
            planned[organism_id] = (organism.cursor, bite)
            for position, symbol in enumerate(bite, start=organism.cursor):
                exposed_positions.add(position)
                affinity = self._food_affinity(organism, symbol)
                if affinity > 0.0:
                    claimants[position].append((organism_id, affinity))

        nutrition = {organism_id: [0.0] * len(bite) for organism_id, (_, bite) in planned.items()}
        for position in sorted(exposed_positions):
            positive = sorted(claimants.get(position, ()))
            remaining = self._nutrition_remaining[position]
            remaining_affinity = sum(affinity for _, affinity in positive)
            if remaining <= 0.0 or remaining_affinity <= 0.0:
                continue
            for index, (organism_id, affinity) in enumerate(positive):
                share = remaining if index == len(positive) - 1 else remaining * affinity / remaining_affinity
                start, _ = planned[organism_id]
                nutrition[organism_id][position - start] = share
                remaining -= share
                remaining_affinity -= affinity
            self._nutrition_remaining[position] = remaining
        if self.result.consumed_nutrition_total > self.result.available_nutrition_total + 1e-12:
            raise AssertionError("nutrition conservation violated")
        return {
            organism_id: (bite, tuple(nutrition[organism_id]))
            for organism_id, (_, bite) in planned.items()
        }

    def _food_affinity(self, organism: MathematicalLifeOrganism, symbol: str) -> float:
        """Local affinity: known strength, or affordable novelty exploration."""
        if not organism.atoms:
            return 1.0
        atom = organism.atoms.get(symbol)
        if atom is not None:
            return atom.strength
        return self.config.novelty_affinity if organism.reserve >= self.config.atom_formation_cost else 0.0

    def _digest(self, organism: MathematicalLifeOrganism, bite: tuple[str, ...], nutrition: tuple[float, ...]) -> None:
        # `bite` is local-only and goes out of scope after this method.
        if len(bite) != len(nutrition):
            raise AssertionError("every exposure needs one nutrition allocation")
        organism.consumed_total += len(bite)
        assimilated = 0.0
        for symbol, food in zip(bite, nutrition):
            if food <= 0.0:
                continue
            organism.activate_receptor(symbol)
            atom = organism.atoms.get(symbol)
            if atom is None:
                if organism.atoms and self._under_metabolic_pressure(organism, self.config.atom_maintenance):
                    if not self._metabolize_for_capacity(organism):
                        continue
                if organism.atoms and not self._fund_cost(organism, self.config.atom_formation_cost):
                    continue
                atom = LivingStructure(symbol, "ATOM", maintenance=self.config.atom_maintenance)
                atom.strength = food
                atom.evidence = 1.0
                atom.income_rate = self.config.atom_income * food
                organism.atoms[symbol] = atom
            else:
                atom.feed(self.config.atom_income * food)
            organism.adjust_reserve(self.config.atom_income * food)
            assimilated += food
        for index, pair in enumerate(zip(bite, bite[1:])):
            food = min(nutrition[index], nutrition[index + 1])
            if food <= 0.0:
                continue
            receptor_pair = organism.activate_receptor(pair[0]) and organism.activate_receptor(pair[1])
            if not receptor_pair and (pair[0] not in organism.atoms or pair[1] not in organism.atoms):
                continue
            if pair in organism.composites:
                composite = organism.composites[pair]
                organism.set_strength(composite, composite.strength + self.config.composite_income * food)
                composite.evidence += 1.0; composite.income_rate += self.config.composite_income * food
                organism.adjust_reserve(self.config.composite_income * food)
                continue
            relation = organism.relations.get(pair)
            if relation is None:
                if self._under_metabolic_pressure(organism, self.config.relation_maintenance):
                    if not self._metabolize_for_capacity(organism):
                        continue
                if self._fund_relation_formation(organism, pair):
                    relation = LivingStructure(pair, "RELATION", maintenance=self.config.relation_maintenance)
                    relation.strength = food
                    relation.evidence = 1.0
                    relation.income_rate = self.config.relation_income * food
                    organism.add_structure(organism.relations, relation)
                    organism.adjust_reserve(self.config.relation_income * food)
            else:
                organism.set_strength(relation, relation.strength + self.config.relation_income * food)
                relation.evidence += 1.0; relation.income_rate += self.config.relation_income * food
                organism.adjust_reserve(self.config.relation_income * food)
        organism.assimilated_total += assimilated
        organism.nutrition_consumed_total += assimilated
        self.result.consumed_nutrition_total += assimilated
        if self.result.consumed_nutrition_total > self.result.available_nutrition_total + 1e-12:
            raise AssertionError("nutrition conservation violated during digestion")
        organism.waste_total += len(bite) - assimilated

    def _fund_relation_formation(self, organism: MathematicalLifeOrganism, pair: Pair) -> bool:
        """Pay formation from the organism's single energy ledger."""
        return self._fund_cost(organism, self.config.relation_formation_cost)

    @staticmethod
    def _fund_cost(organism: MathematicalLifeOrganism, cost: float) -> bool:
        if organism.reserve < cost:
            return False
        organism.adjust_reserve(-cost)
        return True

    def _consolidate(self, organism: MathematicalLifeOrganism) -> None:
        for pair, relation in sorted(list(organism.relations.items())):
            before = relation.maintenance * max(1.0, relation.evidence)
            after = self.config.composite_maintenance * max(1.0, relation.evidence)
            useful_evidence = relation.evidence * (relation.strength / max(1.0, relation.evidence))
            if after + self.config.consolidation_formation_cost < before and useful_evidence > self.config.consolidation_formation_cost:
                composite = LivingStructure(pair, "COMPOSITE", maintenance=self.config.composite_maintenance, members=(pair,))
                composite.strength = relation.strength
                composite.evidence = relation.evidence
                composite.income_rate = relation.income_rate
                organism.add_structure(organism.composites, composite)
                organism.remove_structure(organism.relations, pair)
                if organism.first_consolidation_age is None:
                    organism.first_consolidation_age = organism.age_in_cycles
                self.result.events.append(LifecycleEvent(organism.id, organism.cursor, "CONSOLIDATE", repr(pair)))

    def _maintain_and_resorb(self, organism: MathematicalLifeOrganism) -> None:
        """Weaken continuously; physically resorb only under body-level scarcity.

        Definition: organism reserve follows ``E <- max(0, E-M(O))``;
        ordinary forgetting follows ``w_i <- max(1, rho*w_i)``.  Thus a weak
        structure remains a live part of the skeleton at strength one.  The
        body's linear metabolic load is ``M(O)=sum_i M_i``.  Deletion happens
        only when the organism cannot fund that next load, never merely because
        one otherwise-supported structure reached a low reserve.
        """
        organism.adjust_reserve(-self._body_maintenance(organism))
        for structure in organism._structures():
            delta = forgetting_delta(structure, self.config)
            organism.set_strength(structure, delta.strength_after)
            structure.income_rate = delta.income_rate_after
        # Long-term starvation is the only regular resorption trigger.  It is
        # evaluated on the whole body, not on a lone weak edge.
        while organism.size and organism.reserve < self._body_maintenance(organism):
            if not self._remove_weakest_structure(organism, reason="STARVATION", allow_critical=True):
                break

    @staticmethod
    def _body_maintenance(organism: MathematicalLifeOrganism) -> float:
        """Linear body metabolic load M(O)=sum_i maintenance_i, O(N(O))."""
        return sum(item.maintenance for item in organism._structures())

    def _under_metabolic_pressure(self, organism: MathematicalLifeOrganism, new_maintenance: float) -> bool:
        """Whether adding one structure would exceed the current reserve-backed body load."""
        return organism.reserve < self._body_maintenance(organism) + new_maintenance

    def _metabolize_for_capacity(self, organism: MathematicalLifeOrganism) -> bool:
        """Make room deterministically without breaking a stronger bridge.

        This is called only while creating a food-supported new structure under
        body-level pressure.  It is not a periodic garbage collector.
        """
        return self._remove_weakest_structure(organism, reason="METABOLIZE", allow_critical=False)

    def _remove_weakest_structure(self, organism: MathematicalLifeOrganism, *, reason: str, allow_critical: bool) -> bool:
        candidates: list[tuple[tuple[float, float, float, str, str], dict, str | Pair]] = []
        for collection in (organism.composites, organism.relations):
            for key, item in collection.items():
                if allow_critical or not self._is_critical_bridge(organism, key, item.strength):
                    candidates.append(((item.strength, item.evidence, item.income_rate, item.kind, repr(key)), collection, key))
        # An atom connected to any surviving edge is part of the current
        # skeleton; capacity metabolism prefers edges and isolated atoms.
        supported_atoms = {symbol for pair in (*organism.relations, *organism.composites) for symbol in pair}
        for key, item in organism.atoms.items():
            if allow_critical or key not in supported_atoms:
                candidates.append(((item.strength, item.evidence, item.income_rate, item.kind, repr(key)), organism.atoms, key))
        if not candidates:
            return False
        _, collection, key = min(candidates, key=lambda item: item[0])
        if not resorption_allowed(collection[key], organism, body_maintenance=self._body_maintenance(organism)):
            return False
        organism.remove_structure(collection, key)
        self.result.events.append(LifecycleEvent(organism.id, organism.cursor, "RESORB", f"{reason}:{key!r}"))
        return True

    def _is_critical_bridge(self, organism: MathematicalLifeOrganism, pair: Pair, edge_strength: float) -> bool:
        """Protect a weak edge when its removal disconnects stronger endpoint regions."""
        if pair[0] == pair[1] or pair not in {**organism.relations, **organism.composites}:
            return False
        baseline = self._components_without_boundary(organism, None)
        without = self._components_without_boundary(organism, tuple(sorted(pair)))
        if len(baseline) != 1 or len(without) <= len(baseline):
            return False
        return all(
            sum(organism.atoms[symbol].strength for symbol in component) > edge_strength
            for component in without
        )

    def _divide_if_profitable(self, organism: MathematicalLifeOrganism) -> None:
        edges = {**organism.relations, **organism.composites}
        if len(organism.atoms) < 2 or not edges:
            return
        by_boundary: dict[Pair, list[LivingStructure]] = defaultdict(list)
        for pair, edge in edges.items():
            if pair[0] != pair[1]:
                by_boundary[tuple(sorted(pair))].append(edge)
        candidates = []
        baseline_components = self._components_without_boundary(organism, None)
        if len(baseline_components) != 1:
            return
        for boundary, boundary_edges in by_boundary.items():
            # A boundary is a DIVIDE candidate only when its removal produces
            # exactly two non-empty components.  Ratio selection before this
            # topological filter can deterministically choose an invalid
            # multiway cut and mask valid two-way alternatives.
            regions = self._components_without_boundary(organism, boundary)
            if len(regions) != 2 or not all(regions):
                continue
            a, b = boundary
            boundary_strength = sum(edge.strength for edge in boundary_edges)
            local_mass = organism.atoms[a].strength + organism.atoms[b].strength + boundary_strength
            ratio = boundary_strength / local_mass if local_mass else 1.0
            candidates.append((ratio, boundary, boundary_edges, regions))
        if not candidates:
            return
        ratio, boundary, boundary_edges, regions = min(candidates, key=lambda item: (item[0], item[1]))
        if ratio >= self.config.boundary_ratio_limit:
            return
        child_region = min(regions, key=lambda region: (len(region), tuple(sorted(region))))
        parent_region = next(region for region in regions if region is not child_region)
        child_maintenance = self._region_maintenance(organism, child_region)
        parent_maintenance = self._region_maintenance(organism, parent_region)
        child_income = self._region_expected_income(organism, child_region)
        parent_income = self._region_expected_income(organism, parent_region)
        birth_gain = self.config.division_horizon * sum(edge.maintenance for edge in boundary_edges) - self.config.birth_cost
        if not (
            child_income > child_maintenance
            and parent_income > parent_maintenance
            and organism.reserve >= self.config.birth_cost
            and birth_gain > 0.0
        ):
            return
        before_size = organism.size
        before_strength = organism.total_strength
        before_reserve = organism.reserve
        boundary_strength = sum(edge.strength for edge in boundary_edges)
        child = organism.clone_region(child_region, child_id=self.next_id, birth_position=organism.cursor)
        self.next_id += 1
        for collection in (organism.relations, organism.composites):
            for pair in list(collection):
                if tuple(sorted(pair)) == boundary:
                    organism.remove_structure(collection, pair)
        self._pay_birth_cost(organism)
        organism.children_created += 1
        self.organisms[child.id] = child
        self.result.births.append(BirthEvent(
            birth_index=len(self.result.births) + 1,
            parent_id=organism.id,
            child_id=child.id,
            data_position=organism.cursor,
            parent_generation=organism.generation,
            parent_size_before=before_size,
            parent_total_strength=before_strength,
            parent_reserve=before_reserve,
            candidate_region=tuple(sorted(child_region)),
            boundary_strength=boundary_strength,
            child_generation=child.generation,
            child_size_at_birth=child.size,
            child_total_strength=child.total_strength,
            child_reserve=child.reserve,
            parent_size_after=organism.size,
            parent_strength_after=organism.total_strength,
            parent_reserve_after=organism.reserve,
            next_parent_bite=min(len(self.payload) - organism.cursor, organism.bite_limit(self.config)),
            next_child_bite=min(len(self.payload) - child.cursor, child.bite_limit(self.config)),
            child_size=child.size,
            reserve_before=before_reserve,
            reserve_after=organism.reserve + child.reserve,
            reason=f"boundary={boundary!r}, ratio={ratio:.6f}",
        ))
        self.result.events.append(LifecycleEvent(organism.id, organism.cursor, "DIVIDE", f"child={child.id}"))

    def _components_without_boundary(self, organism: MathematicalLifeOrganism, boundary: Pair | None) -> list[set[str]]:
        adjacency: dict[str, set[str]] = {atom: set() for atom in organism.atoms}
        for pair in (*organism.relations, *organism.composites):
            if boundary is not None and tuple(sorted(pair)) == boundary:
                continue
            if pair[0] not in adjacency or pair[1] not in adjacency:
                continue
            adjacency[pair[0]].add(pair[1])
            adjacency[pair[1]].add(pair[0])
        remaining = set(adjacency)
        components: list[set[str]] = []
        while remaining:
            seed = min(remaining, key=repr)
            component = {seed}
            queue: deque[str] = deque([seed])
            remaining.remove(seed)
            while queue:
                current = queue.popleft()
                for neighbour in sorted(adjacency[current], key=repr):
                    if neighbour in remaining:
                        remaining.remove(neighbour)
                        component.add(neighbour)
                        queue.append(neighbour)
            components.append(component)
        return components

    def _region_maintenance(self, organism: MathematicalLifeOrganism, region: set[str]) -> float:
        return sum(item.maintenance for symbol, item in organism.atoms.items() if symbol in region) + sum(
            item.maintenance for pair, item in {**organism.relations, **organism.composites}.items()
            if pair[0] in region and pair[1] in region
        )

    def _region_expected_income(self, organism: MathematicalLifeOrganism, region: set[str]) -> float:
        relevant = [item for symbol, item in organism.atoms.items() if symbol in region]
        relevant.extend(item for pair, item in {**organism.relations, **organism.composites}.items() if pair[0] in region and pair[1] in region)
        return sum(item.income_rate for item in relevant)

    def _pay_birth_cost(self, organism: MathematicalLifeOrganism) -> None:
        if not self._fund_cost(organism, self.config.birth_cost):
            raise AssertionError("division passed viability without affordable birth cost")

    def snapshot(self) -> dict:
        return {
            "cycles": self.result.cycles,
            "next_id": self.next_id,
            "organisms": [
                {
                    "id": item.id, "parent_id": item.parent_id, "generation": item.generation,
                    "cursor": item.cursor, "status": item.status.value, "age": item.age_in_cycles, "reserve": item.reserve,
                    "atoms": sorted((key, value.strength, value.income_rate) for key, value in item.atoms.items()),
                    "relations": sorted((key, value.strength, value.income_rate) for key, value in item.relations.items()),
                    "composites": sorted((key, value.strength, value.income_rate) for key, value in item.composites.items()),
                }
                for item in sorted(self.organisms.values(), key=lambda item: item.id)
            ],
        }
