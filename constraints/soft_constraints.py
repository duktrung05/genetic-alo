"""Normalized soft constraints for the timetable objective.

Every objective follows the same pipeline::

    raw metric -> instance-derived denominator -> normalized [0, 1]
               -> stakeholder weight -> weighted contribution

The normalized convention prevents count-valued objectives (especially room
seat waste) from dominating only because their raw unit has a larger scale.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from types import MappingProxyType
from typing import Any, Dict, List, Mapping, Optional, Set, Tuple

from domain import (
    ConstraintDefinition,
    CourseSection,
    Room,
    Schedule,
    StudentGroup,
    Timeslot,
)
from dataset import get_occupied_periods


SOFT_CONSTRAINT_KEY_BY_ID: Dict[str, str] = {
    "S1": "compact_student_schedule",
    "S2": "late_day_periods",
    "S3": "preferred_shift_mismatch",
    "S4": "room_seat_waste",
    "S5": "consecutive_cross_campus",
    "S6": "preferred_campus_mismatch",
    "S7": "student_home_campus_mismatch",
}

_KEY_TO_ID: Dict[str, str] = {
    value: key for key, value in SOFT_CONSTRAINT_KEY_BY_ID.items()
}

# Older integrations may still request the former S1 key. Configuration lookup
# remains compatible, while all new breakdowns use the accurate compact name.
_LEGACY_KEY_ALIASES: Dict[str, str] = {
    "weekly_distribution": "compact_student_schedule",
}

SOFT_CONSTRAINT_KEYS: List[str] = list(SOFT_CONSTRAINT_KEY_BY_ID.values())

DEFAULT_SOFT_WEIGHT_PROFILE = "balanced"

# All profiles use the same normalized S1-S7 metrics.  Only stakeholder
# priorities differ, and every profile has the same total weight (28) so that
# profile comparisons are easy to audit.
SOFT_WEIGHT_PROFILES: Mapping[str, Mapping[str, int]] = MappingProxyType({
    "student-centric": MappingProxyType({
        "compact_student_schedule": 6,
        "late_day_periods": 4,
        "preferred_shift_mismatch": 5,
        "room_seat_waste": 2,
        "consecutive_cross_campus": 3,
        "preferred_campus_mismatch": 3,
        "student_home_campus_mismatch": 5,
    }),
    "balanced": MappingProxyType({
        "compact_student_schedule": 5,
        "late_day_periods": 4,
        "preferred_shift_mismatch": 4,
        "room_seat_waste": 4,
        "consecutive_cross_campus": 4,
        "preferred_campus_mismatch": 3,
        "student_home_campus_mismatch": 4,
    }),
    "resource-centric": MappingProxyType({
        "compact_student_schedule": 3,
        "late_day_periods": 3,
        "preferred_shift_mismatch": 3,
        "room_seat_waste": 10,
        "consecutive_cross_campus": 4,
        "preferred_campus_mismatch": 2,
        "student_home_campus_mismatch": 3,
    }),
})

_DEFAULT_WEIGHTS: Mapping[str, int] = SOFT_WEIGHT_PROFILES[
    DEFAULT_SOFT_WEIGHT_PROFILE
]

_DEFAULT_NAMES: Dict[str, str] = {
    "compact_student_schedule": "Giảm số ngày sinh viên phải đến trường",
    "late_day_periods": "Hạn chế quá nhiều tiết cuối ngày",
    "preferred_shift_mismatch": "Ưu tiên ca học mong muốn của lớp học phần",
    "room_seat_waste": "Giảm tỷ lệ ghế trống trong phòng",
    "consecutive_cross_campus": "Hạn chế giảng viên chuyển cơ sở liên tiếp",
    "preferred_campus_mismatch": "Ưu tiên cơ sở mong muốn của lớp học phần",
    "student_home_campus_mismatch": "Ưu tiên cơ sở chính của nhóm sinh viên",
}


def _canonical_key(key: str) -> str:
    return _LEGACY_KEY_ALIASES.get(key, key)


def _normalized(raw: float, denominator: float) -> float:
    if denominator <= 0:
        return 0.0
    return min(1.0, max(0.0, float(raw) / float(denominator)))


@dataclass(frozen=True)
class SoftConstraintDefinition:
    constraint_id: str
    key: str
    name: str
    weight: int
    enabled: bool


@dataclass(frozen=True)
class NormalizedSoftMetric:
    """Auditable result for one normalized objective."""

    raw: float
    denominator: float
    normalized: float
    weight: int
    weighted: float
    enabled: bool


class SoftConstraintConfig:
    def __init__(self, definitions: Mapping[str, SoftConstraintDefinition]) -> None:
        canonical = {_canonical_key(key): value for key, value in definitions.items()}
        self._defs: MappingProxyType[str, SoftConstraintDefinition] = MappingProxyType(
            canonical
        )

    @property
    def definitions(self) -> MappingProxyType[str, SoftConstraintDefinition]:
        return self._defs

    def get_weight(self, key: str) -> int:
        definition = self._defs.get(_canonical_key(key))
        return definition.weight if definition else 0

    def is_enabled(self, key: str) -> bool:
        definition = self._defs.get(_canonical_key(key))
        return definition.enabled if definition else False

    def get_name(self, key: str) -> str:
        canonical = _canonical_key(key)
        definition = self._defs.get(canonical)
        return definition.name if definition else canonical

    def get_constraint_id(self, key: str) -> str:
        canonical = _canonical_key(key)
        definition = self._defs.get(canonical)
        return definition.constraint_id if definition else _KEY_TO_ID.get(canonical, "")

    def to_metadata(self) -> Dict[str, Dict[str, object]]:
        """Return the effective S1-S7 configuration in a stable export shape."""
        return {
            definition.constraint_id: {
                "key": definition.key,
                "name": definition.name,
                "weight": definition.weight,
                "enabled": definition.enabled,
            }
            for definition in sorted(
                self._defs.values(), key=lambda item: item.constraint_id
            )
        }

    @classmethod
    def from_constraint_definitions(
        cls, constraint_defs: List[ConstraintDefinition]
    ) -> "SoftConstraintConfig":
        """Use workbook weights, adding S6/S7 defaults for legacy workbooks.

        Missing legacy S1-S5 rows stay disabled to preserve partial custom
        configurations. S6/S7 are new Phase-1 objectives and default to weight
        5/enabled when an older workbook has no rows for them.
        """

        definitions: Dict[str, SoftConstraintDefinition] = {}
        for constraint in constraint_defs:
            if constraint.constraint_type != "SOFT":
                continue
            key = SOFT_CONSTRAINT_KEY_BY_ID.get(constraint.constraint_id)
            if key is None:
                continue
            definitions[key] = SoftConstraintDefinition(
                constraint_id=constraint.constraint_id,
                key=key,
                # S1 changed semantics in Phase 1; do not expose the legacy
                # "weekly distribution" label for the compactness metric.
                name=(
                    _DEFAULT_NAMES[key]
                    if constraint.constraint_id == "S1"
                    else constraint.constraint_name
                ),
                weight=constraint.weight,
                enabled=constraint.enabled,
            )

        for key in SOFT_CONSTRAINT_KEYS:
            if key in definitions:
                continue
            constraint_id = _KEY_TO_ID[key]
            is_new_campus_objective = constraint_id in {"S6", "S7"}
            definitions[key] = SoftConstraintDefinition(
                constraint_id=constraint_id,
                key=key,
                name=_DEFAULT_NAMES[key],
                weight=_DEFAULT_WEIGHTS[key] if is_new_campus_objective else 0,
                enabled=is_new_campus_objective,
            )
        return cls(definitions)

    @classmethod
    def default(cls) -> "SoftConstraintConfig":
        return cls.from_profile(DEFAULT_SOFT_WEIGHT_PROFILE)

    @classmethod
    def from_profile(cls, profile_name: str) -> "SoftConstraintConfig":
        """Build an enabled S1-S7 config from a named calibration profile."""

        normalized_name = profile_name.strip().lower().replace("_", "-")
        if normalized_name not in SOFT_WEIGHT_PROFILES:
            choices = ", ".join(SOFT_WEIGHT_PROFILES)
            raise ValueError(
                f"Unknown soft weight profile '{profile_name}'. Expected one of: {choices}"
            )
        weights = SOFT_WEIGHT_PROFILES[normalized_name]
        return cls(
            {
                key: SoftConstraintDefinition(
                    constraint_id=_KEY_TO_ID[key],
                    key=key,
                    name=_DEFAULT_NAMES[key],
                    weight=weights[key],
                    enabled=True,
                )
                for key in SOFT_CONSTRAINT_KEYS
            }
        )

    def validate(self) -> None:
        """Compatibility hook retained for existing callers."""


class SoftConstraintChecker:
    def __init__(
        self,
        section_map: Dict[str, CourseSection],
        room_map: Dict[str, Room],
        timeslot_map: Dict[int, Timeslot],
        config: Optional[SoftConstraintConfig] = None,
        student_group_map: Optional[Dict[str, StudentGroup]] = None,
    ) -> None:
        self.section_map = section_map
        self.room_map = room_map
        self.timeslot_map = timeslot_map
        self.config = config if config is not None else SoftConstraintConfig.default()
        self.student_group_map = student_group_map or {}

    def evaluate(self, schedule: Schedule) -> Tuple[float, Dict[str, float]]:
        raw_total, raw_details, _, _, _ = self.evaluate_metrics(schedule)
        return raw_total, raw_details

    def evaluate_detailed(
        self, schedule: Schedule
    ) -> Tuple[float, Dict[str, float], List[Dict[str, Any]]]:
        """Backward-compatible raw-detail view used by existing reports/tests."""

        raw_total, raw_details, _, items, _ = self.evaluate_metrics(schedule)
        return raw_total, raw_details, items

    def calculate_weighted_penalty(self, normalized_details: Mapping[str, float]) -> float:
        """Apply stakeholder weights to normalized metrics."""

        return sum(
            float(value) * self.config.get_weight(key)
            for key, value in normalized_details.items()
            if self.config.is_enabled(key)
        )

    def evaluate_metrics(
        self, schedule: Schedule
    ) -> Tuple[
        float,
        Dict[str, float],
        Dict[str, NormalizedSoftMetric],
        List[Dict[str, Any]],
        Dict[str, float],
    ]:
        """Return raw values, normalized metrics, instances, and denominators."""

        raw: Dict[str, float] = {key: 0.0 for key in SOFT_CONSTRAINT_KEYS}
        denominators: Dict[str, float] = {key: 0.0 for key in SOFT_CONSTRAINT_KEYS}
        items: List[Dict[str, Any]] = []

        if not isinstance(schedule, Schedule) or not isinstance(
            getattr(schedule, "genes", None), list
        ):
            metrics = self._build_metrics(raw, denominators)
            return 0.0, raw, metrics, items, denominators

        group_days: Dict[str, Set[str]] = defaultdict(set)
        lecturer_day_blocks: Dict[
            str, Dict[str, List[Tuple[int, int, str, Optional[str]]]]
        ] = defaultdict(lambda: defaultdict(list))
        valid_genes = []

        for gene in schedule.genes:
            section_id = getattr(gene, "section_id", None)
            timeslot_id = getattr(gene, "timeslot_id", None)
            room_id = getattr(gene, "room_id", None)
            if section_id not in self.section_map or timeslot_id not in self.timeslot_map:
                continue
            section = self.section_map[section_id]
            timeslot = self.timeslot_map[timeslot_id]
            room = self.room_map.get(room_id)
            duration = getattr(section, "duration_periods", 1)
            occupied = get_occupied_periods(timeslot.period, duration)
            valid_genes.append((gene, section, timeslot, room, duration, occupied, room_id))

            if section.group_id:
                group_days[section.group_id].add(timeslot.day)
            if section.lecturer_id:
                lecturer_day_blocks[section.lecturer_id][timeslot.day].append(
                    (
                        timeslot.period,
                        timeslot.period + duration - 1,
                        section_id,
                        getattr(room, "campus_id", None) if room else None,
                    )
                )

        available_days = {timeslot.day for timeslot in self.timeslot_map.values()}

        # S1: excess active group-days above the compact optimum (one day per
        # scheduled group), normalized by the maximum possible excess.
        s1_key = "compact_student_schedule"
        if self.config.is_enabled(s1_key) and available_days and group_days:
            scheduled_group_count = len(group_days)
            available_day_count = len(available_days)
            denominators[s1_key] = float(
                scheduled_group_count * (available_day_count - 1)
            )
            for group_id, active_days in group_days.items():
                active_count = len(active_days)
                excess_count = max(0, active_count - 1)
                raw[s1_key] += excess_count
                if excess_count == 0:
                    continue
                items.append(self._item(
                    s1_key,
                    raw_count=float(excess_count),
                    section_ids="-",
                    student_group_ids=group_id,
                    day=",".join(sorted(active_days)),
                    periods=f"active_days={active_count}/{available_day_count}",
                    description=(
                        f"Nhóm '{group_id}' học {active_count}/{len(available_days)} "
                        "ngày có thể xếp lịch"
                    ),
                ))

        # S2: fraction of scheduled occupied periods placed in the evening.
        s2_key = "late_day_periods"
        if self.config.is_enabled(s2_key):
            denominators[s2_key] = float(sum(row[4] for row in valid_genes))
            for _, section, timeslot, _, duration, _, room_id in valid_genes:
                if timeslot.session != "evening":
                    continue
                raw[s2_key] += duration
                items.append(self._item(
                    s2_key,
                    raw_count=float(duration),
                    section=section,
                    room_id=room_id,
                    day=timeslot.day,
                    periods=self._period_label(timeslot.period, duration),
                    description=(
                        f"Section '{section.section_id}' có {duration} tiết ca tối "
                        f"({timeslot.day})"
                    ),
                ))

        # S3: mismatch rate among assignments declaring a preferred shift.
        s3_key = "preferred_shift_mismatch"
        if self.config.is_enabled(s3_key):
            eligible = [row for row in valid_genes if row[1].preferred_shift is not None]
            denominators[s3_key] = float(len(eligible))
            for _, section, timeslot, _, duration, _, room_id in eligible:
                if timeslot.session == section.preferred_shift:
                    continue
                raw[s3_key] += 1.0
                items.append(self._item(
                    s3_key,
                    raw_count=1.0,
                    section=section,
                    room_id=room_id,
                    day=timeslot.day,
                    periods=self._period_label(timeslot.period, duration),
                    description=(
                        f"Section '{section.section_id}' muốn ca "
                        f"'{section.preferred_shift}' nhưng được xếp '{timeslot.session}'"
                    ),
                ))

        # S4: mean room-waste ratio. Capacity failures are hard-only.
        s4_key = "room_seat_waste"
        if self.config.is_enabled(s4_key):
            eligible_count = 0
            for _, section, timeslot, room, duration, _, room_id in valid_genes:
                if room is None or room.capacity < section.student_count or room.capacity <= 0:
                    continue
                eligible_count += 1
                waste_ratio = (room.capacity - section.student_count) / room.capacity
                raw[s4_key] += waste_ratio
                if waste_ratio <= 0:
                    continue
                items.append(self._item(
                    s4_key,
                    raw_count=float(waste_ratio),
                    section=section,
                    room_id=room_id,
                    day=timeslot.day,
                    periods=self._period_label(timeslot.period, duration),
                    description=(
                        f"Phòng '{room_id}' ({room.capacity} chỗ) cho "
                        f"{section.student_count} SV: waste_ratio={waste_ratio:.4f}"
                    ),
                ))
            denominators[s4_key] = float(eligible_count)

        # S5: mismatched immediately-consecutive campus transitions divided by
        # all adjacent lecturer transitions with known campuses.
        s5_key = "consecutive_cross_campus"
        if self.config.is_enabled(s5_key):
            for lecturer_id, day_map in lecturer_day_blocks.items():
                for day, blocks in day_map.items():
                    ordered = sorted(blocks, key=lambda row: (row[0], row[1], row[2]))
                    for previous, current in zip(ordered, ordered[1:]):
                        if previous[3] is None or current[3] is None:
                            continue
                        denominators[s5_key] += 1.0
                        if current[0] != previous[1] + 1 or current[3] == previous[3]:
                            continue
                        raw[s5_key] += 1.0
                        items.append(self._item(
                            s5_key,
                            raw_count=1.0,
                            section_ids=f"{previous[2]},{current[2]}",
                            lecturer_id=lecturer_id,
                            day=day,
                            periods=(
                                f"Tiết {previous[0]}-{previous[1]} ({previous[3]}) → "
                                f"Tiết {current[0]}-{current[1]} ({current[3]})"
                            ),
                            severity="MEDIUM",
                            description=(
                                f"GV '{lecturer_id}' chuyển cơ sở liên tiếp từ "
                                f"{previous[3]} sang {current[3]} ({day})"
                            ),
                        ))

        # S6: section preferred-campus mismatch rate.
        s6_key = "preferred_campus_mismatch"
        if self.config.is_enabled(s6_key):
            eligible = [row for row in valid_genes if row[1].preferred_campus_id is not None]
            denominators[s6_key] = float(len(eligible))
            for _, section, timeslot, room, duration, _, room_id in eligible:
                assigned_campus = getattr(room, "campus_id", None) if room else None
                if assigned_campus == section.preferred_campus_id:
                    continue
                raw[s6_key] += 1.0
                items.append(self._item(
                    s6_key,
                    raw_count=1.0,
                    section=section,
                    room_id=room_id,
                    day=timeslot.day,
                    periods=self._period_label(timeslot.period, duration),
                    description=(
                        f"Section '{section.section_id}' muốn cơ sở "
                        f"'{section.preferred_campus_id}' nhưng được xếp '{assigned_campus}'"
                    ),
                ))

        # S7: one contribution per assignment because the current domain has
        # exactly one student group per CourseSection.
        s7_key = "student_home_campus_mismatch"
        if self.config.is_enabled(s7_key):
            eligible_rows = []
            for row in valid_genes:
                group = self.student_group_map.get(row[1].group_id)
                if group is not None and group.home_campus_id is not None:
                    eligible_rows.append((row, group))
            denominators[s7_key] = float(len(eligible_rows))
            for row, group in eligible_rows:
                _, section, timeslot, room, duration, _, room_id = row
                assigned_campus = getattr(room, "campus_id", None) if room else None
                if assigned_campus == group.home_campus_id:
                    continue
                raw[s7_key] += 1.0
                items.append(self._item(
                    s7_key,
                    raw_count=1.0,
                    section=section,
                    room_id=room_id,
                    day=timeslot.day,
                    periods=self._period_label(timeslot.period, duration),
                    description=(
                        f"Nhóm '{group.id}' có cơ sở chính '{group.home_campus_id}' "
                        f"nhưng section '{section.section_id}' được xếp '{assigned_campus}'"
                    ),
                ))

        metrics = self._build_metrics(raw, denominators)
        for item in items:
            metric = metrics[item["constraint_key"]]
            item["denominator"] = metric.denominator
            item["normalized_contribution"] = (
                item["raw_count"] / metric.denominator
                if metric.denominator > 0 else 0.0
            )
            item["normalized_penalty"] = metric.normalized
            item["weighted_penalty"] = (
                item["normalized_contribution"] * metric.weight
                if metric.enabled else 0.0
            )

        return sum(raw.values()), raw, metrics, items, denominators

    def _build_metrics(
        self, raw: Mapping[str, float], denominators: Mapping[str, float]
    ) -> Dict[str, NormalizedSoftMetric]:
        metrics: Dict[str, NormalizedSoftMetric] = {}
        for key in SOFT_CONSTRAINT_KEYS:
            normalized = _normalized(raw.get(key, 0.0), denominators.get(key, 0.0))
            enabled = self.config.is_enabled(key)
            weight = self.config.get_weight(key)
            metrics[key] = NormalizedSoftMetric(
                raw=float(raw.get(key, 0.0)),
                denominator=float(denominators.get(key, 0.0)),
                normalized=normalized,
                weight=weight,
                weighted=(normalized * weight) if enabled else 0.0,
                enabled=enabled,
            )
        return metrics

    def _item(
        self,
        key: str,
        *,
        raw_count: float,
        section: Optional[CourseSection] = None,
        section_ids: Optional[str] = None,
        lecturer_id: Optional[str] = None,
        student_group_ids: Optional[str] = None,
        room_id: Optional[str] = None,
        day: str = "-",
        periods: str = "-",
        severity: str = "LOW",
        description: str,
    ) -> Dict[str, Any]:
        return {
            "violation_type": "SOFT",
            "severity": severity,
            "constraint_id": self.config.get_constraint_id(key),
            "constraint_name": self.config.get_name(key),
            "constraint_key": key,
            "section_ids": section_ids or (
                getattr(section, "activity_id", section.section_id)
                if section else "-"
            ),
            "lecturer_id": lecturer_id or (
                getattr(section, "lecturer_id", None) if section else None
            ) or "-",
            "student_group_ids": student_group_ids or (
                getattr(section, "group_id", None) if section else None
            ) or "-",
            "room_id": room_id or "-",
            "day": day,
            "periods": periods,
            "raw_count": raw_count,
            "weight": self.config.get_weight(key),
            "weighted_penalty": 0.0,
            "description": description,
        }

    @staticmethod
    def _period_label(start_period: int, duration: int) -> str:
        if duration == 1:
            return f"Tiết {start_period}"
        return f"Tiết {start_period}-{start_period + duration - 1}"
