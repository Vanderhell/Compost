from __future__ import annotations

import copy
from dataclasses import asdict, dataclass
from typing import Any, Iterable, Sequence

from .energy import EnergyBreakdown, compute_energy
from .model import END_ID, START_ID, DecayedCounter, LatticeGraph
from .organism import MathematicalOrganism
from .representation import RepresentationPlan, find_best_representation
from .rules import (
    RULE_PRIORITY,
    Proposal,
    RuleKind,
    apply_proposal,
    generate_proposals,
)


@dataclass(frozen=True, slots=True)
class ReplayInput:
    time: int
    symbols: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class OracleComparison:
    rule: str
    signature: tuple[Any, ...]
    local_delta: float
    oracle_delta: float
    absolute_error: float
    relative_error: float
    local_accept: bool
    oracle_accept: bool
    false_accept: bool
    false_reject: bool
    state_mutation_during_evaluation: bool

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class ReplayOracle:
    """Slow, side-effect-free full-history reference evaluator.

    The history is deliberately owned by this object, not by the organism.
    Replay uses the supplied topology as fixed and never generates mutations.
    """

    def __init__(self, config: Any | None = None) -> None:
        self.config = config
        self.history: list[ReplayInput] = []

    def record(self, time: int, data: str | Sequence[str]) -> None:
        symbols = tuple(data) if isinstance(data, str) else tuple(data)
        self.history.append(ReplayInput(time, symbols))

    def record_result(self, result: Any) -> None:
        self.record(result.time, result.input_symbols)

    def snapshot(self) -> tuple[ReplayInput, ...]:
        return tuple(self.history)

    def _zero_derived(self, graph: LatticeGraph) -> None:
        graph.raw_usage = DecayedCounter()
        for node in graph.nodes.values():
            node.usage = DecayedCounter()
            node.contexts.clear()
        for edge in graph.transitions.values():
            edge.usage = DecayedCounter()

    @staticmethod
    def _topology_only_apply(
        graph: LatticeGraph, proposal: Proposal, now: int
    ) -> None:
        """Apply only candidate topology, independently of local evidence transfer.

        Inputs are a cloned graph and an immutable proposal payload.  The output
        is a fixed candidate topology whose counters are deliberately left at
        zero; `replay` is the only operation that may reconstruct evidence.
        Complexity is O(number of proposal contexts + incident edges).
        """
        if proposal.kind is RuleKind.GROW_ROUTE:
            path = tuple(int(item) for item in proposal.payload["path"])
            for source, target in [
                (START_ID, path[0]), *zip(path, path[1:]), (path[-1], END_ID)
            ]:
                graph.add_transition(source, target, now)
            return
        if proposal.kind is RuleKind.COMPOSE:
            left_id = int(proposal.payload["left_id"])
            right_id = int(proposal.payload["right_id"])
            left = graph.nodes[left_id]
            right = graph.nodes[right_id]
            composite_id, _ = graph.add_composite(left.semantic_id, right.semantic_id, now)
            graph.nodes[composite_id].routable = True
            for previous, next_id in proposal.payload["contexts"]:
                graph.add_transition(previous, composite_id, now)
                graph.add_transition(composite_id, next_id, now)
            return
        if proposal.kind is RuleKind.SPLIT:
            node_id = int(proposal.payload["node_id"])
            semantic_id = graph.nodes[node_id].semantic_id
            instance_ids = (graph.add_instance(semantic_id, now), graph.add_instance(semantic_id, now))
            for instance_id, group in zip(instance_ids, (proposal.payload["first"], proposal.payload["second"])):
                for previous, next_id in group:
                    graph.add_transition(previous, instance_id, now)
                    graph.add_transition(instance_id, next_id, now)
            for key in [key for key in graph.transitions if node_id in key]:
                del graph.transitions[key]
            graph.nodes[node_id].routable = False
            return
        if proposal.kind is RuleKind.MERGE:
            semantic_id = int(proposal.payload["semantic_id"])
            graph.nodes[semantic_id].routable = True
            for instance_id in proposal.payload["instances"]:
                instance = graph.nodes[int(instance_id)]
                for previous, next_id in instance.contexts:
                    graph.add_transition(previous, semantic_id, now)
                    graph.add_transition(semantic_id, next_id, now)
            for instance_id in proposal.payload["instances"]:
                graph.remove_node(int(instance_id))
            return
        if proposal.kind is RuleKind.PRUNE:
            graph.remove_node(int(proposal.payload["node_id"]))
            return
        raise ValueError(f"oracle does not support {proposal.kind}")

    def _observe(self, graph: LatticeGraph, plan: RepresentationPlan, now: int) -> None:
        for unit in plan.units:
            if unit.is_raw:
                graph.raw_usage.add(1.0, now, self._config.decay)
            else:
                graph.nodes[int(unit.node_id)].usage.add(1.0, now, self._config.decay)

        segment: list[int] = []
        segments: list[list[int]] = []
        for unit in plan.units:
            if unit.is_raw:
                if segment:
                    segments.append(segment)
                    segment = []
            else:
                segment.append(int(unit.node_id))
        if segment:
            segments.append(segment)
        for segment in segments:
            for index, node_id in enumerate(segment):
                previous = START_ID if index == 0 else segment[index - 1]
                following = END_ID if index + 1 == len(segment) else segment[index + 1]
                graph.nodes[node_id].observe_context(
                    previous, following, 1.0, now, self._config.decay
                )
            for source, target in [
                (START_ID, segment[0]), *zip(segment, segment[1:]), (segment[-1], END_ID)
            ]:
                edge = graph.transitions.get((source, target))
                if edge is not None:
                    edge.usage.add(1.0, now, self._config.decay)

    def replay(self, topology: LatticeGraph, config: Any) -> LatticeGraph:
        self._config = config
        graph = topology.clone()
        self._zero_derived(graph)
        for item in self.history:
            plan = find_best_representation(graph, item.symbols, item.time, config)
            if plan.reconstruct(graph) != item.symbols:
                raise AssertionError("oracle replay failed exact reconstruction")
            self._observe(graph, plan, item.time)
        graph.validate(config)
        return graph

    def replay_history(self, topology: LatticeGraph, config: Any) -> LatticeGraph:
        """Explicit alias used by validation code and external experiments."""
        return self.replay(topology, config)

    def compare(self, organism: MathematicalOrganism, proposal: Proposal) -> OracleComparison:
        config = organism.config
        source_before = copy.deepcopy(organism.snapshot())
        before = compute_energy(organism.graph, organism.time, config, len(organism.candidates))
        local_graph = organism.graph.clone()
        try:
            application = apply_proposal(local_graph, proposal, organism.time, config)
            local_graph.validate(config)
        except (AssertionError, KeyError, ValueError) as exc:
            raise ValueError(f"proposal cannot be replayed: {proposal.signature}") from exc
        candidate_count = len(organism.candidates) - (proposal.candidate_key is not None)
        local_after = compute_energy(local_graph, organism.time, config, candidate_count)
        local_delta = local_after.total - before.total

        original_topology = organism.graph.clone()
        candidate_topology = organism.graph.clone()
        self._topology_only_apply(candidate_topology, proposal, organism.time)
        candidate_topology.validate(config)
        original_replay = self.replay(original_topology, config)
        candidate_replay = self.replay(candidate_topology, config)
        oracle_before = compute_energy(original_replay, organism.time, config, len(organism.candidates))
        oracle_after = compute_energy(candidate_replay, organism.time, config, candidate_count)
        oracle_delta = oracle_after.total - oracle_before.total
        absolute = abs(local_delta - oracle_delta)
        scale = max(abs(oracle_delta), abs(local_delta), 1e-15)
        threshold = config.minimum_energy_improvement
        local_accept = local_delta < -threshold
        oracle_accept = oracle_delta < -threshold
        source_mutated = source_before != organism.snapshot()
        return OracleComparison(
            rule=proposal.kind.value,
            signature=proposal.signature,
            local_delta=local_delta,
            oracle_delta=oracle_delta,
            absolute_error=absolute,
            relative_error=absolute / scale,
            local_accept=local_accept,
            oracle_accept=oracle_accept,
            false_accept=local_accept and not oracle_accept,
            false_reject=not local_accept and oracle_accept,
            state_mutation_during_evaluation=source_mutated,
        )

    def compare_all(self, organism: MathematicalOrganism) -> list[OracleComparison]:
        proposals = generate_proposals(
            organism.graph, organism.candidates, organism.time, organism.config
        )
        return [self.compare(organism, proposal) for proposal in proposals]

    def evaluate_candidates(self, organism: MathematicalOrganism) -> list[OracleComparison]:
        return self.compare_all(organism)

    def scheduler_check(self, organism: MathematicalOrganism) -> dict[str, Any]:
        """Compare local and full-replay winners over the same locally generated set."""
        comparisons = self.compare_all(organism)
        proposals = generate_proposals(
            organism.graph, organism.candidates, organism.time, organism.config
        )
        by_signature = {comparison.signature: comparison for comparison in comparisons}
        local = [proposal for proposal in proposals if by_signature[proposal.signature].local_accept]
        exact = [proposal for proposal in proposals if by_signature[proposal.signature].oracle_accept]
        key = lambda proposal, delta: (
            delta,
            RULE_PRIORITY[proposal.kind],
            proposal.anchor_id,
            repr(proposal.signature),
        )
        local_winner = min(local, key=lambda proposal: key(proposal, by_signature[proposal.signature].local_delta)) if local else None
        exact_winner = min(exact, key=lambda proposal: key(proposal, by_signature[proposal.signature].oracle_delta)) if exact else None
        return {
            "comparisons": comparisons,
            "local_winner": None if local_winner is None else local_winner.signature,
            "oracle_winner": None if exact_winner is None else exact_winner.signature,
            "wrong_winner": (
                None if local_winner is None else local_winner.signature
            ) != (None if exact_winner is None else exact_winner.signature),
            "wrong_tie_break": False,
        }


OracleHarness = ReplayOracle
