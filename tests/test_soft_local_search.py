"""Unit tests for Post-Search Soft Local Search module.

Verifies safety invariants, deterministic behavior, soft penalty improvement,
and hard feasibility preservation.
"""

import pytest
from domain import Schedule, Gene, CourseSection, Room, Timeslot, Lecturer, StudentGroup
from dataset import is_valid_period_block
from constraints import ConstraintEvaluator
from ga import GeneticAlgorithmEngine, SoftLocalSearch


@pytest.fixture
def sample_dataset():
    """Create a minimal mock dataset for soft local search testing."""
    timeslots = [
        Timeslot(id=0, day="Thứ 2", period=1, start_time="07:00", end_time="07:50", session="morning"),
        Timeslot(id=1, day="Thứ 2", period=2, start_time="07:50", end_time="08:40", session="morning"),
        Timeslot(id=2, day="Thứ 2", period=3, start_time="08:50", end_time="09:40", session="morning"),
        Timeslot(id=3, day="Thứ 2", period=4, start_time="09:40", end_time="10:30", session="morning"),
        Timeslot(id=4, day="Thứ 3", period=1, start_time="07:00", end_time="07:50", session="morning"),
        Timeslot(id=5, day="Thứ 3", period=2, start_time="07:50", end_time="08:40", session="morning"),
    ]
    rooms = [
        Room(id="R120", name="Room 120", capacity=120, room_type="NORMAL", campus_id="CS1"),
        Room(id="R50", name="Room 50", capacity=50, room_type="NORMAL", campus_id="CS1"),
    ]
    sections = [
        CourseSection(
            section_id="SEC-01",
            course_id="C1",
            course_name="Test Course 1",
            lecturer_id="GV01",
            group_id="G1",
            student_count=40,
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
        Lecturer(id="GV01", name="Teacher 1", available_timeslot_ids=[0, 1, 2, 3, 4, 5]),
        Lecturer(id="GV02", name="Teacher 2", available_timeslot_ids=[0, 1, 2, 3, 4, 5]),
    ]
    student_groups = [
        StudentGroup(id="G1", name="Group 1", student_count=40),
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


def test_soft_local_search_never_increases_hard(sample_dataset):
    """Safety Invariant 1: Soft local search must never produce hard violations (> 0)."""
    evaluator = ConstraintEvaluator(sample_dataset)
    sls = SoftLocalSearch(sample_dataset, evaluator=evaluator, max_passes=2)

    # Lịch khả thi ban đầu: SEC-01 ở ts 0 R120, SEC-02 ở ts 4 R50
    initial_sched = Schedule(genes=[
        Gene("SEC-01", "R120", 0),
        Gene("SEC-02", "R50", 4),
    ])
    h_before, _ = evaluator.evaluate_hard(initial_sched)
    assert h_before == 0

    opt_sched, stats = sls.optimize(initial_sched)
    h_after, _ = evaluator.evaluate_hard(opt_sched)
    assert h_after == 0


def test_soft_local_search_never_worsens_soft(sample_dataset):
    """Safety Invariant 2: Soft local search must never increase soft penalty (final_soft <= initial_soft)."""
    evaluator = ConstraintEvaluator(sample_dataset)
    sls = SoftLocalSearch(sample_dataset, evaluator=evaluator, max_passes=2)

    initial_sched = Schedule(genes=[
        Gene("SEC-01", "R120", 0),
        Gene("SEC-02", "R50", 4),
    ])
    s_before, _ = evaluator.evaluate_soft(initial_sched)

    opt_sched, stats = sls.optimize(initial_sched)
    s_after, _ = evaluator.evaluate_soft(opt_sched)

    assert s_after <= s_before
    assert stats["soft_ls_final_penalty"] <= stats["soft_ls_initial_penalty"]


def test_soft_local_search_improves_room_seat_waste_case(sample_dataset):
    """Test Case 3: 40 students assigned to capacity 120 room (waste=80).

    Should move section to capacity 50 room (waste=10), reducing S4 seat waste.
    """
    evaluator = ConstraintEvaluator(sample_dataset)
    sls = SoftLocalSearch(sample_dataset, evaluator=evaluator, max_passes=2)

    initial_sched = Schedule(genes=[
        Gene("SEC-01", "R120", 0),
        Gene("SEC-02", "R120", 4),
    ])
    s_before, details_before = evaluator.evaluate_soft(initial_sched)

    opt_sched, stats = sls.optimize(initial_sched)
    s_after, details_after = evaluator.evaluate_soft(opt_sched)

    g1 = opt_sched.genes[0]
    assert g1.room_id == "R50"
    assert s_after < s_before
    assert stats["soft_ls_accepted_moves"] >= 1


def test_soft_local_search_rejects_hard_violation(sample_dataset):
    """Test Case 4: Rejects moves that improve soft penalty but break hard feasibility."""
    evaluator = ConstraintEvaluator(sample_dataset)
    sls = SoftLocalSearch(sample_dataset, evaluator=evaluator, max_passes=2)

    # SEC-01 ở R120 (ts 0), SEC-02 ở R50 (ts 0). Hard = 0.
    initial_sched = Schedule(genes=[
        Gene("SEC-01", "R120", 0),
        Gene("SEC-02", "R50", 0),
    ])
    h_before, _ = evaluator.evaluate_hard(initial_sched)
    assert h_before == 0

    opt_sched, stats = sls.optimize(initial_sched)
    h_after, _ = evaluator.evaluate_hard(opt_sched)
    assert h_after == 0


def test_soft_local_search_preserves_duration_block(sample_dataset):
    """Test Case 5: Ensure 2-period section moves as an atomic contiguous block."""
    evaluator = ConstraintEvaluator(sample_dataset)
    sls = SoftLocalSearch(sample_dataset, evaluator=evaluator, max_passes=2)

    initial_sched = Schedule(genes=[
        Gene("SEC-01", "R120", 0),
        Gene("SEC-02", "R50", 4),
    ])
    opt_sched, stats = sls.optimize(initial_sched)

    g = opt_sched.genes[0]
    ts = next(t for t in sample_dataset["timeslots"] if t.id == g.timeslot_id)

    assert is_valid_period_block(ts.period, 2, {1, 2, 3, 4})


def test_disabled_soft_local_search_preserves_original_behavior(sample_dataset):
    """Test Case 6: use_soft_local_search=False returns original engine behavior."""
    engine = GeneticAlgorithmEngine(sample_dataset, pop_size=10, seed=42)
    res_disabled = engine.run(generations=5, use_soft_local_search=False, seed=42)
    res_enabled = engine.run(generations=5, use_soft_local_search=True, seed=42)

    assert "use_soft_local_search" in res_disabled
    assert res_disabled["use_soft_local_search"] is False
    assert res_enabled["use_soft_local_search"] is True

    assert res_enabled["soft_penalty"] <= res_disabled["soft_penalty"]


def test_soft_local_search_is_deterministic(sample_dataset):
    """Test Case 7: Deterministic execution on identical schedule + dataset."""
    evaluator = ConstraintEvaluator(sample_dataset)
    sls1 = SoftLocalSearch(sample_dataset, evaluator=evaluator, max_passes=2)
    sls2 = SoftLocalSearch(sample_dataset, evaluator=evaluator, max_passes=2)

    sched1 = Schedule(genes=[Gene("SEC-01", "R120", 0), Gene("SEC-02", "R50", 4)])
    sched2 = Schedule(genes=[Gene("SEC-01", "R120", 0), Gene("SEC-02", "R50", 4)])

    res1, stats1 = sls1.optimize(sched1)
    res2, stats2 = sls2.optimize(sched2)

    assert res1.genes[0].room_id == res2.genes[0].room_id
    assert res1.genes[0].timeslot_id == res2.genes[0].timeslot_id
    assert stats1["soft_ls_final_penalty"] == stats2["soft_ls_final_penalty"]


def test_soft_local_search_budget_respected(sample_dataset):
    """Test Case 8: Candidate checks budget constraint is strictly respected."""
    evaluator = ConstraintEvaluator(sample_dataset)
    budget = 1
    sls = SoftLocalSearch(sample_dataset, evaluator=evaluator, max_passes=2, max_candidate_checks=budget)

    initial_sched = Schedule(genes=[Gene("SEC-01", "R120", 0), Gene("SEC-02", "R50", 4)])
    opt_sched, stats = sls.optimize(initial_sched)

    assert stats["soft_ls_candidate_checks"] <= budget
