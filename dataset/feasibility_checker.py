"""Feasibility Checker Module.

Constructive / backtracking scheduler to verify that a dataset possesses at least
one valid reference schedule with 0 hard violations.
"""

from collections import defaultdict
from typing import Dict, List, Set, Tuple, Optional
from domain import Schedule, Gene, CourseSection, Room, Timeslot, Lecturer
from .timeslot_factory import get_occupied_periods, is_valid_period_block


class FeasibilityChecker:
    """Constructive Backtracking Solver to prove dataset feasibility."""

    def __init__(self, dataset: dict):
        self.dataset = dataset
        self.sections: List[CourseSection] = dataset["course_sections"]
        self.rooms: List[Room] = dataset["rooms"]
        self.timeslots: List[Timeslot] = dataset["timeslots"]
        self.lecturers: List[Lecturer] = dataset.get("lecturers", [])
        self.lecturer_map: Dict[str, Lecturer] = {l.id: l for l in self.lecturers}

        self.day_period_to_ts_id: Dict[Tuple[str, int], int] = {
            (ts.day, ts.period): ts.id for ts in self.timeslots
        }
        self.day_available_periods: Dict[str, Set[int]] = defaultdict(set)
        for ts in self.timeslots:
            self.day_available_periods[ts.day].add(ts.period)

    def _get_priority_key(self, sec: CourseSection) -> Tuple[int, int, int, int]:
        is_lab = 0 if getattr(sec, "required_room_type", "NORMAL") == "LAB" else 1
        dur = -getattr(sec, "duration_periods", 1)
        lec = self.lecturer_map.get(sec.lecturer_id)
        is_restricted = 0 if (lec and getattr(lec, "available_timeslot_ids", None) is not None) else 1
        st_count = -sec.student_count
        return (is_lab, dur, is_restricted, st_count)

    def find_feasible_schedule(self) -> Optional[Schedule]:
        """Find a schedule with 0 hard violations on dataset, or None if impossible."""
        sorted_sections = sorted(self.sections, key=self._get_priority_key)

        # Pre-compute candidate (ts, room) options per section
        sec_candidates: Dict[str, List[Tuple[Timeslot, Room]]] = {}
        for sec in sorted_sections:
            duration = getattr(sec, "duration_periods", 1)
            req_type = getattr(sec, "required_room_type", "NORMAL")
            lec = self.lecturer_map.get(sec.lecturer_id)
            avail_ts = getattr(lec, "available_timeslot_ids", None) if lec else None

            valid_rooms = [
                r for r in self.rooms
                if getattr(r, "room_type", "NORMAL") == req_type and r.capacity >= sec.student_count
            ]

            candidates = []
            for ts in self.timeslots:
                if not is_valid_period_block(ts.period, duration, self.day_available_periods.get(ts.day)):
                    continue
                occupied = get_occupied_periods(ts.period, duration)
                if avail_ts is not None:
                    if not all(self.day_period_to_ts_id.get((ts.day, p)) in avail_ts for p in occupied):
                        continue
                for r in valid_rooms:
                    candidates.append((ts, r))

            if not candidates:
                return None
            sec_candidates[sec.section_id] = candidates

        used_lec_time: Set[Tuple[str, str, int]] = set()
        used_grp_time: Set[Tuple[str, str, int]] = set()
        used_rm_time: Set[Tuple[str, str, int]] = set()
        assigned_genes: List[Gene] = []

        def backtrack(index: int) -> bool:
            if index == len(sorted_sections):
                return True

            sec = sorted_sections[index]
            duration = getattr(sec, "duration_periods", 1)
            candidates = sec_candidates[sec.section_id]

            for ts, rm in candidates:
                occupied = get_occupied_periods(ts.period, duration)
                day = ts.day

                # Check overlaps
                lec_conflict = False
                if sec.lecturer_id:
                    for p in occupied:
                        if (sec.lecturer_id, day, p) in used_lec_time:
                            lec_conflict = True
                            break
                if lec_conflict:
                    continue

                grp_conflict = False
                if sec.group_id:
                    for p in occupied:
                        if (sec.group_id, day, p) in used_grp_time:
                            grp_conflict = True
                            break
                if grp_conflict:
                    continue

                rm_conflict = False
                for p in occupied:
                    if (rm.id, day, p) in used_rm_time:
                        rm_conflict = True
                        break
                if rm_conflict:
                    continue

                # Make assignment
                if sec.lecturer_id:
                    for p in occupied:
                        used_lec_time.add((sec.lecturer_id, day, p))
                if sec.group_id:
                    for p in occupied:
                        used_grp_time.add((sec.group_id, day, p))
                for p in occupied:
                    used_rm_time.add((rm.id, day, p))

                assigned_genes.append(Gene(sec.section_id, rm.id, ts.id))

                if backtrack(index + 1):
                    return True

                # Undo assignment
                assigned_genes.pop()
                if sec.lecturer_id:
                    for p in occupied:
                        used_lec_time.remove((sec.lecturer_id, day, p))
                if sec.group_id:
                    for p in occupied:
                        used_grp_time.remove((sec.group_id, day, p))
                for p in occupied:
                    used_rm_time.remove((rm.id, day, p))

            return False

        if backtrack(0):
            # Maintain original section ordering
            sec_order = {s.section_id: i for i, s in enumerate(self.sections)}
            assigned_genes.sort(key=lambda g: sec_order[g.section_id])
            return Schedule(genes=assigned_genes)

        return None


def find_feasible_schedule(dataset: dict) -> Optional[Schedule]:
    checker = FeasibilityChecker(dataset)
    return checker.find_feasible_schedule()
