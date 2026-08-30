from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass(frozen=True, slots=True)
class AuditRecord:
    time: int
    input_symbols: tuple[str, ...]
    representation: tuple[str, ...]
    raw_positions: tuple[int, ...]
    energy_before: dict[str, float]
    energy_after: dict[str, float]
    adaptive_rule: str
    affected_nodes: tuple[int, ...] = ()
    semantic_proof: tuple[str, ...] = ()
    invariant_result: str = "PASS"
    notes: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class AuditLog:
    records: list[AuditRecord] = field(default_factory=list)

    def append(self, record: AuditRecord) -> None:
        self.records.append(record)

    def to_json_lines(self) -> str:
        return "\n".join(
            json.dumps(record.to_dict(), sort_keys=True, separators=(",", ":"))
            for record in self.records
        )

    def digest(self) -> str:
        return hashlib.sha256(self.to_json_lines().encode("utf-8")).hexdigest()

