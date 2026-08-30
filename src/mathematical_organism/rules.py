from __future__ import annotations

import math
from dataclasses import dataclass
from enum import Enum
from typing import Any, Iterable

from .config import OrganismConfig
from .model import (
    END_ID,
    START_ID,
    Candidate,
    CandidateKind,
    DecayedCounter,
    LatticeGraph,
    NodeKind,
)


class RuleKind(str, Enum):
    MERGE = "MERGE"
    PRUNE = "PRUNE"
    COMPOSE = "COMPOSE"
    SPLIT = "SPLIT"
    GROW_ROUTE = "GROW_ROUTE"
    KEEP = "KEEP"


RULE_PRIORITY = {
    RuleKind.MERGE: 1,
    RuleKind.PRUNE: 2,
    RuleKind.COMPOSE: 3,
    RuleKind.SPLIT: 4,
    RuleKind.GROW_ROUTE: 6,
    RuleKind.KEEP: 7,
}


@dataclass(frozen=True, slots=True)
class Proposal:
    kind: RuleKind
    anchor_id: int
    signature: tuple[Any, ...]
    estimated_delta: float
    payload: dict[str, Any]
    candidate_key: tuple[Any, ...] | None = None

    @property
    def deterministic_key(self) -> tuple[float, int, int, str]:
        return (
            self.estimated_delta,
            RULE_PRIORITY[self.kind],
            self.anchor_id,
            repr(self.signature),
        )


@dataclass(frozen=True, slots=True)
class RuleApplication:
    affected_nodes: tuple[int, ...]
    semantic_proof: tuple[str, ...]
    note: str


def _entropy(weights: Iterable[float]) -> float:
    values = [value for value in weights if value > 0.0]
    total = sum(values)
    if total <= 0.0:
        return 0.0
    return -sum((value / total) * math.log2(value / total) for value in values)


def generate_proposals(
    graph: LatticeGraph,
    candidates: dict[tuple[Any, ...], Candidate],
    now: int,
    config: OrganismConfig,
) -> list[Proposal]:
    proposals: list[Proposal] = []
    proposals.extend(_route_proposals(graph, candidates, now, config))
    proposals.extend(_compose_proposals(graph, candidates, now, config))
    proposals.extend(_split_proposals(graph, now, config))
    proposals.extend(_merge_proposals(graph, now, config))
    proposals.extend(_prune_proposals(graph, now, config))
    return sorted(proposals, key=lambda item: item.deterministic_key)


def _route_proposals(
    graph: LatticeGraph,
    candidates: dict[tuple[Any, ...], Candidate],
    now: int,
    config: OrganismConfig,
) -> list[Proposal]:
    result: list[Proposal] = []
    for key, candidate in candidates.items():
        if candidate.kind is not CandidateKind.ROUTE:
            continue
        support = candidate.support.read(now, config.decay)
        if support + 1e-12 < config.support_threshold(config.route_support):
            continue
        path = tuple(int(item) for item in candidate.signature[1:])
        if not path:
            continue
        route_edges = [(START_ID, path[0])]
        route_edges.extend(zip(path, path[1:]))
        route_edges.append((path[-1], END_ID))
        missing = [edge for edge in route_edges if not graph.has_transition(*edge)]
        if not missing:
            continue
        if len(graph.transitions) + len(missing) > config.max_transitions:
            continue
        represented_symbols = sum(len(graph.nodes[node_id].yield_symbols) for node_id in path)
        saving = support * represented_symbols * (
            config.raw_cost - config.representation_step_cost
        )
        structure = len(missing) * config.transition_cost
        result.append(
            Proposal(
                kind=RuleKind.GROW_ROUTE,
                anchor_id=path[0],
                signature=candidate.signature,
                estimated_delta=structure - saving,
                payload={"path": path, "support": support},
                candidate_key=key,
            )
        )
    return result


def _compose_proposals(
    graph: LatticeGraph,
    candidates: dict[tuple[Any, ...], Candidate],
    now: int,
    config: OrganismConfig,
) -> list[Proposal]:
    result: list[Proposal] = []
    for key, candidate in candidates.items():
        if candidate.kind is not CandidateKind.COMPOSE:
            continue
        support = candidate.support.read(now, config.decay)
        if support + 1e-12 < config.support_threshold(config.compose_support):
            continue
        left_id = int(candidate.signature[1])
        right_id = int(candidate.signature[2])
        if left_id not in graph.nodes or right_id not in graph.nodes:
            continue
        left = graph.nodes[left_id]
        right = graph.nodes[right_id]
        semantic_left = graph.nodes[left.semantic_id]
        semantic_right = graph.nodes[right.semantic_id]
        combined = semantic_left.yield_symbols + semantic_right.yield_symbols
        if len(combined) > config.max_composite_length:
            continue
        if max(semantic_left.depth, semantic_right.depth) + 1 > config.max_composite_depth:
            continue
        existing = graph.semantic_index.get(combined)
        if existing is not None and graph.nodes[existing].routable:
            continue

        contexts = {
            context: counter.read(now, config.decay)
            for context, counter in candidate.contexts.items()
            if counter.read(now, config.decay) > 0.0
        }
        if not contexts:
            continue
        new_transition_count = 0
        prospective_id = existing if existing is not None else graph.next_node_id
        for previous, next_id in contexts:
            if not graph.has_transition(previous, prospective_id):
                new_transition_count += 1
            if not graph.has_transition(prospective_id, next_id):
                new_transition_count += 1
        new_nodes = 0 if existing is not None else 1
        if len(graph.nodes) + new_nodes > config.max_nodes:
            continue
        if len(graph.transitions) + new_transition_count > config.max_transitions:
            continue

        saving = support * config.representation_step_cost
        structure = (
            new_nodes * config.node_cost
            + 2 * new_nodes * config.decomposition_edge_cost
            + new_transition_count * config.transition_cost
        )
        result.append(
            Proposal(
                kind=RuleKind.COMPOSE,
                anchor_id=min(left_id, right_id),
                signature=candidate.signature,
                estimated_delta=structure - saving,
                payload={
                    "left_id": left_id,
                    "right_id": right_id,
                    "support": support,
                    "contexts": contexts,
                },
                candidate_key=key,
            )
        )
    return result


def _best_context_partition(
    contexts: dict[tuple[int, int], float],
    minimum_support: float,
) -> tuple[tuple[tuple[int, int], ...], tuple[tuple[int, int], ...], float] | None:
    if len(contexts) < 2:
        return None
    before_total = sum(contexts.values())
    before_entropy = before_total * _entropy(contexts.values())
    best: tuple[float, tuple[tuple[int, int], ...], tuple[tuple[int, int], ...]] | None = None

    for axis in (0, 1):
        values = sorted({context[axis] for context in contexts})
        for selected in values:
            first = tuple(sorted(context for context in contexts if context[axis] == selected))
            second = tuple(sorted(context for context in contexts if context[axis] != selected))
            first_weight = sum(contexts[item] for item in first)
            second_weight = sum(contexts[item] for item in second)
            if first_weight < minimum_support or second_weight < minimum_support:
                continue
            after = (
                first_weight * _entropy(contexts[item] for item in first)
                + second_weight * _entropy(contexts[item] for item in second)
            )
            gain = before_entropy - after
            candidate = (-gain, first, second)
            if best is None or candidate < best:
                best = candidate
    if best is None:
        return None
    return best[1], best[2], -best[0]


def _split_proposals(
    graph: LatticeGraph,
    now: int,
    config: OrganismConfig,
) -> list[Proposal]:
    result: list[Proposal] = []
    for node in sorted(graph.nodes.values(), key=lambda item: item.id):
        # V0 splits learned composites only. Canonical atoms remain routable so
        # every observed symbol always has a stable base representation.
        if not node.routable or node.kind is not NodeKind.COMPOSITE:
            continue
        contexts = {
            context: counter.read(now, config.decay)
            for context, counter in node.contexts.items()
            if counter.read(now, config.decay) > 0.0
        }
        if any(node.id in context for context in contexts):
            continue
        partition = _best_context_partition(
            contexts, config.support_threshold(config.child_support)
        )
        if partition is None:
            continue
        first, second, entropy_gain = partition
        transition_growth = 2 * (len(first) + len(second)) - sum(
            1 for key in graph.transitions if node.id in key
        )
        transition_growth = max(0, transition_growth)
        if len(graph.nodes) + 2 > config.max_nodes:
            continue
        if len(graph.transitions) + transition_growth > config.max_transitions:
            continue
        structure = 2 * config.node_cost + transition_growth * config.transition_cost
        estimated_delta = structure - config.context_entropy_cost * entropy_gain
        result.append(
            Proposal(
                kind=RuleKind.SPLIT,
                anchor_id=node.id,
                signature=("split", node.id, first, second),
                estimated_delta=estimated_delta,
                payload={
                    "node_id": node.id,
                    "first": first,
                    "second": second,
                    "contexts": contexts,
                },
            )
        )
    return result


def _merge_proposals(
    graph: LatticeGraph,
    now: int,
    config: OrganismConfig,
) -> list[Proposal]:
    by_semantic: dict[int, list[int]] = {}
    for node in graph.nodes.values():
        if node.kind is NodeKind.INSTANCE and node.routable:
            by_semantic.setdefault(node.semantic_id, []).append(node.id)

    result: list[Proposal] = []
    for semantic_id, instance_ids in sorted(by_semantic.items()):
        if len(instance_ids) < 2:
            continue
        instance_ids.sort()
        left_id, right_id = instance_ids[0], instance_ids[1]
        left = graph.nodes[left_id]
        right = graph.nodes[right_id]
        left_contexts = {
            key: counter.read(now, config.decay) for key, counter in left.contexts.items()
        }
        right_contexts = {
            key: counter.read(now, config.decay) for key, counter in right.contexts.items()
        }
        combined: dict[tuple[int, int], float] = dict(left_contexts)
        for key, value in right_contexts.items():
            combined[key] = combined.get(key, 0.0) + value
        before = (
            sum(left_contexts.values()) * _entropy(left_contexts.values())
            + sum(right_contexts.values()) * _entropy(right_contexts.values())
        )
        after = sum(combined.values()) * _entropy(combined.values())
        entropy_penalty = config.context_entropy_cost * (after - before)
        structural_saving = 2 * config.node_cost
        estimated_delta = entropy_penalty - structural_saving
        result.append(
            Proposal(
                kind=RuleKind.MERGE,
                anchor_id=semantic_id,
                signature=("merge", semantic_id, left_id, right_id),
                estimated_delta=estimated_delta,
                payload={"semantic_id": semantic_id, "instances": (left_id, right_id)},
            )
        )
    return result


def _prune_proposals(
    graph: LatticeGraph,
    now: int,
    config: OrganismConfig,
) -> list[Proposal]:
    result: list[Proposal] = []
    referenced = {
        child
        for node in graph.nodes.values()
        if node.children is not None
        for child in node.children
    }
    for node in sorted(graph.nodes.values(), key=lambda item: item.id):
        if node.kind is NodeKind.ATOM or node.id in referenced:
            continue
        usage = node.usage.read(now, config.decay)
        if usage > config.prune_strength:
            continue
        incident_edges = sum(1 for key in graph.transitions if node.id in key)
        structure_saving = config.node_cost + incident_edges * config.transition_cost
        lost_data = usage * len(node.yield_symbols) * config.raw_cost
        result.append(
            Proposal(
                kind=RuleKind.PRUNE,
                anchor_id=node.id,
                signature=("prune", node.id),
                estimated_delta=lost_data - structure_saving,
                payload={"node_id": node.id, "usage": usage},
            )
        )
    return result


def apply_proposal(
    graph: LatticeGraph,
    proposal: Proposal,
    now: int,
    config: OrganismConfig,
) -> RuleApplication:
    if proposal.kind is RuleKind.GROW_ROUTE:
        return _apply_route(graph, proposal, now, config)
    if proposal.kind is RuleKind.COMPOSE:
        return _apply_compose(graph, proposal, now, config)
    if proposal.kind is RuleKind.SPLIT:
        return _apply_split(graph, proposal, now, config)
    if proposal.kind is RuleKind.MERGE:
        return _apply_merge(graph, proposal, now, config)
    if proposal.kind is RuleKind.PRUNE:
        return _apply_prune(graph, proposal, now, config)
    raise ValueError(f"unsupported proposal {proposal.kind}")


def _apply_route(
    graph: LatticeGraph,
    proposal: Proposal,
    now: int,
    config: OrganismConfig,
) -> RuleApplication:
    path: tuple[int, ...] = proposal.payload["path"]
    requested_support = float(proposal.payload["support"])
    symbol_count = sum(len(graph.nodes[node_id].yield_symbols) for node_id in path)
    removed_raw = graph.raw_usage.subtract(
        requested_support * symbol_count, now, config.decay
    )
    effective_support = removed_raw / symbol_count if symbol_count else 0.0
    if effective_support <= 0.0:
        effective_support = min(requested_support, 1e-12)

    for index, node_id in enumerate(path):
        node = graph.nodes[node_id]
        node.usage.add(effective_support, now, config.decay)
        previous = START_ID if index == 0 else path[index - 1]
        next_id = END_ID if index + 1 == len(path) else path[index + 1]
        node.observe_context(previous, next_id, effective_support, now, config.decay)

    edges = [(START_ID, path[0]), *zip(path, path[1:]), (path[-1], END_ID)]
    for source, target in edges:
        if not graph.has_transition(source, target):
            graph.add_transition(
                source,
                target,
                now,
                initial_usage=effective_support,
                decay=config.decay,
            )

    return RuleApplication(
        affected_nodes=tuple(sorted(set(path))),
        semantic_proof=("route uses canonical atoms in observed order",),
        note=f"activated atomic route with support {effective_support:.6f}",
    )


def _apply_compose(
    graph: LatticeGraph,
    proposal: Proposal,
    now: int,
    config: OrganismConfig,
) -> RuleApplication:
    left_id = int(proposal.payload["left_id"])
    right_id = int(proposal.payload["right_id"])
    left = graph.nodes[left_id]
    right = graph.nodes[right_id]
    composite_id, created = graph.add_composite(left.semantic_id, right.semantic_id, now)
    composite = graph.nodes[composite_id]
    composite.routable = True

    contexts: dict[tuple[int, int], float] = proposal.payload["contexts"]
    total = 0.0
    for (previous, next_id), amount in sorted(contexts.items()):
        if amount <= 0.0:
            continue
        total += amount
        left.usage.subtract(amount, now, config.decay)
        right.usage.subtract(amount, now, config.decay)
        for source, target in (
            (previous, left_id),
            (left_id, right_id),
            (right_id, next_id),
        ):
            edge = graph.transitions.get((source, target))
            if edge is not None:
                edge.usage.subtract(amount, now, config.decay)
        graph.add_transition(
            previous, composite_id, now, initial_usage=amount, decay=config.decay
        )
        graph.add_transition(
            composite_id, next_id, now, initial_usage=amount, decay=config.decay
        )
        composite.observe_context(previous, next_id, amount, now, config.decay)
    composite.usage.add(total, now, config.decay)

    proof = (
        f"gamma({composite_id}) = gamma({left.semantic_id}) concatenated with gamma({right.semantic_id})",
        f"yield={''.join(composite.yield_symbols)}",
    )
    return RuleApplication(
        affected_nodes=tuple(sorted({left_id, right_id, composite_id})),
        semantic_proof=proof,
        note="created composite" if created else "reused canonical composite",
    )


def _apply_split(
    graph: LatticeGraph,
    proposal: Proposal,
    now: int,
    config: OrganismConfig,
) -> RuleApplication:
    node_id = int(proposal.payload["node_id"])
    node = graph.nodes[node_id]
    semantic_id = node.semantic_id
    first_id = graph.add_instance(semantic_id, now)
    second_id = graph.add_instance(semantic_id, now)
    contexts: dict[tuple[int, int], float] = proposal.payload["contexts"]

    for instance_id, group in (
        (first_id, proposal.payload["first"]),
        (second_id, proposal.payload["second"]),
    ):
        instance = graph.nodes[instance_id]
        for context in group:
            previous, next_id = context
            amount = contexts[context]
            instance.usage.add(amount, now, config.decay)
            instance.observe_context(previous, next_id, amount, now, config.decay)
            graph.add_transition(
                previous, instance_id, now, initial_usage=amount, decay=config.decay
            )
            graph.add_transition(
                instance_id, next_id, now, initial_usage=amount, decay=config.decay
            )

    for key in [key for key in graph.transitions if node_id in key]:
        del graph.transitions[key]
    node.usage.subtract(node.usage.read(now, config.decay), now, config.decay)
    node.contexts.clear()
    node.routable = False

    return RuleApplication(
        affected_nodes=(node_id, first_id, second_id),
        semantic_proof=(
            f"gamma({first_id}) = gamma({second_id}) = gamma({semantic_id})",
        ),
        note="split one route into two context-specific instances",
    )


def _apply_merge(
    graph: LatticeGraph,
    proposal: Proposal,
    now: int,
    config: OrganismConfig,
) -> RuleApplication:
    semantic_id = int(proposal.payload["semantic_id"])
    instance_ids: tuple[int, int] = proposal.payload["instances"]
    semantic = graph.nodes[semantic_id]
    semantic.routable = True

    for instance_id in instance_ids:
        instance = graph.nodes[instance_id]
        amount = instance.usage.read(now, config.decay)
        semantic.usage.add(amount, now, config.decay)
        for (previous, next_id), counter in sorted(instance.contexts.items()):
            context_weight = counter.read(now, config.decay)
            semantic.observe_context(
                previous, next_id, context_weight, now, config.decay
            )
            graph.add_transition(
                previous,
                semantic_id,
                now,
                initial_usage=context_weight,
                decay=config.decay,
            )
            graph.add_transition(
                semantic_id,
                next_id,
                now,
                initial_usage=context_weight,
                decay=config.decay,
            )

    for instance_id in instance_ids:
        graph.remove_node(instance_id)

    return RuleApplication(
        affected_nodes=(semantic_id, *instance_ids),
        semantic_proof=(
            f"merged instances share semantic node {semantic_id}",
        ),
        note="merged two context instances",
    )


def _apply_prune(
    graph: LatticeGraph,
    proposal: Proposal,
    now: int,
    config: OrganismConfig,
) -> RuleApplication:
    node_id = int(proposal.payload["node_id"])
    node = graph.nodes[node_id]
    usage = node.usage.read(now, config.decay)
    if usage > 0.0:
        graph.raw_usage.add(
            usage * len(node.yield_symbols), now, config.decay
        )
    graph.remove_node(node_id)
    return RuleApplication(
        affected_nodes=(node_id,),
        semantic_proof=("RAW fallback preserves reconstructability",),
        note="pruned weak non-atomic node",
    )
