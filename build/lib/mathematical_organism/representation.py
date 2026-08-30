from __future__ import annotations

import math
from dataclasses import dataclass
from functools import lru_cache

from .config import OrganismConfig
from .model import END_ID, START_ID, LatticeGraph


@dataclass(frozen=True, slots=True)
class RepresentationUnit:
    node_id: int | None
    raw_symbol: str | None
    start: int
    length: int

    @property
    def is_raw(self) -> bool:
        return self.node_id is None

    def tie_token(self) -> str:
        if self.node_id is not None:
            return f"N:{self.node_id:020d}"
        return f"R:{self.raw_symbol}"


@dataclass(frozen=True, slots=True)
class RepresentationPlan:
    units: tuple[RepresentationUnit, ...]
    cost: float
    raw_count: int

    @property
    def node_path(self) -> tuple[int, ...]:
        return tuple(unit.node_id for unit in self.units if unit.node_id is not None)

    @property
    def raw_positions(self) -> tuple[int, ...]:
        return tuple(unit.start for unit in self.units if unit.is_raw)

    @property
    def tie_key(self) -> tuple[str, ...]:
        return tuple(unit.tie_token() for unit in self.units)

    def reconstruct(self, graph: LatticeGraph) -> tuple[str, ...]:
        result: list[str] = []
        for unit in self.units:
            if unit.node_id is not None:
                result.extend(graph.nodes[unit.node_id].yield_symbols)
            else:
                if unit.raw_symbol is None:
                    raise AssertionError("RAW unit has no symbol")
                result.append(unit.raw_symbol)
        return tuple(result)


def transition_probability(
    graph: LatticeGraph,
    source: int,
    target: int,
    now: int,
    config: OrganismConfig,
) -> float:
    outgoing = graph.outgoing(source)
    denominator = sum(edge.usage.read(now, config.decay) for edge in outgoing)
    denominator += config.smoothing * (len(outgoing) + 1)
    edge = graph.transitions.get((source, target))
    if edge is None:
        return 0.0
    numerator = edge.usage.read(now, config.decay) + config.smoothing
    return numerator / denominator


def transition_information_cost(
    graph: LatticeGraph,
    source: int,
    target: int,
    now: int,
    config: OrganismConfig,
) -> float:
    probability = transition_probability(graph, source, target, now, config)
    if probability <= 0.0:
        return math.inf
    return -math.log2(probability)


def find_best_representation(
    graph: LatticeGraph,
    symbols: tuple[str, ...],
    now: int,
    config: OrganismConfig,
) -> RepresentationPlan:
    """Find the exact minimum-cost node/RAW plan with deterministic ties."""

    def rank(plan: RepresentationPlan) -> tuple[float, int, int, tuple[str, ...]]:
        return (plan.cost, plan.raw_count, len(plan.units), plan.tie_key)

    @lru_cache(maxsize=None)
    def solve(position: int, previous_node: int | None) -> RepresentationPlan | None:
        if position == len(symbols):
            if previous_node is None:
                return RepresentationPlan((), 0.0, 0)
            if not graph.has_transition(previous_node, END_ID):
                return None
            end_cost = transition_information_cost(
                graph, previous_node, END_ID, now, config
            )
            return RepresentationPlan((), end_cost, 0)

        options: list[RepresentationPlan] = []

        raw_prefix_cost = config.raw_cost + config.representation_step_cost
        if previous_node is not None:
            if graph.has_transition(previous_node, END_ID):
                raw_prefix_cost += transition_information_cost(
                    graph, previous_node, END_ID, now, config
                )
            else:
                raw_prefix_cost = math.inf
        if math.isfinite(raw_prefix_cost):
            suffix = solve(position + 1, None)
            if suffix is not None:
                raw = RepresentationUnit(
                    node_id=None,
                    raw_symbol=symbols[position],
                    start=position,
                    length=1,
                )
                options.append(
                    RepresentationPlan(
                        units=(raw,) + suffix.units,
                        cost=raw_prefix_cost + suffix.cost,
                        raw_count=1 + suffix.raw_count,
                    )
                )

        source = START_ID if previous_node is None else previous_node
        for node in graph.matching_nodes(symbols, position):
            if not graph.has_transition(source, node.id):
                continue
            next_position = position + len(node.yield_symbols)
            suffix = solve(next_position, node.id)
            if suffix is None:
                continue
            unit = RepresentationUnit(
                node_id=node.id,
                raw_symbol=None,
                start=position,
                length=len(node.yield_symbols),
            )
            edge_cost = transition_information_cost(graph, source, node.id, now, config)
            options.append(
                RepresentationPlan(
                    units=(unit,) + suffix.units,
                    cost=config.representation_step_cost + edge_cost + suffix.cost,
                    raw_count=suffix.raw_count,
                )
            )

        if not options:
            return None
        return min(options, key=rank)

    plan = solve(0, None)
    if plan is None:
        raise AssertionError("RAW fallback failed to represent the input")
    if plan.reconstruct(graph) != symbols:
        raise AssertionError("representation does not reconstruct the input")
    return plan

