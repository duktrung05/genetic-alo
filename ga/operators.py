import random
import copy
from typing import List, Tuple
from domain import Schedule, Gene, Room, Timeslot

class GAOperators:
    @staticmethod
    def validate_chromosome(schedule: Schedule, dataset: dict) -> bool:
        """Kiểm tra tính toàn vẹn của chromosome (Schedule)."""
        if not isinstance(schedule, Schedule) or not isinstance(schedule.genes, list):
            return False
        
        sections = dataset.get("course_sections", [])
        rooms = dataset.get("rooms", [])
        timeslots = dataset.get("timeslots", [])

        if len(schedule.genes) != len(sections):
            return False

        valid_section_ids = {s.section_id for s in sections}
        valid_room_ids = {r.id for r in rooms}
        valid_timeslot_ids = {t.id for t in timeslots}

        seen_sections = set()
        for gene in schedule.genes:
            if gene.section_id not in valid_section_ids or gene.section_id in seen_sections:
                return False
            if gene.room_id not in valid_room_ids:
                return False
            if gene.timeslot_id not in valid_timeslot_ids:
                return False
            seen_sections.add(gene.section_id)

        return len(seen_sections) == len(valid_section_ids)

    @staticmethod
    def tournament_selection(population: List[Schedule], fitness_keys: List, k: int = 3) -> Schedule:
        selected_indices = random.sample(range(len(population)), k)
        best_idx = selected_indices[0]
        for idx in selected_indices[1:]:
            if fitness_keys[idx] < fitness_keys[best_idx]:
                best_idx = idx
        return population[best_idx]

    @staticmethod
    def crossover(parent1: Schedule, parent2: Schedule) -> Tuple[Schedule, Schedule]:
        c1_genes = []
        c2_genes = []
        point = random.randint(1, len(parent1.genes) - 1)

        for i in range(len(parent1.genes)):
            if i < point:
                c1_genes.append(copy.deepcopy(parent1.genes[i]))
                c2_genes.append(copy.deepcopy(parent2.genes[i]))
            else:
                c1_genes.append(copy.deepcopy(parent2.genes[i]))
                c2_genes.append(copy.deepcopy(parent1.genes[i]))

        return Schedule(genes=c1_genes), Schedule(genes=c2_genes)

    @staticmethod
    def mutate(schedule: Schedule, rooms: List[Room], timeslots: List[Timeslot], mutation_rate: float = 0.2) -> Schedule:
        mutated = copy.deepcopy(schedule)
        for gene in mutated.genes:
            if random.random() < mutation_rate:
                if random.random() < 0.5:
                    gene.room_id = random.choice(rooms).id
                else:
                    gene.timeslot_id = random.choice(timeslots).id
        return mutated

