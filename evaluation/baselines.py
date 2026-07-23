import random
import copy
from typing import List, Optional, Dict
from domain import Schedule, Gene, CourseSection, Room, Timeslot, Lecturer
from constraints import ConstraintEvaluator

class RandomSearchScheduler:
    def __init__(self, dataset: dict):
        self.dataset = dataset
        self.sections: List[CourseSection] = dataset["course_sections"]
        self.rooms: List[Room] = dataset["rooms"]
        self.timeslots: List[Timeslot] = dataset["timeslots"]
        self.evaluator = ConstraintEvaluator(dataset)

    def run(self, iterations: int = 1000, evaluation_budget: Optional[int] = None) -> dict:
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
            score, hard, soft_penalty = self.evaluator.calculate_fitness(cand)
            _, soft_details = self.evaluator.evaluate_soft(cand)
            raw_soft = sum(soft_details.values())
            evaluation_count += 1

            candidate_key = (hard, soft_penalty)

            if best_key is None or candidate_key < best_key:
                best_key = candidate_key
                best_schedule = copy.deepcopy(cand)
                best_score = score
                best_hard = hard
                best_raw_soft = raw_soft
                best_soft_penalty = soft_penalty

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
    def __init__(self, dataset: dict):
        self.dataset = dataset
        self.sections: List[CourseSection] = dataset["course_sections"]
        self.rooms: List[Room] = dataset["rooms"]
        self.timeslots: List[Timeslot] = dataset["timeslots"]
        self.lecturer_map: Dict[str, Lecturer] = {l.id: l for l in dataset.get("lecturers", [])}
        self.evaluator = ConstraintEvaluator(dataset)

    def run(self) -> dict:
        """Thuật toán Xếp lịch Tham ăn (Greedy Scheduler)."""
        genes = []
        used_lecturer_time = set()
        used_room_time = set()
        used_group_time = set()

        for sec in self.sections:
            best_r = None
            best_ts = None
            found_valid = False

            lec = self.lecturer_map.get(sec.lecturer_id)
            avail_ts = getattr(lec, "available_timeslot_ids", None) if lec else None
            req_type = getattr(sec, "required_room_type", "NORMAL")

            for ts in self.timeslots:
                if avail_ts is not None and ts.id not in avail_ts:
                    continue
                if (sec.lecturer_id, ts.id) in used_lecturer_time or (sec.group_id, ts.id) in used_group_time:
                    continue

                for r in self.rooms:
                    rm_type = getattr(r, "room_type", "NORMAL")
                    if r.capacity >= sec.student_count and rm_type == req_type and (r.id, ts.id) not in used_room_time:
                        best_r = r
                        best_ts = ts
                        found_valid = True
                        break
                if found_valid:
                    break

            # Fallback if no conflict-free slot:
            if not found_valid:
                valid_rooms = [
                    r for r in self.rooms
                    if r.capacity >= sec.student_count and getattr(r, "room_type", "NORMAL") == req_type
                ] or [
                    r for r in self.rooms if r.capacity >= sec.student_count
                ] or self.rooms

                best_r = random.choice(valid_rooms)

                valid_ts = [
                    t for t in self.timeslots
                    if avail_ts is None or t.id in avail_ts
                ] or self.timeslots

                best_ts = random.choice(valid_ts)

            used_lecturer_time.add((sec.lecturer_id, best_ts.id))
            used_room_time.add((best_r.id, best_ts.id))
            used_group_time.add((sec.group_id, best_ts.id))
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
