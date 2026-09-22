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
        ("atom_maintenance", ctypes.c_double),
        ("relation_maintenance", ctypes.c_double),
        ("atom_formation_cost", ctypes.c_double),
        ("relation_formation_cost", ctypes.c_double),
        ("birth_reserve", ctypes.c_double),
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
        ("status_after", ctypes.c_int),
    ]


class NativeBackend:
    """Small explicit ctypes adapter for the versioned native ABI."""

    ABI_VERSION = 2
    MAX_ATOMS = 256

    def __init__(self, library: str | Path, *, organism_id: int = 0) -> None:
        self.library_path = Path(library).resolve()
        if not self.library_path.is_file():
            raise NativeBackendError(f"native library does not exist: {self.library_path}")
        try:
            self._library = ctypes.CDLL(str(self.library_path))
        except OSError as error:
            raise NativeBackendError(f"cannot load native library: {self.library_path}") from error
        self._configure_symbols()
        config = _Config()
        status = self._library.compost_config_default(ctypes.byref(config))
        self._check(status, "compost_config_default")
        self._context = ctypes.c_void_p()
        status = self._library.compost_create(ctypes.byref(config), ctypes.c_uint64(organism_id), ctypes.byref(self._context))
        self._check(status, "compost_create")
        if not self._context.value:
            raise NativeBackendError("native create returned a null context")

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
        library.compost_context_state_digest.argtypes = [ctypes.c_void_p]
        library.compost_context_state_digest.restype = ctypes.c_uint64
        library.compost_context_select_partition.argtypes = [
            ctypes.c_void_p,
            ctypes.c_double,
            ctypes.POINTER(ctypes.c_uint8),
            ctypes.c_size_t,
            ctypes.POINTER(ctypes.c_size_t),
            ctypes.POINTER(ctypes.c_double),
        ]
        library.compost_context_select_partition.restype = ctypes.c_int

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

    def state_digest(self) -> int:
        """Return the native behavioral-state digest for differential checks."""
        if not self._context or not self._context.value:
            raise NativeBackendError("native backend is closed")
        return int(self._library.compost_context_state_digest(self._context))

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
