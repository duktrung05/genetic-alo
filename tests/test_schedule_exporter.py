import os
import csv
import json
import pytest
from dataset import DatasetFactory
from domain import Schedule, Gene
from evaluation import GreedyScheduler, export_schedule_to_csv, export_metadata_to_json
from evaluation.schedule_exporter import CSV_HEADERS

def test_csv_file_creation(tmp_path):
    # Test 1 — File CSV creation & header completeness
    dataset = DatasetFactory.create_small_dataset()
    greedy = GreedyScheduler(dataset)
    res = greedy.run()
    assert res["hard_violations"] == 0

    csv_file = tmp_path / "schedule.csv"
    res_path = export_schedule_to_csv(res["best_schedule"], dataset, csv_file)

    assert os.path.exists(res_path)
    assert os.path.getsize(res_path) > 0

    with open(csv_file, "r", encoding="utf-8-sig") as f:
        reader = csv.reader(f)
        header = next(reader)
        assert header == CSV_HEADERS

def test_csv_row_count(tmp_path):
    # Test 2 — Exact row count matching number of course sections
    dataset = DatasetFactory.create_small_dataset()
    greedy = GreedyScheduler(dataset)
    res = greedy.run()

    csv_file = tmp_path / "schedule.csv"
    export_schedule_to_csv(res["best_schedule"], dataset, csv_file)

    with open(csv_file, "r", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        rows = list(reader)
        assert len(rows) == len(dataset["course_sections"])

def test_no_duplicate_section_ids(tmp_path):
    # Test 3 — No duplicate Section IDs in CSV
    dataset = DatasetFactory.create_small_dataset()
    greedy = GreedyScheduler(dataset)
    res = greedy.run()

    csv_file = tmp_path / "schedule.csv"
    export_schedule_to_csv(res["best_schedule"], dataset, csv_file)

    with open(csv_file, "r", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        section_ids = [row["Section ID"] for row in reader]
        assert len(section_ids) == len(set(section_ids)) == len(dataset["course_sections"])

def test_row_sorting(tmp_path):
    # Test 4 — Rows sorted by Day, Period, Room ID, Section ID
    dataset = DatasetFactory.create_small_dataset()
    greedy = GreedyScheduler(dataset)
    res = greedy.run()

    csv_file = tmp_path / "schedule.csv"
    export_schedule_to_csv(res["best_schedule"], dataset, csv_file)

    day_order = {}
    for ts in dataset["timeslots"]:
        if ts.day not in day_order:
            day_order[ts.day] = len(day_order)

    with open(csv_file, "r", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        rows = list(reader)

        sort_keys = [
            (
                day_order.get(r["Day"], 999),
                int(r["Period"]),
                str(r["Room ID"]),
                str(r["Section ID"])
            )
            for r in rows
        ]
        assert sort_keys == sorted(sort_keys)

def test_content_mapping(tmp_path):
    # Test 5 — Field mapping accuracy for a known gene
    dataset = DatasetFactory.create_small_dataset()
    greedy = GreedyScheduler(dataset)
    res = greedy.run()

    csv_file = tmp_path / "schedule.csv"
    export_schedule_to_csv(res["best_schedule"], dataset, csv_file)

    section_map = {s.section_id: s for s in dataset["course_sections"]}
    lecturer_map = {l.id: l for l in dataset["lecturers"]}
    room_map = {r.id: r for r in dataset["rooms"]}
    group_map = {g.id: g for g in dataset["student_groups"]}
    timeslot_map = {t.id: t for t in dataset["timeslots"]}

    gene0 = res["best_schedule"].genes[0]
    expected_sec = section_map[gene0.section_id]
    expected_room = room_map[gene0.room_id]
    expected_ts = timeslot_map[gene0.timeslot_id]

    with open(csv_file, "r", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        matched_row = [r for r in reader if r["Section ID"] == gene0.section_id][0]

        assert matched_row["Course Name"] == expected_sec.course_name
        assert matched_row["Lecturer Name"] == lecturer_map[expected_sec.lecturer_id].name
        assert matched_row["Student Group Name"] == group_map[expected_sec.group_id].name
        assert matched_row["Room Name"] == expected_room.name
        assert matched_row["Day"] == expected_ts.day
        assert int(matched_row["Period"]) == expected_ts.period

def test_utf8_vietnamese(tmp_path):
    # Test 6 — UTF-8 Vietnamese encoding works properly
    dataset = DatasetFactory.create_small_dataset()
    greedy = GreedyScheduler(dataset)
    res = greedy.run()

    csv_file = tmp_path / "schedule_vietnamese.csv"
    export_schedule_to_csv(res["best_schedule"], dataset, csv_file)

    with open(csv_file, "r", encoding="utf-8-sig") as f:
        content = f.read()
        assert "Cấu trúc dữ liệu & Giải thuật" in content
        assert "ThS. Nguyễn Văn A" in content

def test_missing_section_raises_value_error(tmp_path):
    # Test 7 — Schedule missing a section raises ValueError
    dataset = DatasetFactory.create_small_dataset()
    sec_ids = [s.section_id for s in dataset["course_sections"]]
    # Drop last section
    genes = [
        Gene(section_id=sec_id, room_id=dataset["rooms"][0].id, timeslot_id=i)
        for i, sec_id in enumerate(sec_ids[:-1])
    ]
    sched = Schedule(genes=genes)
    csv_file = tmp_path / "invalid.csv"

    with pytest.raises(ValueError):
        export_schedule_to_csv(sched, dataset, csv_file)

def test_duplicate_section_raises_value_error(tmp_path):
    # Test 8 — Schedule with duplicate section raises ValueError
    dataset = DatasetFactory.create_small_dataset()
    sec_ids = [s.section_id for s in dataset["course_sections"]]
    sec_ids[-1] = sec_ids[0]
    genes = [
        Gene(section_id=sec_id, room_id=dataset["rooms"][0].id, timeslot_id=i)
        for i, sec_id in enumerate(sec_ids)
    ]
    sched = Schedule(genes=genes)
    csv_file = tmp_path / "invalid.csv"

    with pytest.raises(ValueError):
        export_schedule_to_csv(sched, dataset, csv_file)

def test_invalid_reference_raises_value_error(tmp_path):
    # Test 9 — Invalid room or timeslot reference raises ValueError
    dataset = DatasetFactory.create_small_dataset()
    sec_ids = [s.section_id for s in dataset["course_sections"]]
    genes = [
        Gene(section_id=sec_ids[i], room_id="NON_EXISTENT_ROOM", timeslot_id=i)
        for i, sec_id in enumerate(sec_ids)
    ]
    sched = Schedule(genes=genes)
    csv_file = tmp_path / "invalid.csv"

    with pytest.raises(ValueError):
        export_schedule_to_csv(sched, dataset, csv_file)

def test_metadata_json(tmp_path):
    # Test 10 — Metadata JSON creation & content parsing
    meta = {
        "method": "Hybrid GA + Repair",
        "dataset_preset": "MEDIUM",
        "seed": 42,
        "hard_violations": 0,
        "raw_soft_violations": 5,
        "soft_penalty": 15,
        "fitness": 15.0,
        "fitness_evaluations": 6000,
        "runtime_seconds": 5.2,
        "course_sections": 60,
        "lecturers": 15,
        "rooms": 8,
        "student_groups": 12,
        "timeslots": 30,
    }
    json_file = tmp_path / "metadata.json"
    res_path = export_metadata_to_json(meta, json_file)

    assert os.path.exists(res_path)
    with open(json_file, "r", encoding="utf-8") as f:
        data = json.load(f)
        assert data["method"] == "Hybrid GA + Repair"
        assert data["seed"] == 42
        assert data["hard_violations"] == 0
        assert data["soft_penalty"] == 15
        assert data["course_sections"] == 60

def test_hard_violations_raises_value_error(tmp_path):
    # Test 11 — Schedule with hard_violations > 0 raises ValueError
    dataset = DatasetFactory.create_small_dataset()
    sec_ids = [s.section_id for s in dataset["course_sections"]]
    # Place all sections at same room and same timeslot (causes lecturer/room overlap)
    genes = [
        Gene(section_id=sec_id, room_id=dataset["rooms"][0].id, timeslot_id=0)
        for sec_id in sec_ids
    ]
    sched = Schedule(genes=genes)
    csv_file = tmp_path / "invalid.csv"

    with pytest.raises(ValueError):
        export_schedule_to_csv(sched, dataset, csv_file)
