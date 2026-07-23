import random
import copy
from typing import List, Dict, Optional
from domain import Schedule, Gene, CourseSection, Room, Timeslot
from constraints import ConstraintEvaluator, ScheduleRepairEngine
from .operators import GAOperators

class GeneticAlgorithmEngine:
    def __init__(self, dataset: dict, pop_size: int = 60, hard_weight: int = 1000, soft_weight: int = 1):
        self.dataset = dataset
        self.pop_size = pop_size
        self.hard_weight = hard_weight
        self.soft_weight = soft_weight

        self.evaluator = ConstraintEvaluator(dataset)
        self.repairer = ScheduleRepairEngine(dataset)

        self.sections: List[CourseSection] = dataset["course_sections"]
        self.rooms: List[Room] = dataset["rooms"]
        self.timeslots: List[Timeslot] = dataset["timeslots"]

    def create_random_schedule(self) -> Schedule:
        genes = []
        for sec in self.sections:
            r = random.choice(self.rooms)
            ts = random.choice(self.timeslots)
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
        if evaluation_budget is not None and evaluation_budget < self.pop_size:
            raise ValueError(f"evaluation_budget ({evaluation_budget}) cannot be smaller than population_size ({self.pop_size}).")

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

                if not GAOperators.validate_chromosome(ind, self.dataset):
                    raise ValueError(f"Chromosome integrity validation failed at generation {gen}.")

                score, h, s = self.evaluator.calculate_fitness(ind, self.hard_weight, self.soft_weight)
                evaluation_count += 1
                scores.append(score)
                hard_v.append(h)
                soft_v.append(s)

            if not scores:
                break

            best_idx = min(
                range(len(scores)),
                key=lambda i: (hard_v[i], soft_v[i]),
            )

            if (hard_v[best_idx], soft_v[best_idx]) < (best_hard, best_soft):
                best_hard = hard_v[best_idx]
                best_soft = soft_v[best_idx]
                best_score = scores[best_idx]
                best_schedule = copy.deepcopy(population[best_idx])

            history.append({
                "generation": gen,
                "fitness_evaluations": evaluation_count,
                "best_score": best_score,
                "best_hard": best_hard,
                "best_soft": best_soft,
                "avg_score": sum(scores) / len(scores)
            })

            if best_hard == 0 and best_soft == 0:
                break

            if evaluation_budget is not None and evaluation_count >= evaluation_budget:
                break

            sorted_indices = sorted(
                range(len(scores)),
                key=lambda i: (hard_v[i], soft_v[i])
            )
            new_pop = [
                copy.deepcopy(population[sorted_indices[0]]),
                copy.deepcopy(population[sorted_indices[1]])
            ]

            fitness_keys = [(hard_v[i], soft_v[i]) for i in range(len(scores))]

            while len(new_pop) < self.pop_size:
                p1 = GAOperators.tournament_selection(population[:len(scores)], fitness_keys)
                p2 = GAOperators.tournament_selection(population[:len(scores)], fitness_keys)

                if random.random() < crossover_rate:
                    c1, c2 = GAOperators.crossover(p1, p2)
                else:
                    c1, c2 = copy.deepcopy(p1), copy.deepcopy(p2)

                c1 = GAOperators.mutate(c1, self.rooms, self.timeslots, mutation_rate)
                c2 = GAOperators.mutate(c2, self.rooms, self.timeslots, mutation_rate)

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
            "use_repair": use_repair
        }
