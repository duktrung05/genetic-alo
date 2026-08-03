"""Tests for Evaluation Consistency, RepairStats Correctness, and Excel Exporter.

Verifies:
1. Unified evaluation result soft_penalty == sum(item.weighted_penalty for item in soft_breakdown).
2. Workbook VIOLATIONS sheet TOTAL SOFT PENALTY == SUMMARY.soft_penalty.
3. RepairStats increment correctness.
4. Hybrid engine repair execution on dataset with intentional conflicts.
5. Lexicographic non-worsening guarantee of Repair Engine.
6. Export prohibition on infeasible schedules unless allow_infeasible_export=True.
"""

import pytest
import openpyxl
from pathlib import Path

from domain import Schedule, Gene, CourseSection, Room, Timeslot, Lecturer
from constraints import ConstraintEvaluator, ScheduleRepairEngine
from constraints.evaluator import UnifiedEvaluationResult, SoftBreakdownItem
from ga import GeneticAlgorithmEngine
from evaluation.schedule_exporter import export_schedule_to_excel


@pytest.fixture
def sample_dataset():
    sections = [
        CourseSection(section_id="SEC01", course_id="CRS01", course_name="Course 1", lecturer_id="LEC01", group_id="GRP01", student_count=30, duration_periods=2, is_difficult=True),
        CourseSection(section_id="SEC02", course_id="CRS02", course_name="Course 2", lecturer_id="LEC01", group_id="GRP01", student_count=30, duration_periods=2, is_difficult=False),
        CourseSection(section_id="SEC03", course_id="CRS03", course_name="Course 3", lecturer_id="LEC02", group_id="GRP02", student_count=20, duration_periods=1, is_difficult=True),
    ]
    rooms = [
        Room(id="R101", name="Room 101", capacity=40, room_type="NORMAL"),
        Room(id="R102", name="Room 102", capacity=50, room_type="NORMAL"),
    ]
    timeslots = [
        Timeslot(id=1, day="Thứ 2", period=1, start_time="07:00", end_time="07:50", session="morning"),
        Timeslot(id=2, day="Thứ 2", period=2, start_time="07:55", end_time="08:45", session="morning"),
        Timeslot(id=3, day="Thứ 2", period=3, start_time="08:50", end_time="09:40", session="morning"),
        Timeslot(id=4, day="Thứ 2", period=4, start_time="09:45", end_time="10:35", session="morning"),
        Timeslot(id=5, day="Thứ 2", period=5, start_time="10:40", end_time="11:30", session="morning"),
        Timeslot(id=7, day="Thứ 2", period=7, start_time="13:00", end_time="13:50", session="afternoon"),
        Timeslot(id=8, day="Thứ 2", period=8, start_time="13:55", end_time="14:45", session="afternoon"),
    ]
    lecturers = [
        Lecturer(id="LEC01", name="Lecturer 1"),
        Lecturer(id="LEC02", name="Lecturer 2"),
    ]
    return {
        "course_sections": sections,
        "rooms": rooms,
        "timeslots": timeslots,
        "lecturers": lecturers,
    }


def test_unified_evaluation_result_breakdown_identity(sample_dataset):
    evaluator = ConstraintEvaluator(sample_dataset)
    sched = Schedule(genes=[
        Gene("SEC01", "R101", 7),  # Difficult afternoon
        Gene("SEC02", "R101", 1),  # Same room conflict with SEC03?
        Gene("SEC03", "R102", 2),
    ])
    unified = evaluator.evaluate_unified(sched)

    calculated_soft = sum(item.weighted_penalty for item in unified.soft_breakdown)
    assert unified.soft_penalty == calculated_soft, (
        f"Expected soft_penalty {unified.soft_penalty} == sum of weighted penalties {calculated_soft}"
    )


def test_workbook_violations_total_equals_summary(sample_dataset, tmp_path):
    evaluator = ConstraintEvaluator(sample_dataset)
    sched = Schedule(genes=[
        Gene("SEC01", "R101", 7),
        Gene("SEC02", "R102", 1),
        Gene("SEC03", "R102", 3),
    ])
    unified = evaluator.evaluate_unified(sched)

    out_file = tmp_path / "test_timetable.xlsx"
    export_schedule_to_excel(
        schedule=sched,
        dataset=sample_dataset,
        output_path=out_file,
        metadata={"method": "Hybrid GA + Repair", "repair_calls": 5, "repair_successes": 5},
        allow_infeasible_export=True
    )

    wb = openpyxl.load_workbook(out_file)

    # Read SUMMARY soft_penalty
    ws_sum = wb["SUMMARY"]
    sum_soft_penalty = None
    for row in ws_sum.iter_rows(values_only=True):
        if row[0] == "soft_penalty":
            sum_soft_penalty = int(row[1])
            break

    assert sum_soft_penalty is not None
    assert sum_soft_penalty == unified.soft_penalty

    # Read VIOLATIONS TOTAL SOFT PENALTY
    ws_viol = wb["VIOLATIONS"]
    viol_total_penalty = None
    for row in ws_viol.iter_rows(values_only=True):
        if row[0] == "SUMMARY" and row[2] == "TOTAL_SOFT_PENALTY":
            viol_total_penalty = int(row[11])  # weighted_penalty column (0-indexed: 11)
            break

    assert viol_total_penalty is not None
    assert viol_total_penalty == sum_soft_penalty == unified.soft_penalty


def test_repair_stats_increment(sample_dataset):
    repairer = ScheduleRepairEngine(sample_dataset)
    sched = Schedule(genes=[
        Gene("SEC01", "R101", 1),  # Hard conflict: SEC01 & SEC02 both on R101, period 1, LEC01, GRP01
        Gene("SEC02", "R101", 1),
        Gene("SEC03", "R102", 1),
    ])

    initial_calls = repairer.stats.repair_calls
    res = repairer.repair(sched)

    assert repairer.stats.repair_calls == initial_calls + 1
    assert repairer.stats.hard_before_repair > 0
    assert res.remaining_hard_violations <= repairer.stats.hard_before_repair


def test_hybrid_engine_calls_repair_on_conflicting_dataset(sample_dataset):
    ga = GeneticAlgorithmEngine(sample_dataset, pop_size=10)
    res = ga.run(generations=5, use_repair=True, evaluation_budget=100)

    rep_stats = res.get("repair_stats", {})
    assert rep_stats.get("repair_enabled") is True
    assert rep_stats.get("repair_calls", 0) > 0


def test_repair_does_not_worsen_lexicographic_tuple(sample_dataset):
    repairer = ScheduleRepairEngine(sample_dataset)
    evaluator = ConstraintEvaluator(sample_dataset)
    sched = Schedule(genes=[
        Gene("SEC01", "R101", 1),
        Gene("SEC02", "R101", 1),
        Gene("SEC03", "R102", 1),
    ])

    h_before, s_before = evaluator.calculate_fitness(sched)[1:]
    res = repairer.repair(sched)
    h_after, s_after = evaluator.calculate_fitness(res.schedule)[1:]

    assert (h_after, s_after) <= (h_before, s_before)


def test_export_prohibits_infeasible_schedule_unless_allowed(sample_dataset, tmp_path):
    infeasible_sched = Schedule(genes=[
        Gene("SEC01", "R101", 1),
        Gene("SEC02", "R101", 1),  # Hard conflict
        Gene("SEC03", "R102", 1),
    ])

    out_file = tmp_path / "infeasible_test.xlsx"

    with pytest.raises(ValueError, match="Cannot export Excel schedule with hard violations"):
        export_schedule_to_excel(
            schedule=infeasible_sched,
            dataset=sample_dataset,
            output_path=out_file,
            allow_infeasible_export=False
        )

    # Should succeed with allow_infeasible_export=True
    exported_path = export_schedule_to_excel(
        schedule=infeasible_sched,
        dataset=sample_dataset,
        output_path=out_file,
        allow_infeasible_export=True
    )
    assert Path(exported_path).exists()
