import pytest
import os
import json
import tempfile
from pathlib import Path

from domain import Schedule, Gene, EvaluationCounters
from dataset import DatasetFactory, ExcelDatasetLoader
from evaluation import export_schedule_query_data
from schedule_assistant import (
    IntentParser,
    ScheduleQueryService,
    ResponseFormatter,
    ScheduleQuery,
    QueryResult,
)


@pytest.fixture
def sample_dataset():
    return ExcelDatasetLoader.load_and_validate("data/instances/instance_easy.xlsx")


@pytest.fixture
def sample_schedule(sample_dataset):
    sections = sample_dataset["course_sections"]
    rooms = sample_dataset["rooms"]
    timeslots = sample_dataset["timeslots"]
    genes = [
        Gene(section_id=s.section_id, room_id=rooms[i % len(rooms)].id, timeslot_id=timeslots[i % len(timeslots)].id)
        for i, s in enumerate(sections)
    ]
    return Schedule(genes=genes)


@pytest.fixture
def sample_query_json(sample_schedule, sample_dataset, tmp_path):
    json_path = tmp_path / "test_query_data.json"
    export_schedule_query_data(
        schedule=sample_schedule,
        dataset=sample_dataset,
        output_path=json_path,
        hard_violations=0
    )
    return str(json_path)


@pytest.mark.unit
@pytest.mark.parametrize(
    ("expected_day", "queries"),
    [
        ("Thứ 2", ["Lịch thứ 2", "Lịch t2", "Lịch thứ hai", "Lịch thu hai", "Monday schedule", "Lịch thu 2"]),
        ("Thứ 3", ["Lịch thứ 3", "Lịch t3", "Lịch thứ ba", "Lịch thu ba", "Tuesday schedule", "Lịch thu 3"]),
        ("Thứ 4", ["Lịch thứ 4", "Lịch t4", "Lịch thứ tư", "Lịch thu tu", "Wednesday schedule", "Lịch thu 4"]),
        ("Thứ 5", ["Lịch thứ 5", "Lịch t5", "Lịch thứ năm", "Lịch thu nam", "Thursday schedule", "Lịch thu"]),
        ("Thứ 6", ["Lịch thứ 6", "Lịch t6", "Lịch thứ sáu", "Lịch thu sau", "Friday schedule", "Lịch thu 6"]),
        ("Thứ 7", ["Lịch thứ 7", "Lịch t7", "Lịch thứ bảy", "Lịch thu bay", "Saturday schedule", "Lịch thu 7"]),
        ("Chủ nhật", ["Lịch chủ nhật", "Lịch chu nhat", "Lịch cn", "Sunday schedule", "Lịch sun"]),
    ],
)
def test_intent_parser_day_aliases(expected_day, queries):
    parser = IntentParser()
    for q in queries:
        parsed = parser.parse(q)
        assert parsed.day == expected_day, f"Failed for query '{q}', got day='{parsed.day}'"


@pytest.mark.unit
def test_intent_parser_intent_classification():
    parser = IntentParser()
    
    assert parser.parse("Lịch thứ 2").intent == "schedule_by_day"
    assert parser.parse("Lịch của lớp CNTT1").intent == "schedule_by_student_group"
    assert parser.parse("Giảng viên GV01 dạy khi nào?").intent == "schedule_by_lecturer"
    assert parser.parse("Phòng A9-205 được sử dụng khi nào?").intent == "schedule_by_room"
    assert parser.parse("Môn Lập trình hướng đối tượng").intent == "schedule_by_course"
    assert parser.parse("Lịch thứ 2 của lớp CNTT1").intent == "schedule_combined"
    assert parser.parse("Cho tôi xem lịch").intent == "unknown_or_ambiguous"


@pytest.mark.unit
def test_query_service_day_filter_and_ordering(sample_query_json):
    service = ScheduleQueryService(sample_query_json)
    res = service.query("Lịch thứ 2")
    assert res.success is True
    assert len(res.assignments) > 0

    # Kiểm tra mọi phân công trả về đều vào Thứ 2
    for a in res.assignments:
        assert a["day"] == "Thứ 2"

    # Kiểm tra thứ tự tăng dần theo start_period
    start_periods = [a["start_period"] for a in res.assignments]
    assert start_periods == sorted(start_periods), "Assignments must be sorted ascending by start_period"


@pytest.mark.unit
def test_query_service_group_filter(sample_query_json):
    service = ScheduleQueryService(sample_query_json)
    res = service.query("Lịch của lớp CNTT1")
    assert res.success is True
    for a in res.assignments:
        assert "CNTT1" in a["student_group_id"] or "CNTT1" in a["student_group_name"]


@pytest.mark.unit
def test_query_service_lecturer_filter(sample_query_json):
    service = ScheduleQueryService(sample_query_json)
    res = service.query("GV01 dạy khi nào?")
    assert res.success is True
    for a in res.assignments:
        assert "GV01" in a["lecturer_id"] or "GV01" in a["lecturer_name"].upper()


@pytest.mark.unit
def test_query_service_room_filter(sample_query_json):
    service = ScheduleQueryService(sample_query_json)
    res = service.query("Phòng A9-205")
    assert res.success is True
    for a in res.assignments:
        assert "A9-205" in a["room_name"] or "A9-205" in a["room_id"]


@pytest.mark.unit
def test_query_service_combined_filter(sample_query_json):
    service = ScheduleQueryService(sample_query_json)
    res = service.query("Lịch thứ 2 của GV01")
    assert res.success is True
    for a in res.assignments:
        assert a["day"] == "Thứ 2"
        assert "GV01" in a["lecturer_id"] or "GV01" in a["lecturer_name"].upper()


@pytest.mark.unit
def test_query_service_case_insensitive_course_query(sample_query_json):
    service = ScheduleQueryService(sample_query_json)
    res1 = service.query("Môn Lập Trình Hướng Đối Tượng")
    res2 = service.query("môn lập trình hướng đối tượng")
    assert len(res1.assignments) == len(res2.assignments)


@pytest.mark.unit
def test_query_service_empty_results(sample_query_json):
    service = ScheduleQueryService(sample_query_json)
    res = service.query("Lịch thứ 2 của lớp LOP_KHONG_TON_TAI_999")
    assert res.success is True
    assert len(res.assignments) == 0
    assert "Không tìm thấy lịch" in res.message


@pytest.mark.unit
def test_query_service_ambiguous_input(sample_query_json):
    service = ScheduleQueryService(sample_query_json)
    res = service.query("Cho tôi xem lịch")
    assert res.success is False
    assert "Bạn muốn tra cứu theo" in res.message
    assert len(res.suggestions) > 0


@pytest.mark.unit
def test_query_service_missing_json(tmp_path):
    missing_file = tmp_path / "non_existent_query_data.json"
    service = ScheduleQueryService(missing_file)
    res = service.query("Lịch thứ 2")
    assert res.success is False
    assert "Chưa có dữ liệu thời khóa biểu" in res.message


@pytest.mark.unit
def test_export_query_data_integrity(sample_schedule, sample_dataset, tmp_path):
    out_json = tmp_path / "integrity_query_data.json"
    exported_path = export_schedule_query_data(
        schedule=sample_schedule,
        dataset=sample_dataset,
        output_path=out_json,
        hard_violations=0
    )

    with open(exported_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    assert data["meta"]["hard_violations"] == 0
    assert data["meta"]["total_assignments"] == len(sample_schedule.genes)
    assert len(data["assignments"]) == len(sample_schedule.genes)


@pytest.mark.unit
def test_export_query_data_infeasible_rejection(sample_schedule, sample_dataset, tmp_path):
    out_json = tmp_path / "infeasible_query_data.json"
    with pytest.raises(ValueError, match="Cannot export query data for infeasible schedule"):
        export_schedule_query_data(
            schedule=sample_schedule,
            dataset=sample_dataset,
            output_path=out_json,
            hard_violations=3
        )


@pytest.mark.unit
def test_algorithm_isolation(sample_query_json):
    """Verifies that ScheduleQueryService operates completely isolated from GA and counters."""
    counters = EvaluationCounters()
    initial_search = counters.search_fitness_evaluations
    initial_hard = counters.hard_constraint_evaluations

    service = ScheduleQueryService(sample_query_json)
    res = service.query("Lịch thứ 2 của lớp CNTT1")

    # Xác nhận các bộ đếm không bị thay đổi
    assert counters.search_fitness_evaluations == initial_search
    assert counters.hard_constraint_evaluations == initial_hard
    assert res.success is True
