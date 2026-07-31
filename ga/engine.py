"""Genetic Algorithm Engine Module.

Core execution engine for course timetabling optimization using Genetic Algorithm,
integrating Lexicographic Selection, Elitism, and Constraint Repair Engine.
"""

import random
from typing import List, Dict, Optional, Tuple, Set
from collections import defaultdict
from domain import Schedule, Gene, CourseSection, Room, Timeslot, Lecturer
from constraints import ConstraintEvaluator, ScheduleRepairEngine
from dataset import get_occupied_periods, is_valid_period_block, DatasetValidator
from .operators import GAOperators


class GeneticAlgorithmEngine:
    """Genetic Algorithm Engine for automatic course schedule optimization."""

    def __init__(
        self,
        dataset: dict,
        pop_size: int = 60,
        hard_weight: int = 1000,
        soft_weight: int = 1,
        elite_count: int = 2,
    ):
        """Initialize GA Engine with dataset parameters and elitism settings.

        Args:
            dataset: Validated dictionary containing course_sections, rooms, timeslots, etc.
            pop_size: Population size (number of schedules per generation).
            hard_weight: Weight multiplier for hard violations in summary score.
            soft_weight: Weight multiplier for soft penalty in summary score.
            elite_count: Number of best elite schedules preserved across generations.
        """
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
        evaluation_budget: Optional[int] = None
    ) -> dict:
        """Run Genetic Algorithm optimization loop.

        Primary selection & sorting uses Lexicographic Comparison:
          (hard_violations, soft_penalty)
        Hard violations have absolute priority (must reach 0 for feasibility).
        Weighted score is computed as (hard_violations * hard_weight + soft_penalty * soft_weight) for reporting.
        """
        if evaluation_budget is not None and evaluation_budget < self.pop_size:
            raise ValueError(f"evaluation_budget ({evaluation_budget}) cannot be smaller than population_size ({self.pop_size}).")

        self.repairer.stats.reset()
        population = [self.create_random_schedule() for _ in range(self.pop_size)]
        history = []
        evaluation_count = 0

        best_schedule = None
        best_hard = float('inf')
        best_soft = float('inf')
        best_score = float('inf')

        for gen in range(generations):
            if evaluation_budget is not None and evaluation_count >= evaluation_budget:
                break

            scores, hard_v, soft_v = [], [], []

            for ind in population:
                if evaluation_budget is not None and evaluation_count >= evaluation_budget:
                    break

                weighted_score, h, s = self.evaluator.calculate_fitness(ind, self.hard_weight, self.soft_weight)
                evaluation_count += 1
                scores.append(weighted_score)
                hard_v.append(h)
                soft_v.append(s)

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

            history.append({
                "generation": gen,
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

        _, h_details = self.evaluator.evaluate_hard(best_schedule)
        _, s_details = self.evaluator.evaluate_soft(best_schedule)
        raw_soft_cnt = sum(s_details.values())

        return {
            "best_schedule": best_schedule,
            "best_score": best_score,
            "hard_violations": best_hard,
            "soft_violations": best_soft,
            "soft_penalty": best_soft,
            "raw_soft_violations": raw_soft_cnt,
            "fitness_evaluations": evaluation_count,
            "hard_details": h_details,
            "soft_details": s_details,
            "history": history,
            "use_repair": use_repair,
            "repair_stats": self.repairer.stats.to_dict()
        }

