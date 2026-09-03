"""Phase 1 regression tests for normalized S1-S7 timetable objectives."""

import pytest

from constraints import ConstraintEvaluator, SoftConstraintConfig
from domain import (
    ConstraintDefinition,
    CourseSection,
    Gene,
    Room,
    Schedule,
    StudentGroup,
    Timeslot,
)
from ga.operators import GAOperators
from ga import SoftLocalSearch


def _dataset(
    *,
    preferred_campus="CS1",
    home_campus="CS1",
    room_capacity=100,
    student_count=50,
):
    sections = [
        CourseSection(
            "SEC1",
            "C1",
            "Course 1",
            "GV1",
            "G1",
            student_count,
            preferred_campus_id=preferred_campus,
            preferred_shift="morning",
        )
    ]
    rooms = [
        Room("R-CS1", "Room CS1", room_capacity, campus_id="CS1"),
        Room("R-CS2", "Room CS2", room_capacity, campus_id="CS2"),
    ]
    timeslots = [
        Timeslot(0, "Thứ 2", 1, "07:00", "07:50", "morning"),
        Timeslot(1, "Thứ 3", 1, "07:00", "07:50", "morning"),
        Timeslot(2, "Thứ 2", 13, "18:00", "18:50", "evening"),
    ]
    groups = [StudentGroup("G1", "Group 1", student_count, home_campus)]
    return {
        "course_sections": sections,
        "rooms": rooms,
        "timeslots": timeslots,
        "student_groups": groups,
        "lecturers": [],
        "courses": [],
        "constraints": [],
    }


@pytest.mark.unit
@pytest.mark.parametrize(
    "preferred,room_id,expected_raw,expected_denominator,expected_normalized",
    [
        ("CS1", "R-CS1", 0.0, 1.0, 0.0),
        ("CS1", "R-CS2", 1.0, 1.0, 1.0),
        (None, "R-CS2", 0.0, 0.0, 0.0),
    ],
)
def test_s6_preferred_campus_mismatch(
    preferred, room_id, expected_raw, expected_denominator, expected_normalized
):
    dataset = _dataset(preferred_campus=preferred)
    result = ConstraintEvaluator(dataset).evaluate_unified(
        Schedule([Gene("SEC1", room_id, 0)])
    )
    metric = next(item for item in result.soft_breakdown if item.constraint_id == "S6")
    assert metric.raw_count == expected_raw
    assert metric.denominator == expected_denominator
    assert metric.normalized_penalty == expected_normalized


@pytest.mark.unit
@pytest.mark.parametrize(
    "home,room_id,expected_raw,expected_denominator,expected_normalized",
    [
        ("CS1", "R-CS1", 0.0, 1.0, 0.0),
        ("CS1", "R-CS2", 1.0, 1.0, 1.0),
        (None, "R-CS2", 0.0, 0.0, 0.0),
    ],
)
def test_s7_student_home_campus_mismatch(
    home, room_id, expected_raw, expected_denominator, expected_normalized
):
    dataset = _dataset(home_campus=home)
    result = ConstraintEvaluator(dataset).evaluate_unified(
        Schedule([Gene("SEC1", room_id, 0)])
    )
    metric = next(item for item in result.soft_breakdown if item.constraint_id == "S7")
    assert metric.raw_count == expected_raw
    assert metric.denominator == expected_denominator
    assert metric.normalized_penalty == expected_normalized


@pytest.mark.unit
def test_all_normalized_objectives_are_bounded():
    dataset = _dataset(room_capacity=200, student_count=50)
    result = ConstraintEvaluator(dataset).evaluate_unified(
        Schedule([Gene("SEC1", "R-CS2", 2)])
    )
    assert [item.constraint_id for item in result.soft_breakdown] == [
        "S1", "S2", "S3", "S4", "S5", "S6", "S7"
    ]
    assert all(0.0 <= item.normalized_penalty <= 1.0 for item in result.soft_breakdown)


@pytest.mark.unit
def test_s4_large_absolute_seat_count_no_longer_dominates_normalized_objective():
    dataset = _dataset(room_capacity=200, student_count=50)
    result = ConstraintEvaluator(dataset).evaluate_unified(
        Schedule([Gene("SEC1", "R-CS2", 0)])
    )
    breakdown = {item.constraint_id: item for item in result.soft_breakdown}

    # Số ghế trống thô theo cách cũ là 150. S4 mới là tỷ lệ 0,75 có giới hạn.
    assert breakdown["S4"].raw_count == pytest.approx(0.75)
    assert breakdown["S4"].normalized_penalty == pytest.approx(0.75)
    assert breakdown["S4"].weighted_penalty == pytest.approx(3.0)
    assert breakdown["S6"].weighted_penalty == pytest.approx(3.0)
    assert breakdown["S4"].weighted_penalty == breakdown["S6"].weighted_penalty


@pytest.mark.unit
def test_legacy_workbook_config_gets_default_s6_s7():
    old_rows = [
        ConstraintDefinition("S1", "SOFT", "Old S1", 10, True),
        ConstraintDefinition("S2", "SOFT", "Old S2", 5, True),
        ConstraintDefinition("S3", "SOFT", "Old S3", 4, True),
        ConstraintDefinition("S4", "SOFT", "Old S4", 2, True),
        ConstraintDefinition("S5", "SOFT", "Old S5", 8, True),
    ]
    config = SoftConstraintConfig.from_constraint_definitions(old_rows)
    assert config.get_weight("preferred_campus_mismatch") == 3
    assert config.is_enabled("preferred_campus_mismatch")
    assert config.get_weight("student_home_campus_mismatch") == 4
    assert config.is_enabled("student_home_campus_mismatch")


@pytest.mark.unit
def test_hard_first_ranking_prefers_feasible_schedule(monkeypatch):
    dataset = _dataset(room_capacity=100, student_count=50)
    dataset.pop("lecturers")  # Tham chiếu giảng viên nằm ngoài kiểm thử xếp hạng này.
    second = CourseSection(
        "SEC2", "C2", "Course 2", "GV2", "G2", 50,
        preferred_campus_id="CS1", preferred_shift="morning",
    )
    dataset["course_sections"].append(second)
    dataset["student_groups"].append(StudentGroup("G2", "Group 2", 50, "CS1"))

    # Lịch không khả thi bị trùng phòng nhưng có các ưu tiên mềm rất tốt.
    infeasible = Schedule([
        Gene("SEC1", "R-CS1", 0),
        Gene("SEC2", "R-CS1", 0),
    ])
    # Lịch khả thi được chủ ý cho chịu điểm phạt cơ sở cao hơn.
    feasible = Schedule([
        Gene("SEC1", "R-CS2", 0),
        Gene("SEC2", "R-CS2", 1),
    ])
    evaluator = ConstraintEvaluator(dataset)
    _, hard_a, soft_a = evaluator.calculate_fitness(infeasible)
    _, hard_b, soft_b = evaluator.calculate_fitness(feasible)
    assert hard_a > hard_b == 0
    assert soft_a < soft_b

    monkeypatch.setattr("ga.operators.random.sample", lambda population, k: [0, 1])
    selected = GAOperators.tournament_selection(
        [infeasible, feasible], [(hard_a, soft_a), (hard_b, soft_b)], k=2
    )
    assert selected is feasible


@pytest.mark.unit
@pytest.mark.parametrize("active_day_count,expected", [(1, 0.0), (3, 0.4), (6, 1.0)])
def test_s1_excess_day_normalization_for_six_days(active_day_count, expected):
    days = [f"D{i}" for i in range(1, 7)]
    timeslots = [
        Timeslot(i, day, 1, "07:00", "07:50", "morning")
        for i, day in enumerate(days)
    ]
    sections = [
        CourseSection(f"SEC{i}", f"C{i}", f"Course {i}", f"GV{i}", "G1", 20)
        for i in range(active_day_count)
    ]
    dataset = {
        "course_sections": sections,
        "rooms": [Room("R1", "Room", 20)],
        "timeslots": timeslots,
        "student_groups": [StudentGroup("G1", "Group", 20)],
        "lecturers": [],
        "courses": [],
        "constraints": [],
    }
    result = ConstraintEvaluator(dataset).evaluate_unified(Schedule([
        Gene(section.section_id, "R1", i) for i, section in enumerate(sections)
    ]))
    s1 = next(item for item in result.soft_breakdown if item.constraint_id == "S1")
    assert s1.raw_count == active_day_count - 1
    assert s1.denominator == 5
    assert s1.normalized_penalty == pytest.approx(expected)


@pytest.mark.unit
def test_s6_s7_double_mismatch_remains_two_auditable_objectives():
    dataset = _dataset(preferred_campus="CS1", home_campus="CS1")
    result = ConstraintEvaluator(dataset).evaluate_unified(
        Schedule([Gene("SEC1", "R-CS2", 0)])
    )
    breakdown = {item.constraint_id: item for item in result.soft_breakdown}
    assert breakdown["S6"].raw_count == 1
    assert breakdown["S7"].raw_count == 1
    assert breakdown["S6"].weighted_penalty == 3
    assert breakdown["S7"].weighted_penalty == 4


def _campus_vs_room_fit_dataset():
    dataset = _dataset(student_count=50)
    dataset.pop("lecturers")
    dataset["rooms"] = [
        Room("R-CS1", "Large preferred-campus room", 200, campus_id="CS1"),
        Room("R-CS2", "Exact-fit other-campus room", 50, campus_id="CS2"),
    ]
    return dataset


@pytest.mark.unit
def test_weight_profiles_can_change_schedule_ranking():
    dataset = _campus_vs_room_fit_dataset()
    campus_better = Schedule([Gene("SEC1", "R-CS1", 0)])
    room_fit_better = Schedule([Gene("SEC1", "R-CS2", 0)])

    student_eval = ConstraintEvaluator(
        dataset, SoftConstraintConfig.from_profile("student-centric")
    )
    resource_eval = ConstraintEvaluator(
        dataset, SoftConstraintConfig.from_profile("resource-centric")
    )
    student_a, _ = student_eval.evaluate_soft(campus_better)
    student_b, _ = student_eval.evaluate_soft(room_fit_better)
    resource_a, _ = resource_eval.evaluate_soft(campus_better)
    resource_b, _ = resource_eval.evaluate_soft(room_fit_better)

    assert student_a < student_b
    assert resource_b < resource_a


@pytest.mark.unit
def test_sls_uses_total_weighted_objective():
    dataset = _campus_vs_room_fit_dataset()
    initial = Schedule([Gene("SEC1", "R-CS1", 0)])

    student_eval = ConstraintEvaluator(
        dataset, SoftConstraintConfig.from_profile("student-centric")
    )
    student_result, _ = SoftLocalSearch(
        dataset, evaluator=student_eval, max_passes=1
    ).optimize(initial)
    assert student_result.genes[0].room_id == "R-CS1"

    resource_eval = ConstraintEvaluator(
        dataset, SoftConstraintConfig.from_profile("resource-centric")
    )
    resource_result, _ = SoftLocalSearch(
        dataset, evaluator=resource_eval, max_passes=1
    ).optimize(initial)
    assert resource_result.genes[0].room_id == "R-CS2"
