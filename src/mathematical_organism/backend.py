"""Explicit reference/native backend handles.

The native backend is intentionally opt-in. Loading or native execution errors
are raised to the caller; this module never silently falls back to Python.
"""

from __future__ import annotations

import ctypes
from pathlib import Path
from typing import Any

from .lifecycle import LifecycleConfig, MathematicalLifePopulation


class NativeBackendError(RuntimeError):
    pass


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

    def __init__(self, library: str | Path, *, organism_id: int = 0) -> None:
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
        config = _Config()
        status = self._library.compost_config_default(ctypes.byref(config))
        self._check(status, "compost_config_default")
        self._context = ctypes.c_void_p()
        status = self._library.compost_create(ctypes.byref(config), ctypes.c_uint64(organism_id), ctypes.byref(self._context))
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
        library.compost_context_enqueue_external.argtypes = [ctypes.c_void_p, ctypes.POINTER(_Input)]
        library.compost_context_enqueue_external.restype = ctypes.c_int
        library.compost_context_process_gut.argtypes = [
            ctypes.c_void_p, ctypes.c_uint64, ctypes.POINTER(_GutProcessResult)
        ]
        library.compost_context_process_gut.restype = ctypes.c_int
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

    def close(self) -> None:
        if self._context and self._context.value:
            self._library.compost_destroy(self._context)
            self._context = ctypes.c_void_p()

    def __enter__(self) -> "NativeBackend":
        return self

    def __exit__(self, *_: object) -> None:
        self.close()


class ReferenceBackend:
    """Python reference backend retained as the semantic oracle."""

    def __init__(self, payload: str, config: LifecycleConfig | None = None) -> None:
        self.population = MathematicalLifePopulation(payload, config)

    def step(self) -> None:
        self.population.cycle()


def create_backend(name: str, **kwargs: Any) -> NativeBackend | ReferenceBackend:
    if name == "native":
        library = kwargs.get("library")
        if library is None:
            raise NativeBackendError("native backend requires an explicit library path")
        return NativeBackend(library, organism_id=int(kwargs.get("organism_id", 0)))
    if name == "python":
        return ReferenceBackend(str(kwargs.get("payload", "")), kwargs.get("config"))
    raise ValueError(f"unknown backend: {name!r}")


__all__ = ["NativeBackend", "NativeBackendError", "ReferenceBackend", "create_backend"]
