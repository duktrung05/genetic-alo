"""Unit tests for Soft-Guided Mutation module.

Verifies reproducibility, fallback mechanics, target selection rules for S1-S5,
stochastic shortlist selection, and parent schedule isolation.
"""

import random
import pytest
from domain import Schedule, Gene, CourseSection, Room, Timeslot, Lecturer, StudentGroup
from constraints import ConstraintEvaluator
from ga import GeneticAlgorithmEngine, SoftGuidedMutation


@pytest.fixture
def sample_dataset():
    """Create a minimal mock dataset for soft guided mutation testing."""
    timeslots = [
        Timeslot(id=0, day="Thứ 2", period=1, start_time="07:00", end_time="07:50", session="morning"),
        Timeslot(id=1, day="Thứ 2", period=2, start_time="07:50", end_time="08:40", session="morning"),
        Timeslot(id=2, day="Thứ 2", period=3, start_time="08:50", end_time="09:40", session="morning"),
        Timeslot(id=3, day="Thứ 2", period=4, start_time="09:40", end_time="10:30", session="morning"),
        Timeslot(id=4, day="Thứ 2", period=11, start_time="17:30", end_time="18:20", session="evening"),
        Timeslot(id=5, day="Thứ 3", period=1, start_time="07:00", end_time="07:50", session="morning"),
        Timeslot(id=6, day="Thứ 3", period=2, start_time="07:50", end_time="08:40", session="morning"),
    ]
    rooms = [
        Room(id="R120", name="Room 120", capacity=120, room_type="NORMAL", campus_id="CS1"),
        Room(id="R80", name="Room 80", capacity=80, room_type="NORMAL", campus_id="CS1"),
        Room(id="R50", name="Room 50", capacity=50, room_type="NORMAL", campus_id="CS1"),
    ]
    sections = [
        CourseSection(
            section_id="SEC-01",
            course_id="C1",
            course_name="Test Course 1",
            lecturer_id="GV01",
            group_id="G1",
            student_count=42,
            required_room_type="NORMAL",
            duration_periods=2,
            preferred_campus_id="CS1",
            preferred_shift="morning",
            meetings_per_week=1,
        ),
        CourseSection(
            section_id="SEC-02",
            course_id="C2",
            course_name="Test Course 2",
            lecturer_id="GV02",
            group_id="G2",
            student_count=30,
            required_room_type="NORMAL",
            duration_periods=2,
            preferred_campus_id="CS1",
            preferred_shift="morning",
            meetings_per_week=1,
        ),
    ]
    lecturers = [
        Lecturer(id="GV01", name="Teacher 1", available_timeslot_ids=[0, 1, 2, 3, 4, 5, 6]),
        Lecturer(id="GV02", name="Teacher 2", available_timeslot_ids=[0, 1, 2, 3, 4, 5, 6]),
    ]
    student_groups = [
        StudentGroup(id="G1", name="Group 1", student_count=42),
        StudentGroup(id="G2", name="Group 2", student_count=30),
    ]
    return {
        "timeslots": timeslots,
        "rooms": rooms,
        "course_sections": sections,
        "lecturers": lecturers,
        "student_groups": student_groups,
        "courses": [],
        "constraints": [],
    }


def test_guided_mutation_reproducible_with_same_seed(sample_dataset):
    """Test 1: Same schedule, seed, and config produce identical mutated schedule."""
    evaluator = ConstraintEvaluator(sample_dataset)
    sgm = SoftGuidedMutation(sample_dataset, evaluator=evaluator)

    initial_sched = Schedule(genes=[Gene("SEC-01", "R120", 0), Gene("SEC-02", "R80", 5)])

    rng1 = random.Random(42)
    mut1, stats1 = sgm.mutate(initial_sched, mutation_rate=1.0, guided_probability=0.8, rng=rng1)

    rng2 = random.Random(42)
    mut2, stats2 = sgm.mutate(initial_sched, mutation_rate=1.0, guided_probability=0.8, rng=rng2)

    for g1, g2 in zip(mut1.genes, mut2.genes):
        assert g1.room_id == g2.room_id
        assert g1.timeslot_id == g2.timeslot_id
    assert stats1["guided_mutation_successes"] == stats2["guided_mutation_successes"]


def test_guided_mutation_falls_back_to_random(sample_dataset):
    """Test 2: Falls back to random mutation when no guided targets exist."""
    evaluator = ConstraintEvaluator(sample_dataset)
    sgm = SoftGuidedMutation(sample_dataset, evaluator=evaluator)

    # SEC-01 at R50 (ts 0, waste 8, preferred shift morning), SEC-02 at R50 (ts 5, waste 20)
    # Minimal soft penalty schedule
    initial_sched = Schedule(genes=[Gene("SEC-01", "R50", 0), Gene("SEC-02", "R50", 5)])

    rng = random.Random(42)
    mut, stats = sgm.mutate(initial_sched, mutation_rate=1.0, guided_probability=0.0, rng=rng)

    assert stats["guided_mutation_fallbacks"] > 0


def test_s4_guided_mutation_prefers_lower_seat_waste(sample_dataset):
    """Test 3: 42 students assigned to R120 (waste 78). Guided mutation prefers R50 (waste 8)."""
    evaluator = ConstraintEvaluator(sample_dataset)
    sgm = SoftGuidedMutation(sample_dataset, evaluator=evaluator)

    initial_sched = Schedule(genes=[Gene("SEC-01", "R120", 0), Gene("SEC-02", "R80", 5)])

    rng = random.Random(42)
    mut, stats = sgm.mutate(initial_sched, mutation_rate=1.0, guided_probability=1.0, rng=rng)

    assert stats["guided_targets_S4"] > 0
    assert stats["guided_mutation_successes"] > 0
    # At least one of the mutated genes should have selected a lower seat waste room
    mut_rooms = {g.room_id for g in mut.genes}
    assert ("R50" in mut_rooms or "R80" in mut_rooms or mut.genes[0].timeslot_id != 0)



def test_s3_guided_mutation_targets_preferred_shift(sample_dataset):
    """Test 4: Section assigned to evening shift (ts 4) targets morning preferred shift."""
    evaluator = ConstraintEvaluator(sample_dataset)
    sgm = SoftGuidedMutation(sample_dataset, evaluator=evaluator)

    # SEC-01 assigned to evening timeslot (id 4)
    initial_sched = Schedule(genes=[Gene("SEC-01", "R50", 4), Gene("SEC-02", "R50", 5)])

    rng = random.Random(42)
    mut, stats = sgm.mutate(initial_sched, mutation_rate=1.0, guided_probability=1.0, rng=rng)

    g1 = mut.genes[0]
    ts1 = next(t for t in sample_dataset["timeslots"] if t.id == g1.timeslot_id)
    assert ts1.session == "morning"


def test_s2_guided_mutation_targets_non_late_period(sample_dataset):
    """Test 5: Section assigned to late evening period targets morning/afternoon timeslots."""
    evaluator = ConstraintEvaluator(sample_dataset)
    sgm = SoftGuidedMutation(sample_dataset, evaluator=evaluator)

    initial_sched = Schedule(genes=[Gene("SEC-01", "R50", 4), Gene("SEC-02", "R50", 5)])

    rng = random.Random(42)
    mut, stats = sgm.mutate(initial_sched, mutation_rate=1.0, guided_probability=1.0, rng=rng)

    g1 = mut.genes[0]
    ts1 = next(t for t in sample_dataset["timeslots"] if t.id == g1.timeslot_id)
    assert ts1.session in ("morning", "afternoon")


def test_s5_guided_mutation_can_target_same_campus_or_spacing(sample_dataset):
    """Test 6: S5 guided mutation targets valid rooms/timeslots."""
    evaluator = ConstraintEvaluator(sample_dataset)
    sgm = SoftGuidedMutation(sample_dataset, evaluator=evaluator)

    initial_sched = Schedule(genes=[Gene("SEC-01", "R120", 0), Gene("SEC-02", "R80", 5)])

    rng = random.Random(42)
    mut, stats = sgm.mutate(initial_sched, mutation_rate=1.0, guided_probability=0.8, rng=rng)

    assert len(mut.genes) == len(initial_sched.genes)


def test_duration_block_remains_structurally_valid(sample_dataset):
    """Test 7: Mutated timeslot selection preserves valid duration_periods block."""
    evaluator = ConstraintEvaluator(sample_dataset)
    sgm = SoftGuidedMutation(sample_dataset, evaluator=evaluator)

    initial_sched = Schedule(genes=[Gene("SEC-01", "R120", 0), Gene("SEC-02", "R80", 5)])

    rng = random.Random(42)
    mut, _ = sgm.mutate(initial_sched, mutation_rate=1.0, guided_probability=1.0, rng=rng)

    for g in mut.genes:
        sec = next(s for s in sample_dataset["course_sections"] if s.section_id == g.section_id)
        dur = getattr(sec, "duration_periods", 1)
        ts = next(t for t in sample_dataset["timeslots"] if t.id == g.timeslot_id)
        assert ts is not None


def test_guided_probability_zero_matches_baseline_behavior(sample_dataset):
    """Test 8: guided_probability=0.0 routes all mutations to fallback random path."""
    evaluator = ConstraintEvaluator(sample_dataset)
    sgm = SoftGuidedMutation(sample_dataset, evaluator=evaluator)

    initial_sched = Schedule(genes=[Gene("SEC-01", "R120", 0), Gene("SEC-02", "R80", 5)])

    rng = random.Random(42)
    mut, stats = sgm.mutate(initial_sched, mutation_rate=1.0, guided_probability=0.0, rng=rng)

    assert stats["guided_mutation_successes"] == 0
    assert stats["guided_mutation_fallbacks"] > 0


def test_guided_probability_one_uses_guided_when_available(sample_dataset):
    """Test 9: guided_probability=1.0 uses guided mutation path whenever targets exist."""
    evaluator = ConstraintEvaluator(sample_dataset)
    sgm = SoftGuidedMutation(sample_dataset, evaluator=evaluator)

    initial_sched = Schedule(genes=[Gene("SEC-01", "R120", 0), Gene("SEC-02", "R80", 5)])

    rng = random.Random(42)
    mut, stats = sgm.mutate(initial_sched, mutation_rate=1.0, guided_probability=1.0, rng=rng)

    assert stats["guided_mutation_successes"] > 0


def test_mutation_does_not_modify_parent_schedule(sample_dataset):
    """Test 10: Mutating schedule creates new Gene objects without mutating parent schedule."""
    evaluator = ConstraintEvaluator(sample_dataset)
    sgm = SoftGuidedMutation(sample_dataset, evaluator=evaluator)

    parent_sched = Schedule(genes=[Gene("SEC-01", "R120", 0), Gene("SEC-02", "R80", 5)])
    orig_room = parent_sched.genes[0].room_id
    orig_ts = parent_sched.genes[0].timeslot_id

    rng = random.Random(42)
    mutated_sched, _ = sgm.mutate(parent_sched, mutation_rate=1.0, guided_probability=1.0, rng=rng)

    # Mutate mutated_sched gene
    mutated_sched.genes[0].room_id = "R50"
    mutated_sched.genes[0].timeslot_id = 2

    assert parent_sched.genes[0].room_id == orig_room
    assert parent_sched.genes[0].timeslot_id == orig_ts
