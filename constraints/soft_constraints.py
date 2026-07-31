"""Soft Constraint Checker Module.

Evaluates 4 desirable soft constraints (student gaps, consecutive teaching,
difficult afternoon courses, and daily study load imbalance) with configurable weights.
"""

from dataclasses import dataclass, field
from typing import Dict, Tuple, Optional
from collections import defaultdict
from domain import Schedule, CourseSection, Room, Timeslot
from dataset import get_occupied_periods

@dataclass(frozen=True)
class SoftConstraintConfig:
    """Configurable penalty weights and period boundaries for soft constraints."""
    afternoon_start_period: int = 7
    weights: Dict[str, int] = field(default_factory=lambda: {
        "student_gaps": 5,
        "consecutive_teaching": 6,
        "difficult_afternoon": 3,
        "daily_imbalance": 8,
    })

    def validate(self) -> None:
        if self.afternoon_start_period < 1:
            raise ValueError(f"afternoon_start_period must be >= 1, got {self.afternoon_start_period}")

        required_keys = {"student_gaps", "consecutive_teaching", "difficult_afternoon", "daily_imbalance"}
        for key in required_keys:
            if key not in self.weights:
                raise ValueError(f"Missing soft constraint weight for: {key}")

        for name, weight in self.weights.items():
            if not isinstance(weight, int):
                raise ValueError(f"Weight for {name} must be an int, got {type(weight).__name__}")
            if weight < 0:
                raise ValueError(f"Weight for {name} cannot be negative, got {weight}")

class SoftConstraintChecker:
    """Evaluates soft constraint violations and calculates weighted penalty scores."""

    def __init__(
        self,
        section_map: Dict[str, CourseSection],
        room_map: Dict[str, Room],
        timeslot_map: Dict[int, Timeslot],
        config: Optional[SoftConstraintConfig] = None,
    ):
        self.section_map = section_map
        self.room_map = room_map
        self.timeslot_map = timeslot_map
        self.config = config or SoftConstraintConfig()
        self._validate_config()

    def _validate_config(self) -> None:
        self.config.validate()

    def calculate_weighted_penalty(self, details: Dict[str, int]) -> int:
        penalty = 0
        for name, count in details.items():
            if name not in self.config.weights:
                raise ValueError(f"Missing soft constraint weight: {name}")
            if self.config.weights[name] < 0:
                raise ValueError(f"Weight for {name} cannot be negative")
            penalty += count * self.config.weights[name]
        return penalty

    def evaluate(self, schedule: Schedule) -> Tuple[int, Dict[str, int]]:
        details = {
            "consecutive_teaching": 0,
            "student_gaps": 0,
            "difficult_afternoon": 0,
            "daily_imbalance": 0
        }

        if not isinstance(schedule, Schedule) or not isinstance(getattr(schedule, "genes", None), list):
            return 0, details

        # 1. Môn khó học tiết chiều (period >= afternoon_start_period, e.g. >= 7)
        for gene in schedule.genes:
            sec_id = getattr(gene, "section_id", None)
            ts_id = getattr(gene, "timeslot_id", None)
            if sec_id in self.section_map and ts_id in self.timeslot_map:
                section = self.section_map[sec_id]
                ts = self.timeslot_map[ts_id]
                if section.is_difficult and ts.period >= self.config.afternoon_start_period:
                    details["difficult_afternoon"] += 1

        lecturer_day_periods = defaultdict(list)
        group_day_periods = defaultdict(list)

        for gene in schedule.genes:
            sec_id = getattr(gene, "section_id", None)
            ts_id = getattr(gene, "timeslot_id", None)
            if sec_id in self.section_map and ts_id in self.timeslot_map:
                section = self.section_map[sec_id]
                ts = self.timeslot_map[ts_id]
                duration = getattr(section, "duration_periods", 1)
                occupied = get_occupied_periods(ts.period, duration)

                if section.lecturer_id:
                    for p in occupied:
                        lecturer_day_periods[(section.lecturer_id, ts.day)].append(p)
                if section.group_id:
                    for p in occupied:
                        group_day_periods[(section.group_id, ts.day)].append(p)

        # 2. GV dạy liên tục > 4 tiết (hoặc dạy liên tục kéo dài qua nhiều lớp)
        for (lec, day), periods in lecturer_day_periods.items():
            if not lec:
                continue
            sorted_p = sorted(set(periods))
            consecutive = 1
            for i in range(len(sorted_p) - 1):
                if sorted_p[i+1] == sorted_p[i] + 1:
                    consecutive += 1
                    if consecutive > 4:
                        details["consecutive_teaching"] += 1
                else:
                    consecutive = 1

        # 3. Tiết trống (gaps) của sinh viên (tính theo unique periods trong ngày)
        for (grp, day), periods in group_day_periods.items():
            if not grp:
                continue
            unique_periods = sorted(set(periods))
            if len(unique_periods) > 1:
                span = unique_periods[-1] - unique_periods[0] + 1
                gaps = span - len(unique_periods)
                if gaps > 0:
                    details["student_gaps"] += gaps

        # 4. Mất cân bằng ngày học (quá 4 tiết/ngày cho 1 nhóm SV)
        group_daily_counts = defaultdict(lambda: defaultdict(int))
        for gene in schedule.genes:
            sec_id = getattr(gene, "section_id", None)
            ts_id = getattr(gene, "timeslot_id", None)
            if sec_id in self.section_map and ts_id in self.timeslot_map:
                section = self.section_map[sec_id]
                ts = self.timeslot_map[ts_id]
                duration = getattr(section, "duration_periods", 1)
                if section.group_id:
                    group_daily_counts[section.group_id][ts.day] += duration

        for grp, days_dict in group_daily_counts.items():
            for count in days_dict.values():
                if count > 4:
                    details["daily_imbalance"] += (count - 4)

        total_raw_count = sum(details.values())
        return total_raw_count, details
