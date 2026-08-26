"""Unified Constraint Evaluator.

Combines hard constraint checking (HardConstraintChecker) with the new
Excel-driven normalized soft constraint checking.

The soft_breakdown in UnifiedEvaluationResult iterates constraints in canonical
order S1 → S7. The retired legacy constraints
(student_gaps, consecutive_teaching, difficult_afternoon, daily_imbalance)
are permanently retired from this evaluator.
"""

from dataclasses import dataclass, field
from typing import Tuple, Dict, Optional, List, Any
from domain import Schedule, CourseSection, Room, Timeslot, Lecturer, StudentGroup
from .hard_constraints import HardConstraintChecker
from .soft_constraints import (
    SoftConstraintChecker,
    SoftConstraintConfig,
    SOFT_CONSTRAINT_KEYS,
)


@dataclass
class SoftBreakdownItem:
    """Per-constraint breakdown of soft penalty contributions."""
    constraint_id: str          # "S1", "S2", ...
    constraint_name: str        # Vietnamese display name from config
    constraint_key: str         # canonical key, e.g. "compact_student_schedule"
    raw_count: float
    denominator: float
    normalized_penalty: float
    weight: int
    weighted_penalty: float
    details: List[Dict[str, Any]] = field(default_factory=list)

    # Legacy compat: expose constraint_name also as just `name`
    @property
    def name(self) -> str:
        return self.constraint_name


@dataclass
class UnifiedEvaluationResult:
    hard_violations: int
    soft_penalty: float
    hard_details: Dict[str, int]
    soft_breakdown: List[SoftBreakdownItem]
    instance_violations: List[Dict[str, Any]] = field(default_factory=list)

    def __post_init__(self):
        calculated_soft = sum(item.weighted_penalty for item in self.soft_breakdown)
        if abs(self.soft_penalty - calculated_soft) > 1e-12:
            raise ValueError(
                f"soft_penalty ({self.soft_penalty}) does not match "
                f"sum of weighted penalties ({calculated_soft})."
            )


from domain import EvaluationCounters


class ConstraintEvaluator:
    def __init__(
        self,
        dataset: dict,
        soft_config: Optional[SoftConstraintConfig] = None,
        counters: Optional[EvaluationCounters] = None,
    ) -> None:
        self.counters = counters if counters is not None else EvaluationCounters()
        self.section_map: Dict[str, CourseSection] = {
            c.section_id: c for c in dataset["course_sections"]
        }
        self.room_map: Dict[str, Room] = {r.id: r for r in dataset["rooms"]}
        self.timeslot_map: Dict[int, Timeslot] = {t.id: t for t in dataset["timeslots"]}
        self.lecturer_map: Dict[str, Lecturer] = {
            l.id: l for l in dataset.get("lecturers", [])
        }
        self.student_group_map: Dict[str, StudentGroup] = {
            group.id: group for group in dataset.get("student_groups", [])
        }

        lecturer_ids = (
            set(self.lecturer_map.keys()) if "lecturers" in dataset else None
        )
        group_ids = (
            {g.id for g in dataset.get("student_groups", [])}
            if "student_groups" in dataset
            else None
        )

        self.hard_checker = HardConstraintChecker(
            self.section_map,
            self.room_map,
            self.timeslot_map,
            lecturer_ids=lecturer_ids,
            group_ids=group_ids,
            lecturer_map=self.lecturer_map,
        )

        # Resolve soft config: explicit arg > dataset["constraints"] > default
        if soft_config is None:
            constraint_defs = dataset.get("constraints", [])
            if constraint_defs:
                soft_config = SoftConstraintConfig.from_constraint_definitions(
                    constraint_defs
                )
            else:
                soft_config = SoftConstraintConfig.default()

        self.soft_checker = SoftConstraintChecker(
            self.section_map,
            self.room_map,
            self.timeslot_map,
            config=soft_config,
            student_group_map=self.student_group_map,
        )

    def _increment_hard(self, category: str = "search") -> None:
        if category == "internal":
            self.counters.internal_hard_constraint_evaluations += 1
        elif category == "reporting":
            self.counters.reporting_hard_constraint_evaluations += 1
        else:
            self.counters.search_hard_constraint_evaluations += 1

    def _increment_soft(self, category: str = "search") -> None:
        if category == "internal":
            self.counters.internal_soft_constraint_evaluations += 1
        elif category == "reporting":
            self.counters.reporting_soft_constraint_evaluations += 1
        else:
            self.counters.search_soft_constraint_evaluations += 1

    def evaluate_hard(self, schedule: Schedule, category: str = "search") -> Tuple[int, Dict[str, int]]:
        self._increment_hard(category)
        return self.hard_checker.evaluate(schedule)

    def evaluate_soft(self, schedule: Schedule, category: str = "search") -> Tuple[float, Dict[str, float]]:
        """Return normalized weighted penalty and legacy raw details."""
        self._increment_soft(category)
        _, raw_details, metrics, _, _ = self.soft_checker.evaluate_metrics(schedule)
        weighted_penalty = sum(metric.weighted for metric in metrics.values())
        return weighted_penalty, raw_details

    def evaluate_soft_raw(self, schedule: Schedule, category: str = "search") -> Tuple[float, Dict[str, float]]:
        self._increment_soft(category)
        raw_count, details, _ = self.soft_checker.evaluate_detailed(schedule)
        return raw_count, details

    def evaluate_unified(self, schedule: Schedule, category: str = "reporting") -> UnifiedEvaluationResult:
        hard_count, hard_details = self.evaluate_hard(schedule, category=category)
        self._increment_soft(category)
        _, details, metrics, instance_items, _ = self.soft_checker.evaluate_metrics(schedule)

        soft_breakdown: List[SoftBreakdownItem] = []
        total_weighted_soft = 0.0

        config = self.soft_checker.config
        for key in SOFT_CONSTRAINT_KEYS:
            metric = metrics[key]
            c_raw = metric.raw
            c_weight = metric.weight
            c_id = config.get_constraint_id(key)
            c_name = config.get_name(key)
            c_weighted = metric.weighted
            total_weighted_soft += c_weighted

            c_instances = [
                item for item in instance_items
                if item.get("constraint_key") == key
            ]
            soft_breakdown.append(SoftBreakdownItem(
                constraint_id=c_id,
                constraint_name=c_name,
                constraint_key=key,
                raw_count=c_raw,
                denominator=metric.denominator,
                normalized_penalty=metric.normalized,
                weight=c_weight,
                weighted_penalty=c_weighted,
                details=c_instances,
            ))

        return UnifiedEvaluationResult(
            hard_violations=hard_count,
            soft_penalty=total_weighted_soft,
            hard_details=hard_details,
            soft_breakdown=soft_breakdown,
            instance_violations=instance_items,
        )

    def calculate_fitness(
        self,
        schedule: Schedule,
        hard_weight: int = 1000,
        soft_weight: int = 1,
        is_search_eval: bool = False,
        category: str = "search",
    ) -> Tuple[float, int, float]:
        cat = "search" if is_search_eval else category
        h_cnt, _ = self.evaluate_hard(schedule, category=cat)
        soft_penalty, _ = self.evaluate_soft(schedule, category=cat)
        weighted_score = (h_cnt * hard_weight) + (soft_penalty * soft_weight)
        return float(weighted_score), h_cnt, soft_penalty
