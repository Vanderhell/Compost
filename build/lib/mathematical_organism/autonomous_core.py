from __future__ import annotations

"""Local lifecycle equations used by autonomous organisms, without a population owner."""

from collections import deque
from dataclasses import dataclass, field
from time import perf_counter
from typing import Iterable

from .lifecycle import LifecycleEvent, LivingStructure, MathematicalLifeOrganism
from .biology_rules import forgetting_delta, lazy_metabolism_delta, resorption_allowed, structural_mass


@dataclass(slots=True)
class HotPathMetrics:
    """Opt-in timing counters; they never participate in organism decisions."""
    seconds: dict[str, float] = field(default_factory=dict)
    calls: dict[str, int] = field(default_factory=dict)

    def add(self, name: str, started: float) -> None:
        self.seconds[name] = self.seconds.get(name, 0.0) + perf_counter() - started
        self.calls[name] = self.calls.get(name, 0) + 1

    def snapshot(self) -> dict[str, tuple[int, float, float]]:
        return {name: (self.calls.get(name, 0), elapsed, elapsed / self.calls[name]) for name, elapsed in self.seconds.items()}


class AutonomousCore:
    """Mixin methods; ``self`` is one organism and owns ``config`` and ``result``."""

    def digest(self, organism: MathematicalLifeOrganism, bite: tuple[int, ...], nutrition: tuple[float, ...], trace: dict[str, int] | None = None) -> None:
        if len(bite) != len(nutrition):
            raise AssertionError("every exposure needs one nutrition allocation")
        if trace is not None:
            trace.update(input_bytes=len(bite), assimilated_bytes=0, activated_receptors=0, relation_evidence_generated=0, relations_created=0, relations_strengthened=0, composites_created=0, composites_strengthened=0, structural_mass_created=0, body_mass_before=organism.body_mass)
        metrics = getattr(self, "hot_metrics", None)
        digest_started = perf_counter() if metrics is not None else 0.0
        organism.consumed_total += len(bite); assimilated = 0.0
        for symbol, food in zip(bite, nutrition):
            if food <= 0.0: continue
            if organism.activate_receptor(symbol) and trace is not None:
                trace["activated_receptors"] += 1
            atom = organism.atoms.get(symbol)
            if atom is None:
                if organism.atoms and self.under_pressure(organism, self.config.atom_maintenance) and not self.metabolize(organism): continue
                if organism.atoms and not self.fund_cost(organism, self.config.atom_formation_cost): continue
                atom = LivingStructure(symbol, "ATOM", maintenance=self.config.atom_maintenance)
                atom.strength = food; atom.evidence = 1.0; atom.income_rate = self.config.atom_income * food
                organism.add_structure(organism.atoms, atom)
            else:
                gain = self.config.atom_income * food
                atom.strength += gain; atom.evidence += 1.0; atom.income_rate += gain
            # Food is the only normal source of organism-level reserve.  It
            # is credited once here, never attached to a learned structure.
            organism.adjust_reserve(self.config.atom_income * food)
            if hasattr(self, "note_structure_changed"):
                self.note_structure_changed(atom)
            assimilated += food
            if trace is not None:
                trace["assimilated_bytes"] += 1
        for index, pair in enumerate(zip(bite, bite[1:])):
            food = min(nutrition[index], nutrition[index + 1])
            if food <= 0.0: continue
            receptor_pair = organism.activate_receptor(pair[0]) and organism.activate_receptor(pair[1])
            # Byte input derives relation evidence from canonical receptors.
            # Legacy atoms may still fund formation for compatibility, but do
            # not decide whether a real observed byte adjacency is evidence.
            if not receptor_pair and (pair[0] not in organism.atoms or pair[1] not in organism.atoms):
                continue
            if trace is not None: trace["relation_evidence_generated"] += 1
            if pair in organism.composites:
                started = perf_counter() if metrics is not None else 0.0
                composite = organism.composites[pair]; gain = self.config.composite_income * food
                mass_before = structural_mass(composite.strength)
                organism.set_strength(composite, composite.strength + gain); composite.evidence += 1.0; composite.income_rate += gain
                if trace is not None:
                    trace["structural_mass_created"] += max(0, structural_mass(composite.strength) - mass_before)
                organism.adjust_reserve(self.config.composite_income * food)
                if hasattr(self, "note_structure_changed"):
                    self.note_structure_changed(composite)
                if trace is not None: trace["composites_strengthened"] += 1
                if metrics is not None: metrics.add("composite_lookup_strengthen", started)
                continue
            started = perf_counter() if metrics is not None else 0.0
            relation = organism.relations.get(pair)
            if metrics is not None: metrics.add("relation_lookup", started)
            if relation is None:
                if self.under_pressure(organism, self.config.relation_maintenance) and not self.metabolize(organism): continue
                started = perf_counter() if metrics is not None else 0.0
                if self.fund_cost(organism, self.config.relation_formation_cost):
                    relation = LivingStructure(pair, "RELATION", maintenance=self.config.relation_maintenance)
                    relation.strength = food; relation.evidence = 1.0; relation.income_rate = self.config.relation_income * food
                    organism.add_structure(organism.relations, relation)
                    organism.adjust_reserve(self.config.relation_income * food)
                    if hasattr(self, "note_structure_changed"):
                        self.note_structure_changed(relation)
                    if trace is not None:
                        trace["relations_created"] += 1
                        trace["structural_mass_created"] += structural_mass(relation.strength)
                if metrics is not None: metrics.add("relation_create", started)
            else:
                started = perf_counter() if metrics is not None else 0.0
                gain = self.config.relation_income * food
                mass_before = structural_mass(relation.strength)
                organism.set_strength(relation, relation.strength + gain); relation.evidence += 1.0; relation.income_rate += gain
                if trace is not None:
                    trace["structural_mass_created"] += max(0, structural_mass(relation.strength) - mass_before)
                organism.adjust_reserve(gain)
                if hasattr(self, "note_structure_changed"):
                    self.note_structure_changed(relation)
                if trace is not None: trace["relations_strengthened"] += 1
                if metrics is not None: metrics.add("relation_strengthen", started)
        organism.assimilated_total += assimilated; organism.nutrition_consumed_total += assimilated; self.result.consumed_nutrition_total += assimilated
        if self.result.consumed_nutrition_total > self.result.available_nutrition_total + 1e-12: raise AssertionError("nutrition conservation violated during digestion")
        organism.waste_total += len(bite) - assimilated
        if trace is not None:
            trace["body_mass_after"] = organism.body_mass
            trace["next_bite"] = organism.bite_limit(self.config)
        if metrics is not None: metrics.add("digest", digest_started)

    @staticmethod
    def apply_pending_metabolism(
        organism: MathematicalLifeOrganism, structure: LivingStructure, current_epoch: int, income_decay: float,
    ) -> None:
        """Apply an exact pending local recurrence before new evidence.

        This primitive is intentionally independent of global resorption.  It
        is safe to use only in an execution model that also maintains exact
        aggregate reserve, maintenance and weakest-structure event queues.
        """
        pending = current_epoch - structure.last_metabolic_epoch
        if pending < 0:
            raise ValueError("metabolic epoch moved backwards")
        if pending == 0:
            return
        delta = lazy_metabolism_delta(
            strength=structure.strength,
            income_rate=structure.income_rate, maintenance=structure.maintenance,
            income_decay=income_decay, epochs=pending,
        )
        organism.set_strength(structure, delta.strength_after)
        structure.income_rate = delta.income_rate_after
        structure.last_metabolic_epoch = current_epoch

    @staticmethod
    def fund_cost(organism: MathematicalLifeOrganism, cost: float) -> bool:
        if organism.reserve < cost: return False
        organism.adjust_reserve(-cost)
        return True

    def consolidate(self, organism: MathematicalLifeOrganism, trace: dict[str, int] | None = None) -> None:
        metrics = getattr(self, "hot_metrics", None); started = perf_counter() if metrics is not None else 0.0
        for pair, relation in sorted(list(organism.relations.items())):
            before = relation.maintenance * max(1.0, relation.evidence); after = self.config.composite_maintenance * max(1.0, relation.evidence)
            useful = relation.evidence * (relation.strength / max(1.0, relation.evidence))
            if after + self.config.consolidation_formation_cost < before and useful > self.config.consolidation_formation_cost:
                composite = LivingStructure(pair, "COMPOSITE", maintenance=self.config.composite_maintenance, members=(pair,))
                composite.strength = relation.strength; composite.evidence = relation.evidence; composite.income_rate = relation.income_rate
                organism.add_structure(organism.composites, composite); organism.remove_structure(organism.relations, pair)
                if hasattr(self, "note_structure_changed"):
                    self.note_structure_changed(composite)
                if trace is not None: trace["composites_created"] = trace.get("composites_created", 0) + 1
                if organism.first_consolidation_age is None: organism.first_consolidation_age = organism.age_in_cycles
                self.result.events.append(LifecycleEvent(organism.id, organism.cursor, "CONSOLIDATE", repr(pair)))
        if metrics is not None: metrics.add("composite_full_step", started)

    @staticmethod
    def body_maintenance(organism: MathematicalLifeOrganism) -> float:
        return organism.cached_maintenance()

    def under_pressure(self, organism: MathematicalLifeOrganism, new_maintenance: float) -> bool:
        return organism.reserve < organism.cached_maintenance() + new_maintenance

    def maintain_and_resorb(self, organism: MathematicalLifeOrganism) -> None:
        metrics = getattr(self, "hot_metrics", None); started = perf_counter() if metrics is not None else 0.0
        for structure in organism._structures():
            old_mass = structural_mass(structure.strength) if structure.kind in {"RELATION", "COMPOSITE"} else 0
            delta = forgetting_delta(structure, self.config)
            organism.set_strength(structure, delta.strength_after)
            structure.income_rate = delta.income_rate_after
            new_mass = structural_mass(structure.strength) if structure.kind in {"RELATION", "COMPOSITE"} else 0
            if old_mass > new_mass and hasattr(self, "enqueue_resorbed_material"):
                self.enqueue_resorbed_material(old_mass - new_mass)
        while organism.size and organism.reserve < self.body_maintenance(organism):
            if not self.remove_weakest(organism, "STARVATION", True): break
        if metrics is not None: metrics.add("maintenance_forgetting_resorption", started)

    def metabolize(self, organism: MathematicalLifeOrganism) -> bool:
        # Runtime organisms own a member-cohesion cache.  Metabolisation is a
        # member event there: invalid incident edges disappear only because
        # their member detached.  The legacy relation path remains a reference
        # fallback for the standalone core.
        weakest = getattr(self, "get_weakest_members", None)
        detach_member = getattr(self, "_detach_member", None)
        if callable(weakest) and callable(detach_member):
            members = weakest()
            if members:
                detach_member(members[0], "METABOLIZE")
                return True
        return self.remove_weakest(organism, "METABOLIZE", False)

    def remove_weakest(self, organism: MathematicalLifeOrganism, reason: str, allow_critical: bool) -> bool:
        candidates = []
        for collection in (organism.composites, organism.relations):
            for key, item in collection.items():
                if allow_critical or not self.critical_bridge(organism, key, item.strength): candidates.append(((item.strength,item.evidence,item.income_rate,item.kind,repr(key)),collection,key))
        supported = {symbol for pair in (*organism.relations,*organism.composites) for symbol in pair}
        for key,item in organism.atoms.items():
            if allow_critical or key not in supported: candidates.append(((item.strength,item.evidence,item.income_rate,item.kind,repr(key)),organism.atoms,key))
        if not candidates: return False
        _,collection,key=min(candidates,key=lambda item:item[0])
        if not resorption_allowed(collection[key], organism, body_maintenance=self.body_maintenance(organism)):
            return False
        removed = organism.remove_structure(collection, key)
        mass = structural_mass(removed.strength) if removed.kind in {"RELATION", "COMPOSITE"} else 0
        if mass and hasattr(self, "enqueue_resorbed_material"):
            self.enqueue_resorbed_material(mass)
        self.result.events.append(LifecycleEvent(organism.id, organism.cursor, "RESORB", f"{reason}:{key!r}")); return True

    def components_without_boundary(self, organism: MathematicalLifeOrganism, boundary: tuple | None) -> list[set]:
        adjacency={atom:set() for atom in organism.atoms}
        for pair in (*organism.relations,*organism.composites):
            if boundary is not None and tuple(sorted(pair)) == boundary: continue
            # Resorption can remove an atom while an older edge awaits its
            # next metabolic cleanup.  Such an edge cannot contribute a live
            # boundary or a valid division candidate.
            if pair[0] not in adjacency or pair[1] not in adjacency: continue
            adjacency[pair[0]].add(pair[1]); adjacency[pair[1]].add(pair[0])
        remaining=set(adjacency); components=[]
        while remaining:
            seed=min(remaining); component={seed}; queue=deque([seed]); remaining.remove(seed)
            while queue:
                current=queue.popleft()
                for neighbour in sorted(adjacency[current]):
                    if neighbour in remaining: remaining.remove(neighbour); component.add(neighbour); queue.append(neighbour)
            components.append(component)
        return components

    def critical_bridge(self, organism: MathematicalLifeOrganism, pair: tuple, strength: float) -> bool:
        if pair[0] == pair[1] or pair not in {**organism.relations,**organism.composites}: return False
        baseline=self.components_without_boundary(organism,None); without=self.components_without_boundary(organism,tuple(sorted(pair)))
        return len(baseline)==1 and len(without)>len(baseline) and all(sum(organism.atoms[s].strength for s in component)>strength for component in without)

    @staticmethod
    def region_maintenance(organism: MathematicalLifeOrganism, region: set) -> float:
        return sum(item.maintenance for key,item in organism.atoms.items() if key in region)+sum(item.maintenance for pair,item in {**organism.relations,**organism.composites}.items() if pair[0] in region and pair[1] in region)

    @staticmethod
    def region_income(organism: MathematicalLifeOrganism, region: set) -> float:
        return sum(item.income_rate for key,item in organism.atoms.items() if key in region)+sum(item.income_rate for pair,item in {**organism.relations,**organism.composites}.items() if pair[0] in region and pair[1] in region)

    def pay_birth_cost(self, organism: MathematicalLifeOrganism) -> None:
        if not self.fund_cost(organism, self.config.birth_cost):
            raise AssertionError("division passed viability without affordable birth cost")
