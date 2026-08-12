"""Deterministic Post-Search Soft Local Search Module.

Performs bounded post-search Hill-Climbing optimization on a 100% hard-feasible
Schedule chromosome (hard_violations == 0) to strictly reduce soft constraint penalty
without compromising feasibility.
"""

from __future__ import annotations
import time
from typing import Dict, List, Set, Tuple, Optional, Any
from collections import defaultdict

from domain import Schedule, Gene, CourseSection, Room, Timeslot, Lecturer
from dataset import get_occupied_periods, is_valid_period_block
from constraints.evaluator import ConstraintEvaluator


class SoftLocalSearch:
    """Post-search deterministic Hill-Climbing optimizer for soft penalty reduction."""

    def __init__(
        self,
        dataset: dict,
        evaluator: Optional[ConstraintEvaluator] = None,
        max_passes: int = 2,
        max_candidate_checks: int = 5000,
    ) -> None:
        self.dataset = dataset
        self.evaluator = evaluator if evaluator is not None else ConstraintEvaluator(dataset)
        self.max_passes = max_passes
        self.max_candidate_checks = max_candidate_checks

        self.sections: List[CourseSection] = dataset["course_sections"]
        self.section_map: Dict[str, CourseSection] = {s.section_id: s for s in self.sections}
        self.rooms: List[Room] = dataset["rooms"]
        self.timeslots: List[Timeslot] = dataset["timeslots"]
        self.timeslot_map: Dict[int, Timeslot] = {t.id: t for t in self.timeslots}
        self.room_map: Dict[str, Room] = {r.id: r for r in self.rooms}
        self.lecturer_map: Dict[str, Lecturer] = {l.id: l for l in dataset.get("lecturers", [])}

        self.day_period_to_ts_id: Dict[Tuple[str, int], int] = {
            (ts.day, ts.period): ts.id for ts in self.timeslots
        }
        self.day_available_periods: Dict[str, Set[int]] = defaultdict(set)
        for ts in self.timeslots:
            self.day_available_periods[ts.day].add(ts.period)

        # Pre-cache candidate rooms per section sorted deterministically by (capacity, id)
        self._valid_rooms_cache: Dict[str, List[Room]] = {}
        for sec in self.sections:
            req_type = getattr(sec, "required_room_type", "NORMAL")
            self._valid_rooms_cache[sec.section_id] = sorted(
                [
                    r for r in self.rooms
                    if r.capacity >= sec.student_count and getattr(r, "room_type", "NORMAL") == req_type
                ],
                key=lambda r: (r.capacity, r.id),
            )

        # Pre-cache valid start timeslots per duration sorted by id
        self._valid_ts_by_duration: Dict[int, List[Timeslot]] = {}
        unique_durations = {getattr(s, "duration_periods", 1) for s in self.sections}
        for dur in unique_durations:
            self._valid_ts_by_duration[dur] = sorted(
                [
                    t for t in self.timeslots
                    if is_valid_period_block(t.period, dur, self.day_available_periods.get(t.day))
                ],
                key=lambda t: t.id,
            )

    def optimize(
        self,
        schedule: Schedule,
    ) -> Tuple[Schedule, Dict[str, Any]]:
        """Run post-search deterministic Hill-Climbing on a feasible schedule.

        Invariant:
            final_hard == 0
            final_soft <= initial_soft
        """
        start_time = time.perf_counter()

        initial_hard, _ = self.evaluator.evaluate_hard(schedule, category="internal")
        initial_soft, _ = self.evaluator.evaluate_soft(schedule, category="internal")

        stats: Dict[str, Any] = {
            "soft_ls_calls": 1,
            "soft_ls_initial_penalty": initial_soft,
            "soft_ls_final_penalty": initial_soft,
            "soft_ls_improvement": 0,
            "soft_ls_candidate_checks": 0,
            "soft_ls_accepted_moves": 0,
            "soft_ls_runtime_seconds": 0.0,
        }

        # Safety Check: If input schedule is not hard-feasible, reject immediately
        if initial_hard > 0:
            stats["soft_ls_runtime_seconds"] = round(time.perf_counter() - start_time, 4)
            return schedule, stats

        current_genes_map: Dict[str, Gene] = {g.section_id: Gene(g.section_id, g.room_id, g.timeslot_id) for g in schedule.genes}
        current_soft = initial_soft
        candidate_checks = 0
        accepted_moves = 0

        for pass_idx in range(self.max_passes):
            pass_improved = False
            if candidate_checks >= self.max_candidate_checks:
                break

            for sec in self.sections:
                if candidate_checks >= self.max_candidate_checks:
                    break

                sec_id = sec.section_id
                cur_gene = current_genes_map[sec_id]
                duration = getattr(sec, "duration_periods", 1)
                req_type = getattr(sec, "required_room_type", "NORMAL")
                lec = self.lecturer_map.get(sec.lecturer_id)
                avail_ts = getattr(lec, "available_timeslot_ids", None) if lec else None

                candidate_rooms = self._valid_rooms_cache.get(sec_id, [])
                valid_ts_list = [
                    t for t in self._valid_ts_by_duration.get(duration, [])
                    if avail_ts is None or all(
                        self.day_period_to_ts_id.get((t.day, p)) in avail_ts
                        for p in get_occupied_periods(t.period, duration)
                    )
                ]

                section_move_accepted = False

                # MOVE A — Change room only (keep timeslot)
                cur_ts_id = cur_gene.timeslot_id
                for r in candidate_rooms:
                    if candidate_checks >= self.max_candidate_checks:
                        break
                    if r.id == cur_gene.room_id:
                        continue

                    candidate_checks += 1
                    test_genes = [
                        Gene(s.section_id, r.id if s.section_id == sec_id else current_genes_map[s.section_id].room_id, current_genes_map[s.section_id].timeslot_id)
                        for s in self.sections
                    ]
                    cand_sched = Schedule(genes=test_genes)
                    cand_h, _ = self.evaluator.evaluate_hard(cand_sched, category="internal")

                    if cand_h == 0:
                        cand_s, _ = self.evaluator.evaluate_soft(cand_sched, category="internal")
                        if cand_s < current_soft:
                            current_genes_map[sec_id] = Gene(sec_id, r.id, cur_ts_id)
                            current_soft = cand_s
                            accepted_moves += 1
                            pass_improved = True
                            section_move_accepted = True
                            break

                if section_move_accepted:
                    continue

                # MOVE B — Change timeslot only (keep room)
                cur_room_id = current_genes_map[sec_id].room_id
                for ts in valid_ts_list:
                    if candidate_checks >= self.max_candidate_checks:
                        break
                    if ts.id == cur_gene.timeslot_id:
                        continue

                    candidate_checks += 1
                    test_genes = [
                        Gene(s.section_id, current_genes_map[s.section_id].room_id, ts.id if s.section_id == sec_id else current_genes_map[s.section_id].timeslot_id)
                        for s in self.sections
                    ]
                    cand_sched = Schedule(genes=test_genes)
                    cand_h, _ = self.evaluator.evaluate_hard(cand_sched, category="internal")

                    if cand_h == 0:
                        cand_s, _ = self.evaluator.evaluate_soft(cand_sched, category="internal")
                        if cand_s < current_soft:
                            current_genes_map[sec_id] = Gene(sec_id, cur_room_id, ts.id)
                            current_soft = cand_s
                            accepted_moves += 1
                            pass_improved = True
                            section_move_accepted = True
                            break

                if section_move_accepted:
                    continue

                # MOVE C — Change room + timeslot
                for ts in valid_ts_list:
                    if candidate_checks >= self.max_candidate_checks or section_move_accepted:
                        break
                    if ts.id == cur_gene.timeslot_id:
                        continue
                    for r in candidate_rooms:
                        if candidate_checks >= self.max_candidate_checks:
                            break
                        if r.id == cur_gene.room_id:
                            continue

                        candidate_checks += 1
                        test_genes = [
                            Gene(s.section_id, r.id if s.section_id == sec_id else current_genes_map[s.section_id].room_id, ts.id if s.section_id == sec_id else current_genes_map[s.section_id].timeslot_id)
                            for s in self.sections
                        ]
                        cand_sched = Schedule(genes=test_genes)
                        cand_h, _ = self.evaluator.evaluate_hard(cand_sched, category="internal")

                        if cand_h == 0:
                            cand_s, _ = self.evaluator.evaluate_soft(cand_sched, category="internal")
                            if cand_s < current_soft:
                                current_genes_map[sec_id] = Gene(sec_id, r.id, ts.id)
                                current_soft = cand_s
                                accepted_moves += 1
                                pass_improved = True
                                section_move_accepted = True
                                break

            if not pass_improved:
                break

        final_genes = [current_genes_map[s.section_id] for s in self.sections]
        final_schedule = Schedule(genes=final_genes)

        final_hard, _ = self.evaluator.evaluate_hard(final_schedule, category="internal")
        final_soft, _ = self.evaluator.evaluate_soft(final_schedule, category="internal")

        if final_hard > 0 or final_soft > initial_soft:
            final_schedule = schedule
            final_soft = initial_soft
            accepted_moves = 0

        stats["soft_ls_final_penalty"] = final_soft
        stats["soft_ls_improvement"] = initial_soft - final_soft
        stats["soft_ls_candidate_checks"] = candidate_checks
        stats["soft_ls_accepted_moves"] = accepted_moves
        stats["soft_ls_runtime_seconds"] = round(time.perf_counter() - start_time, 4)

        return final_schedule, stats
