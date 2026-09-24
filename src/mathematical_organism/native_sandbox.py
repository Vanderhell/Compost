"""Explicit Python-host/native-core sandbox replay boundary.

The reference sandbox remains authoritative.  This module only turns one
reference ``live_step`` into a deterministic native action-trace epoch; it
does not let the native library inspect the filesystem or choose biological
actions.
"""

from __future__ import annotations

import copy
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
        living_organisms = tuple(organism for organism in organisms if organism.alive)
        if not living_organisms:
            raise ValueError(
                "NativeSandboxReplay requires at least one living initial organism; "
                "initial corpse/world ownership remains Python-owned"
            )
        if len(living_organisms) != len(organism_ids):
            raise ValueError("organism_ids must map exactly to initial living Python organisms")
        effective_config = config
        if effective_config is None:
            effective_config = living_organisms[0].config
        if any(organism.config != effective_config for organism in living_organisms):
            raise ValueError("all initial organisms must use the native replay configuration")
        self.runtime = runtime
        self._native_ids: dict[str, int] = {
            organism.name: int(organism_ids[index])
            for index, organism in enumerate(living_organisms)
        }
        self._population = NativePopulationBackend(
            library,
            organism_ids=organism_ids,
            config=effective_config,
        )
        for index, organism in enumerate(living_organisms):
            self._population.restore_from_python(int(organism_ids[index]), organism)
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
        with self._population._native_transaction():
            return self._step_impl()

    def _step_impl(self) -> NativeSandboxEpoch:
        """Execute one epoch inside the population's native transaction."""
        if self._closed:
            raise RuntimeError("native sandbox replay is closed")
        traces: dict[int, tuple[NativeAction, ...]] = {}
        python_action_states: dict[int, dict[int, Any]] = {}
        python_organisms: dict[int, Any] = {}
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
            python_organisms[native_id] = organism
            python_action_states[native_id] = {}

            def observe(action: NativeAction, *, _organism: Any = organism,
                        _native_id: int = native_id) -> None:
                python_action_states[_native_id][id(action)] = copy.deepcopy(_organism)

            organism.live_step(
                self.runtime,
                action_trace=trace,
                action_observer=observe,
            )
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
        self._population.preflight_action_traces(traces)

        def replay_sequence(
            organism_id: int,
            sequence: tuple[NativeAction, ...],
        ) -> list[dict[str, object]]:
            results: list[dict[str, object]] = []
            index = 0
            while index < len(sequence):
                action = sequence[index]
                expected_action = action
                if action.kind is NativeActionKind.METABOLIC_PROGRESS:
                    grouped = self._population.accumulate_metabolic_progress_and_run_due(
                        organism_id,
                        action.amount,
                        action.minimum_work,
                        action.body_size,
                    )
                    executed = int(grouped["executed_steps"])
                    lifecycle_actions = sequence[index + 1:index + 1 + executed]
                    if any(
                        item.kind is not NativeActionKind.LIFECYCLE_STEP
                        for item in lifecycle_actions
                    ) or len(lifecycle_actions) != executed:
                        raise RuntimeError(
                            f"native due-lifecycle count diverged at epoch {self._epoch}, "
                            f"organism {organism_id}: native executed {executed}, "
                            f"trace has {len(lifecycle_actions)} lifecycle actions"
                        )
                    if executed:
                        expected_action = lifecycle_actions[-1]
                    results.append(dict(grouped))
                    index += executed + 1
                else:
                    results.extend(
                        self._population.replay_action_traces(
                            {organism_id: (action,)}
                        )[organism_id]
                    )
                    index += 1
                expected = python_action_states.get(organism_id, {}).get(id(expected_action))
                if expected is not None:
                    self._assert_shared_state(
                        self._population.snapshot(organism_id), expected
                    )
            return results

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
                replayed[organism_id] = tuple(replay_sequence(organism_id, sequence))
                continue

            prefix = sequence[:division_index]
            results: list[dict[str, object]] = []
            if prefix:
                results.extend(replay_sequence(organism_id, prefix))
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
                self._assert_shared_state(
                    self._population.snapshot(organism_id),
                    python_organisms[organism_id],
                )
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
                self._assert_shared_state(
                    self._population.snapshot(organism_id),
                    python_organisms[organism_id],
                )
            suffix = sequence[division_index + 1 :]
            if suffix:
                results.extend(replay_sequence(organism_id, suffix))
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
        for organism in self.runtime.organisms:
            if not organism.alive or organism.name not in self._native_ids:
                continue
            native_id = self._native_ids[organism.name]
            native = snapshots.get(native_id)
            if native is None:
                raise RuntimeError(
                    f"native live snapshot is missing at epoch {self._epoch}, "
                    f"organism {organism.name}"
                )
            self._assert_shared_state(native, organism)
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

    @staticmethod
    def _assert_shared_state(native: dict[str, object], organism: Any) -> None:
        """Compare the complete state represented by both current boundaries.

        Python-only names, navigation, caches, filesystem ownership, native
        handle parent identity, and the legacy body cursor are deliberately
        excluded.  The error names the first checked field so a replay failure
        points to a semantic divergence rather than merely a different final
        digest.  The cursor belongs to the historical stream-oriented
        lifecycle model; sandbox FOOD claims use host navigation state.
        """
        def fail(field: str, expected: object, actual: object) -> None:
            if expected != actual:
                raise RuntimeError(
                    f"native sandbox state diverged at {field}: "
                    f"expected {expected!r}, got {actual!r}"
                )

        body = organism.body
        fail("status", 0 if organism.alive else 1, native["status"])
        fail("generation", body.generation, native["generation"])
        fail("age_in_cycles", body.age_in_cycles, native["age_in_cycles"])
        fail("reserve", body.reserve, native["reserve"])
        fail("current_metabolic_epoch", organism.current_metabolic_epoch,
             native["current_metabolic_epoch"])
        fail("metabolic_progress", organism.metabolic_progress,
             native["metabolic_progress"])
        fail("metabolic_steps", organism.metabolic_steps,
             native["metabolic_steps"])
        fail("maintenance_deficit", organism.maintenance_deficit,
             native["maintenance_deficit"])
        fail("maintenance_deficit_total", organism.maintenance_deficit_total,
             native["maintenance_deficit_total"])
        fail("maintenance_paid_total", organism.maintenance_paid_total,
             native["maintenance_paid_total"])
        fail("weakening_events", organism.weakening_events,
             native["weakening_events"])
        native_body = native["body"]
        assert isinstance(native_body, dict)
        for field, expected in (
            ("structural_mass", body.full_body_mass()),
            ("atom_count", len(body.atoms)),
            ("relation_count", len(body.relations)),
            ("composite_count", len(body.composites)),
        ):
            fail(f"body.{field}", expected, native_body[field])

        def structures(values: dict[object, Any]) -> tuple[tuple[int, int, float, float, float, float], ...]:
            result: list[tuple[int, int, float, float, float, float]] = []
            for key, item in sorted(values.items(), key=lambda entry: repr(entry[0])):
                if isinstance(key, tuple):
                    left, right = key
                    if not isinstance(left, int) or not isinstance(right, int):
                        raise RuntimeError(f"native sandbox cannot compare non-integer structure key {key!r}")
                else:
                    if not isinstance(key, int):
                        raise RuntimeError(f"native sandbox cannot compare non-integer structure key {key!r}")
                    left, right = key, 0
                result.append((left, right, float(item.strength), float(item.maintenance),
                               float(item.evidence), float(item.income_rate)))
            return tuple(result)

        for field, expected in (
            ("atoms", structures(body.atoms)),
            ("relations", structures(body.relations)),
            ("composites", structures(body.composites)),
        ):
            fail(field, expected, native[field])

        expected_receptors = tuple(sorted(body.activated_receptors))
        fail("activated_receptors", expected_receptors, native["activated_receptors"])
        expected_territory = organism.territory_state.territory.path
        fail("territory", expected_territory, native["territory"])
        fail(
            "territory_local_birth_counter",
            organism.territory_state.local_birth_counter,
            native["territory_local_birth_counter"],
        )

        native_flow = native["material_flow"]
        assert isinstance(native_flow, dict)
        for field in (
            "input_mass", "assimilated_mass", "rejected_mass", "resorbed_mass",
            "processed_mass", "expelled_mass", "external_expelled_mass",
            "resorption_expelled_mass", "structural_created_mass",
            "structural_transferred_in", "structural_transferred_out",
        ):
            fail(f"material_flow.{field}", getattr(organism.material_flow, field), native_flow[field])

        native_activity = native["activity"]
        assert isinstance(native_activity, dict)
        fail("activity.metabolic_debt", organism.activity_ledger.metabolic_debt,
             native_activity["metabolic_debt"])
        fail("activity.energy_spent", organism.activity_ledger.energy_spent,
             native_activity["energy_spent"])
        fail("activity.settlements", organism.activity_ledger.settlements,
             native_activity["settlements"])
        native_counters = native_activity["counters"]
        assert isinstance(native_counters, dict)
        for field in (
            "bytes_eaten", "relations_created", "relations_strengthened",
            "composites_created", "composites_strengthened", "structural_mass_added",
            "structural_mass_lost", "resorption_events", "division_events",
            "processed_bytes", "rejected_bytes", "resorbed_processed_bytes",
        ):
            fail(f"activity.counters.{field}",
                 getattr(organism.activity_ledger.counters, field), native_counters[field])

        expected_gut = tuple(
            (
                chunk.mass,
                0 if chunk.origin == "external" else 1,
                bytes(chunk.payload),
                tuple(chunk.nutrition),
            )
            for chunk in organism.gut_queue
        )
        fail("gut", expected_gut, native["gut"])

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
