"""Explicit Python-host/native-core sandbox replay boundary.

The reference sandbox remains authoritative.  This module only turns one
reference ``live_step`` into a deterministic native action-trace epoch; it
does not let the native library inspect the filesystem or choose biological
actions.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .backend import NativeAction, NativeActionKind, NativePopulationBackend
from .lifecycle import LifecycleConfig


@dataclass(frozen=True, slots=True)
class NativeSandboxEpoch:
    """Immutable outer result of one host-built native replay epoch."""

    index: int
    traces: tuple[tuple[int, tuple[NativeAction, ...]], ...]
    results: tuple[tuple[int, tuple[dict[str, object], ...]], ...]
    snapshots: tuple[tuple[int, dict[str, object]], ...]
    corpses: tuple[tuple[int, dict[str, object]], ...]


class NativeSandboxReplay:
    """Replay Python ``AutonomousOrganism.live_step`` traces through C.

    The caller owns the Python ``SandboxRuntime`` and continues to use it as
    the oracle.  This adapter owns native handles and closes dead handles
    after transferring their immutable-friendly snapshots.  Native failures
    are surfaced; there is no fallback.
    """

    def __init__(
        self,
        library: str | Path,
        runtime: Any,
        *,
        config: LifecycleConfig | None = None,
        organism_ids: tuple[int, ...] = (0,),
    ) -> None:
        if not organism_ids or len(set(organism_ids)) != len(organism_ids):
            raise ValueError("organism_ids must be non-empty and unique")
        organisms = tuple(runtime.organisms)
        if len(organisms) != len(organism_ids):
            raise ValueError("organism_ids must map exactly to initial Python organisms")
        self.runtime = runtime
        self._native_ids: dict[str, int] = {
            organism.name: int(organism_ids[index])
            for index, organism in enumerate(organisms)
        }
        self._population = NativePopulationBackend(
            library,
            organism_ids=organism_ids,
            config=config,
        )
        self._epoch = 0
        self._closed = False

    @property
    def population(self) -> NativePopulationBackend:
        """Expose the owned population for explicit conservation checks."""
        if self._closed:
            raise RuntimeError("native sandbox replay is closed")
        return self._population

    @property
    def organism_ids(self) -> tuple[int, ...]:
        """Return currently owned native IDs in deterministic order."""
        return self._population.organism_ids

    def step(self) -> NativeSandboxEpoch:
        """Run one Python-oracle step and replay its native action traces."""
        if self._closed:
            raise RuntimeError("native sandbox replay is closed")
        traces: dict[int, tuple[NativeAction, ...]] = {}
        for organism in tuple(self.runtime.organisms):
            if not organism.alive:
                continue
            try:
                native_id = self._native_ids[organism.name]
            except KeyError as error:
                raise RuntimeError(
                    f"Python organism has no native handle: {organism.name}"
                ) from error
            trace: list[NativeAction] = []
            organism.live_step(self.runtime, action_trace=trace)
            traces[native_id] = tuple(trace)
            division = next(
                (action for action in trace if action.kind is NativeActionKind.DIVISION),
                None,
            )
            if division is not None:
                if not organism.children:
                    raise RuntimeError("division trace has no Python child")
                child = organism.children[-1]
                if child.name in self._native_ids:
                    raise RuntimeError(f"Python child already has a native handle: {child.name}")
                self._native_ids[child.name] = division.child_id

        replayed = self._population.replay_action_traces(traces)
        snapshots: dict[int, dict[str, object]] = {}
        corpses: dict[int, dict[str, object]] = {}
        for organism_id in self._population.organism_ids:
            snapshot = self._population.snapshot(organism_id)
            if int(snapshot["status"]) == 1:
                corpses[organism_id] = self._population.take_corpse(organism_id)
            else:
                snapshots[organism_id] = snapshot
        self._population.verify_material_conservation()
        epoch = NativeSandboxEpoch(
            self._epoch,
            tuple((organism_id, traces[organism_id]) for organism_id in sorted(traces)),
            tuple((organism_id, tuple(replayed[organism_id])) for organism_id in sorted(replayed)),
            tuple(sorted(snapshots.items())),
            tuple(sorted(corpses.items())),
        )
        self._epoch += 1
        return epoch

    def close(self) -> None:
        """Close all remaining native handles exactly once."""
        if not self._closed:
            self._population.close()
            self._closed = True

    def __enter__(self) -> "NativeSandboxReplay":
        return self

    def __exit__(self, _exc_type: object, _exc_value: object, _traceback: object) -> None:
        self.close()


__all__ = ["NativeSandboxEpoch", "NativeSandboxReplay"]
