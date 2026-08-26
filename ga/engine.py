import time
import random
from typing import List, Dict, Optional, Tuple, Set
from collections import defaultdict
import numpy as np

from domain import (
    Schedule, Gene, SchedulingActivity, Room, Timeslot, Lecturer,
    expand_scheduling_activities,
)
from constraints import ConstraintEvaluator, ScheduleRepairEngine, SoftConstraintConfig
from dataset import get_occupied_periods, is_valid_period_block, DatasetValidator
from evaluation.run_metrics import RunMetrics
from .operators import GAOperators


class GeneticAlgorithmEngine:
    def __init__(
        self,
        dataset: dict,
        pop_size: int = 60,
        hard_weight: int = 1000,
        soft_weight: int = 1,
        elite_count: int = 2,
        seed: Optional[int] = None,
        soft_config: Optional[SoftConstraintConfig] = None,
    ):
        DatasetValidator.validate(dataset)
        if not isinstance(pop_size, int) or pop_size < 2:
            raise ValueError(f"pop_size must be an integer >= 2, got {pop_size}")
        if not isinstance(elite_count, int) or not (1 <= elite_count < pop_size):
            raise ValueError(f"elite_count must satisfy 1 <= elite_count < pop_size ({pop_size}), got {elite_count}")

        self.dataset = dataset
        self.pop_size = pop_size
        self.hard_weight = hard_weight
        self.soft_weight = soft_weight
        self.elite_count = elite_count
        self.seed = seed

        self.evaluator = ConstraintEvaluator(dataset, soft_config=soft_config)
        self.repairer = ScheduleRepairEngine(dataset=dataset, evaluator=self.evaluator)

        self.sections: List[SchedulingActivity] = expand_scheduling_activities(
            dataset["course_sections"]
        )

        self.rooms: List[Room] = dataset["rooms"]
        self.timeslots: List[Timeslot] = dataset["timeslots"]
        self.lecturer_map: Dict[str, Lecturer] = {l.id: l for l in dataset.get("lecturers", [])}

        self.day_period_to_ts_id: Dict[Tuple[str, int], int] = {
            (ts.day, ts.period): ts.id for ts in self.timeslots
        }
        self.day_available_periods: Dict[str, Set[int]] = defaultdict(set)
        for ts in self.timeslots:
            self.day_available_periods[ts.day].add(ts.period)

    def create_random_schedule(self) -> Schedule:
        """Tạo nhiễm sắc thể Thời khóa biểu ban đầu ngẫu nhiên với cấu trúc hợp lệ."""

        genes = []
        section_days = defaultdict(set)
        for sec in self.sections:
            duration = getattr(sec, "duration_periods", 1)
            req_type = getattr(sec, "required_room_type", "NORMAL")
            lec = self.lecturer_map.get(sec.lecturer_id)
            avail_ts = getattr(lec, "available_timeslot_ids", None) if lec else None

            valid_rooms = [
                r for r in self.rooms
                if r.capacity >= sec.student_count and getattr(r, "room_type", "NORMAL") == req_type
            ] or [
                r for r in self.rooms if r.capacity >= sec.student_count
            ] or self.rooms

            valid_ts = [
                t for t in self.timeslots
                if is_valid_period_block(t.period, duration, self.day_available_periods.get(t.day))
                and (avail_ts is None or all(self.day_period_to_ts_id.get((t.day, p)) in avail_ts for p in get_occupied_periods(t.period, duration)))
            ] or [
                t for t in self.timeslots
                if is_valid_period_block(t.period, duration, self.day_available_periods.get(t.day))
            ]

            if not valid_ts:
                raise ValueError(f"No valid timeslot block of duration {duration} available for section '{sec.section_id}'.")

            unused_day_ts = [
                ts for ts in valid_ts if ts.day not in section_days[sec.section_id]
            ]
            if unused_day_ts:
                valid_ts = unused_day_ts

            r = random.choice(valid_rooms)
            ts = random.choice(valid_ts)
            genes.append(Gene(activity_id=sec.activity_id, room_id=r.id, timeslot_id=ts.id))
            section_days[sec.section_id].add(ts.day)

        sched = Schedule(genes=genes)
        if not GAOperators.validate_chromosome(sched, self.dataset):
            raise ValueError("Chromosome integrity validation failed during random schedule creation.")
        return sched

    def run(
        self,
        generations: int = 100,
        crossover_rate: float = 0.8,
        mutation_rate: float = 0.2,
        use_repair: bool = True,
        evaluation_budget: Optional[int] = None,
        seed: Optional[int] = None,
        use_soft_local_search: bool = False,
        soft_local_search_max_passes: int = 2,
        soft_local_search_max_candidate_checks: int = 5000,
        use_guided_mutation: bool = False,
        guided_mutation_probability: float = 0.8,
    ) -> dict:

        if evaluation_budget is not None and evaluation_budget < self.pop_size:
            raise ValueError(f"evaluation_budget ({evaluation_budget}) cannot be smaller than population_size ({self.pop_size}).")

        run_seed = seed if seed is not None else self.seed
        if run_seed is not None:
            random.seed(run_seed)
            np.random.seed(run_seed)

        start_time = time.perf_counter()


        # Reset evaluator counters and repair stats per run
        self.evaluator.counters.reset()
        self.repairer.stats.reset()
        self.repairer.evaluator = self.evaluator


        population = [self.create_random_schedule() for _ in range(self.pop_size)]
        history = []
        evaluation_count = 0

        best_schedule = None
        best_hard = float('inf')
        best_soft = float('inf')
        best_score = float('inf')

        first_feasible_time: Optional[float] = None
        first_feasible_search_eval: Optional[int] = None
        first_feasible_total_eval: Optional[int] = None
        first_feasible_gen: Optional[int] = None

        sgm = None
        if use_guided_mutation:
            from .soft_guided_mutation import SoftGuidedMutation
            sgm = SoftGuidedMutation(self.dataset, evaluator=self.evaluator)

        guided_mutation_stats = {
            "guided_mutation_calls": 0,
            "guided_mutation_attempts": 0,
            "guided_mutation_successes": 0,
            "guided_mutation_fallbacks": 0,
        }

        # When a search budget is supplied it is the authoritative stopping
        # contract. Ensure the generation loop has enough iterations to spend
        # it even when the caller configured fewer generations than required.
        generation_limit = generations
        if evaluation_budget is not None:
            generations_for_budget = (
                evaluation_budget + self.pop_size - 1
            ) // self.pop_size
            generation_limit = max(generations, generations_for_budget)

        for gen in range(generation_limit):
            if evaluation_budget is not None and evaluation_count >= evaluation_budget:
                break

            scores, hard_v, soft_v = [], [], []

            for ind in population:
                if evaluation_budget is not None and evaluation_count >= evaluation_budget:
                    break

                weighted_score, h, s = self.evaluator.calculate_fitness(
                    ind, self.hard_weight, self.soft_weight, is_search_eval=True
                )
                evaluation_count += 1
                scores.append(weighted_score)
                hard_v.append(h)
                soft_v.append(s)

                if h == 0 and first_feasible_time is None:
                    first_feasible_time = time.perf_counter() - start_time
                    first_feasible_search_eval = evaluation_count
                    first_feasible_total_eval = self.evaluator.counters.total_constraint_evaluations
                    first_feasible_gen = gen

            if not scores:
                break

            # Primary selection uses Lexicographic Tuple: (hard_violations, soft_penalty)
            best_idx = min(
                range(len(scores)),
                key=lambda i: (hard_v[i], soft_v[i]),
            )

            if (hard_v[best_idx], soft_v[best_idx]) < (best_hard, best_soft):
                best_hard = hard_v[best_idx]
                best_soft = soft_v[best_idx]
                best_score = scores[best_idx]
                best_schedule = Schedule(genes=[Gene(g.section_id, g.room_id, g.timeslot_id) for g in population[best_idx].genes])

            elapsed_now = time.perf_counter() - start_time
            history.append({
                "generation": gen,
                "elapsed_seconds": round(elapsed_now, 4),
                "runtime_seconds": round(elapsed_now, 4),  # legacy alias
                "fitness_evaluations": evaluation_count,
                "best_score": best_score,
                "best_hard": best_hard,
                "best_soft_penalty": best_soft,
                "avg_score": sum(scores) / len(scores)
            })

            # An unbudgeted production run may stop at a perfect solution. A
            # benchmark run must still consume its declared budget so methods
            # remain comparable and validate_search_budget() cannot fail.
            if best_hard == 0 and best_soft == 0 and evaluation_budget is None:
                break

            if evaluation_budget is not None and evaluation_count >= evaluation_budget:
                break

            # Lexicographic sorting for elitism and parent tournament selection
            sorted_indices = sorted(
                range(len(scores)),
                key=lambda i: (hard_v[i], soft_v[i])
            )

            # Preserve top self.elite_count schedules
            new_pop = [
                Schedule(genes=[Gene(g.section_id, g.room_id, g.timeslot_id) for g in population[sorted_indices[i]].genes])
                for i in range(self.elite_count)
            ]

            # Lexicographic fitness keys for tournament selection: (hard_violations, soft_penalty)
            fitness_keys = [(hard_v[i], soft_v[i]) for i in range(len(scores))]

            sgm = None
            if use_guided_mutation:
                from .soft_guided_mutation import SoftGuidedMutation
                sgm = SoftGuidedMutation(self.dataset, evaluator=self.evaluator)

            guided_mutation_stats = {
                "guided_mutation_calls": 0,
                "guided_mutation_attempts": 0,
                "guided_mutation_successes": 0,
                "guided_mutation_fallbacks": 0,
            }

            while len(new_pop) < self.pop_size:
                p1 = GAOperators.tournament_selection(population[:len(scores)], fitness_keys)
                p2 = GAOperators.tournament_selection(population[:len(scores)], fitness_keys)

                if random.random() < crossover_rate:
                    c1, c2 = GAOperators.crossover(p1, p2)
                else:
                    c1 = Schedule(genes=[Gene(g.section_id, g.room_id, g.timeslot_id) for g in p1.genes])
                    c2 = Schedule(genes=[Gene(g.section_id, g.room_id, g.timeslot_id) for g in p2.genes])

                if use_guided_mutation and sgm is not None:
                    c1, s1_st = sgm.mutate(c1, mutation_rate, guided_mutation_probability)
                    c2, s2_st = sgm.mutate(c2, mutation_rate, guided_mutation_probability)
                    guided_mutation_stats["guided_mutation_calls"] += (s1_st["guided_mutation_calls"] + s2_st["guided_mutation_calls"])
                    guided_mutation_stats["guided_mutation_attempts"] += (s1_st["guided_mutation_attempts"] + s2_st["guided_mutation_attempts"])
                    guided_mutation_stats["guided_mutation_successes"] += (s1_st["guided_mutation_successes"] + s2_st["guided_mutation_successes"])
                    guided_mutation_stats["guided_mutation_fallbacks"] += (s1_st["guided_mutation_fallbacks"] + s2_st["guided_mutation_fallbacks"])
                else:
                    c1 = GAOperators.mutate(c1, self.rooms, self.timeslots, mutation_rate,
                        dataset=self.dataset, day_period_to_ts_id=self.day_period_to_ts_id,
                        day_available_periods=self.day_available_periods)
                    c2 = GAOperators.mutate(c2, self.rooms, self.timeslots, mutation_rate,
                        dataset=self.dataset, day_period_to_ts_id=self.day_period_to_ts_id,
                        day_available_periods=self.day_available_periods)

                if use_repair:
                    c1_res = self.repairer.repair(c1)
                    c1 = c1_res.schedule
                    c2_res = self.repairer.repair(c2)
                    c2 = c2_res.schedule

                if not GAOperators.validate_chromosome(c1, self.dataset):
                    raise ValueError("Offspring 1 failed chromosome integrity validation.")
                if not GAOperators.validate_chromosome(c2, self.dataset):
                    raise ValueError("Offspring 2 failed chromosome integrity validation.")

                new_pop.extend([c1, c2])

            population = new_pop[:self.pop_size]

        # Record soft penalty before SLS intervention
        soft_before_sls = best_soft
        soft_after_sls = best_soft

        # Post-search Soft Local Search (only on feasible best schedule)
        soft_ls_stats = {
            "soft_ls_calls": 0,
            "soft_ls_initial_penalty": 0,
            "soft_ls_final_penalty": 0,
            "soft_ls_improvement": 0,
            "soft_ls_candidate_checks": 0,
            "soft_ls_accepted_moves": 0,
            "soft_ls_runtime_seconds": 0.0,
        }
        if best_hard == 0 and use_soft_local_search and best_schedule is not None:
            from .soft_local_search import SoftLocalSearch
            sls = SoftLocalSearch(
                dataset=self.dataset,
                evaluator=self.evaluator,
                max_passes=soft_local_search_max_passes,
                max_candidate_checks=soft_local_search_max_candidate_checks,
            )
            improved_schedule, soft_ls_stats = sls.optimize(best_schedule)

            # Independent Re-evaluation
            imp_h, _ = self.evaluator.evaluate_hard(improved_schedule, category="internal")
            imp_s, _ = self.evaluator.evaluate_soft(improved_schedule, category="internal")

            # Invariant assertion check: Hard must remain 0 and Soft must not increase
            if imp_h == 0 and imp_s <= best_soft:
                best_schedule = improved_schedule
                best_soft = imp_s
                best_score = float((best_hard * self.hard_weight) + (best_soft * self.soft_weight))

        soft_after_sls = best_soft

        runtime_seconds = time.perf_counter() - start_time
        _, h_details = self.evaluator.evaluate_hard(best_schedule, category="reporting")
        _, s_details = self.evaluator.evaluate_soft(best_schedule, category="reporting")
        raw_soft_cnt = sum(s_details.values())

        method_name = "Hybrid GA + Repair" if use_repair else "GA without Repair"
        total_candidate_checks = self.evaluator.counters.candidate_checks + self.repairer.stats.candidate_checks + soft_ls_stats["soft_ls_candidate_checks"]

        metrics = RunMetrics(
            method=method_name,
            seed=run_seed,
            runtime_seconds=runtime_seconds,
            time_to_first_feasible_seconds=first_feasible_time,
            search_fitness_evaluations=self.evaluator.counters.search_fitness_evaluations,
            hard_constraint_evaluations=self.evaluator.counters.hard_constraint_evaluations,
            soft_constraint_evaluations=self.evaluator.counters.soft_constraint_evaluations,
            total_constraint_evaluations=self.evaluator.counters.total_constraint_evaluations,
            candidate_checks=total_candidate_checks,
            repair_calls=self.repairer.stats.repair_calls,
            repair_improved=self.repairer.stats.repair_improved,
            repair_unchanged=self.repairer.stats.repair_unchanged,
            repair_failed=self.repairer.stats.repair_failed,
            first_feasible_search_evaluation=first_feasible_search_eval,
            first_feasible_total_constraint_evaluation=first_feasible_total_eval,
            first_feasible_generation=first_feasible_gen,
            final_hard_violations=best_hard,
            final_soft_penalty=best_soft,
            feasible=(best_hard == 0),
            score=best_score,
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
            soft_ls_calls=soft_ls_stats["soft_ls_calls"],
            soft_ls_candidate_checks=soft_ls_stats["soft_ls_candidate_checks"],
            soft_ls_accepted_moves=soft_ls_stats["soft_ls_accepted_moves"],
            soft_ls_improvement=soft_ls_stats["soft_ls_improvement"],
            soft_ls_runtime_seconds=soft_ls_stats["soft_ls_runtime_seconds"],
            soft_before_sls=soft_before_sls,
            soft_after_sls=soft_after_sls,
            guided_mutation_calls=guided_mutation_stats.get("guided_mutation_calls", 0),
            guided_mutation_attempts=guided_mutation_stats.get("guided_mutation_attempts", 0),
            guided_mutation_successes=guided_mutation_stats.get("guided_mutation_successes", 0),
            guided_mutation_fallbacks=guided_mutation_stats.get("guided_mutation_fallbacks", 0),
        )



        res_dict = metrics.to_dict()
        res_dict.update({
            "best_schedule": best_schedule,
            "best_score": best_score,
            "hard_violations": best_hard,
            "soft_violations": best_soft,
            "soft_penalty": best_soft,
            "fitness_evaluations": evaluation_count,
            "hard_details": h_details,
            "soft_details": s_details,
            "history": history,
            "use_repair": use_repair,
            "use_soft_local_search": use_soft_local_search,
            "soft_local_search_stats": soft_ls_stats,
            "repair_stats": self.repairer.stats.to_dict(),
            "run_metrics": metrics,
        })
        return res_dict


