import time
import random
from typing import List, Optional, Dict
from domain import (
    Schedule, Gene, SchedulingActivity, Room, Timeslot, Lecturer,
    expand_scheduling_activities,
)
from constraints.evaluator import ConstraintEvaluator
from dataset import get_occupied_periods, is_valid_period_block, DatasetValidator

from evaluation.run_metrics import RunMetrics


class RepairOnlyScheduler:
    """Random-restart baseline that applies Repair without any GA operators."""

    def __init__(
        self,
        dataset: dict,
        hard_weight: int = 1000,
        soft_weight: int = 1,
        seed: Optional[int] = None,
    ):
        DatasetValidator.validate(dataset)
        self.dataset = dataset
        self.hard_weight = hard_weight
        self.soft_weight = soft_weight
        self.seed = seed

    @staticmethod
    def _clone(schedule: Schedule) -> Schedule:
        return Schedule(
            genes=[
                Gene(g.section_id, g.room_id, g.timeslot_id)
                for g in schedule.genes
            ]
        )

    def run(
        self,
        iterations: int = 1000,
        evaluation_budget: Optional[int] = None,
        seed: Optional[int] = None,
    ) -> dict:
        """Run exactly one random-restart + Repair attempt per search evaluation."""
        max_evals = evaluation_budget if evaluation_budget is not None else iterations
        if not isinstance(max_evals, int) or max_evals < 1:
            raise ValueError(f"evaluation_budget must be an integer >= 1, got {max_evals}")

        run_seed = seed if seed is not None else self.seed
        if run_seed is not None:
            random.seed(run_seed)

        # Nhập tại thời điểm chạy để tránh vòng lặp nhập evaluation -> ga -> evaluation.
        from ga.engine import GeneticAlgorithmEngine

        engine = GeneticAlgorithmEngine(
            self.dataset,
            pop_size=2,
            hard_weight=self.hard_weight,
            soft_weight=self.soft_weight,
            elite_count=1,
            seed=run_seed,
        )
        evaluator = engine.evaluator
        repairer = engine.repairer
        evaluator.counters.reset()
        repairer.stats.reset()
        repairer.evaluator = evaluator

        start_time = time.perf_counter()
        best_schedule = None
        best_key = None
        best_score = None
        best_hard = None
        best_soft = None
        history = []
        first_feasible_time = None
        first_feasible_search_eval = None
        first_feasible_total_eval = None
        first_feasible_iteration = None

        for iteration in range(max_evals):
            candidate = engine.create_random_schedule()
            candidate = repairer.repair(candidate).schedule
            score, hard, soft = evaluator.calculate_fitness(
                candidate,
                self.hard_weight,
                self.soft_weight,
                is_search_eval=True,
            )
            evaluation_count = evaluator.counters.search_fitness_evaluations

            if hard == 0 and first_feasible_time is None:
                first_feasible_time = time.perf_counter() - start_time
                first_feasible_search_eval = evaluation_count
                first_feasible_total_eval = evaluator.counters.total_constraint_evaluations
                first_feasible_iteration = iteration

            is_new_best = best_key is None or (hard, soft) < best_key
            if is_new_best:
                best_key = (hard, soft)
                best_schedule = self._clone(candidate)
                best_score = score
                best_hard = hard
                best_soft = soft

            if is_new_best or evaluation_count % 100 == 0 or evaluation_count == max_evals:
                history.append({
                    "iteration": iteration,
                    "elapsed_seconds": round(time.perf_counter() - start_time, 4),
                    "fitness_evaluations": evaluation_count,
                    "best_score": best_score,
                    "best_hard": best_hard,
                    "best_soft_penalty": best_soft,
                })

        runtime_seconds = time.perf_counter() - start_time
        _, soft_details = evaluator.evaluate_soft(best_schedule, category="reporting")
        raw_soft = sum(soft_details.values())
        counters = evaluator.counters
        repair_stats = repairer.stats

        metrics = RunMetrics(
            method="Repair-only Random Restart",
            seed=run_seed,
            runtime_seconds=runtime_seconds,
            time_to_first_feasible_seconds=first_feasible_time,
            search_fitness_evaluations=counters.search_fitness_evaluations,
            hard_constraint_evaluations=counters.hard_constraint_evaluations,
            soft_constraint_evaluations=counters.soft_constraint_evaluations,
            total_constraint_evaluations=counters.total_constraint_evaluations,
            candidate_checks=counters.candidate_checks + repair_stats.candidate_checks,
            repair_calls=repair_stats.repair_calls,
            repair_improved=repair_stats.repair_improved,
            repair_unchanged=repair_stats.repair_unchanged,
            repair_failed=repair_stats.repair_failed,
            first_feasible_search_evaluation=first_feasible_search_eval,
            first_feasible_total_constraint_evaluation=first_feasible_total_eval,
            first_feasible_generation=first_feasible_iteration,
            final_hard_violations=best_hard,
            final_soft_penalty=best_soft,
            feasible=(best_hard == 0),
            score=best_score,
            raw_soft_violations=raw_soft,
            search_hard_constraint_evaluations=counters.search_hard_constraint_evaluations,
            search_soft_constraint_evaluations=counters.search_soft_constraint_evaluations,
            search_constraint_evaluations=counters.search_constraint_evaluations,
            internal_hard_constraint_evaluations=counters.internal_hard_constraint_evaluations,
            internal_soft_constraint_evaluations=counters.internal_soft_constraint_evaluations,
            internal_constraint_evaluations=counters.internal_constraint_evaluations,
            reporting_hard_constraint_evaluations=counters.reporting_hard_constraint_evaluations,
            reporting_soft_constraint_evaluations=counters.reporting_soft_constraint_evaluations,
            reporting_constraint_evaluations=counters.reporting_constraint_evaluations,
            total_hard_constraint_evaluations=counters.hard_constraint_evaluations,
            total_soft_constraint_evaluations=counters.soft_constraint_evaluations,
        )

        result = metrics.to_dict()
        result.update({
            "best_schedule": best_schedule,
            "best_score": best_score,
            "hard_violations": best_hard,
            "soft_violations": best_soft,
            "soft_penalty": best_soft,
            "raw_soft_violations": raw_soft,
            "fitness_evaluations": counters.search_fitness_evaluations,
            "history": history,
            "repair_stats": repair_stats.to_dict(),
            "uses_ga_operators": False,
            "use_repair": True,
            "use_soft_local_search": False,
            "run_metrics": metrics,
        })
        return result

class RandomSearchScheduler:
    """Bộ lập lịch Random Search dùng làm baseline lấy mẫu lịch ngẫu nhiên."""

    def __init__(self, dataset: dict, seed: Optional[int] = None):
        DatasetValidator.validate(dataset)
        self.dataset = dataset
        self.sections: List[SchedulingActivity] = expand_scheduling_activities(
            dataset["course_sections"]
        )
        self.rooms: List[Room] = dataset["rooms"]
        self.timeslots: List[Timeslot] = dataset["timeslots"]
        self.seed = seed

    def run(self, iterations: int = 1000, evaluation_budget: Optional[int] = None, seed: Optional[int] = None) -> dict:
        """Thực thi vòng lặp lấy mẫu Random Search theo ngân sách đánh giá quy định."""
        run_seed = seed if seed is not None else self.seed
        if run_seed is not None:
            random.seed(run_seed)

        start_time = time.perf_counter()
        self.evaluator = ConstraintEvaluator(self.dataset)

        best_schedule = None
        best_key = None
        best_score = None
        best_hard = None
        best_raw_soft = None
        best_soft_penalty = None
        history = []
        evaluation_count = 0

        first_feasible_time: Optional[float] = None
        first_feasible_search_eval: Optional[int] = None
        first_feasible_total_eval: Optional[int] = None
        first_feasible_gen: Optional[int] = None

        max_evals = evaluation_budget if evaluation_budget is not None else iterations

        for i in range(max_evals):
            genes = [
                Gene(activity_id=sec.activity_id, room_id=random.choice(self.rooms).id, timeslot_id=random.choice(self.timeslots).id)
                for sec in self.sections
            ]
            cand = Schedule(genes=genes)
            hard, _ = self.evaluator.evaluate_hard(cand, category="search")
            soft_penalty, soft_details = self.evaluator.evaluate_soft(cand, category="search")
            score = float((hard * 1000) + (soft_penalty * 1))
            raw_soft = sum(soft_details.values())
            evaluation_count += 1

            if hard == 0 and first_feasible_time is None:
                first_feasible_time = time.perf_counter() - start_time
                first_feasible_search_eval = evaluation_count
                first_feasible_total_eval = self.evaluator.counters.total_constraint_evaluations
                first_feasible_gen = i

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

            elapsed_now = time.perf_counter() - start_time
            if is_new_best or (evaluation_count % 100 == 0) or (i == max_evals - 1):
                history.append({
                    "iteration": i,
                    "elapsed_seconds": round(elapsed_now, 4),
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

        runtime_seconds = time.perf_counter() - start_time
        metrics = RunMetrics(
            method="Random Search",
            seed=run_seed,
            runtime_seconds=runtime_seconds,
            time_to_first_feasible_seconds=first_feasible_time,
            search_fitness_evaluations=self.evaluator.counters.search_fitness_evaluations,
            hard_constraint_evaluations=self.evaluator.counters.hard_constraint_evaluations,
            soft_constraint_evaluations=self.evaluator.counters.soft_constraint_evaluations,
            total_constraint_evaluations=self.evaluator.counters.total_constraint_evaluations,
            candidate_checks=self.evaluator.counters.candidate_checks,
            repair_calls=0,
            repair_improved=0,
            repair_unchanged=0,
            repair_failed=0,
            first_feasible_search_evaluation=first_feasible_search_eval,
            first_feasible_total_constraint_evaluation=first_feasible_total_eval,
            first_feasible_generation=first_feasible_gen,
            final_hard_violations=best_hard if best_hard is not None else 999,
            final_soft_penalty=best_soft_penalty if best_soft_penalty is not None else 9999,
            feasible=(best_hard == 0 if best_hard is not None else False),
            score=best_score if best_score is not None else 99999.0,
            raw_soft_violations=best_raw_soft if best_raw_soft is not None else 0,
            search_hard_constraint_evaluations=self.evaluator.counters.search_hard_constraint_evaluations,
            search_soft_constraint_evaluations=self.evaluator.counters.search_soft_constraint_evaluations,
            search_constraint_evaluations=self.evaluator.counters.search_constraint_evaluations,
            internal_hard_constraint_evaluations=self.evaluator.counters.internal_hard_constraint_evaluations,
            internal_soft_constraint_evaluations=self.evaluator.counters.internal_soft_constraint_evaluations,
            internal_constraint_evaluations=self.evaluator.counters.internal_constraint_evaluations,
            reporting_hard_constraint_evaluations=self.evaluator.counters.reporting_hard_constraint_evaluations,
            reporting_soft_constraint_evaluations=self.evaluator.counters.reporting_soft_constraint_evaluations,
            reporting_constraint_evaluations=self.evaluator.counters.reporting_constraint_evaluations,
            total_hard_constraint_evaluations=self.evaluator.counters.hard_constraint_evaluations,
            total_soft_constraint_evaluations=self.evaluator.counters.soft_constraint_evaluations,
        )


        res_dict = metrics.to_dict()
        res_dict.update({
            "best_schedule": best_schedule,
            "best_score": best_score,
            "hard_violations": best_hard,
            "soft_violations": best_soft_penalty,
            "raw_soft_violations": best_raw_soft,
            "soft_penalty": best_soft_penalty,
            "fitness_evaluations": evaluation_count,
            "history": history,
            "run_metrics": metrics,
        })
        return res_dict

class GreedyScheduler:
    """Bộ lập lịch Greedy thuần định hướng dùng làm baseline phân công lớp học phần tham lam."""

    def __init__(self, dataset: dict, seed: Optional[int] = None):
        """Khởi tạo Bộ lập lịch Greedy với dữ liệu đầu vào."""
        DatasetValidator.validate(dataset)
        self.dataset = dataset
        self.sections: List[SchedulingActivity] = expand_scheduling_activities(
            dataset["course_sections"]
        )
        self.rooms: List[Room] = dataset["rooms"]
        self.timeslots: List[Timeslot] = dataset["timeslots"]
        self.lecturer_map: Dict[str, Lecturer] = {l.id: l for l in dataset.get("lecturers", [])}
        self.seed = seed

    def run(self, seed: Optional[int] = None) -> dict:
        """Thực thi xây dựng thời khóa biểu theo thuật toán Greedy định hướng 100%."""
        run_seed = seed if seed is not None else self.seed
        start_time = time.perf_counter()
        self.evaluator = ConstraintEvaluator(self.dataset)

        genes = []
        used_lecturer_time = set()
        used_room_time = set()
        used_group_time = set()
        used_section_days = set()

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
                if (sec.section_id, ts.day) in used_section_days:
                    continue
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
                    self.evaluator.counters.candidate_checks += 1
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
                    and (sec.section_id, t.day) not in used_section_days
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
            used_section_days.add((sec.section_id, best_ts.day))
            genes.append(Gene(activity_id=sec.activity_id, room_id=best_r.id, timeslot_id=best_ts.id))

        schedule = Schedule(genes=genes)
        score, final_h, final_s = self.evaluator.calculate_fitness(schedule, is_search_eval=True)
        _, s_details = self.evaluator.evaluate_soft(schedule, category="reporting")
        raw_soft_cnt = sum(s_details.values())
        runtime_seconds = time.perf_counter() - start_time


        is_feasible = (final_h == 0)
        first_feasible_time = runtime_seconds if is_feasible else None
        first_feasible_search_eval = 1 if is_feasible else None
        first_feasible_total_eval = self.evaluator.counters.total_constraint_evaluations if is_feasible else None
        first_feasible_gen = 0 if is_feasible else None

        metrics = RunMetrics(
            method="Greedy Search",
            seed=run_seed,
            runtime_seconds=runtime_seconds,
            time_to_first_feasible_seconds=first_feasible_time,
            search_fitness_evaluations=self.evaluator.counters.search_fitness_evaluations,
            hard_constraint_evaluations=self.evaluator.counters.hard_constraint_evaluations,
            soft_constraint_evaluations=self.evaluator.counters.soft_constraint_evaluations,
            total_constraint_evaluations=self.evaluator.counters.total_constraint_evaluations,
            candidate_checks=self.evaluator.counters.candidate_checks,
            repair_calls=0,
            repair_improved=0,
            repair_unchanged=0,
            repair_failed=0,
            first_feasible_search_evaluation=first_feasible_search_eval,
            first_feasible_total_constraint_evaluation=first_feasible_total_eval,
            first_feasible_generation=first_feasible_gen,
            final_hard_violations=final_h,
            final_soft_penalty=final_s,
            feasible=is_feasible,
            score=score,
            raw_soft_violations=raw_soft_cnt,
            search_hard_constraint_evaluations=self.evaluator.counters.search_hard_constraint_evaluations,
            search_soft_constraint_evaluations=self.evaluator.counters.search_soft_constraint_evaluations,
            search_constraint_evaluations=self.evaluator.counters.search_constraint_evaluations,
            internal_hard_constraint_evaluations=self.evaluator.counters.internal_hard_constraint_evaluations,
            internal_soft_constraint_evaluations=self.evaluator.counters.internal_soft_constraint_evaluations,
            internal_constraint_evaluations=self.evaluator.counters.internal_constraint_evaluations,
            reporting_hard_constraint_evaluations=self.evaluator.counters.reporting_hard_constraint_evaluations,
            reporting_soft_constraint_evaluations=self.evaluator.counters.reporting_soft_constraint_evaluations,
            reporting_constraint_evaluations=self.evaluator.counters.reporting_constraint_evaluations,
            total_hard_constraint_evaluations=self.evaluator.counters.hard_constraint_evaluations,
            total_soft_constraint_evaluations=self.evaluator.counters.soft_constraint_evaluations,
        )


        res_dict = metrics.to_dict()
        res_dict.update({
            "best_schedule": schedule,
            "best_score": score,
            "hard_violations": final_h,
            "soft_violations": final_s,
            "soft_penalty": final_s,
            "raw_soft_violations": raw_soft_cnt,
            "fitness_evaluations": 1,
            "run_metrics": metrics,
        })
        return res_dict
