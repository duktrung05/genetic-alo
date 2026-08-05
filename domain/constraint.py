"""Constraint Domain Model.

Defines ConstraintDefinition — a parsed row from the CONSTRAINTS sheet of the
timetable Excel workbook.  Both hard and soft constraints are represented;
the soft-constraint pipeline only processes rows with constraint_type == "SOFT".
"""
from dataclasses import dataclass
from enum import Enum


class RepairStatus(str, Enum):
    """Execution status of a single Repair Engine transformation call."""
    IMPROVED = "improved"    # (after_hard, after_soft) < (before_hard, before_soft)
    UNCHANGED = "unchanged"  # (after_hard, after_soft) == (before_hard, before_soft)
    FAILED = "failed"        # (after_hard, after_soft) > (before_hard, before_soft) or invalid


@dataclass
class EvaluationCounters:
    """Tracks distinct evaluation and candidate-checking counter metrics per run."""
    search_hard_constraint_evaluations: int = 0
    search_soft_constraint_evaluations: int = 0
    internal_hard_constraint_evaluations: int = 0
    internal_soft_constraint_evaluations: int = 0
    reporting_hard_constraint_evaluations: int = 0
    reporting_soft_constraint_evaluations: int = 0
    candidate_checks: int = 0

    @property
    def search_fitness_evaluations(self) -> int:
        return max(self.search_hard_constraint_evaluations, self.search_soft_constraint_evaluations)

    @search_fitness_evaluations.setter
    def search_fitness_evaluations(self, val: int) -> None:
        self.search_hard_constraint_evaluations = val
        self.search_soft_constraint_evaluations = val

    @property
    def hard_constraint_evaluations(self) -> int:
        return (
            self.search_hard_constraint_evaluations
            + self.internal_hard_constraint_evaluations
            + self.reporting_hard_constraint_evaluations
        )

    @property
    def soft_constraint_evaluations(self) -> int:
        return (
            self.search_soft_constraint_evaluations
            + self.internal_soft_constraint_evaluations
            + self.reporting_soft_constraint_evaluations
        )

    @property
    def search_constraint_evaluations(self) -> int:
        return self.search_hard_constraint_evaluations + self.search_soft_constraint_evaluations

    @property
    def internal_constraint_evaluations(self) -> int:
        return self.internal_hard_constraint_evaluations + self.internal_soft_constraint_evaluations

    @property
    def reporting_constraint_evaluations(self) -> int:
        return self.reporting_hard_constraint_evaluations + self.reporting_soft_constraint_evaluations

    @property
    def total_constraint_evaluations(self) -> int:
        return self.hard_constraint_evaluations + self.soft_constraint_evaluations

    def reset(self) -> None:
        self.search_hard_constraint_evaluations = 0
        self.search_soft_constraint_evaluations = 0
        self.internal_hard_constraint_evaluations = 0
        self.internal_soft_constraint_evaluations = 0
        self.reporting_hard_constraint_evaluations = 0
        self.reporting_soft_constraint_evaluations = 0
        self.candidate_checks = 0

    def snapshot(self) -> "EvaluationCounters":
        return EvaluationCounters(
            search_hard_constraint_evaluations=self.search_hard_constraint_evaluations,
            search_soft_constraint_evaluations=self.search_soft_constraint_evaluations,
            internal_hard_constraint_evaluations=self.internal_hard_constraint_evaluations,
            internal_soft_constraint_evaluations=self.internal_soft_constraint_evaluations,
            reporting_hard_constraint_evaluations=self.reporting_hard_constraint_evaluations,
            reporting_soft_constraint_evaluations=self.reporting_soft_constraint_evaluations,
            candidate_checks=self.candidate_checks,
        )





@dataclass(frozen=True)
class ConstraintDefinition:
    """Represents a single row from the CONSTRAINTS sheet.

    Attributes:
        constraint_id:   Unique identifier, e.g. "S1", "H3".
        constraint_type: Normalized type string: "SOFT" or "HARD".
        constraint_name: Human-readable name (Vietnamese label from Excel).
        weight:          Integer penalty weight (>= 0).
        enabled:         Whether the constraint is active.
    """
    constraint_id: str
    constraint_type: str    # "SOFT" | "HARD"
    constraint_name: str
    weight: int
    enabled: bool

    def __post_init__(self) -> None:
        if not self.constraint_id:
            raise ValueError("constraint_id must not be empty")
        if self.constraint_type not in ("SOFT", "HARD"):
            raise ValueError(
                f"constraint_type must be 'SOFT' or 'HARD', got '{self.constraint_type}'"
            )
        if not isinstance(self.weight, int):
            raise TypeError(
                f"weight must be int, got {type(self.weight).__name__}"
            )
        if self.weight < 0:
            raise ValueError(
                f"weight cannot be negative, got {self.weight}"
            )
