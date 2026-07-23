from typing import Tuple, Dict, Optional
from domain import Schedule, CourseSection, Room, Timeslot, Lecturer
from .hard_constraints import HardConstraintChecker
from .soft_constraints import SoftConstraintChecker, SoftConstraintConfig

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

    def calculate_fitness(self, schedule: Schedule, hard_weight: int = 1000, soft_weight: int = 1) -> Tuple[float, int, int]:
        h_cnt, _ = self.evaluate_hard(schedule)
        soft_penalty, _ = self.evaluate_soft(schedule)
        score = (h_cnt * hard_weight) + (soft_penalty * soft_weight)
        return float(score), h_cnt, soft_penalty
