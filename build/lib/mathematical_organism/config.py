from __future__ import annotations

from dataclasses import dataclass
import math


@dataclass(frozen=True, slots=True)
class OrganismConfig:
    """Finite limits and energy coefficients for the V0 reference model."""

    alphabet_limit: int = 16
    max_input_length: int = 64
    max_nodes: int = 4096
    max_transitions: int = 16384
    max_decomposition_edges: int = 8192
    max_candidates: int = 2048
    max_composite_depth: int = 8
    max_composite_length: int = 16
    mutations_per_input: int = 1

    decay: float = 1023.0 / 1024.0
    smoothing: float = 1.0
    raw_cost: float = 8.0
    representation_step_cost: float = 1.0
    node_cost: float = 0.75
    transition_cost: float = 0.20
    decomposition_edge_cost: float = 0.20
    candidate_cost: float = 0.005
    context_entropy_cost: float = 1.50
    minimum_energy_improvement: float = 1e-9

    route_support: float = 2.0
    compose_support: float = 4.0
    child_support: float = 4.0
    prune_strength: float = 0.05
    candidate_expiry_steps: int = 4096

    def support_threshold(self, observations: float) -> float:
        """Decayed weight produced by consecutive unit observations."""
        if observations <= 0.0:
            return 0.0
        whole = int(math.floor(observations))
        fraction = observations - whole
        total = sum(self.decay**index for index in range(whole))
        if fraction > 0.0:
            total += fraction * (self.decay**whole)
        return total

    def validate(self) -> None:
        integer_limits = (
            self.alphabet_limit,
            self.max_input_length,
            self.max_nodes,
            self.max_transitions,
            self.max_decomposition_edges,
            self.max_candidates,
            self.max_composite_depth,
            self.max_composite_length,
            self.mutations_per_input,
        )
        if any(value <= 0 for value in integer_limits):
            raise ValueError("all finite limits must be positive")
        if not 0.0 < self.decay <= 1.0:
            raise ValueError("decay must be in (0, 1]")
        if self.smoothing <= 0.0:
            raise ValueError("smoothing must be positive")
        if self.raw_cost <= 0.0:
            raise ValueError("raw_cost must be positive")
        if self.minimum_energy_improvement < 0.0:
            raise ValueError("minimum_energy_improvement must be non-negative")
