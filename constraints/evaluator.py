from dataclasses import dataclass, field
from typing import Tuple, Dict, Optional, List, Any
from domain import Schedule, CourseSection, Room, Timeslot, Lecturer
from .hard_constraints import HardConstraintChecker
from .soft_constraints import SoftConstraintChecker, SoftConstraintConfig


@dataclass
class SoftBreakdownItem:
    constraint_name: str
    raw_count: int
    weight: int
    weighted_penalty: int
    details: List[Dict[str, Any]] = field(default_factory=list)


@dataclass
class UnifiedEvaluationResult:
    hard_violations: int
    soft_penalty: int
    hard_details: Dict[str, int]
    soft_breakdown: List[SoftBreakdownItem]
    instance_violations: List[Dict[str, Any]] = field(default_factory=list)

    def __post_init__(self):
        calculated_soft = sum(item.weighted_penalty for item in self.soft_breakdown)
        if self.soft_penalty != calculated_soft:
            raise ValueError(
                f"soft_penalty ({self.soft_penalty}) does not match sum of weighted penalties ({calculated_soft})."
            )


class ConstraintEvaluator:
    def __init__(self, dataset: dict, soft_config: Optional[SoftConstraintConfig] = None):
        self.section_map: Dict[str, CourseSection] = {c.section_id: c for c in dataset["course_sections"]}
        self.room_map: Dict[str, Room] = {r.id: r for r in dataset["rooms"]}
        self.timeslot_map: Dict[int, Timeslot] = {t.id: t for t in dataset["timeslots"]}
        self.lecturer_map: Dict[str, Lecturer] = {l.id: l for l in dataset.get("lecturers", [])}

        lecturer_ids = set(self.lecturer_map.keys()) if "lecturers" in dataset else None
        group_ids = {g.id for g in dataset.get("student_groups", [])} if "student_groups" in dataset else None

        self.hard_checker = HardConstraintChecker(
            self.section_map,
            self.room_map,
            self.timeslot_map,
            lecturer_ids=lecturer_ids,
            group_ids=group_ids,
            lecturer_map=self.lecturer_map
        )
        self.soft_checker = SoftConstraintChecker(
            self.section_map,
            self.room_map,
            self.timeslot_map,
            config=soft_config
        )

    def evaluate_hard(self, schedule: Schedule) -> Tuple[int, Dict[str, int]]:
        return self.hard_checker.evaluate(schedule)

    def evaluate_soft(self, schedule: Schedule) -> Tuple[int, Dict[str, int]]:
        raw_count, details = self.soft_checker.evaluate(schedule)
        weighted_penalty = self.soft_checker.calculate_weighted_penalty(details)
        return weighted_penalty, details

    def evaluate_soft_raw(self, schedule: Schedule) -> Tuple[int, Dict[str, int]]:
        return self.soft_checker.evaluate(schedule)

    def evaluate_unified(self, schedule: Schedule) -> UnifiedEvaluationResult:
        hard_count, hard_details = self.evaluate_hard(schedule)
        raw_count, details, instance_items = self.soft_checker.evaluate_detailed(schedule)

        soft_breakdown: List[SoftBreakdownItem] = []
        total_weighted_soft = 0

        for name in ["student_gaps", "consecutive_teaching", "difficult_afternoon", "daily_imbalance"]:
            c_raw = details.get(name, 0)
            c_weight = self.soft_checker.config.weights.get(name, 0)
            c_weighted = c_raw * c_weight
            total_weighted_soft += c_weighted

            c_instances = [item for item in instance_items if item["constraint_name"] == name]
            soft_breakdown.append(SoftBreakdownItem(
                constraint_name=name,
                raw_count=c_raw,
                weight=c_weight,
                weighted_penalty=c_weighted,
                details=c_instances
            ))

        return UnifiedEvaluationResult(
            hard_violations=hard_count,
            soft_penalty=total_weighted_soft,
            hard_details=hard_details,
            soft_breakdown=soft_breakdown,
            instance_violations=instance_items
        )

    def calculate_fitness(self, schedule: Schedule, hard_weight: int = 1000, soft_weight: int = 1) -> Tuple[float, int, int]:
        h_cnt, _ = self.evaluate_hard(schedule)
        soft_penalty, _ = self.evaluate_soft(schedule)
        weighted_score = (h_cnt * hard_weight) + (soft_penalty * soft_weight)
        return float(weighted_score), h_cnt, soft_penalty
