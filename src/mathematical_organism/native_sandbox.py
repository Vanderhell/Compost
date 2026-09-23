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
        python_division_children: dict[int, Any] = {}
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
                python_division_children[division.child_id] = child

        # Keep each organism's trace order, but execute a division through the
        # native reproduction policy.  The Python action remains the oracle:
        # the selected native child must contain exactly the atoms selected by
        # that trace, otherwise the first divergent epoch is reported here.
        replayed: dict[int, tuple[dict[str, object], ...]] = {}
        for organism_id in sorted(traces):
            sequence = traces[organism_id]
            division_index = next(
                (
                    index
                    for index, action in enumerate(sequence)
                    if action.kind is NativeActionKind.DIVISION
                ),
                None,
            )
            if division_index is None:
                replayed[organism_id] = tuple(
                    self._population.replay_action_traces({organism_id: sequence})[organism_id]
                )
                continue

            prefix = sequence[:division_index]
            results: list[dict[str, object]] = []
            if prefix:
                results.extend(
                    self._population.replay_action_traces({organism_id: prefix})[organism_id]
                )
            division = sequence[division_index]
            native_result = self._population.try_local_reproduction(
                organism_id,
                child_id=division.child_id,
            )
            native_child = native_result["child"]
            if not isinstance(native_child, dict):
                # The reference still has a historical deterministic
                # ``_divide_locally`` path when the weakest-member policy has
                # no viable component. Run that second native policy rather
                # than replaying the host-selected child atom set.
                native_result = self._population.try_divide(
                    organism_id,
                    child_id=division.child_id,
                )
                native_child = native_result["child"]
                if not isinstance(native_child, dict):
                    raise RuntimeError(
                        f"native division policies found no child at epoch {self._epoch}, "
                        f"organism {organism_id}"
                    )
                native_child_atoms = tuple(sorted(int(atom[0]) for atom in native_child["atoms"]))
                if native_child_atoms != tuple(sorted(division.child_atoms)):
                    raise RuntimeError(
                        f"native boundary division diverged at epoch {self._epoch}, "
                        f"organism {organism_id}: expected child atoms "
                        f"{tuple(sorted(division.child_atoms))!r}, got {native_child_atoms!r}"
                    )
                python_child = python_division_children[division.child_id]
                if (
                    native_child["body"]["structural_mass"] != python_child.body.full_body_mass()
                    or native_child["reserve"] != python_child.body.reserve
                    or native_child["territory"] != python_child.territory_state.territory.path
                ):
                    raise RuntimeError(
                        f"native boundary division state diverged at epoch {self._epoch}, "
                        f"organism {organism_id}: child state differs from Python oracle"
                    )
                results.append({
                    **native_result,
                    "kind": "division",
                    "policy": "global_partition_policy",
                })
            else:
                native_child_atoms = tuple(sorted(int(atom[0]) for atom in native_child["atoms"]))
                if native_child_atoms != tuple(sorted(division.child_atoms)):
                    raise RuntimeError(
                        f"native local reproduction diverged at epoch {self._epoch}, "
                        f"organism {organism_id}: expected child atoms "
                        f"{tuple(sorted(division.child_atoms))!r}, got {native_child_atoms!r}"
                    )
                python_child = python_division_children[division.child_id]
                if (
                    native_child["body"]["structural_mass"] != python_child.body.full_body_mass()
                    or native_child["reserve"] != python_child.body.reserve
                    or native_child["territory"] != python_child.territory_state.territory.path
                ):
                    raise RuntimeError(
                        f"native local reproduction state diverged at epoch {self._epoch}, "
                        f"organism {organism_id}: child state differs from Python oracle"
                    )
                results.append({
                    **native_result,
                    "kind": "division",
                    "policy": "local_reproduction",
                })
            suffix = sequence[division_index + 1 :]
            if suffix:
                results.extend(
                    self._population.replay_action_traces({organism_id: suffix})[organism_id]
                )
            replayed[organism_id] = tuple(results)
        snapshots: dict[int, dict[str, object]] = {}
        corpses: dict[int, dict[str, object]] = {}
        for organism_id in self._population.organism_ids:
            snapshot = self._population.snapshot(organism_id)
            if int(snapshot["status"]) == 1:
                corpses[organism_id] = self._population.take_corpse(organism_id)
            else:
                snapshots[organism_id] = snapshot
        for organism in self.runtime.organisms:
            if organism.alive or organism.name not in self._native_ids:
                continue
            native_id = self._native_ids[organism.name]
            corpse = corpses.get(native_id)
            if corpse is None:
                if native_id not in self._population.organism_ids:
                    # The corpse was transferred in an earlier epoch.  The
                    # Python runtime intentionally retains the dead organism
                    # for history, while the native population no longer owns
                    # its handle.
                    del self._native_ids[organism.name]
                    continue
                raise RuntimeError(
                    f"native corpse is missing at epoch {self._epoch}, organism {organism.name}"
                )
            expected_energy = sum(
                float(item.remaining_energy)
                for item in self.runtime.corpses
                if item.source_organism_id == organism.name
            )
            if (
                tuple(corpse["territory"]) != organism.territory_state.territory.path
                or abs(float(corpse["reserve"]) - expected_energy) > 1e-12
            ):
                raise RuntimeError(
                    f"native corpse diverged at epoch {self._epoch}, organism {organism.name}"
                )
            del self._native_ids[organism.name]
        self._population.verify_material_conservation()
        for organism in self.runtime.organisms:
            organism.verify_material_conservation()
        self.runtime.verify_world_material_conservation()
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
