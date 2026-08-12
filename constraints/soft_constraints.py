from __future__ import annotations
import math
from dataclasses import dataclass
from types import MappingProxyType
from typing import Dict, List, Mapping, Optional, Tuple, Any
from collections import defaultdict

from domain import Schedule, CourseSection, Room, Timeslot, ConstraintDefinition
from dataset import get_occupied_periods

# ---------------------------------------------------------------------------
# Canonical key mapping
# ---------------------------------------------------------------------------

SOFT_CONSTRAINT_KEY_BY_ID: Dict[str, str] = {
    "S1": "weekly_distribution",
    "S2": "late_day_periods",
    "S3": "preferred_shift_mismatch",
    "S4": "room_seat_waste",
    "S5": "consecutive_cross_campus",
}

# Reverse map: key → ID
_KEY_TO_ID: Dict[str, str] = {v: k for k, v in SOFT_CONSTRAINT_KEY_BY_ID.items()}

# Ordered list of canonical keys (S1 → S5)
SOFT_CONSTRAINT_KEYS: List[str] = [
    "weekly_distribution",
    "late_day_periods",
    "preferred_shift_mismatch",
    "room_seat_waste",
    "consecutive_cross_campus",
]

# Default weights used when no Excel constraint definitions are available (mock datasets)
_DEFAULT_WEIGHTS: Dict[str, int] = {
    "weekly_distribution": 10,
    "late_day_periods": 5,
    "preferred_shift_mismatch": 4,
    "room_seat_waste": 2,
    "consecutive_cross_campus": 8,
}

# Vietnamese names used in default config (matches Excel names for S1–S5)
_DEFAULT_NAMES: Dict[str, str] = {
    "weekly_distribution":      "Phân bố môn học của mỗi nhóm đều trong tuần",
    "late_day_periods":         "Hạn chế quá nhiều tiết cuối ngày",
    "preferred_shift_mismatch": "Ưu tiên ca học mong muốn của lớp học phần",
    "room_seat_waste":          "Giảm số ghế trống trong phòng",
    "consecutive_cross_campus": "Hạn chế giảng viên di chuyển liên tiếp giữa hai cơ sở",
}


# ---------------------------------------------------------------------------
# SoftConstraintDefinition & SoftConstraintConfig
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class SoftConstraintDefinition:
    """Per-constraint metadata: id, key, name, weight, enabled."""
    constraint_id: str   # "S1", "S2", ...
    key: str             # "weekly_distribution", ...
    name: str            # Vietnamese display name
    weight: int          # penalty per raw violation
    enabled: bool        # if False, constraint contributes 0 penalty


class SoftConstraintConfig:
    def __init__(self, definitions: Mapping[str, SoftConstraintDefinition]) -> None:
        self._defs: MappingProxyType[str, SoftConstraintDefinition] = MappingProxyType(
            dict(definitions)
        )

    @property
    def definitions(self) -> MappingProxyType[str, SoftConstraintDefinition]:
        return self._defs

    def get_weight(self, key: str) -> int:
        defn = self._defs.get(key)
        return defn.weight if defn else 0

    def is_enabled(self, key: str) -> bool:
        defn = self._defs.get(key)
        return defn.enabled if defn else False

    def get_name(self, key: str) -> str:
        defn = self._defs.get(key)
        return defn.name if defn else key

    def get_constraint_id(self, key: str) -> str:
        defn = self._defs.get(key)
        return defn.constraint_id if defn else _KEY_TO_ID.get(key, "")

    @classmethod
    def from_constraint_definitions(
        cls,
        constraint_defs: List[ConstraintDefinition],
    ) -> "SoftConstraintConfig":
        """Build SoftConstraintConfig from a list of ConstraintDefinition objects.

        Only rows with constraint_type == "SOFT" are used.
        Weight and enabled are taken directly from the Excel data.
        """
        defs: Dict[str, SoftConstraintDefinition] = {}
        for cd in constraint_defs:
            if cd.constraint_type != "SOFT":
                continue
            key = SOFT_CONSTRAINT_KEY_BY_ID.get(cd.constraint_id)
            if key is None:
                # Should have been caught by the loader validator
                continue
            defs[key] = SoftConstraintDefinition(
                constraint_id=cd.constraint_id,
                key=key,
                name=cd.constraint_name,
                weight=cd.weight,
                enabled=cd.enabled,
            )
        # Fill in any missing keys with disabled=True / weight=0 as safety net
        for key in SOFT_CONSTRAINT_KEYS:
            if key not in defs:
                c_id = _KEY_TO_ID.get(key, "")
                defs[key] = SoftConstraintDefinition(
                    constraint_id=c_id,
                    key=key,
                    name=_DEFAULT_NAMES.get(key, key),
                    weight=0,
                    enabled=False,
                )
        return cls(defs)

    @classmethod
    def default(cls) -> "SoftConstraintConfig":
        """Create default SoftConstraintConfig for mock datasets (no Excel).

        Uses weights: S1=10, S2=5, S3=4, S4=2, S5=8  (all enabled).
        This is the ONLY place default weights are defined.
        """
        defs: Dict[str, SoftConstraintDefinition] = {}
        for key in SOFT_CONSTRAINT_KEYS:
            c_id = _KEY_TO_ID.get(key, "")
            defs[key] = SoftConstraintDefinition(
                constraint_id=c_id,
                key=key,
                name=_DEFAULT_NAMES.get(key, key),
                weight=_DEFAULT_WEIGHTS[key],
                enabled=True,
            )
        return cls(defs)

    # Legacy-compatibility: expose validate() as no-op so existing callers
    # that call soft_config.validate() don't break during transition.
    def validate(self) -> None:
        pass


# ---------------------------------------------------------------------------
# SoftConstraintChecker
# ---------------------------------------------------------------------------

class SoftConstraintChecker:
    def __init__(
        self,
        section_map: Dict[str, CourseSection],
        room_map: Dict[str, Room],
        timeslot_map: Dict[int, Timeslot],
        config: Optional[SoftConstraintConfig] = None,
    ) -> None:
        self.section_map = section_map
        self.room_map = room_map
        self.timeslot_map = timeslot_map
        self.config = config if config is not None else SoftConstraintConfig.default()

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    def evaluate(
        self, schedule: Schedule
    ) -> Tuple[int, Dict[str, int]]:
        raw_count, details, _ = self.evaluate_detailed(schedule)
        return raw_count, details

    def calculate_weighted_penalty(self, details: Dict[str, int]) -> int:
        penalty = 0
        for key, count in details.items():
            if self.config.is_enabled(key):
                penalty += count * self.config.get_weight(key)
        return penalty

    def evaluate_detailed(
        self, schedule: Schedule
    ) -> Tuple[int, Dict[str, int], List[Dict[str, Any]]]:
        """Evaluate all 5 soft constraints and return (raw_count, details, items).

        details keys (always present, even if constraint disabled):
            weekly_distribution, late_day_periods, preferred_shift_mismatch,
            room_seat_waste, consecutive_cross_campus

        Each item contains at minimum:
            violation_type, severity, constraint_id, constraint_name,
            constraint_key, section_ids, lecturer_id, student_group_ids,
            room_id, day, periods, raw_count, weight, weighted_penalty, description
        """
        details: Dict[str, int] = {k: 0 for k in SOFT_CONSTRAINT_KEYS}
        items: List[Dict[str, Any]] = []

        if not isinstance(schedule, Schedule) or not isinstance(
            getattr(schedule, "genes", None), list
        ):
            return 0, details, items

        # Pre-process: build per-gene info
        # Maps used by multiple constraints
        # group_id → day → list of occupied periods
        group_day_periods: Dict[str, Dict[str, List[int]]] = defaultdict(
            lambda: defaultdict(list)
        )
        # lecturer_id → day → list of (start_period, end_period, section_id, campus_id)
        lecturer_day_blocks: Dict[str, Dict[str, List[Tuple[int, int, str, Optional[str]]]]] = defaultdict(
            lambda: defaultdict(list)
        )

        valid_genes = []
        for gene in schedule.genes:
            sec_id = getattr(gene, "section_id", None)
            ts_id = getattr(gene, "timeslot_id", None)
            rm_id = getattr(gene, "room_id", None)
            if sec_id not in self.section_map or ts_id not in self.timeslot_map:
                continue
            section = self.section_map[sec_id]
            ts = self.timeslot_map[ts_id]
            room = self.room_map.get(rm_id)
            duration = getattr(section, "duration_periods", 1)
            occupied = get_occupied_periods(ts.period, duration)
            valid_genes.append((gene, section, ts, room, duration, occupied, rm_id))

            # Build group day periods
            if section.group_id:
                group_day_periods[section.group_id][ts.day].extend(occupied)

            # Build lecturer day blocks
            if section.lecturer_id:
                campus_id = getattr(room, "campus_id", None) if room else None
                start_p = ts.period
                end_p = ts.period + duration - 1
                lecturer_day_blocks[section.lecturer_id][ts.day].append(
                    (start_p, end_p, sec_id, campus_id)
                )

        # ----------------------------------------------------------------
        # S1: weekly_distribution
        # ----------------------------------------------------------------
        if self.config.is_enabled("weekly_distribution"):
            w = self.config.get_weight("weekly_distribution")
            c_id = self.config.get_constraint_id("weekly_distribution")
            c_name = self.config.get_name("weekly_distribution")

            # Collect all teaching days across all timeslots
            all_days: List[str] = sorted({
                ts.day for ts in self.timeslot_map.values()
            })
            num_days = len(all_days) if all_days else 1

            for grp_id, day_map in group_day_periods.items():
                total_periods = sum(len(ps) for ps in day_map.values())
                if total_periods == 0:
                    continue
                target = math.ceil(total_periods / num_days)
                excess = sum(
                    max(0, len(day_map.get(d, [])) - target)
                    for d in all_days
                )
                if excess > 0:
                    details["weekly_distribution"] += excess
                    items.append({
                        "violation_type": "SOFT",
                        "severity": "LOW",
                        "constraint_id": c_id,
                        "constraint_name": c_name,
                        "constraint_key": "weekly_distribution",
                        "section_ids": "-",
                        "lecturer_id": "-",
                        "student_group_ids": grp_id,
                        "room_id": "-",
                        "day": "-",
                        "periods": f"target={target}/day, total={total_periods}",
                        "raw_count": excess,
                        "weight": w,
                        "weighted_penalty": excess * w,
                        "description": (
                            f"Nhóm '{grp_id}' phân bố không đều: "
                            f"tổng {total_periods} tiết, target {target}/ngày, "
                            f"excess {excess} tiết"
                        ),
                    })

        # ----------------------------------------------------------------
        # S2: late_day_periods
        # ----------------------------------------------------------------
        if self.config.is_enabled("late_day_periods"):
            w = self.config.get_weight("late_day_periods")
            c_id = self.config.get_constraint_id("late_day_periods")
            c_name = self.config.get_name("late_day_periods")

            for gene, section, ts, room, duration, occupied, rm_id in valid_genes:
                if ts.session == "evening":
                    raw = duration  # all occupied periods are evening (same-session rule)
                    details["late_day_periods"] += raw
                    items.append({
                        "violation_type": "SOFT",
                        "severity": "LOW",
                        "constraint_id": c_id,
                        "constraint_name": c_name,
                        "constraint_key": "late_day_periods",
                        "section_ids": section.section_id,
                        "lecturer_id": getattr(section, "lecturer_id", "-") or "-",
                        "student_group_ids": getattr(section, "group_id", "-") or "-",
                        "room_id": rm_id or "-",
                        "day": ts.day,
                        "periods": (
                            f"Tiết {ts.period}"
                            if duration == 1
                            else f"Tiết {ts.period}-{ts.period + duration - 1}"
                        ),
                        "raw_count": raw,
                        "weight": w,
                        "weighted_penalty": raw * w,
                        "description": (
                            f"Section '{section.section_id}' xếp vào ca tối "
                            f"({ts.day}, Tiết {ts.period}-{ts.period + duration - 1}, "
                            f"{raw} tiết ca tối)"
                        ),
                    })

        # ----------------------------------------------------------------
        # S3: preferred_shift_mismatch
        # ----------------------------------------------------------------
        if self.config.is_enabled("preferred_shift_mismatch"):
            w = self.config.get_weight("preferred_shift_mismatch")
            c_id = self.config.get_constraint_id("preferred_shift_mismatch")
            c_name = self.config.get_name("preferred_shift_mismatch")

            for gene, section, ts, room, duration, occupied, rm_id in valid_genes:
                pref = getattr(section, "preferred_shift", None)
                if pref is None:
                    continue
                assigned = ts.session
                if assigned != pref:
                    details["preferred_shift_mismatch"] += 1
                    items.append({
                        "violation_type": "SOFT",
                        "severity": "LOW",
                        "constraint_id": c_id,
                        "constraint_name": c_name,
                        "constraint_key": "preferred_shift_mismatch",
                        "section_ids": section.section_id,
                        "lecturer_id": getattr(section, "lecturer_id", "-") or "-",
                        "student_group_ids": getattr(section, "group_id", "-") or "-",
                        "room_id": rm_id or "-",
                        "day": ts.day,
                        "periods": (
                            f"Tiết {ts.period}"
                            if duration == 1
                            else f"Tiết {ts.period}-{ts.period + duration - 1}"
                        ),
                        "raw_count": 1,
                        "weight": w,
                        "weighted_penalty": w,
                        "description": (
                            f"Section '{section.section_id}' muốn ca '{pref}' "
                            f"nhưng được xếp ca '{assigned}' ({ts.day})"
                        ),
                    })

        # ----------------------------------------------------------------
        # S4: room_seat_waste
        # ----------------------------------------------------------------
        if self.config.is_enabled("room_seat_waste"):
            w = self.config.get_weight("room_seat_waste")
            c_id = self.config.get_constraint_id("room_seat_waste")
            c_name = self.config.get_name("room_seat_waste")

            for gene, section, ts, room, duration, occupied, rm_id in valid_genes:
                if room is None:
                    continue
                unused = max(0, room.capacity - section.student_count)
                if unused > 0:
                    details["room_seat_waste"] += unused
                    items.append({
                        "violation_type": "SOFT",
                        "severity": "LOW",
                        "constraint_id": c_id,
                        "constraint_name": c_name,
                        "constraint_key": "room_seat_waste",
                        "section_ids": section.section_id,
                        "lecturer_id": getattr(section, "lecturer_id", "-") or "-",
                        "student_group_ids": getattr(section, "group_id", "-") or "-",
                        "room_id": rm_id or "-",
                        "day": ts.day,
                        "periods": (
                            f"Tiết {ts.period}"
                            if duration == 1
                            else f"Tiết {ts.period}-{ts.period + duration - 1}"
                        ),
                        "raw_count": unused,
                        "weight": w,
                        "weighted_penalty": unused * w,
                        "description": (
                            f"Phòng '{rm_id}' ({room.capacity} chỗ) cho "
                            f"{section.student_count} SV: {unused} ghế trống"
                        ),
                    })

        # ----------------------------------------------------------------
        # S5: consecutive_cross_campus
        # ----------------------------------------------------------------
        if self.config.is_enabled("consecutive_cross_campus"):
            w = self.config.get_weight("consecutive_cross_campus")
            c_id = self.config.get_constraint_id("consecutive_cross_campus")
            c_name = self.config.get_name("consecutive_cross_campus")

            for lec_id, day_map in lecturer_day_blocks.items():
                for day, blocks in day_map.items():
                    # Sort by (start_period, end_period, section_id) for determinism
                    sorted_blocks = sorted(blocks, key=lambda b: (b[0], b[1], b[2]))
                    for i in range(1, len(sorted_blocks)):
                        prev = sorted_blocks[i - 1]
                        curr = sorted_blocks[i]
                        prev_end = prev[1]
                        curr_start = curr[0]
                        prev_campus = prev[3]
                        curr_campus = curr[3]

                        # Both must have campus_id; skip if either is None
                        if prev_campus is None or curr_campus is None:
                            continue

                        # Consecutive = curr starts immediately after prev ends
                        if curr_start == prev_end + 1 and curr_campus != prev_campus:
                            details["consecutive_cross_campus"] += 1
                            items.append({
                                "violation_type": "SOFT",
                                "severity": "MEDIUM",
                                "constraint_id": c_id,
                                "constraint_name": c_name,
                                "constraint_key": "consecutive_cross_campus",
                                "section_ids": f"{prev[2]},{curr[2]}",
                                "lecturer_id": lec_id,
                                "student_group_ids": "-",
                                "room_id": "-",
                                "day": day,
                                "periods": (
                                    f"Tiết {prev[0]}-{prev[1]} ({prev_campus}) "
                                    f"→ Tiết {curr[0]}-{curr[1]} ({curr_campus})"
                                ),
                                "raw_count": 1,
                                "weight": w,
                                "weighted_penalty": w,
                                "description": (
                                    f"GV '{lec_id}' phải chuyển từ {prev_campus} "
                                    f"(Tiết {prev[0]}-{prev[1]}) sang {curr_campus} "
                                    f"(Tiết {curr[0]}-{curr[1]}) liên tiếp ({day})"
                                ),
                            })

        total_raw = sum(details.values())
        return total_raw, details, items
