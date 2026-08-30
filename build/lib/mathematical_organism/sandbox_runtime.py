from __future__ import annotations

"""Persistent sandbox with independently owned organism state."""

from dataclasses import dataclass
from collections import defaultdict, deque
import heapq
import json
from pathlib import Path
from time import perf_counter, sleep
from statistics import mean, median
from typing import Callable

from .destructive_ingest import BlockClaim, StreamingDestructiveFood
from .food import FoodNavigationState, _power_of_two_at_least
from .autonomous_core import AutonomousCore, HotPathMetrics
from .biology_rules import (
    BASE_RECEPTOR_MASS,
    ActivityCounters,
    ActivityLedger,
    REPRODUCTION_SPLIT_MINIMUM_STRENGTH,
    maintenance_weakening_budget,
    reproduction_allowed,
    structural_mass,
)
from .lifecycle import (
    LifecycleConfig, LifecycleEvent, LivingStructure, MathematicalLifeOrganism, OrganismStatus, PopulationResult,
)
from .territory import AutonomousTerritoryState, FoodTerritory


@dataclass(frozen=True, slots=True)
class Observation:
    kind: str
    organism_id: str | None = None
    detail: str = ""


@dataclass(slots=True)
class Corpse:
    """Neutral energy only: it intentionally stores no learned graph state."""
    territory: FoodTerritory
    remaining_energy: float
    source_organism_id: str | None = None

    @property
    def energy(self) -> float:
        """Compatibility view; corpse state is only ``remaining_energy``."""
        return self.remaining_energy


@dataclass(slots=True)
class GutChunk:
    """Unprocessed material; payload is present only for external bytes."""
    mass: int
    origin: str
    payload: tuple[int, ...] = ()
    nutrition: tuple[float, ...] = ()


@dataclass(slots=True)
class MaterialFlow:
    input_mass: int = 0
    assimilated_mass: int = 0
    rejected_mass: int = 0
    resorbed_mass: int = 0
    processed_mass: int = 0
    expelled_mass: int = 0
    external_expelled_mass: int = 0
    resorption_expelled_mass: int = 0
    structural_created_mass: int = 0
    structural_transferred_in: int = 0
    structural_transferred_out: int = 0

    def gut_mass(self, queue: "deque[GutChunk]") -> int:
        return sum(chunk.mass for chunk in queue)

    def gut_mass_by_origin(self, queue: "deque[GutChunk]", origin: str) -> int:
        return sum(chunk.mass for chunk in queue if chunk.origin == origin)


@dataclass(frozen=True, slots=True)
class DivisionMaterialTrace:
    """Read-only accounting record for one committed skeleton partition."""
    organism_id: str
    division_index: int
    structural_before: int
    parent_atoms_before: int
    parent_relations_before: int
    parent_composites_before: int
    selected_members_mass: int
    selected_internal_relation_mass: int
    selected_internal_composite_mass: int
    cross_split_relation_mass: int
    cross_split_composite_mass: int
    parent_structural_after: int
    child_structural_mass: int
    gut_before: int
    gut_after: int
    mass_sent_to_gut: int
    expelled_during_transaction: int
    delta: int
    parent_conservation_before: str | None
    parent_conservation_after: str | None
    child_conservation_after: str | None

    def snapshot(self) -> dict[str, object]:
        return {
            name: getattr(self, name)
            for name in self.__dataclass_fields__
        }


class SandboxObserver:
    """Append-only passive observer; runtime never reads it for decisions."""
    def __init__(self) -> None:
        self.events: list[Observation] = []

    def observe(self, kind: str, organism_id: str | None = None, detail: str = "") -> None:
        self.events.append(Observation(kind, organism_id, detail))


class AutonomousOrganism(AutonomousCore):
    """One organism owns its body, lifecycle ledger, navigation and territory."""

    def __init__(self, name: str = "ORG-ROOT", *, territory: FoodTerritory = FoodTerritory(), config: LifecycleConfig | None = None) -> None:
        self.name = name
        stable_name_id = int.from_bytes(name.encode("utf-8"), "little", signed=False) & 0x7FFFFFFF
        self.territory_state = AutonomousTerritoryState((0,) if name == "ORG-ROOT" else (stable_name_id,), territory)
        self.config = config or LifecycleConfig()
        self.config.validate()
        self.body = MathematicalLifeOrganism(0, None, 0, 0, 0, reserve=self.config.birth_reserve)
        self.result = PopulationResult()
        self.navigation: dict[str, FoodNavigationState] = {}
        self.local_claim_counter = 0
        self.children: list[AutonomousOrganism] = []
        self.biomass_consumed = 0.0
        self.metabolic_progress = 0
        self.metabolic_steps = 0
        self.parent_name: str | None = None
        self.hot_metrics: HotPathMetrics | None = None
        self.activity_ledger = ActivityLedger()
        self.gut_queue: deque[GutChunk] = deque()
        self.material_flow = MaterialFlow()
        self.division_material_traces: list[DivisionMaterialTrace] = []
        # Read-only execution diagnostics.  No lifecycle decision reads them.
        self.live_steps = 0
        self.successful_bites = 0
        self.wanted_bite_bytes = 0
        self.actual_bite_bytes = 0
        self.partial_bites = 0
        self.failed_food_lookups = 0
        self.last_claim_request = 0
        self.bytes_at_last_division = 0
        self.division_diagnostics: list[dict[str, object]] = []
        # Event indexes are organism-local.  Entries are immutable snapshots;
        # stale entries are rejected when popped after a later mutation.
        self.current_metabolic_epoch = 0
        self.maintenance_deficit = 0.0
        self.maintenance_deficit_total = 0.0
        self.maintenance_paid_total = 0.0
        self.weakening_events = 0
        self.maintenance_full_scans = 0
        self._index_serial = 0
        self._weakness_queue: list[tuple[float, float, float, str, str, int, object]] = []
        self.member_weights: dict[object, float] = {}
        self.weakest_weight: float | None = None
        self.weakest_members: tuple[object, ...] = ()
        self._member_adjacency: dict[object, set[object]] = {}
        self._member_incident: dict[object, list[tuple[str, object]]] = {}
        self._weakness_cache_valid = False
        self._defer_weakness_rebuild = 0

    def enable_hot_profile(self) -> HotPathMetrics:
        """Enable diagnostic timing explicitly; normal feeding pays nothing."""
        self.hot_metrics = HotPathMetrics()
        return self.hot_metrics

    @property
    def alive(self) -> bool:
        return self.territory_state.alive and self.body.status is OrganismStatus.ALIVE

    def _state_for(self, food: StreamingDestructiveFood) -> FoodNavigationState:
        return self.navigation.setdefault(
            food.source_hash,
            FoodNavigationState(0, 0xF00D, min(65536, _power_of_two_at_least(food.block_count)), food.block_count),
        )

    def _claim(self, food: StreamingDestructiveFood) -> BlockClaim | None:
        started = perf_counter() if self.hot_metrics is not None else 0.0
        wanted = self.body.bite_limit(self.config)
        self.last_claim_request = wanted
        self.wanted_bite_bytes += wanted
        active_claim = getattr(food, "claim_active", None)
        if active_claim is not None:
            claim = active_claim(wanted, self.territory_state.territory)
            if claim is not None:
                if self.hot_metrics is not None:
                    self.hot_metrics.add("food_lookup", started)
                return claim
        state = self._state_for(food)
        for skipped in range(max(1, state.node_count * 2)):
            block_id = state.next_parcel()
            if block_id is None:
                continue
            # Territory is a property of a whole physical block.  Check it
            # before making any claim so a foreign block is never reserved,
            # even transiently.
            if not self.territory_state.territory.owns_block(food.source_hash, block_id):
                continue
            claim = food.claim(
                block_id,
                wanted,
                skipped_regions=skipped,
                territory=self.territory_state.territory,
            )
            if claim is not None:
                if self.hot_metrics is not None:
                    self.hot_metrics.add("food_lookup", started)
                return claim
        self.failed_food_lookups += 1
        if self.hot_metrics is not None:
            self.hot_metrics.add("food_lookup", started)
        return None

    def metabolic_work_threshold(self) -> int:
        """Food volume required for one full metabolic step.

        The threshold depends only on the current living body and configuration,
        so splitting the same food into different physical bite sizes does not
        create a different maintenance cadence.
        """
        return max(self.config.metabolic_minimum_work, self.body.size)

    def _collection_for_kind(self, kind: str) -> dict:
        if kind == "ATOM":
            return self.body.atoms
        if kind == "RELATION":
            return self.body.relations
        if kind == "COMPOSITE":
            return self.body.composites
        raise ValueError(f"unknown structure kind {kind!r}")

    def note_structure_changed(self, structure: LivingStructure, *, refresh_weakness: bool = True) -> None:
        """Refresh local weakness snapshots after one known mutation."""
        self._index_serial += 1
        serial = self._index_serial
        key_text = repr(structure.key)
        heapq.heappush(
            self._weakness_queue,
            (structure.strength, structure.evidence, structure.income_rate, structure.kind, key_text, serial, structure.key),
        )
        if refresh_weakness and self._defer_weakness_rebuild:
            self._weakness_cache_valid = False
        elif refresh_weakness:
            self.recompute_weakness_cache()

    def recompute_weakness_cache(self) -> None:
        """Event-driven O(V + E) member cohesion cache rebuild.

        A member's weight is the weakest live incident relation/composite.
        This bottleneck cohesion measure makes a weak neck visible even when
        both of its endpoints also have strong internal links.  An isolated
        member has weight zero.  Weight is cohesion information only, never
        energy.
        """
        started = perf_counter() if self.hot_metrics is not None else 0.0
        # Runtime skeletons normally materialise all endpoint receptors.  The
        # endpoint union also keeps older, relation-only reference fixtures
        # meaningful without inventing learned atoms.
        members = set(self.body.atoms)
        for collection in (self.body.relations, self.body.composites):
            for left, right in collection:
                members.add(left)
                members.add(right)
        weights = {key: 0.0 for key in members}
        adjacency = {key: set() for key in members}
        incident = {key: [] for key in members}
        for kind, collection in (("RELATION", self.body.relations), ("COMPOSITE", self.body.composites)):
            for key, structure in collection.items():
                left, right = key
                if left not in weights or right not in weights:
                    continue
                weights[left] = structure.strength if weights[left] == 0.0 else min(weights[left], structure.strength)
                weights[right] = structure.strength if weights[right] == 0.0 else min(weights[right], structure.strength)
                adjacency[left].add(right)
                adjacency[right].add(left)
                incident[left].append((kind, key))
                if right != left:
                    incident[right].append((kind, key))
        self.member_weights = weights
        self._member_adjacency = adjacency
        self._member_incident = incident
        if weights:
            minimum = min(weights.values())
            self.weakest_weight = minimum
            self.weakest_members = tuple(sorted((key for key, value in weights.items() if value == minimum), key=repr))
        else:
            self.weakest_weight = None
            self.weakest_members = ()
        self._weakness_cache_valid = True
        if self.hot_metrics is not None:
            self.hot_metrics.add("weakness_cache_rebuild", started)

    def get_weakest_members(self) -> tuple[object, ...]:
        """O(1) cached weakest-member lookup; no graph traversal."""
        if not self._weakness_cache_valid:
            self.recompute_weakness_cache()
        return self.weakest_members

    def rebuild_metabolic_indexes(self) -> None:
        """One-time deterministic index bootstrap; never used by a maintenance step."""
        self._weakness_queue.clear()
        for structure in self.body._structures():
            self.note_structure_changed(structure, refresh_weakness=False)
        self.recompute_weakness_cache()

    def _pop_weakest_live(self) -> LivingStructure | None:
        while self._weakness_queue:
            strength, evidence, income, kind, _key_text, _serial, key = heapq.heappop(self._weakness_queue)
            candidate = self._collection_for_kind(kind).get(key)
            if candidate is None:
                continue
            if (candidate.strength, candidate.evidence, candidate.income_rate) != (strength, evidence, income):
                continue
            return candidate
        return None

    def _withdraw_reserve(self, requested: float) -> float:
        """Settle from the organism's single O(1) reserve ledger."""
        paid = min(max(0.0, requested), self.body.reserve)
        self.body.adjust_reserve(-paid)
        return paid

    def _detach_structure(self, structure: LivingStructure, reason: str) -> int:
        collection = self._collection_for_kind(structure.kind)
        if collection.get(structure.key) is not structure:
            return 0
        removed = self.body.remove_structure(collection, structure.key)
        mass = structural_mass(removed.strength) if removed.kind in {"RELATION", "COMPOSITE"} else 0
        if mass:
            self.enqueue_resorbed_material(mass)
        self.result.events.append(LifecycleEvent(self.body.id, self.body.cursor, "RESORB", f"{reason}:{removed.key!r}"))
        return mass

    def _detach_member(self, member_key: object, reason: str) -> int:
        """Detach one member and only its locally incident skeleton objects."""
        if not self._weakness_cache_valid:
            self.recompute_weakness_cache()
        incident = tuple(self._member_incident.get(member_key, ()))
        member = self.body.atoms.get(member_key)
        if member is None and not incident:
            return 0
        resorbed = 0
        for kind, key in incident:
            collection = self._collection_for_kind(kind)
            structure = collection.get(key)
            if structure is None:
                continue
            removed = self.body.remove_structure(collection, key)
            mass = structural_mass(removed.strength)
            if mass:
                self.enqueue_resorbed_material(mass)
                resorbed += mass
        if member is not None:
            self.body.remove_structure(self.body.atoms, member_key)
        self.result.events.append(LifecycleEvent(self.body.id, self.body.cursor, "RESORB_MEMBER", f"{reason}:{member_key!r}"))
        self.recompute_weakness_cache()
        return resorbed

    def _apply_maintenance_deficit(self, deficit: float) -> tuple[int, int]:
        """Weaken only due weakest candidates; no all-structure maintenance pass."""
        weakened = 0
        resorbed = 0
        for _ in range(maintenance_weakening_budget(deficit, self.body.body_mass)):
            members = self.get_weakest_members()
            if not members:
                break
            member_key = members[0]
            candidate = self.body.atoms.get(member_key)
            if candidate is None:
                # Compatibility only for a legacy relation-only fixture: a
                # real organism always has receptor members.  Its endpoint is
                # still a member, so operate on one local incident object.
                incident = self._member_incident.get(member_key, ())
                if not incident:
                    self._weakness_cache_valid = False
                    continue
                kind, key = min(incident, key=lambda item: (self._collection_for_kind(item[0])[item[1]].strength, item[0], repr(item[1])))
                structure = self._collection_for_kind(kind).get(key)
                if structure is None:
                    self._weakness_cache_valid = False
                    continue
                if structure.strength <= 1.0:
                    resorbed += self._detach_member(member_key, "MAINTENANCE_DEFICIT")
                else:
                    old_mass = structural_mass(structure.strength)
                    self.body.set_strength(structure, max(1.0, structure.strength - 1.0))
                    lost_mass = old_mass - structural_mass(structure.strength)
                    if lost_mass:
                        self.enqueue_resorbed_material(lost_mass)
                    self.note_structure_changed(structure)
                    weakened += 1
                continue
            if candidate.strength <= 1.0:
                resorbed += self._detach_member(member_key, "MAINTENANCE_DEFICIT")
                continue
            # Maintenance failure acts on the selected member.  Its incident
            # links define why it was selected but are removed only if member
            # detachment later invalidates them.
            new_strength = max(1.0, candidate.strength - 1.0)
            self.body.set_strength(candidate, new_strength)
            self.note_structure_changed(candidate)
            self.result.events.append(LifecycleEvent(self.body.id, self.body.cursor, "WEAKEN_MEMBER", f"MAINTENANCE_DEFICIT:{candidate.key!r}"))
            weakened += 1
        self.weakening_events += weakened
        return weakened, resorbed

    def run_maintenance_settlement(self) -> tuple[float, float, int, int]:
        """Settle aggregate maintenance then express only its deficit as decay.

        Returns ``(required, paid, weakened, resorbed_mass)``.  All aggregate
        values are cached; candidate work is heap-driven and local.
        """
        self.current_metabolic_epoch += 1
        required = self.body.cached_maintenance()
        paid = self._withdraw_reserve(required)
        deficit = required - paid
        self.maintenance_paid_total += paid
        self.maintenance_deficit = deficit
        self.maintenance_deficit_total += deficit
        weakened, resorbed = self._apply_maintenance_deficit(deficit) if deficit > 0.0 else (0, 0)
        return required, paid, weakened, resorbed

    def live_step(self, sandbox: "SandboxRuntime") -> None:
        """The organism itself discovers, ingests and immediately continues."""
        if not self.alive:
            return
        self.live_steps += 1
        self._reclaim_sibling_if_available(sandbox)
        if not sandbox.has_active_food():
            sandbox.ingest_one_available(self)
        # A committed physical bite must already have completed DIGEST.  When
        # older external or resorbed material is pending, this life step spends
        # its one shared throughput on that backlog and deliberately does not
        # claim another byte range yet.  This is backpressure, not a second
        # capacity lane: a full gut cannot make a new bite durable early.
        if self.gut_queue:
            started = perf_counter() if self.hot_metrics is not None else 0.0
            self.process_gut(self.body.bite_limit(self.config))
            if self.hot_metrics is not None:
                self.hot_metrics.add("metabolism", started)
            return
        ate = False
        for food in sandbox.food_sources.values():
            claim = self._claim(food)
            if claim is None:
                continue
            started = perf_counter() if self.hot_metrics is not None else 0.0
            bite = food.read(claim)
            if self.hot_metrics is not None:
                self.hot_metrics.add("read", started)
            try:
                self.result.available_nutrition_total += len(bite)
                self.enqueue_external_material(bite)
                self.process_gut(self.body.bite_limit(self.config))
            except Exception:
                raise
            else:
                started = perf_counter() if self.hot_metrics is not None else 0.0
                food.consume(claim)
                if self.hot_metrics is not None:
                    self.hot_metrics.add("commit", started)
                self.local_claim_counter += 1
                self.successful_bites += 1
                self.actual_bite_bytes += claim.length
                if claim.length < self.last_claim_request:
                    self.partial_bites += 1
                self.metabolic_progress += claim.length
                ate = True
                sandbox.note_bite(self.name, claim.length)
            finally:
                del bite
            break
        if not ate:
            sandbox.refresh_food_sources()
            self._consume_corpse(sandbox)
            self.process_gut(self.body.bite_limit(self.config))
            # No clock-based starvation.  An already unpaid maintenance event,
            # however, is real pending biological work and progresses locally.
            if self.maintenance_deficit > 0.0 and self.body.size:
                self.run_maintenance_settlement()
                if self.body.size == 0:
                    self._die(sandbox)
        if ate:
            started = perf_counter() if self.hot_metrics is not None else 0.0
            self._run_due_metabolic_steps(sandbox)
            if self.hot_metrics is not None:
                self.hot_metrics.add("metabolic_schedule", started)
            return
        # An empty bootstrap body has no maintenance burden.  It remains an
        # autonomous listener until physical FOOD appears.
        if self.body.size == 0:
            return
        # No wall-clock starvation: an idle organism produces no meaningful
        # work debt.  Future hibernation can choose how it waits for FOOD.
        return

    def enqueue_external_material(self, bite: tuple[int, ...], nutrition: tuple[float, ...] | None = None) -> None:
        allocation = nutrition if nutrition is not None else (1.0,) * len(bite)
        if len(bite) != len(allocation):
            raise ValueError("gut payload and nutrition differ")
        self.gut_queue.append(GutChunk(len(bite), "external", bite, allocation))
        self.material_flow.input_mass += len(bite)

    def enqueue_resorbed_material(self, mass: int) -> None:
        if mass <= 0:
            return
        self.gut_queue.append(GutChunk(mass, "resorption"))
        self.material_flow.resorbed_mass += mass

    @property
    def gut_mass(self) -> int:
        """Material waiting for the single shared metabolic throughput."""
        return self.material_flow.gut_mass(self.gut_queue)

    def verify_material_conservation(self) -> None:
        """Check material ledgers without treating strength or reserve as mass.

        External byte material is either retained as accepted evidence, rejected
        and expelled, or still awaiting digestion.  Learned structural material
        is introduced only by recorded positive mass deltas and subsequently is
        either still present in the body or in/resolved from the resorption path.
        """
        flow = self.material_flow
        external_gut = flow.gut_mass_by_origin(self.gut_queue, "external")
        resorption_gut = flow.gut_mass_by_origin(self.gut_queue, "resorption")
        if flow.input_mass != flow.assimilated_mass + flow.external_expelled_mass + external_gut:
            raise AssertionError("external material conservation failed")
        if flow.rejected_mass != flow.external_expelled_mass:
            raise AssertionError("rejected material was not expelled exactly once")
        if flow.resorbed_mass != flow.resorption_expelled_mass + resorption_gut:
            raise AssertionError("resorbed structural material conservation failed")
        dynamic_body_mass = self.body.body_mass - BASE_RECEPTOR_MASS
        created = flow.structural_created_mass + flow.structural_transferred_in
        accounted = dynamic_body_mass + flow.resorbed_mass + flow.structural_transferred_out
        if created != accounted:
            raise AssertionError(
                "structural material conservation failed: "
                f"created={flow.structural_created_mass} inherited={flow.structural_transferred_in} "
                f"current={dynamic_body_mass} resorbed={flow.resorbed_mass} transferred={flow.structural_transferred_out}"
            )

    def material_conservation_error(self) -> str | None:
        """Read-only local-ledger check used by transaction telemetry."""
        try:
            self.verify_material_conservation()
        except AssertionError as error:
            return str(error) or error.__class__.__name__
        return None

    def process_gut(self, capacity: int) -> int:
        """Process at most one current bite of shared external/internal material."""
        remaining = max(0, capacity); processed = 0
        while remaining and self.gut_queue:
            chunk = self.gut_queue[0]; amount = min(remaining, chunk.mass)
            if chunk.origin == "external":
                payload, nutrition = chunk.payload[:amount], chunk.nutrition[:amount]
                trace: dict[str, int] = {}; mass_before = self.body.body_mass
                # DIGEST can mutate hundreds of local objects in one bite.
                # Its member cache is rebuilt once at the bite boundary, not
                # once per byte-level relation mutation.  No biological rule
                # observes the cache within this atomic digestion interval.
                self._defer_weakness_rebuild += 1
                try:
                    self.digest(self.body, payload, nutrition, trace)
                finally:
                    self._defer_weakness_rebuild -= 1
                    if self._defer_weakness_rebuild == 0 and not self._weakness_cache_valid:
                        self.recompute_weakness_cache()
                self._record_digest_activity(trace, payload)
                accepted = trace["assimilated_bytes"]
                rejected = amount - accepted
                self.material_flow.assimilated_mass += accepted
                self.material_flow.rejected_mass += rejected
                self.material_flow.expelled_mass += rejected
                self.material_flow.external_expelled_mass += rejected
                # Gross structural creation is not the same thing as the net
                # body-mass delta: a pressure-triggered resorption may occur
                # in the same DIGEST transaction.  The digest trace records
                # the canonical local creation deltas before that loss.
                self.material_flow.structural_created_mass += trace["structural_mass_created"]
                if amount == chunk.mass:
                    self.gut_queue.popleft()
                else:
                    chunk.mass -= amount; chunk.payload = chunk.payload[amount:]; chunk.nutrition = chunk.nutrition[amount:]
                payer = self.body.atoms.get(payload[-1]) if payload else None
                self._record_material_cost(amount, rejected, 0, payer)
            elif chunk.origin == "resorption":
                self.material_flow.expelled_mass += amount
                self.material_flow.resorption_expelled_mass += amount
                if amount == chunk.mass:
                    self.gut_queue.popleft()
                else:
                    chunk.mass -= amount
                payer = next(iter(self.body.atoms.values()), None)
                self._record_material_cost(amount, 0, amount, payer)
            else:
                raise AssertionError("unknown gut material origin")
            self.material_flow.processed_mass += amount
            processed += amount; remaining -= amount
        self._settle_activity_debt()
        return processed

    def _record_material_cost(self, processed: int, rejected: int, resorbed: int, payer: LivingStructure | None) -> None:
        amount = self.activity_ledger.add_activity(
            # External DIGEST charges its throughput in _record_digest_activity.
            # This path charges only disposal work; resorption has no DIGEST.
            ActivityCounters(rejected_bytes=rejected, resorbed_processed_bytes=resorbed), self.body.body_mass,
        )
        del payer

    def _record_digest_activity(self, trace: dict[str, int], bite: tuple[int, ...]) -> None:
        before = int(trace["body_mass_before"]); after = int(trace["body_mass_after"])
        counters = ActivityCounters(
            bytes_eaten=len(bite),
            processed_bytes=len(bite),
            relations_created=trace["relations_created"],
            relations_strengthened=trace["relations_strengthened"],
            composites_created=trace["composites_created"],
            composites_strengthened=trace["composites_strengthened"],
            structural_mass_added=max(0, after - before),
            structural_mass_lost=max(0, before - after),
        )
        amount = self.activity_ledger.add_activity(counters, self.body.body_mass)
        del amount

    def _settle_activity_debt(self) -> bool:
        """Pay activity debt only from recorded active sources, never a body scan."""
        threshold = self.activity_ledger.settlement_threshold(self.body.body_mass)
        if self.activity_ledger.metabolic_debt < threshold:
            return False
        basal = self.activity_ledger.basal_cost(self.body.body_mass)
        self.activity_ledger.metabolic_debt += basal
        paid = min(self.body.reserve, self.activity_ledger.metabolic_debt)
        self.body.adjust_reserve(-paid)
        self.activity_ledger.metabolic_debt -= paid
        if paid > 0.0:
            self.activity_ledger.energy_spent += paid
            self.activity_ledger.settlements += 1
        return paid > 0.0

    def _run_due_metabolic_steps(self, sandbox: "SandboxRuntime") -> None:
        while self.alive and self.metabolic_progress >= self.metabolic_work_threshold():
            self.metabolic_progress -= self.metabolic_work_threshold()
            self._run_metabolic_step(sandbox)

    def _run_metabolic_step(self, sandbox: "SandboxRuntime") -> None:
        """The expensive biological phase, charged by food volume not bites."""
        lifecycle_trace: dict[str, int] = {}
        events_before = len(self.result.events)
        mass_before = self.body.body_mass
        self.consolidate(self.body, lifecycle_trace)
        required, paid, weakened, resorbed_mass = self.run_maintenance_settlement()
        resorptions = sum(event.kind == "RESORB" for event in self.result.events[events_before:])
        lifecycle_counters = ActivityCounters(
            composites_created=lifecycle_trace.get("composites_created", 0),
            structural_mass_added=max(0, self.body.body_mass - mass_before),
            structural_mass_lost=max(0, mass_before - self.body.body_mass),
            resorption_events=resorptions,
        )
        self.material_flow.structural_created_mass += max(0, self.body.body_mass - mass_before)
        amount = self.activity_ledger.add_activity(lifecycle_counters, self.body.body_mass)
        del amount
        self._settle_activity_debt()
        self.body.age_in_cycles += 1
        self.metabolic_steps += 1
        started = perf_counter() if self.hot_metrics is not None else 0.0
        child = self._reproduce_conservatively()
        if child is None:
            # A weak-neck split remains a structural-specialisation mechanism;
            # it is no longer the sole reproduction path.
            child = self._divide_locally()
        if self.hot_metrics is not None:
            self.hot_metrics.add("division_candidate_evaluation", started)
        if child is not None:
            # Division is a topology-changing event, not a maintenance step.
            # Rebuild both local event indexes once from their conserved new
            # skeletons so neither parent nor child retains stale candidates.
            self.rebuild_metabolic_indexes()
            child.rebuild_metabolic_indexes()
            sandbox.register_child(self, child)
            amount = self.activity_ledger.add_activity(ActivityCounters(division_events=1), self.body.body_mass)
            del amount
            self._settle_activity_debt()
        if self.body.size == 0:
            self._die(sandbox)

    def _partition_plan(self, child_atoms: set[object], *, require_maturity: bool) -> tuple[list[object], list[LivingStructure], list[LivingStructure], list[LivingStructure], list[LivingStructure]] | None:
        """Build an immutable division plan without changing the parent.

        The five lists are child atom keys, child internal edges, parent
        internal edges, cross-partition edges, and retained parent structures.
        Only the commit phase moves objects; this makes an invalid candidate a
        genuine no-op.
        """
        parent_atoms = set(self.body.atoms) - child_atoms
        if not child_atoms or not parent_atoms:
            return None
        child_edges: list[LivingStructure] = []
        parent_edges: list[LivingStructure] = []
        cross_edges: list[LivingStructure] = []
        for collection in (self.body.relations, self.body.composites):
            for _key, item in sorted(collection.items(), key=lambda entry: repr(entry[0])):
                left, right = item.key
                if left in child_atoms and right in child_atoms:
                    child_edges.append(item)
                elif left in parent_atoms and right in parent_atoms:
                    parent_edges.append(item)
                else:
                    cross_edges.append(item)
        child_items = [*(self.body.atoms[key] for key in sorted(child_atoms, key=repr)), *child_edges]
        parent_items = [*(self.body.atoms[key] for key in sorted(parent_atoms, key=repr)), *parent_edges]
        assessment = reproduction_allowed(self.body, self.config, selected_count=len(child_items))
        if (require_maturity and not assessment.allowed) or not parent_items:
            return None
        # Every cross edge is invalid on both sides; its learned structural
        # mass is routed to gut.  It has no reserve to transfer.
        return sorted(child_atoms, key=repr), child_edges, parent_edges, cross_edges, parent_items

    def _commit_skeleton_partition(self, child_atoms: set[object], *, require_maturity: bool = True) -> "AutonomousOrganism | None":
        """Move a viable skeleton partition to a new organism, never clone it."""
        started = perf_counter() if self.hot_metrics is not None else 0.0
        plan = self._partition_plan(child_atoms, require_maturity=require_maturity)
        if plan is None:
            return None
        child_atom_keys, child_edges, _parent_edges, cross_edges, parent_items = plan
        before_mass = self.body.body_mass - BASE_RECEPTOR_MASS
        before_strength = self.body.total_strength
        before_reserve = self.body.reserve
        gut_before = self.gut_mass
        parent_conservation_before = self.material_conservation_error()
        relation_count_before = len(self.body.relations)
        composite_count_before = len(self.body.composites)
        selected_relation_mass = sum(structural_mass(item.strength) for item in child_edges if item.kind == "RELATION")
        selected_composite_mass = sum(structural_mass(item.strength) for item in child_edges if item.kind == "COMPOSITE")
        cross_relation_mass = sum(structural_mass(item.strength) for item in cross_edges if item.kind == "RELATION")
        cross_composite_mass = sum(structural_mass(item.strength) for item in cross_edges if item.kind == "COMPOSITE")

        # Everything above was read-only.  Territory changes only after both
        # sides passed the existing viability predicate.
        child_state = self.territory_state.divide_territory()
        child = AutonomousOrganism(
            "ORG-" + "-".join(map(str, child_state.organism_id)), territory=child_state.territory, config=self.config,
        )
        child.territory_state = child_state
        child.parent_name = self.name
        child.body = MathematicalLifeOrganism(0, None, self.body.cursor, self.body.generation + 1, self.body.cursor, reserve=0.0)

        for item in cross_edges:
            self.body.remove_structure(self._collection_for_kind(item.kind), item.key)
            mass = structural_mass(item.strength)
            if mass:
                self.enqueue_resorbed_material(mass)

        for key in child_atom_keys:
            child.body.add_structure(child.body.atoms, self.body.remove_structure(self.body.atoms, key))
        for item in child_edges:
            source = self._collection_for_kind(item.kind)
            target = child.body.relations if item.kind == "RELATION" else child.body.composites
            child.body.add_structure(target, self.body.remove_structure(source, item.key))

        self.pay_birth_cost(self.body)
        child.body.reserve = 0.0
        self.body.refresh_resource_cache()
        child.body.refresh_resource_cache()
        moved_mass = child.body.body_mass - BASE_RECEPTOR_MASS
        self.material_flow.structural_transferred_out += moved_mass
        child.material_flow.structural_transferred_in += moved_mass
        self.body.children_created += 1
        self.rebuild_metabolic_indexes()
        child.rebuild_metabolic_indexes()

        after_mass = (self.body.body_mass - BASE_RECEPTOR_MASS) + moved_mass
        tolerance = 1e-9 * max(1.0, before_strength, before_reserve)
        if before_mass != after_mass + sum(structural_mass(item.strength) for item in cross_edges):
            raise AssertionError("division structural mass mismatch")
        if abs(before_reserve - (self.body.reserve + self.config.birth_cost)) > tolerance:
            raise AssertionError("division manufactured reserve")
        parent_after = self.body.body_mass - BASE_RECEPTOR_MASS
        gut_after = self.gut_mass
        mass_sent_to_gut = gut_after - gut_before
        trace = DivisionMaterialTrace(
            organism_id=self.name,
            division_index=len(self.division_material_traces) + 1,
            structural_before=before_mass,
            parent_atoms_before=len(child_atom_keys) + len(self.body.atoms),
            parent_relations_before=relation_count_before,
            parent_composites_before=composite_count_before,
            selected_members_mass=0,
            selected_internal_relation_mass=selected_relation_mass,
            selected_internal_composite_mass=selected_composite_mass,
            cross_split_relation_mass=cross_relation_mass,
            cross_split_composite_mass=cross_composite_mass,
            parent_structural_after=parent_after,
            child_structural_mass=moved_mass,
            gut_before=gut_before,
            gut_after=gut_after,
            mass_sent_to_gut=mass_sent_to_gut,
            expelled_during_transaction=0,
            delta=before_mass - parent_after - moved_mass - mass_sent_to_gut,
            parent_conservation_before=parent_conservation_before,
            parent_conservation_after=self.material_conservation_error(),
            child_conservation_after=child.material_conservation_error(),
        )
        self.division_material_traces.append(trace)
        if trace.delta != 0:
            raise AssertionError("division structural transaction conservation failed")
        self.children.append(child)
        self.division_diagnostics.append({
            "organism_id": self.name,
            "generation": self.body.generation,
            "body_before": before_mass + BASE_RECEPTOR_MASS,
            "bite_size": max(self.config.bite_minimum, before_mass + BASE_RECEPTOR_MASS),
            "reserve": before_reserve,
            "weakest_weight": self.weakest_weight,
            "bytes_since_birth": self.body.consumed_total,
            "bytes_since_previous_division": self.body.consumed_total - self.bytes_at_last_division,
            "live_steps": self.live_steps,
            "accepted": True,
            "parent_body_after": self.body.body_mass,
            "child_body": child.body.body_mass,
            "child_reserve": child.body.reserve,
        })
        self.bytes_at_last_division = self.body.consumed_total
        if self.hot_metrics is not None:
            self.hot_metrics.add("division_commit", started)
        return child

    def _reproduce_conservatively(self) -> "AutonomousOrganism | None":
        """Try local partitions exposed by the cached weakest member.

        Removing one weak member is not a global graph optimisation: it only
        reveals the connected regions immediately separated by that member.
        Candidate regions are then validated transactionally by the existing
        maturity/viability rule.
        """
        active = {key for key, item in self.body.atoms.items() if item.strength >= REPRODUCTION_SPLIT_MINIMUM_STRENGTH}
        if len(active) < 3:
            return None
        for boundary_member in self.get_weakest_members():
            remaining = active - {boundary_member}
            if len(remaining) < 2:
                continue
            components: list[set[object]] = []
            unseen = set(remaining)
            while unseen:
                seed = min(unseen, key=repr)
                component = {seed}
                queue = deque([seed])
                unseen.remove(seed)
                while queue:
                    current = queue.popleft()
                    for neighbour in sorted(self._member_adjacency.get(current, ()), key=repr):
                        if neighbour in unseen:
                            unseen.remove(neighbour)
                            component.add(neighbour)
                            queue.append(neighbour)
                components.append(component)
            # Preserve each strong local component.  The deterministic order
            # merely selects among already-local alternatives.
            for candidate in sorted(components, key=lambda region: (len(region), tuple(sorted(region, key=repr)))):
                child = self._commit_skeleton_partition(candidate)
                if child is not None:
                    return child
        return None

    def _reclaim_sibling_if_available(self, sandbox: "SandboxRuntime") -> bool:
        path = self.territory_state.territory.path
        if not path:
            return False
        sibling = FoodTerritory(path[:-1] + (1 - path[-1],))
        if sandbox.is_territory_unoccupied(sibling, excluding=self):
            self.territory_state.territory = FoodTerritory(path[:-1])
            sandbox.update_territory(self.name, self.territory_state.territory)
            sandbox.observer.observe("TERRITORY_RECLAIM", self.name, "D" + "".join(map(str, path[:-1])) )
            return True
        return False

    def _consume_corpse(self, sandbox: "SandboxRuntime") -> float:
        """Transfer neutral corpse energy to reserve, never to learned state."""
        if not hasattr(sandbox, "take_corpse_energy"):
            return 0.0
        gained = sandbox.take_corpse_energy(self.territory_state.territory, self.body.bite_limit(self.config), self.name)
        if gained <= 0.0:
            return 0.0
        before = self.body.reserve
        self.body.adjust_reserve(gained)
        self.biomass_consumed += gained
        self.result.consumed_nutrition_total += gained
        if abs((before + gained) - self.body.reserve) > 1e-12:
            raise AssertionError("corpse energy conservation violated")
        return gained

    def _die(self, sandbox: "SandboxRuntime") -> Corpse | None:
        """Stop life, release space, preserve only neutral body energy."""
        if not self.alive:
            raise RuntimeError("organism is already dead")
        reserve_before_death = self.body.reserve
        corpse = Corpse(self.territory_state.territory, reserve_before_death) if reserve_before_death > 0.0 else None
        if corpse is not None:
            sandbox.add_corpse(corpse, self.name)
        self.body.atoms.clear()
        self.body.relations.clear()
        self.body.composites.clear()
        self.member_weights.clear()
        self.weakest_weight = None
        self.weakest_members = ()
        self._member_adjacency.clear()
        self._member_incident.clear()
        self._weakness_cache_valid = True
        self.body.status = OrganismStatus.DEAD
        self.territory_state.die()
        sandbox.release_territory(self.name, corpse.territory if corpse is not None else self.territory_state.territory)
        marker = getattr(sandbox, "mark_organism_dead", None)
        if marker is not None:
            marker(self.name)
        sandbox.observer.observe("ORG_DEATH", self.name)
        if corpse is not None:
            sandbox.observer.observe("CORPSE_CREATED", self.name, f"{reserve_before_death:.6f}")
        return corpse

    def _divide_locally(self) -> "AutonomousOrganism | None":
        """Unchanged DIVIDE predicate; only child identity/territory is local."""
        edges = {**self.body.relations, **self.body.composites}
        if len(self.body.atoms) < 2 or not edges or len(self.components_without_boundary(self.body, None)) != 1:
            return None
        by_boundary: dict[tuple[str, str], list[object]] = defaultdict(list)
        for pair, edge in edges.items():
            if pair[0] != pair[1] and pair[0] in self.body.atoms and pair[1] in self.body.atoms:
                by_boundary[tuple(sorted(pair))].append(edge)
        candidates = []
        for boundary, boundary_edges in by_boundary.items():
            regions = self.components_without_boundary(self.body, boundary)
            if len(regions) != 2 or not all(regions):
                continue
            a, b = boundary
            strength = sum(edge.strength for edge in boundary_edges)
            mass = self.body.atoms[a].strength + self.body.atoms[b].strength + strength
            candidates.append((strength / mass if mass else 1.0, boundary, boundary_edges, regions))
        if not candidates:
            return None
        ratio, boundary, boundary_edges, regions = min(candidates, key=lambda item: (item[0], item[1]))
        if ratio >= self.config.boundary_ratio_limit:
            return None
        child_region = min(regions, key=lambda region: (len(region), tuple(sorted(region))))
        parent_region = next(region for region in regions if region is not child_region)
        child_ok = self.region_income(self.body, child_region) > self.region_maintenance(self.body, child_region)
        parent_ok = self.region_income(self.body, parent_region) > self.region_maintenance(self.body, parent_region) and self.body.reserve >= self.config.birth_cost
        gain = self.config.division_horizon * sum(edge.maintenance for edge in boundary_edges) - self.config.birth_cost
        if not (child_ok and parent_ok and gain > 0.0):
            return None
        return self._commit_skeleton_partition(set(child_region), require_maturity=False)

    def spawn_child(self) -> "AutonomousOrganism":
        child_state = self.territory_state.divide_territory()
        child = AutonomousOrganism(
            name="ORG-" + "-".join(map(str, child_state.organism_id)),
            territory=child_state.territory,
            config=self.config,
        )
        child.territory_state = child_state
        child.parent_name = self.name
        self.children.append(child)
        return child


class SandboxRuntime:
    """Disk environment only: FOOD physics, directory discovery and observation."""
    def __init__(
        self,
        root: str | Path = "sandbox",
        *,
        block_size: int = 64,
        observer: SandboxObserver | None = None,
        inbox: str | Path | None = None,
    ) -> None:
        self.root = Path(root)
        self.block_size = block_size
        # ``inbox`` may be supplied by a public sandbox wrapper.  It changes
        # only where raw files are discovered; FOOD and biology stay local to
        # this runtime's world directory.
        self.inbox = Path(inbox) if inbox is not None else self.root / "inbox"
        self.food = self.root / "food"
        self.organisms_dir = self.root / "organisms"
        self.corpses_dir = self.root / "corpses"
        self.traces = self.root / "traces"
        self.results = self.root / "results"
        for directory in (self.inbox, self.food, self.organisms_dir, self.corpses_dir, self.traces, self.results):
            directory.mkdir(parents=True, exist_ok=True)
        self.observer = observer or SandboxObserver()
        self.food_sources: dict[str, StreamingDestructiveFood] = {}
        self.organisms: list[AutonomousOrganism] = []
        self.corpses: list[Corpse] = []
        self.local_bite_events = 0

    def organism_directory(self, organism_id: str) -> Path:
        """Persistent marker for an actually registered autonomous organism."""
        safe_id = organism_id.replace("/", "_").replace("\\", "_")
        return self.organisms_dir / f"org_{safe_id}"

    def mark_organism_alive(self, organism_id: str) -> None:
        marker = self.organism_directory(organism_id)
        marker.mkdir(parents=True, exist_ok=True)
        (marker / "ALIVE").touch()

    def mark_organism_dead(self, organism_id: str) -> None:
        marker = self.organism_directory(organism_id)
        marker.mkdir(parents=True, exist_ok=True)
        (marker / "DEAD").touch()
        alive = marker / "ALIVE"
        if alive.exists():
            alive.unlink()

    def sync_organism_markers(self) -> None:
        """Persist low-frequency observer snapshots, never a feeding decision."""
        for organism in self.organisms:
            marker = self.organism_directory(organism.name)
            marker.mkdir(parents=True, exist_ok=True)
            record = self.organism_record(organism)
            record["state"] = "ACTIVE" if organism.alive else "DEAD"
            (marker / "state.json").write_text(
                json.dumps(record, sort_keys=True, indent=2), encoding="utf-8",
            )

    def note_bite(self, organism_id: str, bite_size: int) -> None:
        """Sampling hook only; observation must not gate feeding progress."""
        if self.local_bite_events % 128 == 0:
            self.observer.observe("ORG_BITE", organism_id, str(bite_size))
        self.local_bite_events += 1

    def food_accounting(self) -> tuple[int, int, int, int]:
        """Read-only aggregate: original, eaten, remaining, duplicates."""
        original = sum(food.size for food in self.food_sources.values())
        eaten = sum(food.metrics.bytes_consumed for food in self.food_sources.values())
        remaining = sum(food.remaining for food in self.food_sources.values())
        duplicates = sum(food.metrics.duplicate_consumption for food in self.food_sources.values())
        return original, eaten, remaining, duplicates

    def verify_world_material_conservation(self) -> None:
        """Read-only lineage/world conservation; ownership transfers cancel."""
        flows = [organism.material_flow for organism in self.organisms]
        external_input = sum(flow.input_mass for flow in flows)
        external_assimilated = sum(flow.assimilated_mass for flow in flows)
        external_expelled = sum(flow.external_expelled_mass for flow in flows)
        external_gut = sum(flow.gut_mass_by_origin(organism.gut_queue, "external") for flow, organism in zip(flows, self.organisms))
        if external_input != external_assimilated + external_expelled + external_gut:
            raise AssertionError("world external material conservation failed")
        transfer_in = sum(flow.structural_transferred_in for flow in flows)
        transfer_out = sum(flow.structural_transferred_out for flow in flows)
        if transfer_in != transfer_out:
            raise AssertionError("world structural ownership transfer mismatch")
        created = sum(flow.structural_created_mass for flow in flows)
        living = sum(organism.body.body_mass - BASE_RECEPTOR_MASS for organism in self.organisms)
        resorbed = sum(flow.resorbed_mass for flow in flows)
        if created != living + resorbed:
            raise AssertionError(
                "world structural material conservation failed: "
                f"created={created} living={living} resorbed={resorbed}"
            )

    def organism_record(self, organism: AutonomousOrganism) -> dict[str, object]:
        return {
            "id": organism.name,
            "parent": organism.parent_name,
            "generation": organism.body.generation,
            "alive": organism.alive,
            "territory": "D" + "".join(map(str, organism.territory_state.territory.path)),
            "body": organism.body.size,
            "body_mass": organism.body.body_mass,
            "atoms": len(organism.body.atoms),
            "relations": len(organism.body.relations),
            "composites": len(organism.body.composites),
            "bite": organism.body.bite_limit(organism.config),
            "reserve": organism.body.reserve,
            "metabolic_debt": organism.activity_ledger.metabolic_debt,
            "gut": organism.gut_mass,
            "weakest_weight": organism.weakest_weight,
            "bytes_eaten": organism.body.consumed_total,
            "births": organism.body.children_created,
            "divisions": organism.body.children_created,
            "corpse_nutrition": organism.biomass_consumed,
            "division_transactions": [trace.snapshot() for trace in organism.division_material_traces],
        }

    def observation_snapshot(self) -> dict[str, object]:
        """A read-only camera view for CLI/observer code."""
        original, eaten, remaining, duplicates = self.food_accounting()
        inbox_pending = sum(food.inbox_remaining for food in self.food_sources.values())
        records = [self.organism_record(organism) for organism in self.organisms]
        alive = [record for record in records if record["alive"]]
        bodies = [int(record["body"]) for record in records]
        bites = [int(record["bite"]) for record in records]
        return {
            "food_original": original,
            "food_eaten": eaten,
            "food_remaining": remaining,
            "food_inbox_pending": inbox_pending,
            "duplicates": duplicates,
            "alive": len(alive),
            "born": sum(int(record["births"]) for record in records),
            "dead": len(records) - len(alive),
            "generations": max((int(record["generation"]) for record in records), default=0),
            "body_min": min(bodies, default=0),
            "body_median": median(bodies) if bodies else 0,
            "body_max": max(bodies, default=0),
            "body_average": mean(bodies) if bodies else 0,
            "bite_min": min(bites, default=0),
            "bite_median": median(bites) if bites else 0,
            "bite_max": max(bites, default=0),
            "bite_average": mean(bites) if bites else 0,
            "corpses": len(self.corpses),
            "corpse_energy": sum(corpse.remaining_energy for corpse in self.corpses),
            "relations": sum(len(organism.body.relations) for organism in self.organisms),
            "composites": sum(len(organism.body.composites) for organism in self.organisms),
            "organisms": records,
            "territory_reclaims": sum(event.kind == "TERRITORY_RECLAIM" for event in self.observer.events),
        }

    def first_corpse_in(self, territory: FoodTerritory) -> Corpse | None:
        eligible = [corpse for corpse in self.corpses if corpse.remaining_energy > 0.0 and territory.path == corpse.territory.path[:len(territory.path)]]
        return min(eligible, key=lambda corpse: (corpse.territory.path, corpse.remaining_energy)) if eligible else None

    def add_corpse(self, corpse: Corpse, organism_id: str | None = None) -> None:
        corpse.source_organism_id = organism_id
        self.corpses.append(corpse)
        marker = self.corpses_dir / f"corpse_{len(self.corpses):06d}.json"
        marker.write_text(json.dumps({
            "source_organism": organism_id,
            "territory": "D" + "".join(map(str, corpse.territory.path)),
            "remaining_energy": corpse.remaining_energy,
        }, sort_keys=True), encoding="utf-8")

    def take_corpse_energy(self, territory: FoodTerritory, capacity: int, organism_id: str) -> float:
        """Environment transfer only; the caller alone credits its reserve."""
        corpse = self.first_corpse_in(territory)
        if corpse is None or capacity <= 0:
            return 0.0
        before = corpse.remaining_energy
        gained = min(float(capacity), before)
        corpse.remaining_energy = before - gained
        if abs(before - (corpse.remaining_energy + gained)) > 1e-12:
            raise AssertionError("corpse energy conservation violated")
        self.observer.observe("CORPSE_CONSUMED", organism_id, f"{gained:.6f}")
        if corpse.remaining_energy <= 0.0:
            corpse.remaining_energy = 0.0
            self.corpses.remove(corpse)
            self.observer.observe("CORPSE_EMPTY", organism_id)
        return gained

    def is_territory_unoccupied(self, territory: FoodTerritory, *, excluding: AutonomousOrganism | None = None) -> bool:
        """Vacancy depends solely on living territory ownership, never corpses."""
        return not any(
            organism is not excluding and organism.alive and organism.territory_state.territory.overlaps(territory)
            for organism in self.organisms
        )

    def register_child(self, parent: AutonomousOrganism, child: AutonomousOrganism) -> None:
        """Execution registration only; DIVIDE has already happened locally."""
        if parent.hot_metrics is not None:
            child.enable_hot_profile()
        self.organisms.append(child)
        self.mark_organism_alive(child.name)
        self.observer.observe("ORG_BORN", child.name, "division")

    def release_territory(self, organism_id: str, territory: FoodTerritory) -> None:
        return None

    def update_territory(self, organism_id: str, territory: FoodTerritory) -> None:
        return None

    def bootstrap(self) -> AutonomousOrganism:
        living = [organism for organism in self.organisms if organism.alive]
        if living:
            return living[0]
        root = AutonomousOrganism()
        self.organisms.append(root)
        self.mark_organism_alive(root.name)
        self.observer.observe("ORG_BORN", root.name, "D")
        return root

    def ingest_one_available(self, organism: AutonomousOrganism | str) -> None:
        organism_name = organism if isinstance(organism, str) else organism.name
        # A claimed source keeps its temporary name until the final tail block
        # is committed.  Continue that existing transfer before discovering a
        # different inbox file.
        for logical_name, food in sorted(self.food_sources.items()):
            if not food.inbox.exists() or food.inbox_remaining == 0:
                continue
            event = food.ingest_next()
            if event is not None:
                self.observer.observe("FOOD_BLOCK", organism_name, f"{logical_name}:{event.block_id}")
                if food.inbox_remaining == 0 and food.inbox.exists():
                    food.inbox.unlink()
                    food.metrics.filesystem_operations += 1
            return

        for source in sorted(self.inbox.iterdir()):
            if not source.is_file() or source.name.endswith(".ingesting"):
                continue
            logical_name = source.name
            food = self.food_sources.get(logical_name)
            if food is None:
                # The rename is the environment's atomic raw-file claim.  It
                # selects the physical ingest worker only; it conveys no
                # biological policy and does not assign food to an organism.
                claimed_source = source.with_name(source.name + ".ingesting")
                try:
                    source.replace(claimed_source)
                except FileNotFoundError:
                    continue
                food = StreamingDestructiveFood(
                    claimed_source,
                    self.root,
                    block_size=self.block_size,
                    logical_name=logical_name,
                    inbox_is_source=True,
                )
                self.food_sources[logical_name] = food
                self.observer.observe("FOOD_DISCOVERED", organism_name, logical_name)
            event = food.ingest_next()
            if event is not None:
                self.observer.observe("FOOD_BLOCK", organism_name, f"{logical_name}:{event.block_id}")
                if food.inbox_remaining == 0 and food.inbox.exists():
                    food.inbox.unlink()
                    food.metrics.filesystem_operations += 1
            return

    def refresh_food_sources(self) -> None:
        """Serial runtime already owns live FOOD handles; no refresh is needed."""
        return None

    def has_active_food(self) -> bool:
        return False

    def run(self, *, poll_seconds: float = 0.05, stop: Callable[[], bool] | None = None) -> None:
        while not (stop and stop()):
            self.autonomous_step()
            sleep(poll_seconds)

    def autonomous_step(self) -> None:
        """Environment heartbeat; each organism performs its own life step."""
        self.bootstrap()
        for organism in tuple(self.organisms):
            organism.live_step(self)
            for child in organism.children:
                if child not in self.organisms:
                    self.organisms.append(child)
                    self.mark_organism_alive(child.name)
                    self.observer.observe("ORG_BORN", child.name, "child")
