import json
from pathlib import Path
from types import SimpleNamespace

import openpyxl
import pytest
from streamlit.testing.v1 import AppTest

from dataset import FeasibilityChecker
from ui_app import (
    DATASET_OPTIONS,
    create_demo_exports,
    filter_assignments,
    format_dataframe,
    load_benchmark_artifacts,
    load_demo_dataset,
    run_demo_scheduler,
)


def test_frozen_ui_dataset_paths_load_and_validate():
    for name in ("EASY", "MEDIUM"):
        result = load_demo_dataset(name)
        assert result.path == DATASET_OPTIONS[name]["path"]
        assert result.valid is True
        assert result.counts["sections"] == 62
        assert result.counts["activities"] == 62


def test_validation_failure_is_returned_not_raised(monkeypatch):
    monkeypatch.setitem(DATASET_OPTIONS, "BROKEN", {
        "path": Path("broken.xlsx"), "description": "test",
    })
    monkeypatch.setattr(Path, "exists", lambda self: True)
    monkeypatch.setattr(
        "ui_app.ExcelDatasetLoader.load",
        lambda path: (_ for _ in ()).throw(ValueError("invalid workbook")),
    )
    result = load_demo_dataset("BROKEN")
    assert result.valid is False
    assert "invalid workbook" in result.errors[0]


def _assignments():
    return [
        {
            "activity_id": "SEC1-M1", "section_id": "SEC1", "meeting_index": 1,
            "meeting_count": 2, "course_id": "C1", "course_code": "IT001",
            "course_name": "Programming", "class_code": "IT001.01",
            "student_group_id": "G1", "student_group_name": "Group 1",
            "lecturer_id": "L1", "lecturer_name": "Lecturer 1",
            "room_id": "R1", "room_name": "Room 1", "campus_id": "CS1",
            "day": "Monday", "start_period": 1, "end_period": 2,
            "start_time": "07:00", "end_time": "08:40",
        },
        {
            "activity_id": "SEC2", "section_id": "SEC2", "meeting_index": 1,
            "meeting_count": 1, "course_id": "C2", "course_code": "IT002",
            "course_name": "Algorithms", "class_code": "IT002.01",
            "student_group_id": "G2", "student_group_name": "Group 2",
            "lecturer_id": "L2", "lecturer_name": "Lecturer 2",
            "room_id": "R2", "room_name": "Room 2", "campus_id": "CS2",
            "day": "Tuesday", "start_period": 3, "end_period": 3,
            "start_time": "08:45", "end_time": "09:35",
        },
    ]


def test_official_codes_and_multi_meeting_fields_are_shown():
    frame = format_dataframe(_assignments())
    assert list(frame["Course code"]) == ["IT001", "IT002"]
    assert list(frame["Class code"]) == ["IT001.01", "IT002.01"]
    assert list(frame["Meeting"]) == ["1/2", "1/1"]


def test_group_lecturer_and_room_filters():
    rows = _assignments()
    assert [x["activity_id"] for x in filter_assignments(rows, "Student Group", "Group 1")] == ["SEC1-M1"]
    assert [x["activity_id"] for x in filter_assignments(rows, "Lecturer", "Lecturer 2")] == ["SEC2"]
    assert [x["activity_id"] for x in filter_assignments(rows, "Room", "Room 1")] == ["SEC1-M1"]


def test_benchmark_artifacts_load_without_execution():
    result = load_benchmark_artifacts()
    assert result["valid"] is True
    assert len(result["payload"]["runs"]) == 60


def test_demo_scheduler_returns_complete_schedule(small_dataset):
    result = run_demo_scheduler(small_dataset, seed=0, evaluation_budget=60)
    assert result["scheduled_count"] == result["activity_count"]
    assert result["hard_violations"] == 0


def test_excel_and_json_demo_exports_use_production_exporters(small_dataset, tmp_path):
    schedule = FeasibilityChecker(small_dataset).find_feasible_schedule()
    assert schedule is not None
    run = {
        "schedule": schedule, "hard_violations": 0, "soft_score": 1.25,
        "seed": 0, "run_metrics": SimpleNamespace(runtime_seconds=0.1),
    }
    exports = create_demo_exports(run, small_dataset, "EASY", tmp_path)
    workbook = openpyxl.load_workbook(exports["excel_path"], read_only=True)
    payload = json.loads(exports["json_bytes"].decode("utf-8"))
    assert len(workbook.sheetnames) == 7
    assert len(payload["assignments"]) == len(schedule.genes)
    assert exports["csv_path"].exists()
    required = {"course_code", "class_code", "section_id", "activity_id", "meeting_index"}
    assert required <= set(payload["assignments"][0])


@pytest.mark.integration
def test_exact_easy_live_demo_navigation():
    app = AppTest.from_file(Path(__file__).resolve().parents[1] / "ui_app.py").run(timeout=20)
    assert not app.exception
    assert app.selectbox[0].value == "EASY"
    assert any("Valid" in message.value for message in app.success)

    app.button[0].click().run(timeout=90)
    assert not app.exception
    result = app.session_state["demo_result"]
    assert result["run"]["hard_violations"] == 0
    assert result["run"]["scheduled_count"] == 62
    assert result["run"]["activity_count"] == 62
    assert result["run"]["scheduled_section_count"] == 62
    assert result["run"]["section_count"] == 62

    app.sidebar.radio[0].set_value("Timetable").run(timeout=20)
    assert not app.exception
    assert app.selectbox[0].value == "Student Group"
    assert len(app.get("download_button")) == 3
    app.selectbox[0].set_value("Lecturer").run(timeout=20)
    assert app.selectbox[0].value == "Lecturer"
    app.selectbox[0].set_value("Room").run(timeout=20)
    assert app.selectbox[0].value == "Room"

    app.sidebar.radio[0].set_value("Benchmark").run(timeout=20)
    assert not app.exception
    assert app.title[0].value == "Final Benchmark"
    assert len(app.image) == 3
