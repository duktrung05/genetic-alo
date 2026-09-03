"""Phase 2.3 scheduling-activity expansion and multi-meeting integration."""

import csv
import json

import openpyxl
import pytest

from constraints import ConstraintEvaluator, ScheduleRepairEngine
from dataset import (
    DatasetValidator,
    ExcelDatasetLoader,
    create_theory_timeslots,
    find_feasible_schedule,
)
from domain import (
    Campus,
    Course,
    CourseSection,
    Gene,
    Lecturer,
    Room,
    Schedule,
    StudentGroup,
    expand_scheduling_activities,
)
from evaluation import (
    export_schedule_query_data,
    export_schedule_to_csv,
    export_schedule_to_excel,
)
from ga import GAOperators, GeneticAlgorithmEngine


def _section(section_id="SEC1", meetings=2, lecturer="L1", group="G1"):
    return CourseSection(
        section_id=section_id,
        course_id="C1",
        course_name="Algorithms",
        lecturer_id=lecturer,
        group_id=group,
        student_count=20,
        duration_periods=1,
        meetings_per_week=meetings,
        class_code=f"CLASS-{section_id}",
    )


def _dataset(meetings=2, include_normal=False):
    sections = [_section(meetings=meetings)]
    lecturers = [Lecturer("L1", "Lecturer 1")]
    groups = [StudentGroup("G1", "Group 1", 20, "CAMPUS")]
    courses = [Course("C1", "Algorithms", 3, course_code="ALG101")]
    if include_normal:
        sections.append(_section("SEC2", 1, "L2", "G2"))
        lecturers.append(Lecturer("L2", "Lecturer 2"))
        groups.append(StudentGroup("G2", "Group 2", 20, "CAMPUS"))
    return {
        "campuses": [Campus("CAMPUS", "Main Campus")],
        "courses": courses,
        "course_sections": sections,
        "lecturers": lecturers,
        "student_groups": groups,
        "rooms": [
            Room("R1", "Room 1", 30, campus_id="CAMPUS"),
            Room("R2", "Room 2", 30, campus_id="CAMPUS"),
        ],
        "timeslots": create_theory_timeslots(
            days=["Monday", "Tuesday", "Wednesday"], max_period=2
        ),
        "constraints": [],
    }


@pytest.mark.unit
@pytest.mark.parametrize("meeting_count", [1, 2, 3])
def test_deterministic_section_activity_expansion(meeting_count):
    section = _section(meetings=meeting_count)
    first = expand_scheduling_activities([section])
    second = expand_scheduling_activities([section])
    assert first == second
    assert len(first) == meeting_count
    assert len({activity.activity_id for activity in first}) == meeting_count
    assert [activity.meeting_index for activity in first] == list(
        range(1, meeting_count + 1)
    )
    assert all(activity.section_id == section.section_id for activity in first)
    assert all(activity.section is section for activity in first)
    expected_ids = (
        [section.section_id]
        if meeting_count == 1
        else [f"{section.section_id}-M{i}" for i in range(1, meeting_count + 1)]
    )
    assert [activity.activity_id for activity in first] == expected_ids


@pytest.mark.unit
def test_chromosome_requires_every_activity_exactly_once():
    dataset = _dataset(meetings=3)
    valid = Schedule(
        [
            Gene("SEC1-M1", "R1", 0),
            Gene("SEC1-M2", "R1", 2),
            Gene("SEC1-M3", "R1", 4),
        ]
    )
    assert GAOperators.validate_chromosome(valid, dataset)
    assert not GAOperators.validate_chromosome(
        Schedule([valid.genes[0], valid.genes[0], valid.genes[2]]), dataset
    )
    assert not GAOperators.validate_chromosome(
        Schedule(valid.genes[:2]), dataset
    )


@pytest.mark.unit
def test_same_section_meetings_require_distinct_days():
    dataset = _dataset(meetings=2)
    evaluator = ConstraintEvaluator(dataset)
    same_day = Schedule(
        [Gene("SEC1-M1", "R1", 0), Gene("SEC1-M2", "R1", 1)]
    )
    different_days = Schedule(
        [Gene("SEC1-M1", "R1", 0), Gene("SEC1-M2", "R1", 2)]
    )
    same_count, same_details = evaluator.evaluate_hard(same_day)
    different_count, different_details = evaluator.evaluate_hard(different_days)
    assert same_details["same_section_same_day"] == 1
    assert same_count == 1
    assert different_details["same_section_same_day"] == 0
    assert different_count == 0


@pytest.mark.unit
def test_existing_conflicts_apply_between_activity_genes():
    dataset = _dataset(meetings=1, include_normal=True)
    dataset["course_sections"][1].lecturer_id = "L1"
    dataset["course_sections"][1].group_id = "G1"
    schedule = Schedule([Gene("SEC1", "R1", 0), Gene("SEC2", "R1", 0)])
    _, details = ConstraintEvaluator(dataset).evaluate_hard(schedule)
    assert details["lecturer_overlap"] == 1
    assert details["group_overlap"] == 1
    assert details["room_overlap"] == 1


@pytest.mark.unit
def test_mutation_preserves_activity_identity():
    dataset = _dataset(meetings=2)
    schedule = Schedule(
        [Gene("SEC1-M1", "R1", 0), Gene("SEC1-M2", "R1", 2)]
    )
    mutated = GAOperators.mutate(
        schedule,
        dataset["rooms"],
        dataset["timeslots"],
        mutation_rate=1.0,
        dataset=dataset,
    )
    assert [gene.activity_id for gene in mutated.genes] == ["SEC1-M1", "SEC1-M2"]


@pytest.mark.unit
def test_soft_denominators_expand_per_activity_but_s1_uses_unique_days():
    dataset = _dataset(meetings=2)
    section = dataset["course_sections"][0]
    section.duration_periods = 2
    section.preferred_shift = "morning"
    section.preferred_campus_id = "CAMPUS"
    schedule = Schedule(
        [Gene("SEC1-M1", "R1", 0), Gene("SEC1-M2", "R1", 2)]
    )
    breakdown = {
        item.constraint_id: item
        for item in ConstraintEvaluator(dataset).evaluate_unified(schedule).soft_breakdown
    }
    assert breakdown["S1"].raw_count == 1
    assert breakdown["S1"].denominator == 2
    assert breakdown["S2"].denominator == 4
    assert breakdown["S3"].denominator == 2
    assert breakdown["S4"].denominator == 2
    assert breakdown["S6"].denominator == 2
    assert breakdown["S7"].denominator == 2


@pytest.mark.unit
def test_repair_fixes_same_section_day_conflict():
    dataset = _dataset(meetings=2)
    schedule = Schedule(
        [Gene("SEC1-M1", "R1", 0), Gene("SEC1-M2", "R1", 1)]
    )
    result = ScheduleRepairEngine(dataset).repair(schedule)
    assert result.remaining_hard_violations == 0
    timeslot_map = {ts.id: ts for ts in dataset["timeslots"]}
    assert len({timeslot_map[g.timeslot_id].day for g in result.schedule.genes}) == 2


@pytest.mark.integration
def test_multi_meeting_exports_and_normalized_round_trip(tmp_path):
    dataset = _dataset(meetings=2)
    schedule = Schedule(
        [Gene("SEC1-M1", "R1", 0), Gene("SEC1-M2", "R1", 2)]
    )

    csv_path = tmp_path / "schedule.csv"
    export_schedule_to_csv(schedule, dataset, csv_path)
    with csv_path.open(encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    assert [(row["activity_id"], row["section_id"], row["meeting"]) for row in rows] == [
        ("SEC1-M1", "SEC1", "1/2"),
        ("SEC1-M2", "SEC1", "2/2"),
    ]

    query_path = tmp_path / "query.json"
    export_schedule_query_data(schedule, dataset, query_path)
    query_rows = json.loads(query_path.read_text(encoding="utf-8"))["assignments"]
    assert {row["activity_id"] for row in query_rows} == {"SEC1-M1", "SEC1-M2"}
    assert {row["class_code"] for row in query_rows} == {"CLASS-SEC1"}

    xlsx_path = tmp_path / "schedule.xlsx"
    export_schedule_to_excel(schedule, dataset, xlsx_path)
    workbook = openpyxl.load_workbook(xlsx_path, data_only=True)
    raw = workbook["RAW_ASSIGNMENTS"]
    header = [cell.value for cell in raw[1]]
    assert [row[header.index("meeting")].value for row in raw.iter_rows(min_row=2)] == [
        "1/2", "2/2"
    ]

    normalized_path = tmp_path / "normalized.json"
    ExcelDatasetLoader.export_normalized_json(dataset, str(normalized_path))
    restored = ExcelDatasetLoader.load_normalized_json(str(normalized_path))
    assert restored["course_sections"][0].meetings_per_week == 2
    assert len(expand_scheduling_activities(restored["course_sections"])) == 2


@pytest.mark.integration
def test_ga_repair_schedules_all_multi_meeting_activities():
    dataset = _dataset(meetings=2, include_normal=True)
    DatasetValidator.validate(dataset)
    engine = GeneticAlgorithmEngine(dataset, pop_size=12, seed=23)
    result = engine.run(
        generations=8,
        use_repair=True,
        evaluation_budget=96,
        seed=23,
    )
    assert result["hard_violations"] == 0
    assert {gene.activity_id for gene in result["best_schedule"].genes} == {
        "SEC1-M1", "SEC1-M2", "SEC2"
    }
    timeslot_map = {ts.id: ts for ts in dataset["timeslots"]}
    multi_days = {
        timeslot_map[gene.timeslot_id].day
        for gene in result["best_schedule"].genes
        if gene.activity_id.startswith("SEC1-M")
    }
    assert len(multi_days) == 2


@pytest.mark.integration
def test_canonical_single_meeting_activity_ids_remain_unchanged():
    dataset = ExcelDatasetLoader.load_and_validate("data/instances/instance_easy.xlsx")
    activities = expand_scheduling_activities(dataset["course_sections"])
    assert len(activities) == len(dataset["course_sections"]) == 62
    assert [activity.activity_id for activity in activities] == [
        section.section_id for section in dataset["course_sections"]
    ]
    reference = find_feasible_schedule(dataset)
    assert reference is not None
    assert ConstraintEvaluator(dataset).evaluate_hard(reference)[0] == 0
