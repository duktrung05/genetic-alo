"""Schedule Repair Engine Module.

Independent Constraint Satisfaction Transformer responsible for repairing hard constraint
violations in candidate Schedule chromosomes using Priority-based Constraint Satisfaction.
"""

import time
import random
from dataclasses import dataclass, field
from typing import Dict, List, Set, Tuple, Optional, Any
from collections import defaultdict
from domain import Schedule, Gene, CourseSection, Room, Timeslot, Lecturer, RepairStatus
from dataset import get_occupied_periods, is_valid_period_block
from .hard_constraints import HardConstraintChecker


@dataclass
class RepairResult:
    """Encapsulates repair execution result, success flag, and remaining violations."""
    schedule: Schedule
    success: bool
    remaining_hard_violations: int
    failed_section_ids: List[str] = field(default_factory=list)
    status: RepairStatus = RepairStatus.UNCHANGED

@dataclass
class RepairStats:
    """Tracks execution statistics for ScheduleRepairEngine."""
    repair_enabled: bool = True
    repair_trigger_policy: str = "Offspring Mutation Constraint Satisfaction"
    repair_calls: int = 0
    repair_attempts: int = 0
    repair_improved: int = 0
    repair_unchanged: int = 0
    repair_failed: int = 0
    sections_repaired: int = 0
    sections_failed: int = 0
    candidate_checks: int = 0
    hard_before_repair: int = 0
    hard_after_repair: int = 0
    soft_before_repair: int = 0
    soft_after_repair: int = 0
    repair_runtime_seconds: float = 0.0

    @property
    def repair_successes(self) -> int:
        return self.repair_improved

    @property
    def repair_failures(self) -> int:
        return self.repair_unchanged + self.repair_failed

    def reset(self):
        self.repair_calls = 0
        self.repair_attempts = 0
        self.repair_improved = 0
        self.repair_unchanged = 0
        self.repair_failed = 0
        self.sections_repaired = 0
        self.sections_failed = 0
        self.candidate_checks = 0
        self.hard_before_repair = 0
        self.hard_after_repair = 0
        self.soft_before_repair = 0
        self.soft_after_repair = 0
        self.repair_runtime_seconds = 0.0


    def to_dict(self) -> dict:
        return {
            "repair_enabled": self.repair_enabled,
            "repair_trigger_policy": self.repair_trigger_policy,
            "repair_calls": self.repair_calls,
            "repair_attempts": self.repair_attempts,
            "repair_successes": self.repair_successes,
            "repair_failures": self.repair_failures,
            "repair_improved": self.repair_improved,
            "repair_unchanged": self.repair_unchanged,
            "repair_failed": self.repair_failed,
            "sections_repaired": self.sections_repaired,
            "sections_failed": self.sections_failed,
            "candidate_checks": self.candidate_checks,
            "hard_before_repair": self.hard_before_repair,
            "hard_after_repair": self.hard_after_repair,
            "soft_before_repair": self.soft_before_repair,
            "soft_after_repair": self.soft_after_repair,
            "repair_runtime_seconds": round(self.repair_runtime_seconds, 4),
        }


class ScheduleRepairEngine:
    """Constraint Satisfaction Repair Transformer for repairing hard violations."""

    def __init__(self, dataset: dict, evaluator: Optional[Any] = None):
        """Initialize Repair Engine with pre-cached room and timeslot lookup maps."""
        self.dataset = dataset
        if evaluator is not None:
            self.evaluator = evaluator
        else:
            from .evaluator import ConstraintEvaluator
            self.evaluator = ConstraintEvaluator(dataset)

        self.stats = RepairStats()

        self.section_map: Dict[str, CourseSection] = {c.section_id: c for c in dataset["course_sections"]}
        self.room_map: Dict[str, Room] = {r.id: r for r in dataset["rooms"]}
        self.timeslot_map: Dict[int, Timeslot] = {t.id: t for t in dataset["timeslots"]}
        self.lecturer_map: Dict[str, Lecturer] = {l.id: l for l in dataset.get("lecturers", [])}
        self.rooms: List[Room] = dataset["rooms"]
        self.timeslots: List[Timeslot] = dataset["timeslots"]

        lecturer_ids = set(self.lecturer_map.keys()) if "lecturers" in dataset else None
        group_ids = {g.id for g in dataset.get("student_groups", [])} if "student_groups" in dataset else None

        self.day_period_to_ts_id: Dict[Tuple[str, int], int] = {
            (ts.day, ts.period): ts.id for ts in self.timeslots
        }
        self.day_available_periods: Dict[str, Set[int]] = defaultdict(set)
        for ts in self.timeslots:
            self.day_available_periods[ts.day].add(ts.period)

        # Pre-cache valid rooms per section
        self._valid_rooms_cache: Dict[str, List[Room]] = {}
        for sec in self.section_map.values():
            req_type = getattr(sec, "required_room_type", "NORMAL")
            self._valid_rooms_cache[sec.section_id] = sorted([
                r for r in self.rooms
                if r.capacity >= sec.student_count and getattr(r, "room_type", "NORMAL") == req_type
            ], key=lambda r: (r.capacity, r.id))

        # Pre-cache valid start timeslots per duration
        self._valid_ts_by_duration: Dict[int, List[Timeslot]] = {}
        unique_durations = {getattr(s, "duration_periods", 1) for s in self.section_map.values()}
        for dur in unique_durations:
            self._valid_ts_by_duration[dur] = [
                t for t in self.timeslots
                if is_valid_period_block(t.period, dur, self.day_available_periods.get(t.day))
            ]

        # Pre-calculate candidate count per section for tightness priority key
        self._section_cand_count: Dict[str, int] = {}
        for sec in self.section_map.values():
            dur = getattr(sec, "duration_periods", 1)
            valid_rms = self._valid_rooms_cache.get(sec.section_id, [])
            lec = self.lecturer_map.get(sec.lecturer_id)
            avail_ts = getattr(lec, "available_timeslot_ids", None) if lec else None
            valid_ts_list = [
                t for t in self._valid_ts_by_duration.get(dur, [])
                if avail_ts is None or all(self.day_period_to_ts_id.get((t.day, p)) in avail_ts for p in get_occupied_periods(t.period, dur))
            ]
            self._section_cand_count[sec.section_id] = len(valid_rms) * len(valid_ts_list)

        self.hard_checker = HardConstraintChecker(
            self.section_map,
            self.room_map,
            self.timeslot_map,
            lecturer_ids=lecturer_ids,
            group_ids=group_ids,
            lecturer_map=self.lecturer_map
        )

    def _get_section_priority_key(self, sec: CourseSection) -> Tuple[int, int, int, int, int, str]:
        cand_count = self._section_cand_count.get(sec.section_id, 9999)
        is_lab = 0 if getattr(sec, "required_room_type", "NORMAL") == "LAB" else 1
        duration = -getattr(sec, "duration_periods", 1)
        lec = self.lecturer_map.get(sec.lecturer_id)
        restricted_lec = 0 if (lec and getattr(lec, "available_timeslot_ids", None) is not None) else 1
        st_count = -sec.student_count
        return (cand_count, is_lab, duration, restricted_lec, st_count, sec.section_id)

    def repair(self, schedule: Schedule, max_attempts: int = 15) -> RepairResult:
        start_time = time.perf_counter()
        self.stats.repair_calls += 1

        if not isinstance(schedule, Schedule) or not isinstance(getattr(schedule, "genes", None), list):
            self.stats.repair_failed += 1
            self.stats.repair_runtime_seconds += (time.perf_counter() - start_time)
            return RepairResult(
                schedule=schedule,
                success=False,
                remaining_hard_violations=len(self.section_map),
                failed_section_ids=sorted(list(self.section_map.keys())),
                status=RepairStatus.FAILED,
            )

        expected_section_ids = set(self.section_map)
        genes_are_typed = all(isinstance(gene, Gene) for gene in schedule.genes)
        gene_section_ids = [
            gene.section_id for gene in schedule.genes
            if isinstance(gene, Gene)
        ]
        structurally_valid = (
            genes_are_typed
            and len(schedule.genes) == len(expected_section_ids)
            and len(set(gene_section_ids)) == len(gene_section_ids)
            and set(gene_section_ids) == expected_section_ids
        )

        # Repair transforms assignments only. Missing, duplicate, unknown, or
        # non-Gene chromosome entries violate the representation contract and
        # are rejected instead of being silently invented or discarded.
        if not structurally_valid:
            input_hard, _ = self.evaluator.evaluate_hard(
                schedule, category="internal"
            )
            input_soft, _ = self.evaluator.evaluate_soft(
                schedule, category="internal"
            )
            failed_section_ids = sorted(expected_section_ids)

            self.stats.repair_failed += 1
            self.stats.sections_failed += len(failed_section_ids)
            self.stats.hard_before_repair += input_hard
            self.stats.hard_after_repair += input_hard
            self.stats.soft_before_repair += input_soft
            self.stats.soft_after_repair += input_soft
            self.stats.repair_runtime_seconds += (time.perf_counter() - start_time)

            return RepairResult(
                schedule=schedule,
                success=False,
                remaining_hard_violations=input_hard,
                failed_section_ids=failed_section_ids,
                status=RepairStatus.FAILED,
            )

        input_hard, _ = self.evaluator.evaluate_hard(schedule, category="internal")
        input_soft, _ = self.evaluator.evaluate_soft(schedule, category="internal")


        best_schedule = schedule
        best_hard = input_hard
        best_soft = input_soft
        best_failed_sections: List[str] = []
        best_repaired_count = 0

        input_gene_map = {g.section_id: (g.timeslot_id, g.room_id) for g in schedule.genes}

        for attempt in range(max_attempts):
            self.stats.repair_attempts += 1
            failed_sections: Set[str] = set()

            ordered_sections = list(self.section_map.values())
            if attempt > 0:
                ordered_sections.sort(
                    key=lambda sec: (self._get_section_priority_key(sec), random.random())
                )
            else:
                ordered_sections.sort(
                    key=lambda sec: self._get_section_priority_key(sec)
                )

            used_lecturer_time: Set[Tuple[str, str, int]] = set()
            used_room_time: Set[Tuple[str, str, int]] = set()
            used_group_time: Set[Tuple[str, str, int]] = set()

            repaired_genes_dict: Dict[str, Gene] = {}

            for section in ordered_sections:
                sec_id = section.section_id
                req_type = getattr(section, "required_room_type", "NORMAL")
                duration = getattr(section, "duration_periods", 1)
                lec = self.lecturer_map.get(section.lecturer_id)
                avail_ts = getattr(lec, "available_timeslot_ids", None) if lec else None

                current_gene = input_gene_map.get(sec_id)
                chosen_ts, chosen_room = None, None

                # Check if current assignment is 100% valid & conflict-free
                if current_gene:
                    ts_id, rm_id = current_gene
                    ts = self.timeslot_map.get(ts_id)
                    room = self.room_map.get(rm_id)
                    if ts and room and room.capacity >= section.student_count and getattr(room, "room_type", "NORMAL") == req_type:
                        if is_valid_period_block(ts.period, duration, self.day_available_periods.get(ts.day)):
                            occupied = get_occupied_periods(ts.period, duration)
                            avail_valid = (avail_ts is None or all(self.day_period_to_ts_id.get((ts.day, p)) in avail_ts for p in occupied))
                            lec_conflict = section.lecturer_id and any((section.lecturer_id, ts.day, p) in used_lecturer_time for p in occupied)
                            rm_conflict = any((room.id, ts.day, p) in used_room_time for p in occupied)
                            grp_conflict = section.group_id and any((section.group_id, ts.day, p) in used_group_time for p in occupied)

                            if avail_valid and not lec_conflict and not rm_conflict and not grp_conflict:
                                chosen_ts = ts
                                chosen_room = room

                # 3-Tier Candidate Search Hierarchy
                if chosen_ts is None:
                    candidate_rooms = self._valid_rooms_cache.get(sec_id, [])
                    valid_ts_list = self._valid_ts_by_duration.get(duration, [])

                    curr_ts = self.timeslot_map.get(current_gene[0]) if current_gene else None
                    curr_rm = self.room_map.get(current_gene[1]) if current_gene else None

                    # Tier 1: Keep timeslot, change room
                    if curr_ts and is_valid_period_block(curr_ts.period, duration, self.day_available_periods.get(curr_ts.day)):
                        occ = get_occupied_periods(curr_ts.period, duration)
                        if avail_ts is None or all(self.day_period_to_ts_id.get((curr_ts.day, p)) in avail_ts for p in occ):
                            if not (section.lecturer_id and any((section.lecturer_id, curr_ts.day, p) in used_lecturer_time for p in occ)) and \
                               not (section.group_id and any((section.group_id, curr_ts.day, p) in used_group_time for p in occ)):
                                for r in candidate_rooms:
                                    self.stats.candidate_checks += 1
                                    if not any((r.id, curr_ts.day, p) in used_room_time for p in occ):
                                        chosen_ts = curr_ts
                                        chosen_room = r
                                        break

                    # Tier 2: Change timeslot, keep current room
                    if chosen_ts is None and curr_rm and curr_rm.capacity >= section.student_count and getattr(curr_rm, "room_type", "NORMAL") == req_type:
                        for ts in valid_ts_list:
                            self.stats.candidate_checks += 1
                            occ = get_occupied_periods(ts.period, duration)
                            if avail_ts is not None and not all(self.day_period_to_ts_id.get((ts.day, p)) in avail_ts for p in occ):
                                continue
                            if section.lecturer_id and any((section.lecturer_id, ts.day, p) in used_lecturer_time for p in occ):
                                continue
                            if section.group_id and any((section.group_id, ts.day, p) in used_group_time for p in occ):
                                continue
                            if not any((curr_rm.id, ts.day, p) in used_room_time for p in occ):
                                chosen_ts = ts
                                chosen_room = curr_rm
                                break

                    # Tier 3: Change both timeslot and room
                    if chosen_ts is None:
                        shuffled_ts = list(valid_ts_list)
                        if attempt > 0:
                            random.shuffle(shuffled_ts)
                        for ts in shuffled_ts:
                            occ = get_occupied_periods(ts.period, duration)
                            if avail_ts is not None and not all(self.day_period_to_ts_id.get((ts.day, p)) in avail_ts for p in occ):
                                continue
                            if section.lecturer_id and any((section.lecturer_id, ts.day, p) in used_lecturer_time for p in occ):
                                continue
                            if section.group_id and any((section.group_id, ts.day, p) in used_group_time for p in occ):
                                continue

                            shuffled_rooms = list(candidate_rooms)
                            if attempt > 0:
                                random.shuffle(shuffled_rooms)
                            for r in shuffled_rooms:
                                self.stats.candidate_checks += 1
                                if not any((r.id, ts.day, p) in used_room_time for p in occ):
                                    chosen_ts = ts
                                    chosen_room = r
                                    break
                            if chosen_ts is not None:
                                break

                if chosen_ts is not None and chosen_room is not None:
                    repaired_genes_dict[sec_id] = Gene(sec_id, chosen_room.id, chosen_ts.id)
                    cand_occupied = get_occupied_periods(chosen_ts.period, duration)
                    if section.lecturer_id:
                        for p in cand_occupied:
                            used_lecturer_time.add((section.lecturer_id, chosen_ts.day, p))
                    for p in cand_occupied:
                        used_room_time.add((chosen_room.id, chosen_ts.day, p))
                    if section.group_id:
                        for p in cand_occupied:
                            used_group_time.add((section.group_id, chosen_ts.day, p))
                else:
                    failed_sections.add(sec_id)
                    if current_gene:
                        repaired_genes_dict[sec_id] = Gene(sec_id, current_gene[1], current_gene[0])

            # Reconstruct candidate schedule
            final_genes = [
                repaired_genes_dict.get(sec.section_id, Gene(sec.section_id, input_gene_map[sec.section_id][1], input_gene_map[sec.section_id][0]))
                for sec in self.dataset["course_sections"]
            ]
            cand_schedule = Schedule(genes=final_genes)

            cand_hard, _ = self.evaluator.evaluate_hard(cand_schedule, category="internal")
            cand_soft, _ = self.evaluator.evaluate_soft(cand_schedule, category="internal")


            # Update best_schedule on attempt 0 or when strictly better than best schedule found so far
            if attempt == 0 or (cand_hard, cand_soft) < (best_hard, best_soft):
                best_schedule = cand_schedule
                best_hard = cand_hard
                best_soft = cand_soft
                best_failed_sections = sorted(list(failed_sections))
                # Count sections that ACTUALLY changed from input
                best_repaired_count = sum(
                    1 for g in final_genes
                    if (g.timeslot_id, g.room_id) != input_gene_map.get(g.section_id)
                )

            if best_hard == 0:
                break

        # Classify status based on (best_hard, best_soft) vs (input_hard, input_soft)
        if (best_hard, best_soft) < (input_hard, input_soft):
            status = RepairStatus.IMPROVED
            self.stats.repair_improved += 1
            self.stats.sections_repaired += best_repaired_count
        elif (best_hard, best_soft) == (input_hard, input_soft):
            status = RepairStatus.UNCHANGED
            self.stats.repair_unchanged += 1
        else:
            status = RepairStatus.FAILED
            self.stats.repair_failed += 1


        self.stats.hard_before_repair += input_hard
        self.stats.hard_after_repair += best_hard
        self.stats.soft_before_repair += input_soft
        self.stats.soft_after_repair += best_soft
        self.stats.sections_failed += len(best_failed_sections)
        self.stats.repair_runtime_seconds += (time.perf_counter() - start_time)

        return RepairResult(
            schedule=best_schedule,
            success=(status != RepairStatus.FAILED),
            remaining_hard_violations=best_hard,
            failed_section_ids=best_failed_sections,
            status=status,
        )
