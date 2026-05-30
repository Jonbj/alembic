"""Shared data types for validation gates."""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class GateResult:
    """Result from a single validation gate."""
    passed: bool
    details: dict = field(default_factory=dict)


@dataclass
class GateReport:
    """Aggregated report from all validation gates."""
    gate_results: dict[str, GateResult] = field(default_factory=dict)

    @property
    def overall_passed(self) -> bool:
        return all(g.passed for g in self.gate_results.values())

    @property
    def passed_gates(self) -> list[str]:
        return [name for name, g in self.gate_results.items() if g.passed]

    @property
    def failed_gates(self) -> list[str]:
        return [name for name, g in self.gate_results.items() if not g.passed]

    def summary(self) -> str:
        lines = ["=== GATE REPORT ==="]
        for name, result in self.gate_results.items():
            status = "PASS" if result.passed else "FAIL"
            lines.append(f"  {name}: {status}  {result.details}")
        lines.append(f"Overall: {'PASS' if self.overall_passed else 'FAIL'}")
        return "\n".join(lines)
