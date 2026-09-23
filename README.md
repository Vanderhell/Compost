# Compost

Experimental deterministic artificial-life simulator in which autonomous
mathematical organisms consume binary data as FOOD, maintain internal state,
grow structural bodies, metabolize resources, reproduce, die, and interact
with a sandbox environment.

> Experimental research project. It is not a biological model and not a
> production data-processing system.

## What is Compost?

Compost is a sandbox for deterministic artificial-life and
complex-systems experiments. It runs autonomous entities over binary input and
records the resulting world state and telemetry.

## Research question

The project explores whether relatively simple deterministic local rules for
food, energy, metabolism, growth, maintenance, territory, reproduction, death,
and resource competition can generate interesting global or emergent behaviour
without a central controller. It does not claim to prove biological realism,
life, or evolutionary theory.

## Core concepts

The terms **organism**, **food**, **metabolism**, **body**, **death**,
**reproduction**, and **territory** are simulator abstractions. They describe
state and rules in this model; they do not imply biological realism.

- **FOOD** is binary input prepared for consumption in an experiment-owned
  world.
- **Energy and metabolism** describe the simulator's resource accounting.
- **Bodies and territory** are structural and spatial bookkeeping within the
  sandbox.
- **Reproduction and death** are deterministic lifecycle transitions.

## How it works

Input files placed in an inbox are copied into experiment-owned storage and
partitioned into FOOD. The runtime advances organisms using local rules,
persists world state, and writes observational telemetry. The observer reports
state; it does not make biological decisions.

## Installation

Python 3.11 or newer is required.

```bash
python -m pip install .
```

The installed console command is `compost`.

## Running an experiment

Create an inbox and place one or more binary files in it:

```text
sandbox/
  inbox/
    example.bin
```

Then start the autonomous runtime:

```bash
python -m mathematical_organism run sandbox
```

The runtime creates the remaining directories itself:

```text
sandbox/
  inbox/       user-provided binary input
  world/       prepared FOOD and runtime state
  telemetry/   read-only snapshots
```

Use a bounded observation run when needed:

```bash
python -m mathematical_organism run sandbox --workers 4 --max-seconds 30
```

Use copies of files you are willing to supply to an experiment.

## Observing the world

Inspect the most recent snapshot without changing the world:

```bash
python -m mathematical_organism status sandbox
python -m mathematical_organism status sandbox --organisms
```

The observer reports FOOD accounting, population, body mass and bite sizes,
organism reserve/debt/gut state, territories, corpses, and runtime throughput.
Telemetry is observational and may be eventually consistent while workers run.

## Repository structure

```text
src/mathematical_organism/  simulator package
native/                     C17 deterministic core and CTest suite
tests/                      test suite and fixtures
tools/                      experiment and diagnostic scripts
examples/                   small usage example
experiments/                captured, versioned research runs
docs/native/                migration boundary, determinism, and audit reports
```

The Python implementation remains the behavioral reference oracle. The
versioned native C ABI is opt-in through the Python `native` and
`native-population` backends; it currently covers bounded deterministic core
checkpoints and explicit environment inputs. Filesystem FOOD discovery,
world/corpse orchestration, telemetry, and the existing parallel runtime
remain Python responsibilities while native parity is validated. The sandbox
can optionally emit replayable `NativeAction` traces for the validated
external-gut, queued-gut, corpse-energy, and bounded lifecycle prefixes; this
does not imply complete `live_step` replacement. Python validation code can
drive those traces through the reusable `NativeSandboxReplay` boundary while
retaining the Python sandbox as oracle and filesystem owner.

To run the bounded deterministic checkpoint explicitly through the native
library, provide the library path:

```bash
python -m mathematical_organism checkpoint ABCD --backend native \
  --library path/to/libcompost_native.so --steps 1 --json
```

The default checkpoint backend remains `python`. An explicitly requested
native backend reports library, ABI, argument, and execution failures; it does
not silently fall back to the Python oracle. Use the Python backend for the
reference behavior and the native backend for validated differential
experiments.

## Experiments

Captured 1m runs live under [`experiments/1m`](experiments/1m). They are
intentional reproducibility artifacts, not build output. See
[`experiments/README.md`](experiments/README.md) for the historical labels and
available context.

## Tests

Run the complete suite with:

```bash
python -m pytest
```

## Current limitations

This remains a research project. Performance scaling and population dynamics
are active research questions. Results are specific to the implemented rules,
parameters, and captured inputs; no optimality, security, or scientific proof
is claimed. The native migration is not yet a complete replacement for the
Python sandbox lifecycle; see [`docs/native/FINAL_NATIVE_AUDIT.md`](docs/native/FINAL_NATIVE_AUDIT.md)
for the current release-readiness verdict.

## Project status

Version `0.1.0` is experimental and intended for artificial-life and
complex-systems exploration rather than production use.

## License

This project is released under the [MIT License](LICENSE).
