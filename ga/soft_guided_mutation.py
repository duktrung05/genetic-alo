"""Soft-Guided Mutation Module for Hybrid Genetic Algorithm.

Implements stochastic guided mutation that uses soft-constraint violation breakdown
(S1-S5) to bias gene mutations towards sections with high weighted soft penalty,
while maintaining population diversity via random fallback and stochastic shortlist selection.
"""

from __future__ import annotations
import random
from typing import Dict, List, Set, Tuple, Optional, Any
from collections import defaultdict

from domain import Schedule, Gene, CourseSection, Room, Timeslot, Lecturer
from dataset import get_occupied_periods, is_valid_period_block
from constraints.evaluator import ConstraintEvaluator
from ga.operators import GAOperators


class SoftGuidedMutation:
    """Stochastic soft-constraint guided mutation operator for GA Engine."""

    def __init__(
        self,
        dataset: dict,
        evaluator: Optional[ConstraintEvaluator] = None,
    ) -> None:
        self.dataset = dataset
        self.evaluator = evaluator if evaluator is not None else ConstraintEvaluator(dataset)

        self.sections: List[CourseSection] = dataset["course_sections"]
        self.section_map: Dict[str, CourseSection] = {s.section_id: s for s in self.sections}
        self.rooms: List[Room] = dataset["rooms"]
        self.room_map: Dict[str, Room] = {r.id: r for r in self.rooms}
        self.timeslots: List[Timeslot] = dataset["timeslots"]
        self.timeslot_map: Dict[int, Timeslot] = {t.id: t for t in self.timeslots}
        self.lecturers: List[Lecturer] = dataset.get("lecturers", [])
        self.lecturer_map: Dict[str, Lecturer] = {l.id: l for l in self.lecturers}

        self.day_period_to_ts_id: Dict[Tuple[str, int], int] = {
            (ts.day, ts.period): ts.id for ts in self.timeslots
        }
        self.day_available_periods: Dict[str, Set[int]] = defaultdict(set)
        for ts in self.timeslots:
            self.day_available_periods[ts.day].add(ts.period)

        # Index sections by group and lecturer
        self.sections_by_group: Dict[str, List[CourseSection]] = defaultdict(list)
        self.sections_by_lecturer: Dict[str, List[CourseSection]] = defaultdict(list)
        for sec in self.sections:
            if sec.group_id:
                self.sections_by_group[sec.group_id].append(sec)
            if sec.lecturer_id:
                self.sections_by_lecturer[sec.lecturer_id].append(sec)

        # Pre-cache valid candidate rooms per section sorted by seat waste (capacity - student_count)
        self._valid_rooms_by_waste: Dict[str, List[Room]] = {}
        for sec in self.sections:
            req_type = getattr(sec, "required_room_type", "NORMAL")
            st_count = sec.student_count
            valid = [
                r for r in self.rooms
                if r.capacity >= st_count and getattr(r, "room_type", "NORMAL") == req_type
            ] or [
                r for r in self.rooms if r.capacity >= st_count
            ] or self.rooms

            # Sort candidate rooms ascending by seat waste: (r.capacity - st_count, r.id)
            self._valid_rooms_by_waste[sec.section_id] = sorted(
                valid, key=lambda r: (r.capacity - st_count, r.id)
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

    def mutate(
        self,
        schedule: Schedule,
        mutation_rate: float = 0.2,
        guided_probability: float = 0.8,
        rng: Optional[random.Random] = None,
    ) -> Tuple[Schedule, Dict[str, Any]]:
        """Perform Soft-Guided Mutation on schedule.

        Returns (mutated_schedule, stats_dict).
        """
        random_gen = rng if rng is not None else random

        stats: Dict[str, Any] = {
            "guided_mutation_calls": 1,
            "guided_mutation_attempts": 0,
            "guided_mutation_successes": 0,
            "guided_mutation_fallbacks": 0,
            "guided_targets_S1": 0,
            "guided_targets_S2": 0,
            "guided_targets_S3": 0,
            "guided_targets_S4": 0,
            "guided_targets_S5": 0,
        }

        # Clone schedule to prevent aliasing
        mutated = Schedule(genes=[
            Gene(g.section_id, g.room_id, g.timeslot_id)
            for g in schedule.genes
        ])

        # Evaluate soft breakdown
        unified = self.evaluator.evaluate_unified(schedule)
        instance_items = unified.instance_violations

        # Build guided targets and shortlisted candidates per section
        # Format: section_id -> list of candidate tuples: ("room", room_id) or ("timeslot", ts_id)
        guided_targets: Dict[str, List[Tuple[str, Any]]] = defaultdict(list)
        rule_counts: Dict[str, int] = defaultdict(int)

        for item in instance_items:
            key = item.get("constraint_key")
            sec_ids_raw = item.get("section_ids") or item.get("section_id") or ""
            sec_id_list = [s.strip() for s in sec_ids_raw.split(",") if s.strip() and s.strip() in self.section_map]

            # --- S4: Room Seat Waste ---
            if key == "room_seat_waste":
                for sec_id in sec_id_list:
                    candidate_rooms = self._valid_rooms_by_waste.get(sec_id, [])
                    # Top 3 rooms with minimum seat waste
                    top_rooms = candidate_rooms[:3]
                    for r in top_rooms:
                        if r.id != item.get("room_id"):
                            guided_targets[sec_id].append(("room", r.id))
                    if guided_targets[sec_id]:
                        rule_counts["S4"] += 1

            # --- S2: Late Day Periods ---
            elif key == "late_day_periods":
                for sec_id in sec_id_list:
                    sec = self.section_map[sec_id]
                    dur = getattr(sec, "duration_periods", 1)
                    lec = self.lecturer_map.get(sec.lecturer_id)
                    avail_ts = getattr(lec, "available_timeslot_ids", None) if lec else None

                    valid_ts = [
                        t for t in self._valid_ts_by_duration.get(dur, [])
                        if t.session in ("morning", "afternoon")
                        and (avail_ts is None or all(
                            self.day_period_to_ts_id.get((t.day, p)) in avail_ts
                            for p in get_occupied_periods(t.period, dur)
                        ))
                    ]
                    for t in valid_ts[:5]:
                        guided_targets[sec_id].append(("timeslot", t.id))
                    if guided_targets[sec_id]:
                        rule_counts["S2"] += 1

            # --- S3: Preferred Shift Mismatch ---
            elif key == "preferred_shift_mismatch":
                for sec_id in sec_id_list:
                    sec = self.section_map[sec_id]
                    pref_shift = getattr(sec, "preferred_shift", None) or item.get("preferred_shift")
                    if pref_shift:
                        dur = getattr(sec, "duration_periods", 1)
                        lec = self.lecturer_map.get(sec.lecturer_id)
                        avail_ts = getattr(lec, "available_timeslot_ids", None) if lec else None

                        valid_ts = [
                            t for t in self._valid_ts_by_duration.get(dur, [])
                            if t.session == pref_shift
                            and (avail_ts is None or all(
                                self.day_period_to_ts_id.get((t.day, p)) in avail_ts
                                for p in get_occupied_periods(t.period, dur)
                            ))
                        ]
                        for t in valid_ts[:5]:
                            guided_targets[sec_id].append(("timeslot", t.id))
                        if guided_targets[sec_id]:
                            rule_counts["S3"] += 1

            # --- S1: Weekly Distribution ---
            elif key == "weekly_distribution":
                grp_id = item.get("student_group_ids") or item.get("group_id")
                overloaded_day = item.get("day")
                if grp_id and grp_id in self.sections_by_group:
                    group_sections = self.sections_by_group[grp_id]
                    for sec in group_sections:
                        dur = getattr(sec, "duration_periods", 1)
                        lec = self.lecturer_map.get(sec.lecturer_id)
                        avail_ts = getattr(lec, "available_timeslot_ids", None) if lec else None

                        alt_ts = [
                            t for t in self._valid_ts_by_duration.get(dur, [])
                            if t.day != overloaded_day
                            and (avail_ts is None or all(
                                self.day_period_to_ts_id.get((t.day, p)) in avail_ts
                                for p in get_occupied_periods(t.period, dur)
                            ))
                        ]
                        for t in alt_ts[:3]:
                            guided_targets[sec.section_id].append(("timeslot", t.id))
                        if guided_targets[sec.section_id]:
                            rule_counts["S1"] += 1

            # --- S5: Consecutive Cross-Campus ---
            elif key == "consecutive_cross_campus":
                for sec_id in sec_id_list:
                    sec = self.section_map.get(sec_id)
                    target_campus = getattr(sec, "preferred_campus_id", None) or "CS1"
                    cand_rooms = [
                        r for r in self._valid_rooms_by_waste.get(sec_id, [])
                        if getattr(r, "campus_id", None) == target_campus
                    ]
                    for r in cand_rooms[:2]:
                        guided_targets[sec_id].append(("room", r.id))
                    if guided_targets[sec_id]:
                        rule_counts["S5"] += 1


        stats["guided_targets_S1"] = rule_counts["S1"]
        stats["guided_targets_S2"] = rule_counts["S2"]
        stats["guided_targets_S3"] = rule_counts["S3"]
        stats["guided_targets_S4"] = rule_counts["S4"]
        stats["guided_targets_S5"] = rule_counts["S5"]

        # Mutate genes with per-gene probability mutation_rate
        for gene in mutated.genes:
            if random_gen.random() < mutation_rate:
                stats["guided_mutation_attempts"] += 1
                sec_id = gene.section_id
                candidates = guided_targets.get(sec_id, [])

                # Decide whether to use Guided Mutation or Fallback Random Mutation
                if candidates and (random_gen.random() < guided_probability):
                    # Pick stochastic candidate from shortlist
                    target_type, target_val = random_gen.choice(candidates)
                    if target_type == "room":
                        gene.room_id = target_val
                    elif target_type == "timeslot":
                        gene.timeslot_id = target_val
                    stats["guided_mutation_successes"] += 1
                else:
                    # Fallback Random Mutation (50% room, 50% timeslot)
                    sec = self.section_map.get(sec_id)
                    dur = getattr(sec, "duration_periods", 1) if sec else 1
                    req_type = getattr(sec, "required_room_type", "NORMAL") if sec else "NORMAL"
                    st_cnt = getattr(sec, "student_count", 0) if sec else 0
                    lec = self.lecturer_map.get(sec.lecturer_id) if sec else None
                    avail_ts = getattr(lec, "available_timeslot_ids", None) if lec else None

                    if random_gen.random() < 0.5:
                        valid_rooms = self._valid_rooms_by_waste.get(sec_id, self.rooms)
                        gene.room_id = random_gen.choice(valid_rooms).id
                    else:
                        valid_ts = [
                            t for t in self._valid_ts_by_duration.get(dur, self.timeslots)
                            if avail_ts is None or all(
                                self.day_period_to_ts_id.get((t.day, p)) in avail_ts
                                for p in get_occupied_periods(t.period, dur)
                            )
                        ]
                        if valid_ts:
                            gene.timeslot_id = random_gen.choice(valid_ts).id

                    stats["guided_mutation_fallbacks"] += 1

        return mutated, stats
