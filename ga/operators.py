import random
from typing import List, Tuple, Optional, Dict, Set
from collections import defaultdict
from domain import Schedule, Gene, Room, Timeslot, CourseSection, Lecturer
from dataset import get_occupied_periods, is_valid_period_block


class GAOperators:
    @staticmethod
    def validate_chromosome(schedule: Schedule, dataset: dict) -> bool:
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
    def tournament_selection(population: List[Schedule], fitness_keys: List[Tuple[int, int]], k: int = 3) -> Schedule:
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
            g1 = parent1.genes[i]
            g2 = parent2.genes[i]
            if i < point:
                c1_genes.append(Gene(section_id=g1.section_id, room_id=g1.room_id, timeslot_id=g1.timeslot_id))
                c2_genes.append(Gene(section_id=g2.section_id, room_id=g2.room_id, timeslot_id=g2.timeslot_id))
            else:
                c1_genes.append(Gene(section_id=g2.section_id, room_id=g2.room_id, timeslot_id=g2.timeslot_id))
                c2_genes.append(Gene(section_id=g1.section_id, room_id=g1.room_id, timeslot_id=g1.timeslot_id))

        return Schedule(genes=c1_genes), Schedule(genes=c2_genes)

    @staticmethod
    def mutate(
        schedule: Schedule,
        rooms: List[Room],
        timeslots: List[Timeslot],
        mutation_rate: float = 0.2,
        dataset: Optional[dict] = None,
        day_period_to_ts_id: Optional[Dict[Tuple[str, int], int]] = None,
        day_available_periods: Optional[Dict[str, Set[int]]] = None
    ) -> Schedule:
        """Đột biến các gen trong thời khóa biểu theo xác suất quy định."""

        mutated = Schedule(genes=[
            Gene(section_id=g.section_id, room_id=g.room_id, timeslot_id=g.timeslot_id)
            for g in schedule.genes
        ])
        sections_map = {s.section_id: s for s in dataset.get("course_sections", [])} if dataset else {}
        lecturer_map = {l.id: l for l in dataset.get("lecturers", [])} if dataset else {}

        if day_period_to_ts_id is None:
            day_period_to_ts_id = {
                (ts.day, ts.period): ts.id for ts in timeslots
            }
        if day_available_periods is None:
            day_available_periods = defaultdict(set)
            for ts in timeslots:
                day_available_periods[ts.day].add(ts.period)

        for gene in mutated.genes:
            if random.random() < mutation_rate:
                sec = sections_map.get(gene.section_id)
                duration = getattr(sec, "duration_periods", 1) if sec else 1
                req_type = getattr(sec, "required_room_type", "NORMAL") if sec else "NORMAL"
                student_count = getattr(sec, "student_count", 0) if sec else 0
                lec = lecturer_map.get(sec.lecturer_id) if sec else None
                avail_ts = getattr(lec, "available_timeslot_ids", None) if lec else None

                if random.random() < 0.5:
                    valid_rooms = [
                        r for r in rooms
                        if r.capacity >= student_count and getattr(r, "room_type", "NORMAL") == req_type
                    ] or [
                        r for r in rooms if r.capacity >= student_count
                    ] or rooms
                    gene.room_id = random.choice(valid_rooms).id
                else:
                    preferred_ts = [
                        t for t in timeslots
                        if is_valid_period_block(t.period, duration, day_available_periods.get(t.day))
                        and (avail_ts is None or all(day_period_to_ts_id.get((t.day, p)) in avail_ts for p in get_occupied_periods(t.period, duration)))
                    ]
                    block_valid_ts = [
                        t for t in timeslots
                        if is_valid_period_block(t.period, duration, day_available_periods.get(t.day))
                    ]

                    if preferred_ts:
                        gene.timeslot_id = random.choice(preferred_ts).id
                    elif block_valid_ts:
                        gene.timeslot_id = random.choice(block_valid_ts).id
                    else:
                        cur_ts = next((t for t in timeslots if t.id == gene.timeslot_id), None)
                        if cur_ts and is_valid_period_block(cur_ts.period, duration, day_available_periods.get(cur_ts.day)):
                            pass
                        else:
                            raise ValueError(f"No valid timeslot block of duration {duration} available for section '{gene.section_id}'.")
        return mutated
