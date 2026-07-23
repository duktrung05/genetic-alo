import copy
import random
from dataclasses import dataclass, field
from typing import Dict, List, Set, Tuple
from domain import Schedule, CourseSection, Room, Timeslot, Lecturer
from .hard_constraints import HardConstraintChecker

@dataclass
class RepairResult:
    schedule: Schedule
    success: bool
    remaining_hard_violations: int
    failed_section_ids: List[str] = field(default_factory=list)

class ScheduleRepairEngine:
    """Module độc lập chịu trách nhiệm Sua chữa các vi phạm cứng (Constraint Satisfaction Repair)."""

    def __init__(self, dataset: dict):
        self.dataset = dataset
        self.section_map: Dict[str, CourseSection] = {c.section_id: c for c in dataset["course_sections"]}
        self.room_map: Dict[str, Room] = {r.id: r for r in dataset["rooms"]}
        self.timeslot_map: Dict[int, Timeslot] = {t.id: t for t in dataset["timeslots"]}
        self.lecturer_map: Dict[str, Lecturer] = {l.id: l for l in dataset.get("lecturers", [])}
        self.rooms: List[Room] = dataset["rooms"]
        self.timeslots: List[Timeslot] = dataset["timeslots"]

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

    def repair(self, schedule: Schedule) -> RepairResult:
        repaired = copy.deepcopy(schedule)
        failed_sections: Set[str] = set()

        if not isinstance(repaired, Schedule) or not isinstance(getattr(repaired, "genes", None), list):
            return RepairResult(
                schedule=repaired,
                success=False,
                remaining_hard_violations=len(self.section_map),
                failed_section_ids=sorted(list(self.section_map.keys()))
            )

        # 1. Sua vi phạm sức chứa phòng & loại phòng (Room Type)
        for gene in repaired.genes:
            if gene.section_id not in self.section_map:
                failed_sections.add(str(gene.section_id))
                continue

            section = self.section_map[gene.section_id]
            req_type = getattr(section, "required_room_type", "NORMAL")

            room_ok = False
            if gene.room_id in self.room_map:
                room = self.room_map[gene.room_id]
                if room.capacity >= section.student_count and getattr(room, "room_type", "NORMAL") == req_type:
                    room_ok = True

            if not room_ok:
                valid_rooms = [
                    r for r in self.rooms
                    if r.capacity >= section.student_count and getattr(r, "room_type", "NORMAL") == req_type
                ]
                if valid_rooms:
                    gene.room_id = random.choice(valid_rooms).id
                else:
                    failed_sections.add(gene.section_id)

        # 2. Sua vi phạm trùng khung giờ, giảng viên bận (Availability), trùng phòng/lớp
        used_lecturer_time = set()
        used_room_time = set()
        used_group_time = set()

        for gene in repaired.genes:
            if gene.section_id not in self.section_map:
                failed_sections.add(str(gene.section_id))
                continue

            section = self.section_map[gene.section_id]
            req_type = getattr(section, "required_room_type", "NORMAL")
            lec = self.lecturer_map.get(section.lecturer_id)
            avail_ts = getattr(lec, "available_timeslot_ids", None) if lec else None

            lec_key = (section.lecturer_id, gene.timeslot_id)
            room_key = (gene.room_id, gene.timeslot_id)
            grp_key = (section.group_id, gene.timeslot_id)

            current_room = self.room_map.get(gene.room_id)
            room_valid = (
                current_room is not None and
                current_room.capacity >= section.student_count and
                getattr(current_room, "room_type", "NORMAL") == req_type
            )
            avail_valid = (avail_ts is None or gene.timeslot_id in avail_ts)

            has_conflict = (
                lec_key in used_lecturer_time or
                room_key in used_room_time or
                grp_key in used_group_time or
                not room_valid or
                not avail_valid
            )

            if has_conflict:
                shuffled_ts = list(self.timeslots)
                random.shuffle(shuffled_ts)
                repaired_slot = False

                for candidate_ts in shuffled_ts:
                    if avail_ts is not None and candidate_ts.id not in avail_ts:
                        continue

                    cand_lec_key = (section.lecturer_id, candidate_ts.id)
                    cand_grp_key = (section.group_id, candidate_ts.id)

                    if cand_lec_key not in used_lecturer_time and cand_grp_key not in used_group_time:
                        valid_r = [
                            r for r in self.rooms
                            if r.capacity >= section.student_count and
                               getattr(r, "room_type", "NORMAL") == req_type and
                               (r.id, candidate_ts.id) not in used_room_time
                        ]
                        if valid_r:
                            chosen_room = random.choice(valid_r)
                            gene.timeslot_id = candidate_ts.id
                            gene.room_id = chosen_room.id
                            repaired_slot = True
                            break

                if not repaired_slot:
                    failed_sections.add(gene.section_id)

                lec_key = (section.lecturer_id, gene.timeslot_id)
                room_key = (gene.room_id, gene.timeslot_id)
                grp_key = (section.group_id, gene.timeslot_id)

            used_lecturer_time.add(lec_key)
            used_room_time.add(room_key)
            used_group_time.add(grp_key)

        remaining_hard, _ = self.hard_checker.evaluate(repaired)
        failed_list = sorted(list(failed_sections))
        success = (remaining_hard == 0 and len(failed_list) == 0)

        return RepairResult(
            schedule=repaired,
            success=success,
            remaining_hard_violations=remaining_hard,
            failed_section_ids=failed_list
        )
