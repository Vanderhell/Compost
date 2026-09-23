"""Explicit reference/native backend handles.

The native backend is intentionally opt-in. Loading or native execution errors
are raised to the caller; this module never silently falls back to Python.
"""

from __future__ import annotations

import ctypes
import math
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any, Iterable, Mapping

from .lifecycle import LifecycleConfig, MathematicalLifePopulation


class NativeBackendError(RuntimeError):
    pass


class NativeActionKind(str, Enum):
    """Environment decision which may be applied to one native organism."""

    EXTERNAL_GUT = "external_gut"
    PROCESS_GUT = "process_gut"
    CORPSE_ENERGY = "corpse_energy"
    LIFECYCLE_STEP = "lifecycle_step"


@dataclass(frozen=True)
class NativeAction:
    """Validated host-owned action plan for the narrow native boundary.

    The action is a decision already made by the Python environment.  It does
    not contain paths, callbacks, or object references, and native code never
    uses it to discover external state.  Invalid plans fail before any handle
    is touched.
    """

    kind: NativeActionKind
    payload: bytes = b""
    nutrition: tuple[float, ...] | None = None
    capacity: int = 0
    energy: float = 0.0

    def __post_init__(self) -> None:
        if not isinstance(self.kind, NativeActionKind):
            raise ValueError("kind must be a NativeActionKind")
        payload = bytes(self.payload)
        object.__setattr__(self, "payload", payload)
        values = None if self.nutrition is None else tuple(float(value) for value in self.nutrition)
        if values is not None:
            if len(values) != len(payload) or any(not math.isfinite(value) for value in values):
                raise ValueError("nutrition must be finite and match payload length")
        object.__setattr__(self, "nutrition", values)
        if self.capacity < 0:
            raise ValueError("capacity must be non-negative")
        if not math.isfinite(float(self.energy)) or self.energy < 0.0:
            raise ValueError("energy must be finite and non-negative")
        if self.kind is NativeActionKind.PROCESS_GUT and (payload or values is not None or self.energy):
            raise ValueError("gut-processing action cannot carry material or energy fields")
        if self.kind is NativeActionKind.CORPSE_ENERGY and (payload or values is not None or self.capacity):
            raise ValueError("corpse-energy action cannot carry material fields")
        if self.kind is NativeActionKind.LIFECYCLE_STEP and (self.capacity or self.energy):
            raise ValueError("lifecycle-step action cannot carry capacity or energy")

    @classmethod
    def external_gut(
        cls,
        payload: bytes | bytearray,
        *,
        capacity: int,
        nutrition: tuple[float, ...] | None = None,
    ) -> "NativeAction":
        return cls(NativeActionKind.EXTERNAL_GUT, bytes(payload), nutrition, capacity, 0.0)

    @classmethod
    def corpse_energy(cls, energy: float) -> "NativeAction":
        return cls(NativeActionKind.CORPSE_ENERGY, energy=energy)

    @classmethod
    def process_gut(cls, *, capacity: int) -> "NativeAction":
        return cls(NativeActionKind.PROCESS_GUT, capacity=capacity)

    @classmethod
    def lifecycle_step(
        cls,
        payload: bytes | bytearray,
        *,
        nutrition: tuple[float, ...] | None = None,
    ) -> "NativeAction":
        return cls(NativeActionKind.LIFECYCLE_STEP, bytes(payload), nutrition)


class _Config(ctypes.Structure):
    _fields_ = [
        ("abi_version", ctypes.c_uint32),
        ("seed", ctypes.c_uint64),
        ("max_body_mass", ctypes.c_uint64),
        ("max_territory_depth", ctypes.c_uint32),
        ("income_decay", ctypes.c_double),
        ("atom_income", ctypes.c_double),
        ("relation_income", ctypes.c_double),
        ("composite_income", ctypes.c_double),
        ("atom_maintenance", ctypes.c_double),
        ("relation_maintenance", ctypes.c_double),
        ("composite_maintenance", ctypes.c_double),
        ("atom_formation_cost", ctypes.c_double),
        ("relation_formation_cost", ctypes.c_double),
        ("consolidation_formation_cost", ctypes.c_double),
        ("birth_cost", ctypes.c_double),
        ("division_horizon", ctypes.c_double),
        ("boundary_ratio_limit", ctypes.c_double),
        ("birth_reserve", ctypes.c_double),
        ("reproduction_minimum_body", ctypes.c_uint64),
    ]


class _Input(ctypes.Structure):
    _fields_ = [
        ("food", ctypes.POINTER(ctypes.c_uint8)),
        ("nutrition", ctypes.POINTER(ctypes.c_double)),
        ("length", ctypes.c_size_t),
    ]


class _Result(ctypes.Structure):
    _fields_ = [
        ("consumed_bytes", ctypes.c_size_t),
        ("assimilated_mass", ctypes.c_uint64),
        ("rejected_mass", ctypes.c_uint64),
        ("relations_created", ctypes.c_uint64),
        ("relations_strengthened", ctypes.c_uint64),
    ]


class _GutProcessResult(ctypes.Structure):
    _fields_ = [
        ("processed_mass", ctypes.c_uint64),
        ("assimilated_mass", ctypes.c_uint64),
        ("rejected_mass", ctypes.c_uint64),
        ("expelled_mass", ctypes.c_uint64),
    ]


class _MaintenanceResult(ctypes.Structure):
    _fields_ = [
        ("required", ctypes.c_double),
        ("paid", ctypes.c_double),
        ("deficit", ctypes.c_double),
        ("weakened_candidates", ctypes.c_uint64),
        ("resorbed_mass", ctypes.c_uint64),
    ]


class _CycleResult(ctypes.Structure):
    _fields_ = [
        ("digestion", _Result),
        ("maintenance", _MaintenanceResult),
        ("composites_consolidated", ctypes.c_uint64),
        ("status_after", ctypes.c_int),
    ]


class _DivisionPlan(ctypes.Structure):
    _fields_ = [
        ("candidate_found", ctypes.c_bool),
        ("allowed", ctypes.c_bool),
        ("child_atoms", ctypes.c_uint8 * 256),
        ("child_atom_count", ctypes.c_size_t),
        ("boundary_ratio", ctypes.c_double),
        ("boundary_maintenance", ctypes.c_double),
        ("child_income", ctypes.c_double),
        ("child_maintenance", ctypes.c_double),
        ("parent_income", ctypes.c_double),
        ("parent_maintenance", ctypes.c_double),
        ("birth_gain", ctypes.c_double),
    ]


class _DivisionResult(ctypes.Structure):
    _fields_ = [
        ("child_structural_mass", ctypes.c_uint64),
        ("cross_split_mass", ctypes.c_uint64),
        ("parent_reserve_after_cost", ctypes.c_double),
    ]


class _Body(ctypes.Structure):
    _fields_ = [
        ("structural_mass", ctypes.c_uint64),
        ("atom_count", ctypes.c_uint64),
        ("relation_count", ctypes.c_uint64),
        ("composite_count", ctypes.c_uint64),
    ]


class _Structure(ctypes.Structure):
    _fields_ = [
        ("occupied", ctypes.c_bool),
        ("kind", ctypes.c_int),
        ("left", ctypes.c_uint8),
        ("right", ctypes.c_uint8),
        ("strength", ctypes.c_double),
        ("maintenance", ctypes.c_double),
        ("evidence", ctypes.c_double),
        ("income_rate", ctypes.c_double),
    ]


class _MaterialFlow(ctypes.Structure):
    _fields_ = [(name, ctypes.c_uint64) for name in (
        "input_mass", "assimilated_mass", "rejected_mass", "resorbed_mass",
        "processed_mass", "expelled_mass", "external_expelled_mass",
        "resorption_expelled_mass", "structural_created_mass",
        "structural_transferred_in", "structural_transferred_out",
    )]


class _ActivityCounters(ctypes.Structure):
    _fields_ = [(name, ctypes.c_uint64) for name in (
        "bytes_eaten", "relations_created", "relations_strengthened",
        "composites_created", "composites_strengthened", "structural_mass_added",
        "structural_mass_lost", "resorption_events", "division_events",
        "processed_bytes", "rejected_bytes", "resorbed_processed_bytes",
    )]


class _Activity(ctypes.Structure):
    _fields_ = [
        ("metabolic_debt", ctypes.c_double),
        ("energy_spent", ctypes.c_double),
        ("settlements", ctypes.c_uint64),
        ("counters", _ActivityCounters),
    ]


class _Territory(ctypes.Structure):
    _fields_ = [
        ("path", ctypes.c_uint8 * 64),
        ("depth", ctypes.c_uint32),
        ("organism_id", ctypes.c_uint64),
        ("local_birth_counter", ctypes.c_uint64),
        ("alive", ctypes.c_bool),
    ]


class _GutChunk(ctypes.Structure):
    _fields_ = [
        ("mass", ctypes.c_uint64),
        ("origin", ctypes.c_int),
        ("payload_length", ctypes.c_uint32),
        ("payload", ctypes.c_uint8 * 16),
        ("nutrition", ctypes.c_double * 16),
    ]


class _Snapshot(ctypes.Structure):
    _fields_ = [
        ("abi_version", ctypes.c_uint32),
        ("organism_id", ctypes.c_uint64),
        ("parent_id", ctypes.c_uint64),
        ("has_parent", ctypes.c_bool),
        ("generation", ctypes.c_uint64),
        ("cursor", ctypes.c_uint64),
        ("age_in_cycles", ctypes.c_uint64),
        ("status", ctypes.c_int),
        ("reserve", ctypes.c_double),
        ("body", _Body),
        ("material_flow", _MaterialFlow),
        ("activity", _Activity),
        ("territory", _Territory),
        ("atoms", _Structure * 256),
        ("relations", _Structure * 512),
        ("composites", _Structure * 512),
        ("activated_receptors", ctypes.c_uint64 * 4),
        ("gut", _GutChunk * 128),
        ("gut_head", ctypes.c_uint32),
        ("gut_count", ctypes.c_uint32),
    ]


class NativeBackend:
    """Small explicit ctypes adapter for the versioned native ABI."""

    ABI_VERSION = 3
    MAX_ATOMS = 256

    def __init__(
        self,
        library: str | Path,
        *,
        organism_id: int = 0,
        config: LifecycleConfig | None = None,
    ) -> None:
        self.library_path = Path(library).resolve()
        if not self.library_path.is_file():
            raise NativeBackendError(f"native library does not exist: {self.library_path}")
        try:
            self._library = ctypes.CDLL(str(self.library_path))
        except OSError as error:
            raise NativeBackendError(f"cannot load native library: {self.library_path}") from error
        try:
            self._configure_symbols()
        except AttributeError as error:
            raise NativeBackendError(
                f"native library does not provide ABI version {self.ABI_VERSION}: {self.library_path}"
            ) from error
        lifecycle_config = config
        native_config = _Config()
        status = self._library.compost_config_default(ctypes.byref(native_config))
        self._check(status, "compost_config_default")
        if lifecycle_config is not None:
            lifecycle_config.validate()
            native_defaults = LifecycleConfig()
            unsupported = (
                "bite_minimum", "metabolic_minimum_work", "novelty_affinity",
            )
            if any(
                getattr(lifecycle_config, field) != getattr(native_defaults, field)
                for field in unsupported
            ):
                raise NativeBackendError(
                    "native backend does not yet represent Python scheduling fields: "
                    + ", ".join(unsupported)
                )
            for field in (
                "atom_income", "relation_income", "composite_income",
                "atom_maintenance", "relation_maintenance", "composite_maintenance",
                "atom_formation_cost", "relation_formation_cost",
                "consolidation_formation_cost", "birth_cost", "division_horizon",
                "boundary_ratio_limit", "birth_reserve", "income_decay",
                "reproduction_minimum_body",
            ):
                setattr(native_config, field, getattr(lifecycle_config, field))
        self._context = ctypes.c_void_p()
        status = self._library.compost_create(ctypes.byref(native_config), ctypes.c_uint64(organism_id), ctypes.byref(self._context))
        self._check(status, "compost_create")
        if not self._context.value:
            raise NativeBackendError("native create returned a null context")
        initial_snapshot = _Snapshot()
        status = self._library.compost_context_snapshot(self._context, ctypes.byref(initial_snapshot))
        if status != 0:
            self._library.compost_destroy(self._context)
            self._context = ctypes.c_void_p()
            self._check(status, "compost_context_snapshot")
        if int(initial_snapshot.abi_version) != self.ABI_VERSION:
            self._library.compost_destroy(self._context)
            self._context = ctypes.c_void_p()
            raise NativeBackendError(
                f"native ABI mismatch: expected {self.ABI_VERSION}, "
                f"got {int(initial_snapshot.abi_version)}"
            )

    def _configure_symbols(self) -> None:
        library = self._library
        library.compost_config_default.argtypes = [ctypes.POINTER(_Config)]
        library.compost_config_default.restype = ctypes.c_int
        library.compost_create.argtypes = [ctypes.POINTER(_Config), ctypes.c_uint64, ctypes.POINTER(ctypes.c_void_p)]
        library.compost_create.restype = ctypes.c_int
        library.compost_destroy.argtypes = [ctypes.c_void_p]
        library.compost_destroy.restype = None
        library.compost_context_digest.argtypes = [ctypes.c_void_p, ctypes.POINTER(_Input), ctypes.POINTER(_Result)]
        library.compost_context_digest.restype = ctypes.c_int
        library.compost_context_step.argtypes = [ctypes.c_void_p, ctypes.POINTER(_Input), ctypes.POINTER(_CycleResult)]
        library.compost_context_step.restype = ctypes.c_int
        library.compost_context_step_and_try_divide.argtypes = [
            ctypes.c_void_p, ctypes.POINTER(_Input), ctypes.c_uint64,
            ctypes.POINTER(ctypes.c_void_p), ctypes.POINTER(_CycleResult),
            ctypes.POINTER(_DivisionPlan), ctypes.POINTER(_DivisionResult),
        ]
        library.compost_context_step_and_try_divide.restype = ctypes.c_int
        library.compost_context_enqueue_external.argtypes = [ctypes.c_void_p, ctypes.POINTER(_Input)]
        library.compost_context_enqueue_external.restype = ctypes.c_int
        library.compost_context_process_gut.argtypes = [
            ctypes.c_void_p, ctypes.c_uint64, ctypes.POINTER(_GutProcessResult)
        ]
        library.compost_context_process_gut.restype = ctypes.c_int
        library.compost_context_weaken_weakest.argtypes = [
            ctypes.c_void_p, ctypes.POINTER(ctypes.c_bool), ctypes.POINTER(ctypes.c_uint64)
        ]
        library.compost_context_weaken_weakest.restype = ctypes.c_int
        library.compost_territory_food_block_key.argtypes = [
            ctypes.POINTER(ctypes.c_uint8), ctypes.c_size_t, ctypes.c_uint64,
            ctypes.POINTER(ctypes.c_uint64),
        ]
        library.compost_territory_food_block_key.restype = ctypes.c_int
        library.compost_context_verify_material_conservation.argtypes = [ctypes.c_void_p]
        library.compost_context_verify_material_conservation.restype = ctypes.c_int
        library.compost_context_apply_corpse_energy.argtypes = [
            ctypes.c_void_p, ctypes.c_double, ctypes.POINTER(ctypes.c_double)
        ]
        library.compost_context_apply_corpse_energy.restype = ctypes.c_int
        library.compost_context_state_digest.argtypes = [ctypes.c_void_p]
        library.compost_context_state_digest.restype = ctypes.c_uint64
        library.compost_context_snapshot.argtypes = [ctypes.c_void_p, ctypes.POINTER(_Snapshot)]
        library.compost_context_snapshot.restype = ctypes.c_int
        library.compost_context_select_partition.argtypes = [
            ctypes.c_void_p,
            ctypes.c_double,
            ctypes.POINTER(ctypes.c_uint8),
            ctypes.c_size_t,
            ctypes.POINTER(ctypes.c_size_t),
            ctypes.POINTER(ctypes.c_double),
        ]
        library.compost_context_select_partition.restype = ctypes.c_int
        library.compost_context_plan_division.argtypes = [ctypes.c_void_p, ctypes.POINTER(_DivisionPlan)]
        library.compost_context_plan_division.restype = ctypes.c_int
        library.compost_context_try_divide.argtypes = [
            ctypes.c_void_p, ctypes.c_uint64, ctypes.POINTER(ctypes.c_void_p),
            ctypes.POINTER(_DivisionPlan), ctypes.POINTER(_DivisionResult),
        ]
        library.compost_context_try_divide.restype = ctypes.c_int
        library.compost_context_partition.argtypes = [
            ctypes.c_void_p,
            ctypes.c_uint64,
            ctypes.POINTER(ctypes.c_uint8),
            ctypes.c_size_t,
            ctypes.c_double,
            ctypes.POINTER(ctypes.c_void_p),
            ctypes.POINTER(_DivisionResult),
        ]
        library.compost_context_partition.restype = ctypes.c_int

    @staticmethod
    def _check(status: int, operation: str) -> None:
        if status != 0:
            raise NativeBackendError(f"{operation} failed with native status {status}")

    def digest(self, food: bytes | bytearray, nutrition: tuple[float, ...] | None = None) -> dict[str, int]:
        if not self._context or not self._context.value:
            raise NativeBackendError("native backend is closed")
        payload = bytes(food)
        values = tuple(1.0 for _ in payload) if nutrition is None else nutrition
        if len(values) != len(payload):
            raise ValueError("food and nutrition lengths differ")
        food_buffer = (ctypes.c_uint8 * len(payload))(*payload)
        nutrition_buffer = (ctypes.c_double * len(values))(*values)
        native_input = _Input(food_buffer, nutrition_buffer, len(payload))
        result = _Result()
        status = self._library.compost_context_digest(self._context, ctypes.byref(native_input), ctypes.byref(result))
        self._check(status, "compost_context_digest")
        return {
            "consumed_bytes": int(result.consumed_bytes),
            "assimilated_mass": int(result.assimilated_mass),
            "rejected_mass": int(result.rejected_mass),
            "relations_created": int(result.relations_created),
            "relations_strengthened": int(result.relations_strengthened),
        }

    def enqueue_external(self, food: bytes | bytearray, nutrition: tuple[float, ...] | None = None) -> None:
        """Copy ordered external material into the native FIFO gut."""
        if not self._context or not self._context.value:
            raise NativeBackendError("native backend is closed")
        payload = bytes(food)
        values = tuple(1.0 for _ in payload) if nutrition is None else nutrition
        if len(values) != len(payload):
            raise ValueError("food and nutrition lengths differ")
        food_buffer = (ctypes.c_uint8 * len(payload))(*payload)
        nutrition_buffer = (ctypes.c_double * len(values))(*values)
        native_input = _Input(food_buffer, nutrition_buffer, len(payload))
        status = self._library.compost_context_enqueue_external(
            self._context, ctypes.byref(native_input)
        )
        self._check(status, "compost_context_enqueue_external")

    def process_gut(self, capacity: int) -> dict[str, int]:
        """Process at most capacity units from the native FIFO gut."""
        if not self._context or not self._context.value:
            raise NativeBackendError("native backend is closed")
        result = _GutProcessResult()
        status = self._library.compost_context_process_gut(
            self._context, ctypes.c_uint64(capacity), ctypes.byref(result)
        )
        self._check(status, "compost_context_process_gut")
        return {
            "processed_mass": int(result.processed_mass),
            "assimilated_mass": int(result.assimilated_mass),
            "rejected_mass": int(result.rejected_mass),
            "expelled_mass": int(result.expelled_mass),
        }

    def apply_action(self, action: NativeAction) -> dict[str, float | int | str]:
        """Apply one explicit host decision through the narrow native ABI.

        Environment selection remains outside this method.  A material action
        is queued before its bounded FIFO processing, matching the sandbox
        oracle's durable-ingest order.  The returned mapping is telemetry for
        the host and never contains borrowed native memory.
        """
        if not isinstance(action, NativeAction):
            raise TypeError("action must be a NativeAction")
        if action.kind is NativeActionKind.EXTERNAL_GUT:
            self.enqueue_external(action.payload, action.nutrition)
            result = self.process_gut(action.capacity)
            return {"kind": action.kind.value, **result}
        if action.kind is NativeActionKind.PROCESS_GUT:
            result = self.process_gut(action.capacity)
            return {"kind": action.kind.value, **result}
        if action.kind is NativeActionKind.CORPSE_ENERGY:
            return {
                "kind": action.kind.value,
                "credited_energy": self.apply_corpse_energy(action.energy),
            }
        if action.kind is NativeActionKind.LIFECYCLE_STEP:
            return {"kind": action.kind.value, **self.step(action.payload, action.nutrition)}
        raise NativeBackendError(f"unsupported native action: {action.kind!r}")

    def verify_material_conservation(self) -> None:
        """Raise when the native material-flow invariant is not satisfied."""
        if not self._context or not self._context.value:
            raise NativeBackendError("native backend is closed")
        status = self._library.compost_context_verify_material_conservation(self._context)
        self._check(status, "compost_context_verify_material_conservation")

    def weaken_weakest(self) -> dict[str, int | bool]:
        """Apply one native weakest-structure transition."""
        if not self._context or not self._context.value:
            raise NativeBackendError("native backend is closed")
        changed = ctypes.c_bool()
        resorbed_mass = ctypes.c_uint64()
        status = self._library.compost_context_weaken_weakest(
            self._context, ctypes.byref(changed), ctypes.byref(resorbed_mass)
        )
        self._check(status, "compost_context_weaken_weakest")
        return {"changed": bool(changed.value), "resorbed_mass": int(resorbed_mass.value)}

    def food_block_key(self, file_id: str | bytes, block_index: int) -> int:
        """Return the native deterministic key for one logical FOOD block."""
        if block_index < 0 or block_index > (1 << 64) - 1:
            raise ValueError("block_index must fit uint64")
        encoded = file_id.encode("utf-8") if isinstance(file_id, str) else bytes(file_id)
        file_buffer = (ctypes.c_uint8 * len(encoded))(*encoded)
        key = ctypes.c_uint64()
        status = self._library.compost_territory_food_block_key(
            file_buffer, len(encoded), ctypes.c_uint64(block_index), ctypes.byref(key)
        )
        self._check(status, "compost_territory_food_block_key")
        return int(key.value)

    def apply_corpse_energy(self, energy: float) -> float:
        """Apply energy already selected by the Python environment."""
        if not self._context or not self._context.value:
            raise NativeBackendError("native backend is closed")
        credited = ctypes.c_double()
        status = self._library.compost_context_apply_corpse_energy(
            self._context, ctypes.c_double(energy), ctypes.byref(credited)
        )
        self._check(status, "compost_context_apply_corpse_energy")
        return float(credited.value)

    def state_digest(self) -> int:
        """Return the native behavioral-state digest for differential checks."""
        if not self._context or not self._context.value:
            raise NativeBackendError("native backend is closed")
        return int(self._library.compost_context_state_digest(self._context))

    @staticmethod
    def _structures(values: object) -> tuple[tuple[int, int, float, float, float, float], ...]:
        return tuple(
            (int(item.left), int(item.right), float(item.strength), float(item.maintenance),
             float(item.evidence), float(item.income_rate))
            for item in values if item.occupied
        )

    def snapshot(self) -> dict[str, object]:
        """Return an explicit immutable-friendly native behavioral snapshot."""
        if not self._context or not self._context.value:
            raise NativeBackendError("native backend is closed")
        snapshot = _Snapshot()
        self._check(
            self._library.compost_context_snapshot(self._context, ctypes.byref(snapshot)),
            "compost_context_snapshot",
        )
        return {
            "abi_version": int(snapshot.abi_version),
            "organism_id": int(snapshot.organism_id),
            "parent_id": int(snapshot.parent_id),
            "has_parent": bool(snapshot.has_parent),
            "generation": int(snapshot.generation),
            "cursor": int(snapshot.cursor),
            "age_in_cycles": int(snapshot.age_in_cycles),
            "status": int(snapshot.status),
            "reserve": float(snapshot.reserve),
            "body": {
                "structural_mass": int(snapshot.body.structural_mass),
                "atom_count": int(snapshot.body.atom_count),
                "relation_count": int(snapshot.body.relation_count),
                "composite_count": int(snapshot.body.composite_count),
            },
            "material_flow": {
                field: int(getattr(snapshot.material_flow, field))
                for field, _ctype in _MaterialFlow._fields_
            },
            "activity": {
                "metabolic_debt": float(snapshot.activity.metabolic_debt),
                "energy_spent": float(snapshot.activity.energy_spent),
                "settlements": int(snapshot.activity.settlements),
                "counters": {
                    field: int(getattr(snapshot.activity.counters, field))
                    for field, _ctype in _ActivityCounters._fields_
                },
            },
            "atoms": self._structures(snapshot.atoms),
            "relations": self._structures(snapshot.relations),
            "composites": self._structures(snapshot.composites),
            "gut": tuple(
                (
                    int(snapshot.gut[(snapshot.gut_head + offset) % 128].mass),
                    int(snapshot.gut[(snapshot.gut_head + offset) % 128].origin),
                    bytes(snapshot.gut[(snapshot.gut_head + offset) % 128].payload[:snapshot.gut[(snapshot.gut_head + offset) % 128].payload_length]),
                    tuple(float(value) for value in snapshot.gut[(snapshot.gut_head + offset) % 128].nutrition[:snapshot.gut[(snapshot.gut_head + offset) % 128].payload_length]),
                )
                for offset in range(snapshot.gut_count)
            ),
            "territory": tuple(int(snapshot.territory.path[index]) for index in range(snapshot.territory.depth)),
            "activated_receptors": tuple(
                index for index in range(256)
                if snapshot.activated_receptors[index // 64] & (1 << (index % 64))
            ),
        }

    def step(self, food: bytes | bytearray, nutrition: tuple[float, ...] | None = None) -> dict[str, float | int]:
        """Run the current explicit native digest+maintenance checkpoint."""
        if not self._context or not self._context.value:
            raise NativeBackendError("native backend is closed")
        payload = bytes(food)
        values = tuple(1.0 for _ in payload) if nutrition is None else nutrition
        if len(values) != len(payload):
            raise ValueError("food and nutrition lengths differ")
        food_buffer = (ctypes.c_uint8 * len(payload))(*payload)
        nutrition_buffer = (ctypes.c_double * len(values))(*values)
        native_input = _Input(food_buffer, nutrition_buffer, len(payload))
        result = _CycleResult()
        status = self._library.compost_context_step(self._context, ctypes.byref(native_input), ctypes.byref(result))
        self._check(status, "compost_context_step")
        return {
            "consumed_bytes": int(result.digestion.consumed_bytes),
            "assimilated_mass": int(result.digestion.assimilated_mass),
            "rejected_mass": int(result.digestion.rejected_mass),
            "maintenance_required": float(result.maintenance.required),
            "maintenance_paid": float(result.maintenance.paid),
            "maintenance_deficit": float(result.maintenance.deficit),
            "composites_consolidated": int(result.composites_consolidated),
            "status_after": int(result.status_after),
        }

    def step_and_try_divide(
        self,
        food: bytes | bytearray,
        *,
        child_id: int,
        nutrition: tuple[float, ...] | None = None,
    ) -> tuple["NativeBackend | None", dict[str, float | int], dict[str, object]]:
        """Run one native lifecycle step and its deterministic division policy."""
        if not self._context or not self._context.value:
            raise NativeBackendError("native backend is closed")
        payload = bytes(food)
        values = tuple(1.0 for _ in payload) if nutrition is None else nutrition
        if len(values) != len(payload):
            raise ValueError("food and nutrition lengths differ")
        food_buffer = (ctypes.c_uint8 * len(payload))(*payload)
        nutrition_buffer = (ctypes.c_double * len(values))(*values)
        native_input = _Input(food_buffer, nutrition_buffer, len(payload))
        child_context = ctypes.c_void_p()
        cycle = _CycleResult()
        plan = _DivisionPlan()
        division = _DivisionResult()
        status = self._library.compost_context_step_and_try_divide(
            self._context,
            ctypes.byref(native_input),
            ctypes.c_uint64(child_id),
            ctypes.byref(child_context),
            ctypes.byref(cycle),
            ctypes.byref(plan),
            ctypes.byref(division),
        )
        self._check(status, "compost_context_step_and_try_divide")
        cycle_view: dict[str, float | int] = {
            "consumed_bytes": int(cycle.digestion.consumed_bytes),
            "assimilated_mass": int(cycle.digestion.assimilated_mass),
            "rejected_mass": int(cycle.digestion.rejected_mass),
            "maintenance_required": float(cycle.maintenance.required),
            "maintenance_paid": float(cycle.maintenance.paid),
            "maintenance_deficit": float(cycle.maintenance.deficit),
            "composites_consolidated": int(cycle.composites_consolidated),
            "status_after": int(cycle.status_after),
        }
        plan_view: dict[str, object] = {
            "candidate_found": bool(plan.candidate_found),
            "allowed": bool(plan.allowed),
            "child_atoms": tuple(int(plan.child_atoms[index]) for index in range(plan.child_atom_count)),
            "boundary_ratio": float(plan.boundary_ratio),
            "boundary_maintenance": float(plan.boundary_maintenance),
            "child_income": float(plan.child_income),
            "child_maintenance": float(plan.child_maintenance),
            "parent_income": float(plan.parent_income),
            "parent_maintenance": float(plan.parent_maintenance),
            "birth_gain": float(plan.birth_gain),
        }
        if not child_context.value:
            return None, cycle_view, plan_view
        child = object.__new__(NativeBackend)
        child.library_path = self.library_path
        child._library = self._library
        child._context = child_context
        plan_view["division"] = {
            "child_structural_mass": int(division.child_structural_mass),
            "cross_split_mass": int(division.cross_split_mass),
            "parent_reserve_after_cost": float(division.parent_reserve_after_cost),
        }
        return child, cycle_view, plan_view

    def select_partition(self, boundary_ratio_limit: float = 0.15) -> tuple[tuple[int, ...], float]:
        """Return the native deterministic selected child region and ratio."""
        if not self._context or not self._context.value:
            raise NativeBackendError("native backend is closed")
        atoms = (ctypes.c_uint8 * self.MAX_ATOMS)()
        count = ctypes.c_size_t()
        ratio = ctypes.c_double()
        status = self._library.compost_context_select_partition(
            self._context,
            boundary_ratio_limit,
            atoms,
            self.MAX_ATOMS,
            ctypes.byref(count),
            ctypes.byref(ratio),
        )
        self._check(status, "compost_context_select_partition")
        return tuple(int(atoms[index]) for index in range(count.value)), float(ratio.value)

    def division_plan(self) -> dict[str, object]:
        """Return the native lifecycle viability plan without mutating state."""
        if not self._context or not self._context.value:
            raise NativeBackendError("native backend is closed")
        plan = _DivisionPlan()
        status = self._library.compost_context_plan_division(self._context, ctypes.byref(plan))
        self._check(status, "compost_context_plan_division")
        return {
            "candidate_found": bool(plan.candidate_found),
            "allowed": bool(plan.allowed),
            "child_atoms": tuple(int(plan.child_atoms[index]) for index in range(plan.child_atom_count)),
            "boundary_ratio": float(plan.boundary_ratio),
            "boundary_maintenance": float(plan.boundary_maintenance),
            "child_income": float(plan.child_income),
            "child_maintenance": float(plan.child_maintenance),
            "parent_income": float(plan.parent_income),
            "parent_maintenance": float(plan.parent_maintenance),
            "birth_gain": float(plan.birth_gain),
        }

    def partition(self, child_atoms: tuple[int, ...], *, child_id: int, birth_cost: float = 1.0) -> tuple["NativeBackend", dict[str, float | int]]:
        """Commit a selected partition and return an owned child backend."""
        if not self._context or not self._context.value:
            raise NativeBackendError("native backend is closed")
        values = tuple(int(value) for value in child_atoms)
        atom_buffer = (ctypes.c_uint8 * len(values))(*values)
        child_context = ctypes.c_void_p()
        result = _DivisionResult()
        status = self._library.compost_context_partition(
            self._context,
            ctypes.c_uint64(child_id),
            atom_buffer,
            len(values),
            birth_cost,
            ctypes.byref(child_context),
            ctypes.byref(result),
        )
        self._check(status, "compost_context_partition")
        if not child_context.value:
            raise NativeBackendError("native partition returned a null child context")
        child = object.__new__(NativeBackend)
        child.library_path = self.library_path
        child._library = self._library
        child._context = child_context
        return child, {
            "child_structural_mass": int(result.child_structural_mass),
            "cross_split_mass": int(result.cross_split_mass),
            "parent_reserve_after_cost": float(result.parent_reserve_after_cost),
        }

    def try_divide(self, *, child_id: int) -> tuple["NativeBackend | None", dict[str, object]]:
        """Evaluate and atomically commit the native deterministic division policy."""
        if not self._context or not self._context.value:
            raise NativeBackendError("native backend is closed")
        child_context = ctypes.c_void_p()
        plan = _DivisionPlan()
        result = _DivisionResult()
        status = self._library.compost_context_try_divide(
            self._context,
            ctypes.c_uint64(child_id),
            ctypes.byref(child_context),
            ctypes.byref(plan),
            ctypes.byref(result),
        )
        self._check(status, "compost_context_try_divide")
        plan_view = {
            "candidate_found": bool(plan.candidate_found),
            "allowed": bool(plan.allowed),
            "child_atoms": tuple(int(plan.child_atoms[index]) for index in range(plan.child_atom_count)),
            "boundary_ratio": float(plan.boundary_ratio),
            "boundary_maintenance": float(plan.boundary_maintenance),
            "child_income": float(plan.child_income),
            "child_maintenance": float(plan.child_maintenance),
            "parent_income": float(plan.parent_income),
            "parent_maintenance": float(plan.parent_maintenance),
            "birth_gain": float(plan.birth_gain),
        }
        if not child_context.value:
            return None, plan_view
        child = object.__new__(NativeBackend)
        child.library_path = self.library_path
        child._library = self._library
        child._context = child_context
        plan_view["division"] = {
            "child_structural_mass": int(result.child_structural_mass),
            "cross_split_mass": int(result.cross_split_mass),
            "parent_reserve_after_cost": float(result.parent_reserve_after_cost),
        }
        return child, plan_view

    def close(self) -> None:
        if self._context and self._context.value:
            self._library.compost_destroy(self._context)
            self._context = ctypes.c_void_p()

    def __enter__(self) -> "NativeBackend":
        return self

    def __exit__(self, *_: object) -> None:
        self.close()


class NativePopulationBackend:
    """Deterministic Python orchestration for multiple opaque native organisms.

    The caller owns environment allocation and supplies one ordered bite per
    organism. This class only schedules native handles in numeric ID order,
    applies their explicit transitions, and registers children returned by the
    ABI. It performs no filesystem access, food claiming, or silent fallback.
    """

    def __init__(
        self,
        library: str | Path,
        *,
        organism_ids: Iterable[int] = (0,),
        config: LifecycleConfig | None = None,
    ) -> None:
        ids = tuple(sorted(int(organism_id) for organism_id in organism_ids))
        if (
            not ids or len(set(ids)) != len(ids) or
            any(organism_id < 0 or organism_id > (1 << 64) - 1 for organism_id in ids)
        ):
            raise ValueError("organism_ids must be unique non-negative integers")
        self.library_path = Path(library).resolve()
        self._config = config
        self._contexts: dict[int, NativeBackend] = {}
        try:
            for organism_id in ids:
                self._contexts[organism_id] = NativeBackend(
                    self.library_path, organism_id=organism_id, config=config
                )
        except Exception:
            for context in self._contexts.values():
                context.close()
            raise
        self._closed = False

    @property
    def organism_ids(self) -> tuple[int, ...]:
        """Return currently owned IDs in deterministic scheduling order."""
        return tuple(sorted(self._contexts))

    def step(
        self,
        environment: Mapping[int, tuple[bytes | bytearray, tuple[float, ...] | None]],
        *,
        child_ids: Mapping[int, int] | None = None,
    ) -> dict[int, dict[str, object]]:
        """Apply one explicit environment epoch in ascending organism ID order.

        Missing environment entries are empty bites. Child IDs are supplied by
        the Python world/territory owner; a deterministic unused ID is used
        only when an entry is omitted. A hard native error stops the epoch and
        is surfaced to the caller.
        """
        if self._closed:
            raise NativeBackendError("native population backend is closed")
        unknown = set(environment) - set(self._contexts)
        if unknown:
            raise ValueError(f"environment contains unknown organism IDs: {sorted(unknown)!r}")
        supplied_children = child_ids or {}
        unknown_children = set(supplied_children) - set(self._contexts)
        if unknown_children:
            raise ValueError(f"child_ids contains unknown organism IDs: {sorted(unknown_children)!r}")
        existing = set(self._contexts)
        requested = [int(value) for value in supplied_children.values()]
        if (
            any(value < 0 or value > (1 << 64) - 1 for value in requested) or
            len(requested) != len(set(requested))
        ):
            raise ValueError("child IDs must be unique non-negative integers")
        if existing.intersection(requested):
            raise ValueError("child ID already belongs to the population")

        reserved = existing | set(requested)
        next_automatic = max(reserved) + 1
        automatic_children: dict[int, int] = {}
        for organism_id in sorted(self._contexts):
            if organism_id in supplied_children:
                continue
            while next_automatic in reserved:
                next_automatic += 1
            if next_automatic > (1 << 64) - 1:
                raise ValueError("no available uint64 child ID")
            automatic_children[organism_id] = next_automatic
            reserved.add(next_automatic)
            next_automatic += 1

        prepared: dict[int, tuple[bytes, tuple[float, ...] | None]] = {}
        for organism_id in sorted(self._contexts):
            raw_payload, raw_nutrition = environment.get(organism_id, (b"", ()))
            payload = bytes(raw_payload)
            nutrition = None if raw_nutrition is None else tuple(raw_nutrition)
            if nutrition is not None and len(nutrition) != len(payload):
                raise ValueError(f"food and nutrition lengths differ for organism {organism_id}")
            if nutrition is not None and any(not math.isfinite(float(value)) for value in nutrition):
                raise ValueError(f"nutrition must be finite for organism {organism_id}")
            prepared[organism_id] = (payload, nutrition)

        results: dict[int, dict[str, object]] = {}
        scheduled_ids = tuple(sorted(self._contexts))
        for organism_id in scheduled_ids:
            payload, nutrition = prepared[organism_id]
            if organism_id in supplied_children:
                child_id = int(supplied_children[organism_id])
            else:
                child_id = automatic_children[organism_id]
            child, cycle, plan = self._contexts[organism_id].step_and_try_divide(
                payload, child_id=child_id, nutrition=nutrition
            )
            results[organism_id] = {"cycle": cycle, "plan": plan}
            if child is not None:
                if child_id in self._contexts:
                    child.close()
                    raise NativeBackendError(f"native returned duplicate child ID {child_id}")
                self._contexts[child_id] = child
                results[organism_id]["child_id"] = child_id
        return results

    def snapshot(self, organism_id: int) -> dict[str, object]:
        """Return one native snapshot by stable population ID."""
        if self._closed:
            raise NativeBackendError("native population backend is closed")
        try:
            context = self._contexts[int(organism_id)]
        except KeyError as error:
            raise KeyError(f"unknown organism ID: {organism_id}") from error
        return context.snapshot()

    def snapshots(self) -> dict[int, dict[str, object]]:
        """Return all snapshots sorted by numeric ID."""
        return {organism_id: self._contexts[organism_id].snapshot() for organism_id in sorted(self._contexts)}

    def state_digests(self) -> dict[int, int]:
        """Return deterministic native state digests sorted by numeric ID."""
        if self._closed:
            raise NativeBackendError("native population backend is closed")
        return {
            organism_id: self._contexts[organism_id].state_digest()
            for organism_id in sorted(self._contexts)
        }

    def verify_material_conservation(self) -> None:
        """Validate every currently owned native ledger."""
        if self._closed:
            raise NativeBackendError("native population backend is closed")
        for organism_id in sorted(self._contexts):
            try:
                self._contexts[organism_id].verify_material_conservation()
            except NativeBackendError as error:
                raise NativeBackendError(
                    f"material conservation failed for organism {organism_id}"
                ) from error

    def close(self) -> None:
        if self._closed:
            return
        for organism_id in sorted(self._contexts, reverse=True):
            self._contexts[organism_id].close()
        self._closed = True

    def __enter__(self) -> "NativePopulationBackend":
        return self

    def __exit__(self, *_: object) -> None:
        self.close()


class ReferenceBackend:
    """Python reference backend retained as the semantic oracle."""

    def __init__(self, payload: str, config: LifecycleConfig | None = None) -> None:
        self.population = MathematicalLifePopulation(payload, config)

    def step(self) -> None:
        self.population.cycle()


def create_backend(name: str, **kwargs: Any) -> NativeBackend | NativePopulationBackend | ReferenceBackend:
    if name == "native":
        library = kwargs.get("library")
        if library is None:
            raise NativeBackendError("native backend requires an explicit library path")
        return NativeBackend(
            library,
            organism_id=int(kwargs.get("organism_id", 0)),
            config=kwargs.get("config"),
        )
    if name == "native-population":
        library = kwargs.get("library")
        if library is None:
            raise NativeBackendError("native-population backend requires an explicit library path")
        return NativePopulationBackend(
            library,
            organism_ids=kwargs.get("organism_ids", (0,)),
            config=kwargs.get("config"),
        )
    if name == "python":
        return ReferenceBackend(str(kwargs.get("payload", "")), kwargs.get("config"))
    raise ValueError(f"unknown backend: {name!r}")


__all__ = [
    "NativeBackend", "NativePopulationBackend", "NativeBackendError",
    "ReferenceBackend", "create_backend",
]
