from __future__ import annotations

import copy
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Iterable

from .config import OrganismConfig


START_ID = -1
END_ID = -2


class NodeKind(str, Enum):
    ATOM = "ATOM"
    COMPOSITE = "COMPOSITE"
    INSTANCE = "INSTANCE"


class CandidateKind(str, Enum):
    ROUTE = "GROW_ROUTE"
    COMPOSE = "COMPOSE"


class CandidateStatus(str, Enum):
    SEED = "SEED"
    ELIGIBLE = "ELIGIBLE"
    REJECTED = "REJECTED"
    EXPIRED = "EXPIRED"


@dataclass(slots=True)
class DecayedCounter:
    value: float = 0.0
    last_time: int = 0

    def read(self, now: int, decay: float) -> float:
        if now < self.last_time:
            raise ValueError("time cannot move backwards")
        if self.value == 0.0 or now == self.last_time:
            return self.value
        return self.value * (decay ** (now - self.last_time))

    def touch(self, now: int, decay: float) -> float:
        self.value = self.read(now, decay)
        self.last_time = now
        if abs(self.value) < 1e-15:
            self.value = 0.0
        return self.value

    def add(self, amount: float, now: int, decay: float) -> None:
        if amount < 0.0:
            raise ValueError("amount must be non-negative")
        self.touch(now, decay)
        self.value += amount

    def subtract(self, amount: float, now: int, decay: float) -> float:
        if amount < 0.0:
            raise ValueError("amount must be non-negative")
        self.touch(now, decay)
        removed = min(amount, self.value)
        self.value -= removed
        return removed


@dataclass(slots=True)
class Node:
    id: int
    kind: NodeKind
    yield_symbols: tuple[str, ...]
    semantic_id: int
    children: tuple[int, int] | None
    depth: int
    created_at: int
    routable: bool = True
    usage: DecayedCounter = field(default_factory=DecayedCounter)
    contexts: dict[tuple[int, int], DecayedCounter] = field(default_factory=dict)

    def observe_context(
        self,
        previous_id: int,
        next_id: int,
        amount: float,
        now: int,
        decay: float,
    ) -> None:
        key = (previous_id, next_id)
        counter = self.contexts.setdefault(key, DecayedCounter(last_time=now))
        counter.add(amount, now, decay)


@dataclass(slots=True)
class Transition:
    source: int
    target: int
    created_at: int
    usage: DecayedCounter = field(default_factory=DecayedCounter)


@dataclass(slots=True)
class Candidate:
    kind: CandidateKind
    signature: tuple[Any, ...]
    created_at: int
    last_observed: int
    support: DecayedCounter = field(default_factory=DecayedCounter)
    contexts: dict[tuple[int, int], DecayedCounter] = field(default_factory=dict)
    status: CandidateStatus = CandidateStatus.SEED

    def observe(
        self,
        now: int,
        decay: float,
        amount: float = 1.0,
        context: tuple[int, int] | None = None,
    ) -> None:
        self.support.add(amount, now, decay)
        self.last_observed = now
        if context is not None:
            counter = self.contexts.setdefault(context, DecayedCounter(last_time=now))
            counter.add(amount, now, decay)


class LatticeGraph:
    """Mutable reference graph with explicit semantic yields."""

    def __init__(self) -> None:
        self.nodes: dict[int, Node] = {}
        self.transitions: dict[tuple[int, int], Transition] = {}
        self.atom_index: dict[str, int] = {}
        self.semantic_index: dict[tuple[str, ...], int] = {}
        self.next_node_id = 0
        self.raw_usage = DecayedCounter()

    def clone(self) -> "LatticeGraph":
        return copy.deepcopy(self)

    def add_atom(self, symbol: str, now: int) -> tuple[int, bool]:
        existing = self.atom_index.get(symbol)
        if existing is not None:
            return existing, False
        node_id = self.next_node_id
        self.next_node_id += 1
        node = Node(
            id=node_id,
            kind=NodeKind.ATOM,
            yield_symbols=(symbol,),
            semantic_id=node_id,
            children=None,
            depth=1,
            created_at=now,
        )
        self.nodes[node_id] = node
        self.atom_index[symbol] = node_id
        self.semantic_index[node.yield_symbols] = node_id
        return node_id, True

    def add_composite(self, left_id: int, right_id: int, now: int) -> tuple[int, bool]:
        left = self.nodes[left_id]
        right = self.nodes[right_id]
        yield_symbols = left.yield_symbols + right.yield_symbols
        existing = self.semantic_index.get(yield_symbols)
        if existing is not None:
            return existing, False
        node_id = self.next_node_id
        self.next_node_id += 1
        node = Node(
            id=node_id,
            kind=NodeKind.COMPOSITE,
            yield_symbols=yield_symbols,
            semantic_id=node_id,
            children=(left.semantic_id, right.semantic_id),
            depth=max(left.depth, right.depth) + 1,
            created_at=now,
        )
        self.nodes[node_id] = node
        self.semantic_index[yield_symbols] = node_id
        return node_id, True

    def add_instance(self, semantic_id: int, now: int) -> int:
        semantic = self.nodes[semantic_id]
        if semantic.kind is NodeKind.INSTANCE:
            raise ValueError("instances must reference a semantic node")
        node_id = self.next_node_id
        self.next_node_id += 1
        self.nodes[node_id] = Node(
            id=node_id,
            kind=NodeKind.INSTANCE,
            yield_symbols=semantic.yield_symbols,
            semantic_id=semantic_id,
            children=None,
            depth=semantic.depth,
            created_at=now,
        )
        return node_id

    def add_transition(
        self,
        source: int,
        target: int,
        now: int,
        initial_usage: float = 0.0,
        decay: float = 1.0,
    ) -> tuple[Transition, bool]:
        self._validate_endpoint(source, is_source=True)
        self._validate_endpoint(target, is_source=False)
        key = (source, target)
        existing = self.transitions.get(key)
        if existing is not None:
            if initial_usage > 0.0:
                existing.usage.add(initial_usage, now, decay)
            return existing, False
        edge = Transition(source=source, target=target, created_at=now)
        if initial_usage > 0.0:
            edge.usage.add(initial_usage, now, decay)
        self.transitions[key] = edge
        return edge, True

    def _validate_endpoint(self, node_id: int, *, is_source: bool) -> None:
        if node_id == START_ID:
            if not is_source:
                raise ValueError("START cannot be a transition target")
            return
        if node_id == END_ID:
            if is_source:
                raise ValueError("END cannot be a transition source")
            return
        if node_id not in self.nodes:
            raise KeyError(f"unknown node {node_id}")

    def has_transition(self, source: int, target: int) -> bool:
        return (source, target) in self.transitions

    def outgoing(self, source: int) -> list[Transition]:
        return sorted(
            (edge for edge in self.transitions.values() if edge.source == source),
            key=lambda edge: edge.target,
        )

    def remove_transition(self, source: int, target: int) -> Transition | None:
        return self.transitions.pop((source, target), None)

    def remove_node(self, node_id: int) -> Node:
        node = self.nodes[node_id]
        if node.kind is NodeKind.ATOM:
            raise ValueError("canonical atoms cannot be removed in V0")
        for other in self.nodes.values():
            if other.children is not None and node_id in other.children:
                raise ValueError("cannot remove a node used by a decomposition")
        for key in [key for key in self.transitions if node_id in key]:
            del self.transitions[key]
        del self.nodes[node_id]
        if node.kind is NodeKind.COMPOSITE:
            self.semantic_index.pop(node.yield_symbols, None)
        return node

    def matching_nodes(self, symbols: tuple[str, ...], position: int) -> Iterable[Node]:
        for node in sorted(self.nodes.values(), key=lambda item: item.id):
            if not node.routable:
                continue
            end = position + len(node.yield_symbols)
            if end <= len(symbols) and symbols[position:end] == node.yield_symbols:
                yield node

    def decomposition_edge_count(self) -> int:
        return sum(2 for node in self.nodes.values() if node.children is not None)

    def validate(self, config: OrganismConfig) -> None:
        if len(self.nodes) > config.max_nodes:
            raise AssertionError("node budget exceeded")
        if len(self.transitions) > config.max_transitions:
            raise AssertionError("transition budget exceeded")
        if self.decomposition_edge_count() > config.max_decomposition_edges:
            raise AssertionError("decomposition edge budget exceeded")
        if len(self.atom_index) > config.alphabet_limit:
            raise AssertionError("alphabet budget exceeded")

        seen_atom_symbols: set[str] = set()
        for node in self.nodes.values():
            if not node.yield_symbols:
                raise AssertionError("an active node has an empty meaning")
            if node.depth > config.max_composite_depth:
                raise AssertionError("composite depth exceeded")
            if len(node.yield_symbols) > config.max_composite_length:
                raise AssertionError("composite length exceeded")
            if node.kind is NodeKind.ATOM:
                symbol = node.yield_symbols[0]
                if len(node.yield_symbols) != 1 or symbol in seen_atom_symbols:
                    raise AssertionError("canonical atom invariant failed")
                seen_atom_symbols.add(symbol)
                if node.semantic_id != node.id:
                    raise AssertionError("atom semantic id mismatch")
            elif node.kind is NodeKind.COMPOSITE:
                if node.children is None:
                    raise AssertionError("composite without children")
                left, right = (self.nodes[item] for item in node.children)
                if left.kind is NodeKind.INSTANCE or right.kind is NodeKind.INSTANCE:
                    raise AssertionError("decomposition must use semantic nodes")
                if left.yield_symbols + right.yield_symbols != node.yield_symbols:
                    raise AssertionError("composite meaning mismatch")
                if node.semantic_id != node.id:
                    raise AssertionError("composite semantic id mismatch")
            else:
                semantic = self.nodes.get(node.semantic_id)
                if semantic is None or semantic.kind is NodeKind.INSTANCE:
                    raise AssertionError("instance semantic reference is invalid")
                if semantic.yield_symbols != node.yield_symbols:
                    raise AssertionError("instance meaning mismatch")

        for symbols, node_id in self.semantic_index.items():
            node = self.nodes.get(node_id)
            if node is None or node.kind is NodeKind.INSTANCE or node.yield_symbols != symbols:
                raise AssertionError("semantic index mismatch")

        self._validate_decomposition_dag()
        for edge in self.transitions.values():
            self._validate_endpoint(edge.source, is_source=True)
            self._validate_endpoint(edge.target, is_source=False)

    def _validate_decomposition_dag(self) -> None:
        visiting: set[int] = set()
        visited: set[int] = set()

        def visit(node_id: int) -> None:
            if node_id in visited:
                return
            if node_id in visiting:
                raise AssertionError("decomposition cycle detected")
            visiting.add(node_id)
            node = self.nodes[node_id]
            if node.children is not None:
                for child in node.children:
                    visit(child)
            visiting.remove(node_id)
            visited.add(node_id)

        for node_id in sorted(self.nodes):
            visit(node_id)

    def snapshot(self, now: int, decay: float) -> dict[str, Any]:
        return {
            "next_node_id": self.next_node_id,
            "raw_usage": self.raw_usage.read(now, decay),
            "nodes": [
                {
                    "id": node.id,
                    "kind": node.kind.value,
                    "yield": list(node.yield_symbols),
                    "semantic_id": node.semantic_id,
                    "children": list(node.children) if node.children else None,
                    "depth": node.depth,
                    "routable": node.routable,
                    "usage": node.usage.read(now, decay),
                    "contexts": [
                        {
                            "previous": previous,
                            "next": next_id,
                            "weight": counter.read(now, decay),
                        }
                        for (previous, next_id), counter in sorted(node.contexts.items())
                    ],
                }
                for node in sorted(self.nodes.values(), key=lambda item: item.id)
            ],
            "transitions": [
                {
                    "source": edge.source,
                    "target": edge.target,
                    "usage": edge.usage.read(now, decay),
                }
                for edge in sorted(
                    self.transitions.values(), key=lambda item: (item.source, item.target)
                )
            ],
        }

