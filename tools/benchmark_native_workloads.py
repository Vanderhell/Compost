"""Measure representative Python/native checkpoint workloads.

This deliberately benchmarks only transitions that have an explicit native
boundary. It never presents an incomplete native lifecycle as a full simulator
speed claim.
"""

from __future__ import annotations

import argparse
import ctypes
import os
import sys
from ctypes import wintypes
from pathlib import Path
from statistics import median
from time import perf_counter

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from mathematical_organism.backend import NativeBackend
from mathematical_organism.lifecycle import LifecycleConfig, MathematicalLifePopulation


def _peak_rss_bytes() -> int | None:
    if os.name == "nt":
        class _Counters(ctypes.Structure):
            _fields_ = [
                ("cb", ctypes.c_uint32),
                ("page_fault_count", ctypes.c_uint32),
                ("peak_working_set_size", ctypes.c_size_t),
                ("working_set_size", ctypes.c_size_t),
                ("quota_peak_paged_pool_usage", ctypes.c_size_t),
                ("quota_paged_pool_usage", ctypes.c_size_t),
                ("quota_peak_non_paged_pool_usage", ctypes.c_size_t),
                ("quota_non_paged_pool_usage", ctypes.c_size_t),
                ("pagefile_usage", ctypes.c_size_t),
                ("peak_pagefile_usage", ctypes.c_size_t),
            ]

        counters = _Counters()
        counters.cb = ctypes.sizeof(counters)
        process = ctypes.windll.kernel32.GetCurrentProcess()
        get_memory_info = ctypes.windll.psapi.GetProcessMemoryInfo
        get_memory_info.argtypes = [
            wintypes.HANDLE, ctypes.POINTER(_Counters), wintypes.DWORD
        ]
        get_memory_info.restype = wintypes.BOOL
        if get_memory_info(
            process, ctypes.byref(counters), counters.cb
        ):
            return int(counters.peak_working_set_size)
        return None
    try:
        import resource
    except ImportError:
        return None
    value = int(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)
    return value * (1024 if sys.platform != "darwin" else 1)


def _payload(workload: str) -> bytes:
    return {
        "digest": b"AB" * 128,
        "metabolism": b"ABCD" * 64,
        "structure": b"ABCDEFGH" * 32,
        "division": bytes((4, 5)),
    }[workload]


def _config(workload: str) -> LifecycleConfig:
    if workload == "division":
        return LifecycleConfig(boundary_ratio_limit=0.5, birth_reserve=10.0)
    return LifecycleConfig()


def _reference_run(workload: str, steps: int) -> None:
    payload = _payload(workload)
    population = MathematicalLifePopulation(payload.decode("latin1"), _config(workload))
    for _ in range(steps):
        population.cycle()


def _native_run(library: Path, workload: str, steps: int) -> None:
    payload = _payload(workload)
    config = _config(workload)
    with NativeBackend(library, organism_id=0, config=config) as backend:
        for step in range(steps):
            current = payload if step == 0 else b""
            if workload == "division":
                child, _cycle, _plan = backend.step_and_try_divide(
                    current, child_id=(1 << 32) + step, nutrition=(1.0,) * len(current)
                )
                if child is not None:
                    child.close()
            else:
                backend.step(current, (1.0,) * len(current))


def _measure(function: object, repetitions: int) -> tuple[float, float, float, int | None]:
    timings: list[float] = []
    peak: int | None = None
    for _ in range(repetitions):
        started = perf_counter()
        function()
        timings.append(perf_counter() - started)
        current_peak = _peak_rss_bytes()
        if current_peak is not None:
            peak = current_peak if peak is None else max(peak, current_peak)
    return min(timings), median(timings), max(timings), peak


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--library", type=Path, required=True)
    parser.add_argument("--steps", type=int, default=256)
    parser.add_argument("--repetitions", type=int, default=5)
    parser.add_argument(
        "--workloads",
        nargs="+",
        choices=("digest", "metabolism", "structure", "division"),
        default=["digest", "metabolism", "structure", "division"],
    )
    args = parser.parse_args()
    if args.steps <= 0 or args.repetitions <= 0:
        raise SystemExit("--steps and --repetitions must be positive")
    library = args.library.resolve()
    if not library.is_file():
        raise SystemExit(f"native library does not exist: {library}")
    for workload in args.workloads:
        for backend, function in (
            ("python", lambda workload=workload: _reference_run(workload, args.steps)),
            ("native-ffi", lambda workload=workload: _native_run(library, workload, args.steps)),
        ):
            minimum, middle, maximum, peak = _measure(function, args.repetitions)
            print(
                f"workload={workload} backend={backend} steps={args.steps} "
                f"repetitions={args.repetitions} min_seconds={minimum:.9f} "
                f"median_seconds={middle:.9f} max_seconds={maximum:.9f} "
                f"steps_per_second={args.steps / middle:.3f} "
                f"peak_rss_bytes={peak if peak is not None else 'unavailable'}"
            )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
