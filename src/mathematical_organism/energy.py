from __future__ import annotations

import math
from dataclasses import dataclass

from .config import OrganismConfig
from .model import LatticeGraph
from .representation import transition_probability


@dataclass(frozen=True, slots=True)
class EnergyBreakdown:
    raw: float
    steps: float
    transitions: float
    nodes: float
    transition_structure: float
    decomposition: float
    candidates: float
    context_entropy: float

    @property
    def total(self) -> float:
        return (
            self.raw
            + self.steps
            + self.transitions
            + self.nodes
            + self.transition_structure
            + self.decomposition
            + self.candidates
            + self.context_entropy
        )

    def to_dict(self) -> dict[str, float]:
        return {
            "raw": self.raw,
            "steps": self.steps,
            "transitions": self.transitions,
            "nodes": self.nodes,
            "transition_structure": self.transition_structure,
            "decomposition": self.decomposition,
            "candidates": self.candidates,
            "context_entropy": self.context_entropy,
            "total": self.total,
        }


def _entropy(weights: list[float]) -> float:
    total = sum(weights)
    if total <= 0.0:
        return 0.0
    value = 0.0
    for weight in weights:
        if weight <= 0.0:
            continue
        probability = weight / total
        value -= probability * math.log2(probability)
    return value


def compute_energy(
    graph: LatticeGraph,
    now: int,
    config: OrganismConfig,
    candidate_count: int,
) -> EnergyBreakdown:
    raw_usage = graph.raw_usage.read(now, config.decay)
    node_usage = sum(node.usage.read(now, config.decay) for node in graph.nodes.values())

    transition_loss = 0.0
    for edge in graph.transitions.values():
        weight = edge.usage.read(now, config.decay)
        if weight <= 0.0:
            continue
        probability = transition_probability(
            graph, edge.source, edge.target, now, config
        )
        transition_loss -= weight * math.log2(probability)

    context_entropy = 0.0
    for node in graph.nodes.values():
        context_weights = [
            counter.read(now, config.decay) for counter in node.contexts.values()
        ]
        context_entropy += (
            node.usage.read(now, config.decay) * _entropy(context_weights)
        )

    return EnergyBreakdown(
        raw=config.raw_cost * raw_usage,
        steps=config.representation_step_cost * (raw_usage + node_usage),
        transitions=transition_loss,
        nodes=config.node_cost * len(graph.nodes),
        transition_structure=config.transition_cost * len(graph.transitions),
        decomposition=(
            config.decomposition_edge_cost * graph.decomposition_edge_count()
        ),
        candidates=config.candidate_cost * candidate_count,
        context_entropy=config.context_entropy_cost * context_entropy,
    )

