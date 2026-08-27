from types import SimpleNamespace
from pathlib import Path

from streamlit.testing.v1 import AppTest

from schedule_assistant import RuleBasedParser, ScheduleQueryService
from ui_app import ASK_SCHEDULE_QUICK_PROMPTS, query_active_timetable


def _active_data():
    assignments = [
        {
            "activity_id": "A1", "section_id": "SEC-1", "class_code": "20231CNTT1010",
            "meeting_index": 1, "meeting_count": 1,
            "course_id": "C01", "course_code": "IT2010", "course_name": "Lập trình hướng đối tượng",
            "student_group_id": "CNTT1-K18", "student_group_name": "CNTT1",
            "lecturer_id": "GV01", "lecturer_name": "Nguyễn Minh Anh",
            "room_id": "R1", "room_name": "Room 1", "campus_id": "CS1",
            "day": "Thứ 2", "session": "morning", "start_period": 1, "end_period": 1,
            "start_time": "07:00", "end_time": "07:50", "occupied_periods": [1],
        },
        {
            "activity_id": "A2", "section_id": "SEC-2", "class_code": "20231CNTT1020",
            "meeting_index": 1, "meeting_count": 1,
            "course_id": "C02", "course_code": "IT2020", "course_name": "Cấu trúc dữ liệu",
            "student_group_id": "CNTT1-K18", "student_group_name": "CNTT1",
            "lecturer_id": "GV02", "lecturer_name": "Nguyễn Minh Bình",
            "room_id": "R2", "room_name": "Room 2", "campus_id": "CS1",
            "day": "Thứ 3", "session": "afternoon", "start_period": 7, "end_period": 7,
            "start_time": "12:30", "end_time": "13:20", "occupied_periods": [7],
        },
    ]
    data = {"meta": {"dataset": "EASY", "hard_violations": 0, "soft_penalty": 1.5}, "assignments": assignments}
    dataset = {
        "rooms": [
            SimpleNamespace(id="R1", name="Room 1", campus_id="CS1", room_type="NORMAL"),
            SimpleNamespace(id="R2", name="Room 2", campus_id="CS1", room_type="NORMAL"),
        ],
        "lecturers": [
            SimpleNamespace(id="GV01", name="Nguyễn Minh Anh", available_timeslot_ids=frozenset({0, 1})),
            SimpleNamespace(id="GV02", name="Nguyễn Minh Bình", available_timeslot_ids=None),
        ],
        "timeslots": [
            SimpleNamespace(id=0, day="Thứ 2", period=1, session="morning", start_time="07:00", end_time="07:50"),
            SimpleNamespace(id=1, day="Thứ 2", period=2, session="morning", start_time="07:50", end_time="08:40"),
            SimpleNamespace(id=2, day="Thứ 3", period=7, session="afternoon", start_time="12:30", end_time="13:20"),
        ],
    }
    return data, dataset


def _service():
    data, dataset = _active_data()
    return ScheduleQueryService(data=data, dataset=dataset)


def test_required_schedule_intents_and_day_filter():
    service = _service()
    cases = {
        "Lịch CNTT1-K18": "student_group_schedule",
        "GV01 dạy khi nào?": "lecturer_schedule",
        "Phòng R1 có lịch gì?": "room_schedule",
        "IT2010 học ở đâu?": "course_schedule",
        "Lớp 20231CNTT1010 học khi nào?": "class_schedule",
        "Phòng nào trống thứ 2 buổi sáng?": "free_room_search",
        "GV01 rảnh khi nào?": "lecturer_free_time",
        "Tóm tắt thời khóa biểu": "schedule_summary",
    }
    for question, intent in cases.items():
        assert service.parser.parse(question).intent == intent
        assert service.query(question).success is True
    result = service.query("CNTT1-K18 học gì thứ 2?")
    assert [item["activity_id"] for item in result.assignments] == ["A1"]


def test_lecturer_id_and_name_resolve_to_same_schedule():
    service = _service()
    by_id = service.query("GV01 dạy khi nào?")
    by_name = service.query("Nguyễn Minh Anh dạy khi nào?")
    assert [row["activity_id"] for row in by_id.assignments] == ["A1"]
    assert by_id.assignments == by_name.assignments


def test_room_course_and_class_queries_use_active_assignments():
    service = _service()
    assert [row["activity_id"] for row in service.query("Phòng R1 có lịch gì?").assignments] == ["A1"]
    assert [row["room_id"] for row in service.query("IT2010 học ở đâu?").assignments] == ["R1"]
    assert [row["activity_id"] for row in service.query("Lớp 20231CNTT1010 học khi nào?").assignments] == ["A1"]


def test_free_room_means_free_for_entire_requested_window():
    result = _service().query("Phòng nào trống thứ 2 buổi sáng?")
    assert result.details["semantic"] == "free_for_entire_requested_window"
    assert [room["room_id"] for room in result.details["free_rooms"]] == ["R2"]


def test_lecturer_free_time_respects_availability_and_teaching():
    result = _service().query("GV01 rảnh thứ 2 buổi sáng?")
    assert result.details["free_times"] == [{
        "day": "Thứ 2", "shift": "Sáng", "start_period": 2, "end_period": 2,
        "start_time": "07:50", "end_time": "08:40",
    }]


def test_summary_unknown_ambiguous_and_unsupported_are_safe():
    service = _service()
    summary = service.query("Tóm tắt thời khóa biểu")
    assert summary.details["summary"]["activities"] == 2
    assert summary.details["summary"]["hard_violations"] == 0
    assert not service.query("Giảng viên Nguyễn dạy khi nào?").success
    assert not service.query("Thuật toán GA là gì?").success
    unknown = service.query("GV99 dạy khi nào?")
    assert unknown.assignments == []
    assert "No matching lecturer" in unknown.message


def test_no_active_schedule_and_quick_prompt_use_same_query_flow():
    assert not query_active_timetable(None, ASK_SCHEDULE_QUICK_PROMPTS[0]).success
    data, dataset = _active_data()
    demo_result = {"dataset_name": "EASY", "dataset": dataset, "exports": {"query_data": data}}
    answer = query_active_timetable(demo_result, ASK_SCHEDULE_QUICK_PROMPTS[0])
    assert answer.success and answer.assignments[0]["student_group_id"] == "CNTT1-K18"


def test_ask_schedule_no_active_state_renders_without_crash():
    app = AppTest.from_file(Path(__file__).resolve().parents[1] / "ui_app.py").run(timeout=20)
    app.sidebar.radio[0].set_value("Ask Schedule").run(timeout=20)
    assert not app.exception
    assert app.title[0].value == "Ask Schedule"
    assert any("No active timetable" in item.value for item in app.info)
    assert any(button.label == "Go to Scheduler" for button in app.button)


def test_quick_prompt_adds_chat_history_from_active_timetable():
    app = AppTest.from_file(Path(__file__).resolve().parents[1] / "ui_app.py").run(timeout=20)
    data, dataset = _active_data()
    app.session_state["demo_result"] = {
        "dataset_name": "EASY", "dataset": dataset, "exports": {"query_data": data},
        "run": {"hard_violations": 0, "scheduled_count": 2, "activity_count": 2, "seed": 0},
    }
    app.sidebar.radio[0].set_value("Ask Schedule").run(timeout=20)
    assert [button.label for button in app.button] == ASK_SCHEDULE_QUICK_PROMPTS
    app.button[0].click().run(timeout=20)
    assert not app.exception
    assert len(app.chat_message) == 2
    assert app.chat_message[0].name == "user"
    assert app.chat_message[1].name == "assistant"
    assert "CNTT1-K18 has 2 scheduled classes" in app.chat_message[1].markdown[0].value
