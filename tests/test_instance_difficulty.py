from pathlib import Path

from dataset import DatasetValidator, ExcelDatasetLoader
from domain import CourseSection, Lecturer, Room, StudentGroup
from scripts.analyze_instance_difficulty import analyze_dataset, create_payload


ROOT = Path(__file__).resolve().parents[1]
EASY_INSTANCE = ROOT / "data" / "instances" / "instance_easy.xlsx"


def test_difficulty_analyzer_is_deterministic(small_dataset):
    assert analyze_dataset(small_dataset) == analyze_dataset(small_dataset)


def test_candidate_domain_counts_are_nonnegative_and_present(small_dataset):
    domains = analyze_dataset(small_dataset)["candidate_domains"]
    assert len(domains["per_activity"]) == len(small_dataset["course_sections"])
    assert all(row["candidate_count"] >= 0 for row in domains["per_activity"])
    assert domains["summary"]["min"] >= 0


def test_activity_demand_uses_duration_and_meeting_count(small_dataset):
    section = small_dataset["course_sections"][0]
    section.meetings_per_week = 2
    expected = sum(
        item.duration_periods * item.meetings_per_week
        for item in small_dataset["course_sections"]
    )
    assert analyze_dataset(small_dataset)["resource_pressure"]["total_activity_period_demand"] == expected


def test_lab_supply_is_lab_rooms_times_timeslots(small_dataset):
    pressure = analyze_dataset(small_dataset)["resource_pressure"]
    lab_rooms = sum(room.room_type == "LAB" for room in small_dataset["rooms"])
    assert pressure["lab_room_period_supply"] == lab_rooms * len(small_dataset["timeslots"])


def test_frozen_easy_workbook_loads_validates_and_has_expected_identity():
    dataset = ExcelDatasetLoader.load_and_validate(str(EASY_INSTANCE))
    DatasetValidator.validate(dataset)
    payload = create_payload(EASY_INSTANCE, seeds=[], run_experiment=False)
    assert payload["dataset_counts"]["sections"] == 62
    assert payload["dataset_counts"]["activities"] == 62
    assert len(payload["checksum_sha256"]) == 64
