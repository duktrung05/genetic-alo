"""Baseline Scheduling Algorithms Module.

Provides Random Search Scheduler and Greedy Scheduler baselines for comparison
with Genetic Algorithm optimization performance.
"""

import random
from typing import List, Optional, Dict
from domain import Schedule, Gene, CourseSection, Room, Timeslot, Lecturer
from constraints import ConstraintEvaluator
from dataset import get_occupied_periods, is_valid_period_block, DatasetValidator

class RandomSearchScheduler:
    """Random Search baseline scheduler for random schedule sampling."""

    def __init__(self, dataset: dict):
        DatasetValidator.validate(dataset)
        self.dataset = dataset
        self.sections: List[CourseSection] = dataset["course_sections"]
        self.rooms: List[Room] = dataset["rooms"]
        self.timeslots: List[Timeslot] = dataset["timeslots"]
        self.evaluator = ConstraintEvaluator(dataset)

    def run(self, iterations: int = 1000, evaluation_budget: Optional[int] = None) -> dict:
        """Execute Random Search sampling loop for specified evaluation budget."""
        best_schedule = None
        best_key = None
        best_score = None
        best_hard = None
        best_raw_soft = None
        best_soft_penalty = None
        history = []
        evaluation_count = 0

        max_evals = evaluation_budget if evaluation_budget is not None else iterations

        for i in range(max_evals):
            genes = [
                Gene(section_id=sec.section_id, room_id=random.choice(self.rooms).id, timeslot_id=random.choice(self.timeslots).id)
                for sec in self.sections
            ]
            cand = Schedule(genes=genes)
            hard, _ = self.evaluator.evaluate_hard(cand)
            soft_penalty, soft_details = self.evaluator.evaluate_soft(cand)
            score = float((hard * 1000) + (soft_penalty * 1))
            raw_soft = sum(soft_details.values())
            evaluation_count += 1

            candidate_key = (hard, soft_penalty)
            is_new_best = False

            if best_key is None or candidate_key < best_key:
                best_key = candidate_key
                best_schedule = Schedule(genes=[Gene(g.section_id, g.room_id, g.timeslot_id) for g in cand.genes])
                best_score = score
                best_hard = hard
                best_raw_soft = raw_soft
                best_soft_penalty = soft_penalty
                is_new_best = True

            if is_new_best or (evaluation_count % 100 == 0) or (i == max_evals - 1):
                history.append({
                    "iteration": i,
                    "fitness_evaluations": evaluation_count,
                    "best_score": best_score,
                    "best_hard": best_hard,
                    "best_raw_soft": best_raw_soft,
                    "best_soft_penalty": best_soft_penalty,
                    "hard_violations": best_hard,
                    "soft_violations": best_soft_penalty,
                    "raw_soft_violations": best_raw_soft,
                    "soft_penalty": best_soft_penalty
                })

        return {
            "best_schedule": best_schedule,
            "best_score": best_score,
            "hard_violations": best_hard,
            "soft_violations": best_soft_penalty,
            "raw_soft_violations": best_raw_soft,
            "soft_penalty": best_soft_penalty,
            "fitness_evaluations": evaluation_count,
            "history": history
        }

class GreedyScheduler:
    """Pure Deterministic Greedy baseline scheduler using heuristic first-fit section assignment."""

    def __init__(self, dataset: dict, seed: int = 0):
        """Initialize Greedy Scheduler with dataset."""
        DatasetValidator.validate(dataset)
        self.dataset = dataset
        self.sections: List[CourseSection] = dataset["course_sections"]
        self.rooms: List[Room] = dataset["rooms"]
        self.timeslots: List[Timeslot] = dataset["timeslots"]
        self.lecturer_map: Dict[str, Lecturer] = {l.id: l for l in dataset.get("lecturers", [])}
        self.evaluator = ConstraintEvaluator(dataset)

    def run(self) -> dict:
        """Execute 100% deterministic heuristic Greedy schedule construction."""
        genes = []
        used_lecturer_time = set()
        used_room_time = set()
        used_group_time = set()

        day_period_to_ts_id = {(t.day, t.period): t.id for t in self.timeslots}
        day_available_periods = {}
        for t in self.timeslots:
            if t.day not in day_available_periods:
                day_available_periods[t.day] = set()
            day_available_periods[t.day].add(t.period)

        for sec in self.sections:
            best_r = None
            best_ts = None
            found_valid = False

            lec = self.lecturer_map.get(sec.lecturer_id)
            avail_ts = getattr(lec, "available_timeslot_ids", None) if lec else None
            req_type = getattr(sec, "required_room_type", "NORMAL")

            duration = getattr(sec, "duration_periods", 1)

            for ts in self.timeslots:
                if not is_valid_period_block(ts.period, duration, day_available_periods.get(ts.day)):
                    continue

                occupied_p = get_occupied_periods(ts.period, duration)
                if avail_ts is not None and not all(day_period_to_ts_id.get((ts.day, p)) in avail_ts for p in occupied_p):
                    continue

                if sec.lecturer_id and any((sec.lecturer_id, ts.day, p) in used_lecturer_time for p in occupied_p):
                    continue
                if sec.group_id and any((sec.group_id, ts.day, p) in used_group_time for p in occupied_p):
                    continue

                for r in self.rooms:
                    rm_type = getattr(r, "room_type", "NORMAL")
                    if (
                        r.capacity >= sec.student_count
                        and rm_type == req_type
                        and not any((r.id, ts.day, p) in used_room_time for p in occupied_p)
                    ):
                        best_r = r
                        best_ts = ts
                        found_valid = True
                        break
                if found_valid:
                    break

            if not found_valid:
                valid_rooms = sorted([
                    r for r in self.rooms
                    if r.capacity >= sec.student_count and getattr(r, "room_type", "NORMAL") == req_type
                ] or [
                    r for r in self.rooms if r.capacity >= sec.student_count
                ] or self.rooms, key=lambda r: (r.capacity, r.id))

                best_r = valid_rooms[0]

                valid_ts = sorted([
                    t for t in self.timeslots
                    if is_valid_period_block(t.period, duration, day_available_periods.get(t.day))
                    and (avail_ts is None or all(day_period_to_ts_id.get((t.day, p)) in avail_ts for p in get_occupied_periods(t.period, duration)))
                ] or self.timeslots, key=lambda t: t.id)

                best_ts = valid_ts[0]

            occupied_p = get_occupied_periods(best_ts.period, duration)
            if sec.lecturer_id:
                for p in occupied_p:
                    used_lecturer_time.add((sec.lecturer_id, best_ts.day, p))
            for p in occupied_p:
                used_room_time.add((best_r.id, best_ts.day, p))
            if sec.group_id:
                for p in occupied_p:
                    used_group_time.add((sec.group_id, best_ts.day, p))
            genes.append(Gene(section_id=sec.section_id, room_id=best_r.id, timeslot_id=best_ts.id))

        schedule = Schedule(genes=genes)
        score, final_h, final_s = self.evaluator.calculate_fitness(schedule)
        _, s_details = self.evaluator.evaluate_soft(schedule)
        raw_soft_cnt = sum(s_details.values())

        return {
            "best_schedule": schedule,
            "best_score": score,
            "hard_violations": final_h,
            "soft_violations": final_s,
            "soft_penalty": final_s,
            "raw_soft_violations": raw_soft_cnt,
            "fitness_evaluations": 1,
        }
