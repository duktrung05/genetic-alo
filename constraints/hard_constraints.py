from typing import Dict, Tuple, Set, Optional
from collections import defaultdict
from domain import Schedule, CourseSection, Room, Timeslot, Lecturer
from dataset import get_occupied_periods

class HardConstraintChecker:
    def __init__(
        self,
        section_map: Dict[str, CourseSection],
        room_map: Dict[str, Room],
        timeslot_map: Dict[int, Timeslot],
        lecturer_ids: Optional[Set[str]] = None,
        group_ids: Optional[Set[str]] = None,
        lecturer_map: Optional[Dict[str, Lecturer]] = None
    ):
        self.section_map = section_map
        self.room_map = room_map
        self.timeslot_map = timeslot_map
        self.lecturer_ids = lecturer_ids
        self.group_ids = group_ids
        self.lecturer_map = lecturer_map
        self.day_period_to_ts_id: Dict[Tuple[str, int], int] = {
            (ts.day, ts.period): ts.id for ts in timeslot_map.values()
        }

    def evaluate(self, schedule: Schedule) -> Tuple[int, Dict[str, int]]:
        details = {
            "lecturer_overlap": 0,
            "room_overlap": 0,
            "group_overlap": 0,
            "capacity_violation": 0,
            "lecturer_unavailable": 0,
            "room_type_mismatch": 0,
            "missing_sections": 0,
            "duplicate_sections": 0,
            "invalid_section_ids": 0,
            "invalid_room_ids": 0,
            "invalid_timeslot_ids": 0,
            "invalid_lecturer_references": 0,
            "invalid_group_references": 0,
            "gene_count_mismatch": 0,
        }

        if not isinstance(schedule, Schedule) or not isinstance(getattr(schedule, "genes", None), list):
            details["gene_count_mismatch"] = 1
            details["missing_sections"] = len(self.section_map)
            return sum(details.values()), details

        genes = schedule.genes
        expected_sections = set(self.section_map.keys())

        if len(genes) != len(expected_sections):
            details["gene_count_mismatch"] = 1

        seen_section_counts: Dict[str, int] = defaultdict(int)
        lecturer_time = defaultdict(list)
        room_time = defaultdict(list)
        group_time = defaultdict(list)

        for gene in genes:
            sec_id = getattr(gene, "section_id", None)
            room_id = getattr(gene, "room_id", None)
            ts_id = getattr(gene, "timeslot_id", None)

            section = None
            if sec_id not in self.section_map:
                details["invalid_section_ids"] += 1
            else:
                section = self.section_map[sec_id]
                seen_section_counts[sec_id] += 1

            room = None
            if room_id not in self.room_map:
                details["invalid_room_ids"] += 1
            else:
                room = self.room_map[room_id]

            ts = None
            if ts_id not in self.timeslot_map:
                details["invalid_timeslot_ids"] += 1
            else:
                ts = self.timeslot_map[ts_id]

            if section is not None:
                if self.lecturer_ids is not None and section.lecturer_id not in self.lecturer_ids:
                    details["invalid_lecturer_references"] += 1
                if self.group_ids is not None and section.group_id not in self.group_ids:
                    details["invalid_group_references"] += 1

                if room is not None:
                    if room.capacity < section.student_count:
                        details["capacity_violation"] += 1
                    req_type = getattr(section, "required_room_type", "NORMAL")
                    rm_type = getattr(room, "room_type", "NORMAL")
                    if req_type != rm_type:
                        details["room_type_mismatch"] += 1

                if ts is not None:
                    duration = getattr(section, "duration_periods", 1)
                    occupied_p = get_occupied_periods(ts.period, duration)

                    for p in occupied_p:
                        target_ts_id = self.day_period_to_ts_id.get((ts.day, p))
                        if target_ts_id is None:
                            details["invalid_timeslot_ids"] += 1

                    if section.lecturer_id:
                        lec = self.lecturer_map.get(section.lecturer_id) if self.lecturer_map else None
                        if lec is not None and getattr(lec, "available_timeslot_ids", None) is not None:
                            for p in occupied_p:
                                target_ts_id = self.day_period_to_ts_id.get((ts.day, p))
                                if target_ts_id is None or target_ts_id not in lec.available_timeslot_ids:
                                    details["lecturer_unavailable"] += 1

                    if section.lecturer_id:
                        for p in occupied_p:
                            lecturer_time[(section.lecturer_id, ts.day, p)].append(sec_id)

                    if room_id in self.room_map:
                        for p in occupied_p:
                            room_time[(room_id, ts.day, p)].append(sec_id)

                    if section.group_id:
                        for p in occupied_p:
                            group_time[(section.group_id, ts.day, p)].append(sec_id)

        missing_count = len(expected_sections - set(seen_section_counts.keys()))
        details["missing_sections"] = missing_count

        dup_count = sum(cnt - 1 for cnt in seen_section_counts.values() if cnt > 1)
        details["duplicate_sections"] = dup_count

        for sections in lecturer_time.values():
            if len(sections) > 1:
                details["lecturer_overlap"] += (len(sections) - 1)

        for sections in room_time.values():
            if len(sections) > 1:
                details["room_overlap"] += (len(sections) - 1)

        for sections in group_time.values():
            if len(sections) > 1:
                details["group_overlap"] += (len(sections) - 1)

        total_hard = sum(details.values())
        return total_hard, details
