import time
import random
from typing import List, Dict, Optional, Tuple, Set
from collections import defaultdict
import numpy as np

from domain import Schedule, Gene, CourseSection, Room, Timeslot, Lecturer
from constraints import ConstraintEvaluator, ScheduleRepairEngine
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

        self.evaluator = ConstraintEvaluator(dataset)
        self.repairer = ScheduleRepairEngine(dataset=dataset, evaluator=self.evaluator)

        self.sections: List[CourseSection] = dataset["course_sections"]

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
        """Create a randomized initial valid-structured Schedule chromosome."""
        genes = []
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

            r = random.choice(valid_rooms)
            ts = random.choice(valid_ts)
            genes.append(Gene(section_id=sec.section_id, room_id=r.id, timeslot_id=ts.id))

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

        for gen in range(generations):
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

            if best_hard == 0 and best_soft == 0:
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

            while len(new_pop) < self.pop_size:
                p1 = GAOperators.tournament_selection(population[:len(scores)], fitness_keys)
                p2 = GAOperators.tournament_selection(population[:len(scores)], fitness_keys)

                if random.random() < crossover_rate:
                    c1, c2 = GAOperators.crossover(p1, p2)
                else:
                    c1 = Schedule(genes=[Gene(g.section_id, g.room_id, g.timeslot_id) for g in p1.genes])
                    c2 = Schedule(genes=[Gene(g.section_id, g.room_id, g.timeslot_id) for g in p2.genes])

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

        runtime_seconds = time.perf_counter() - start_time
        _, h_details = self.evaluator.evaluate_hard(best_schedule, category="reporting")
        _, s_details = self.evaluator.evaluate_soft(best_schedule, category="reporting")
        raw_soft_cnt = sum(s_details.values())

        method_name = "Hybrid GA + Repair" if use_repair else "GA without Repair"
        total_candidate_checks = self.evaluator.counters.candidate_checks + self.repairer.stats.candidate_checks

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
            "repair_stats": self.repairer.stats.to_dict(),
            "run_metrics": metrics,
        })
        return res_dict



