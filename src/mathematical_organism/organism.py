from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Sequence

from .audit import AuditLog, AuditRecord
from .config import OrganismConfig
from .energy import EnergyBreakdown, compute_energy
from .model import (
    END_ID,
    START_ID,
    Candidate,
    CandidateKind,
    CandidateStatus,
    LatticeGraph,
)
from .representation import RepresentationPlan, find_best_representation
from .rules import (
    RULE_PRIORITY,
    Proposal,
    RuleApplication,
    RuleKind,
    apply_proposal,
    generate_proposals,
)


@dataclass(frozen=True, slots=True)
class IngestResult:
    time: int
    input_symbols: tuple[str, ...]
    reconstructed: tuple[str, ...]
    raw_count: int
    representation: tuple[str, ...]
    adaptive_rule: str
    energy_before: float
    energy_after: float
    node_count: int
    transition_count: int


@dataclass(slots=True)
class _AcceptedTrial:
    proposal: Proposal
    graph: LatticeGraph
    application: RuleApplication
    energy: EnergyBreakdown
    delta: float

    @property
    def key(self) -> tuple[float, int, int, str]:
        return (
            self.delta,
            RULE_PRIORITY[self.proposal.kind],
            self.proposal.anchor_id,
            repr(self.proposal.signature),
        )


class MathematicalOrganism:
    """Deterministic autonomous step function for the V0 sequence organism."""

    def __init__(self, config: OrganismConfig | None = None) -> None:
        self.config = config or OrganismConfig()
        self.config.validate()
        self.graph = LatticeGraph()
        self.candidates: dict[tuple[Any, ...], Candidate] = {}
        self.audit = AuditLog()
        self.time = 0

    def ingest(self, data: str | Sequence[str]) -> IngestResult:
        symbols = tuple(data) if isinstance(data, str) else tuple(data)
        self._validate_input(symbols)
        self.time += 1

        plan = find_best_representation(
            self.graph, symbols, self.time, self.config
        )
        reconstructed = plan.reconstruct(self.graph)
        if reconstructed != symbols:
            raise AssertionError("I1 failed before learning")

        self._observe_plan(plan)
        atom_path = self._ensure_atoms(symbols)
        if plan.raw_count > 0 and atom_path is not None:
            self._observe_route_candidate(atom_path)
        self._observe_compose_candidates(plan)
        self._expire_and_bound_candidates()

        energy_before = compute_energy(
            self.graph, self.time, self.config, len(self.candidates)
        )
        accepted = self._mutate_once(energy_before)
        if accepted is None:
            adaptive_rule = RuleKind.KEEP.value
            application = RuleApplication((), (), "no energy-reducing proposal")
        else:
            self.graph = accepted.graph
            adaptive_rule = accepted.proposal.kind.value
            application = accepted.application
            if accepted.proposal.candidate_key is not None:
                self.candidates.pop(accepted.proposal.candidate_key, None)
            self._drop_invalid_candidates()

        self.graph.validate(self.config)
        energy_after = compute_energy(
            self.graph, self.time, self.config, len(self.candidates)
        )
        if accepted is not None and not (
            energy_after.total
            < energy_before.total - self.config.minimum_energy_improvement
        ):
            raise AssertionError("I6 failed after committing a mutation")

        representation_labels = self._plan_labels(plan)
        self.audit.append(
            AuditRecord(
                time=self.time,
                input_symbols=symbols,
                representation=representation_labels,
                raw_positions=plan.raw_positions,
                energy_before=energy_before.to_dict(),
                energy_after=energy_after.to_dict(),
                adaptive_rule=adaptive_rule,
                affected_nodes=application.affected_nodes,
                semantic_proof=application.semantic_proof,
                invariant_result="PASS",
                notes=(application.note,),
            )
        )

        return IngestResult(
            time=self.time,
            input_symbols=symbols,
            reconstructed=reconstructed,
            raw_count=plan.raw_count,
            representation=representation_labels,
            adaptive_rule=adaptive_rule,
            energy_before=energy_before.total,
            energy_after=energy_after.total,
            node_count=len(self.graph.nodes),
            transition_count=len(self.graph.transitions),
        )

    def stabilize(self, max_steps: int = 100) -> int:
        """Apply pending energy-reducing changes without consuming new input."""
        if max_steps < 0:
            raise ValueError("max_steps must be non-negative")
        applied = 0
        for _ in range(max_steps):
            self._expire_and_bound_candidates()
            before = compute_energy(
                self.graph, self.time, self.config, len(self.candidates)
            )
            accepted = self._mutate_once(before)
            if accepted is None:
                break
            self.graph = accepted.graph
            if accepted.proposal.candidate_key is not None:
                self.candidates.pop(accepted.proposal.candidate_key, None)
            self._drop_invalid_candidates()
            self.graph.validate(self.config)
            after = compute_energy(
                self.graph, self.time, self.config, len(self.candidates)
            )
            if not after.total < before.total - self.config.minimum_energy_improvement:
                raise AssertionError("stabilization accepted a non-improving mutation")
            applied += 1
        return applied

    def advance_time(self, steps: int) -> None:
        if steps < 0:
            raise ValueError("steps must be non-negative")
        self.time += steps

    def snapshot(self) -> dict[str, Any]:
        return {
            "time": self.time,
            "config": {
                field: getattr(self.config, field)
                for field in self.config.__dataclass_fields__
            },
            "graph": self.graph.snapshot(self.time, self.config.decay),
            "candidates": [
                {
                    "kind": candidate.kind.value,
                    "signature": repr(candidate.signature),
                    "support": candidate.support.read(self.time, self.config.decay),
                    "last_observed": candidate.last_observed,
                    "status": candidate.status.value,
                }
                for candidate in sorted(
                    self.candidates.values(), key=lambda item: repr(item.signature)
                )
            ],
            "audit_digest": self.audit.digest(),
        }

    def write_audit(self, path: str | Path) -> None:
        Path(path).write_text(self.audit.to_json_lines() + "\n", encoding="utf-8")

    def _validate_input(self, symbols: tuple[str, ...]) -> None:
        if not symbols:
            raise ValueError("input must not be empty")
        if len(symbols) > self.config.max_input_length:
            raise ValueError("input exceeds max_input_length")
        if any(not isinstance(symbol, str) or symbol == "" for symbol in symbols):
            raise TypeError("V0 symbols must be non-empty strings")

    def _observe_plan(self, plan: RepresentationPlan) -> None:
        units = plan.units
        for unit in units:
            if unit.is_raw:
                self.graph.raw_usage.add(1.0, self.time, self.config.decay)
            else:
                self.graph.nodes[unit.node_id].usage.add(
                    1.0, self.time, self.config.decay
                )

        segments: list[list[int]] = []
        current: list[int] = []
        for unit in units:
            if unit.is_raw:
                if current:
                    segments.append(current)
                    current = []
                continue
            current.append(int(unit.node_id))
        if current:
            segments.append(current)

        for segment in segments:
            for index, node_id in enumerate(segment):
                previous = START_ID if index == 0 else segment[index - 1]
                next_id = END_ID if index + 1 == len(segment) else segment[index + 1]
                self.graph.nodes[node_id].observe_context(
                    previous, next_id, 1.0, self.time, self.config.decay
                )
            edges = [
                (START_ID, segment[0]),
                *zip(segment, segment[1:]),
                (segment[-1], END_ID),
            ]
            for source, target in edges:
                edge = self.graph.transitions.get((source, target))
                if edge is not None:
                    edge.usage.add(1.0, self.time, self.config.decay)

    def _ensure_atoms(self, symbols: tuple[str, ...]) -> tuple[int, ...] | None:
        unique_new = sorted(set(symbols) - set(self.graph.atom_index))
        available_nodes = self.config.max_nodes - len(self.graph.nodes)
        available_symbols = self.config.alphabet_limit - len(self.graph.atom_index)
        for symbol in unique_new[: min(available_nodes, available_symbols)]:
            self.graph.add_atom(symbol, self.time)
        if any(symbol not in self.graph.atom_index for symbol in symbols):
            return None
        return tuple(self.graph.atom_index[symbol] for symbol in symbols)

    def _observe_route_candidate(self, atom_path: tuple[int, ...]) -> None:
        signature: tuple[Any, ...] = (CandidateKind.ROUTE.value, *atom_path)
        candidate = self.candidates.get(signature)
        if candidate is None:
            candidate = Candidate(
                kind=CandidateKind.ROUTE,
                signature=signature,
                created_at=self.time,
                last_observed=self.time,
            )
            self.candidates[signature] = candidate
        candidate.observe(self.time, self.config.decay)
        if (
            candidate.support.read(self.time, self.config.decay)
            >= self.config.support_threshold(self.config.route_support)
        ):
            candidate.status = CandidateStatus.ELIGIBLE

    def _observe_compose_candidates(self, plan: RepresentationPlan) -> None:
        units = plan.units
        for index in range(len(units) - 1):
            left = units[index]
            right = units[index + 1]
            if left.is_raw or right.is_raw:
                continue
            left_id = int(left.node_id)
            right_id = int(right.node_id)
            previous = START_ID
            if index > 0 and not units[index - 1].is_raw:
                previous = int(units[index - 1].node_id)
            next_id = END_ID
            if index + 2 < len(units) and not units[index + 2].is_raw:
                next_id = int(units[index + 2].node_id)
            signature: tuple[Any, ...] = (
                CandidateKind.COMPOSE.value,
                left_id,
                right_id,
            )
            candidate = self.candidates.get(signature)
            if candidate is None:
                candidate = Candidate(
                    kind=CandidateKind.COMPOSE,
                    signature=signature,
                    created_at=self.time,
                    last_observed=self.time,
                )
                self.candidates[signature] = candidate
            candidate.observe(
                self.time,
                self.config.decay,
                context=(previous, next_id),
            )
            if (
                candidate.support.read(self.time, self.config.decay)
                >= self.config.support_threshold(self.config.compose_support)
            ):
                candidate.status = CandidateStatus.ELIGIBLE

    def _mutate_once(self, energy_before: EnergyBreakdown) -> _AcceptedTrial | None:
        proposals = generate_proposals(
            self.graph, self.candidates, self.time, self.config
        )
        accepted: list[_AcceptedTrial] = []
        for proposal in proposals:
            trial_graph = self.graph.clone()
            try:
                application = apply_proposal(
                    trial_graph, proposal, self.time, self.config
                )
                trial_graph.validate(self.config)
            except (AssertionError, KeyError, ValueError):
                continue
            candidate_count = len(self.candidates)
            if proposal.candidate_key is not None:
                candidate_count -= 1
            energy_after = compute_energy(
                trial_graph, self.time, self.config, candidate_count
            )
            delta = energy_after.total - energy_before.total
            if delta < -self.config.minimum_energy_improvement:
                accepted.append(
                    _AcceptedTrial(
                        proposal=proposal,
                        graph=trial_graph,
                        application=application,
                        energy=energy_after,
                        delta=delta,
                    )
                )
        if not accepted:
            return None
        return min(accepted, key=lambda item: item.key)

    def _expire_and_bound_candidates(self) -> None:
        expired = [
            key
            for key, candidate in self.candidates.items()
            if self.time - candidate.last_observed > self.config.candidate_expiry_steps
        ]
        for key in expired:
            self.candidates[key].status = CandidateStatus.EXPIRED
            del self.candidates[key]

        if len(self.candidates) <= self.config.max_candidates:
            return
        ordered = sorted(
            self.candidates.items(),
            key=lambda item: (
                item[1].support.read(self.time, self.config.decay),
                item[1].last_observed,
                repr(item[0]),
            ),
        )
        remove_count = len(self.candidates) - self.config.max_candidates
        for key, _ in ordered[:remove_count]:
            del self.candidates[key]

    def _drop_invalid_candidates(self) -> None:
        valid_nodes = set(self.graph.nodes)
        invalid: list[tuple[Any, ...]] = []
        for key, candidate in self.candidates.items():
            referenced: tuple[int, ...]
            if candidate.kind is CandidateKind.ROUTE:
                referenced = tuple(int(item) for item in candidate.signature[1:])
            else:
                referenced = (
                    int(candidate.signature[1]),
                    int(candidate.signature[2]),
                )
            if any(node_id not in valid_nodes for node_id in referenced):
                invalid.append(key)
        for key in invalid:
            del self.candidates[key]

    def _plan_labels(self, plan: RepresentationPlan) -> tuple[str, ...]:
        labels: list[str] = []
        for unit in plan.units:
            if unit.is_raw:
                labels.append(f"RAW:{unit.raw_symbol}")
            else:
                node = self.graph.nodes.get(int(unit.node_id))
                if node is None:
                    labels.append(f"REMOVED:{unit.node_id}")
                else:
                    labels.append(
                        f"N{node.id}:{''.join(node.yield_symbols)}"
                    )
        return tuple(labels)
