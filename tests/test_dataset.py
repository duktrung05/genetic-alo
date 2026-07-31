import pytest
from domain import CourseSection, Room, Lecturer, StudentGroup
from dataset import (
    DatasetFactory,
    DatasetValidator,
    THEORY_PERIODS,
    create_theory_timeslots,
    get_occupied_periods,
    is_valid_period_block,
)

@pytest.mark.unit
def test_timeslot_factory_theory_periods():
    assert len(THEORY_PERIODS) == 16
    assert THEORY_PERIODS[1]["session"] == "morning"
    assert THEORY_PERIODS[7]["session"] == "afternoon"
    assert THEORY_PERIODS[13]["session"] == "evening"

    timeslots = create_theory_timeslots(days=["Thứ 2", "Thứ 3"], max_period=6)
    assert len(timeslots) == 12
    assert timeslots[0].start_time == "07:00"
    assert timeslots[0].end_time == "07:50"

@pytest.mark.unit
@pytest.mark.parametrize("start_p, duration, expected", [
    (1, 1, [1]),
    (2, 3, [2, 3, 4]),
    (5, 2, [5, 6]),
])
def test_get_occupied_periods(start_p, duration, expected):
    assert get_occupied_periods(start_p, duration) == expected

@pytest.mark.unit
@pytest.mark.parametrize("start_p, duration, avail, expected", [
    (1, 2, None, True),
    (5, 2, None, True),
    (5, 3, None, True),    # Spans 5, 6, 7 (valid if all periods exist)
    (7, 3, None, True),
    (11, 3, None, True),   # Spans 11, 12, 13 (valid if all periods exist)
    (8, 4, None, True),    # Duration 4 from 8 to 11
    (14, 4, None, False),  # 14..17 exceeds max period 16 -> Invalid!
    (1, 2, {1}, False),    # Missing period 2 in available set
    (1, 2, {1, 2}, True),  # Fully in available set
])
def test_is_valid_period_block(start_p, duration, avail, expected):
    assert is_valid_period_block(start_p, duration, avail) == expected

@pytest.mark.unit
def test_medium_dataset_structure_and_counts(medium_dataset):
    assert len(medium_dataset["course_sections"]) == 60
    assert len(medium_dataset["courses"]) == 20
    assert len(medium_dataset["lecturers"]) == 15
    assert len(medium_dataset["rooms"]) == 8
    assert len(medium_dataset["student_groups"]) == 12
    assert len(medium_dataset["timeslots"]) == 96

@pytest.mark.unit
def test_medium_dataset_duration_distribution(medium_dataset):
    durations = [s.duration_periods for s in medium_dataset["course_sections"]]
    lab_sections = [s for s in medium_dataset["course_sections"] if s.required_room_type == "LAB"]

    assert durations.count(2) == 36 # 60%
    assert durations.count(3) == 15 # 25%
    assert durations.count(4) == 9  # 15%
    assert len(lab_sections) == 10
    assert all(s.duration_periods == 3 for s in lab_sections)

@pytest.mark.unit
def test_medium_dataset_seed_reproducibility():
    d1 = DatasetFactory.create_medium_dataset(seed=42)
    d2 = DatasetFactory.create_medium_dataset(seed=42)
    d3 = DatasetFactory.create_medium_dataset(seed=999)

    s1_ids = [s.section_id for s in d1["course_sections"]]
    s2_ids = [s.section_id for s in d2["course_sections"]]
    s3_ids = [s.section_id for s in d3["course_sections"]]

    assert s1_ids == s2_ids
    assert s1_ids != s3_ids


# --- DatasetValidator Tests ---

def create_valid_validator_base_dataset():
    rooms = [
        Room(id="P101", name="Phòng 101", capacity=100, room_type="NORMAL"),
        Room(id="LAB101", name="Phòng LAB 101", capacity=100, room_type="LAB"),
    ]
    timeslots = create_theory_timeslots(days=["Thứ 2"], max_period=6)
    lecturers = [Lecturer(id="GV1", name="GV1")]
    groups = [StudentGroup(id="G1", name="G1", student_count=30)]
    sections = [
        CourseSection("SEC_1", "C1", "Course 1", "GV1", "G1", 30, duration_periods=2, required_room_type="NORMAL"),
    ]
    return {
        "rooms": rooms,
        "timeslots": timeslots,
        "lecturers": lecturers,
        "student_groups": groups,
        "course_sections": sections,
    }

@pytest.mark.unit
def test_dataset_validator_valid_dataset():
    ds = create_valid_validator_base_dataset()
    DatasetValidator.validate(ds)

@pytest.mark.unit
@pytest.mark.parametrize("entity_key, dup_item, match_str", [
    ("course_sections", CourseSection("SEC_1", "C2", "Course 2", "GV1", "G1", 30), "Duplicate section ID"),
    ("lecturers", Lecturer(id="GV1", name="GV1 Duplicate"), "Duplicate lecturer ID"),
    ("rooms", Room(id="P101", name="P101 Dup", capacity=50), "Duplicate room ID"),
    ("student_groups", StudentGroup(id="G1", name="G1 Dup", student_count=30), "Duplicate student group ID"),
])
def test_dataset_validator_duplicate_ids(entity_key, dup_item, match_str):
    ds = create_valid_validator_base_dataset()
    ds[entity_key].append(dup_item)
    with pytest.raises(ValueError, match=match_str):
        DatasetValidator.validate(ds)

@pytest.mark.unit
def test_dataset_validator_duplicate_timeslot_id():
    ds = create_valid_validator_base_dataset()
    ds["timeslots"].append(ds["timeslots"][0])
    with pytest.raises(ValueError, match="Duplicate timeslot ID"):
        DatasetValidator.validate(ds)

@pytest.mark.unit
def test_dataset_validator_missing_foreign_keys():
    ds = create_valid_validator_base_dataset()
    ds["course_sections"][0] = CourseSection("SEC_1", "C1", "Course 1", "GV_MISSING", "G1", 30)
    with pytest.raises(ValueError, match="non-existent lecturer_id"):
        DatasetValidator.validate(ds)

    ds = create_valid_validator_base_dataset()
    ds["course_sections"][0] = CourseSection("SEC_1", "C1", "Course 1", "GV1", "G_MISSING", 30)
    with pytest.raises(ValueError, match="non-existent group_id"):
        DatasetValidator.validate(ds)

@pytest.mark.unit
def test_dataset_validator_invalid_duration():
    ds = create_valid_validator_base_dataset()
    object.__setattr__(ds["course_sections"][0], "duration_periods", 0)
    with pytest.raises(ValueError, match="invalid duration_periods"):
        DatasetValidator.validate(ds)

@pytest.mark.unit
def test_dataset_validator_lab_room_and_capacity_checks():
    # Missing LAB room
    ds = create_valid_validator_base_dataset()
    ds["rooms"] = [Room(id="P101", name="Phòng 101", capacity=100, room_type="NORMAL")]
    ds["course_sections"][0] = CourseSection("SEC_LAB", "C_LAB", "Lab Course", "GV1", "G1", 30, duration_periods=3, required_room_type="LAB")
    with pytest.raises(ValueError, match="requires LAB room"):
        DatasetValidator.validate(ds)

    # Insufficient LAB capacity
    ds = create_valid_validator_base_dataset()
    ds["rooms"] = [Room(id="LAB101", name="Phòng LAB 101", capacity=20, room_type="LAB")]
    ds["course_sections"][0] = CourseSection("SEC_LAB", "C_LAB", "Lab Course", "GV1", "G1", 30, duration_periods=3, required_room_type="LAB")
    with pytest.raises(ValueError, match="capacity >="):
        DatasetValidator.validate(ds)

@pytest.mark.unit
def test_dataset_validator_timeslot_and_availability_blocks():
    # No start timeslot for duration 3 (only 2 periods max)
    ds = create_valid_validator_base_dataset()
    ds["timeslots"] = create_theory_timeslots(days=["Thứ 2"], max_period=2)
    ds["course_sections"][0] = CourseSection("SEC_1", "C1", "Course 1", "GV1", "G1", 30, duration_periods=3)
    with pytest.raises(ValueError, match="No valid timeslot block"):
        DatasetValidator.validate(ds)

    # Restricted lecturer unavailable for duration 2 block
    ds = create_valid_validator_base_dataset()
    ds["lecturers"] = [Lecturer(id="GV1", name="GV1", available_timeslot_ids=frozenset([0]))]
    ds["course_sections"][0] = CourseSection("SEC_1", "C1", "Course 1", "GV1", "G1", 30, duration_periods=2)
    with pytest.raises(ValueError, match="has no available timeslot block"):
        DatasetValidator.validate(ds)

@pytest.mark.unit
def test_baselines_reject_invalid_dataset():
    from evaluation import GreedyScheduler, RandomSearchScheduler
    ds = create_valid_validator_base_dataset()
    ds["course_sections"].append(CourseSection("SEC_1", "C2", "Course 2", "GV1", "G1", 30))
    with pytest.raises(ValueError, match="Duplicate section ID"):
        GreedyScheduler(ds)
    with pytest.raises(ValueError, match="Duplicate section ID"):
        RandomSearchScheduler(ds)


# --- Section 8 Mandatory Tests for Medium Dataset ---

@pytest.mark.unit
def test_medium_dataset_validator_report_no_errors(medium_dataset):
    report = DatasetValidator.validate_report(medium_dataset)
    assert report["valid"] is True
    assert len(report["errors"]) == 0
    assert report["statistics"]["sections"] == 60
    assert report["statistics"]["lecturers"] == 15
    assert report["statistics"]["student_groups"] == 12
    assert report["statistics"]["rooms"] == 8
    assert report["statistics"]["total_periods"] == 96

@pytest.mark.unit
def test_medium_dataset_all_sections_have_matching_room(medium_dataset):
    rooms = medium_dataset["rooms"]
    for sec in medium_dataset["course_sections"]:
        matching = [
            r for r in rooms
            if getattr(r, "room_type", "NORMAL") == sec.required_room_type and r.capacity >= sec.student_count
        ]
        assert len(matching) > 0, f"Section {sec.section_id} has no matching room"

@pytest.mark.unit
def test_medium_dataset_all_sections_have_valid_start_period(medium_dataset):
    from collections import defaultdict
    day_avail = defaultdict(set)
    for ts in medium_dataset["timeslots"]:
        day_avail[ts.day].add(ts.period)

    for sec in medium_dataset["course_sections"]:
        valid_starts = [
            t for t in medium_dataset["timeslots"]
            if is_valid_period_block(t.period, sec.duration_periods, day_avail.get(t.day))
        ]
        assert len(valid_starts) > 0, f"Section {sec.section_id} has no valid start period"

@pytest.mark.unit
def test_medium_dataset_lecturer_capacity(medium_dataset):
    total_ts = len(medium_dataset["timeslots"])
    lec_map = {l.id: l for l in medium_dataset["lecturers"]}
    from collections import defaultdict
    req_periods = defaultdict(int)
    for sec in medium_dataset["course_sections"]:
        req_periods[sec.lecturer_id] += sec.duration_periods

    for lec_id, req in req_periods.items():
        lec = lec_map[lec_id]
        avail = len(lec.available_timeslot_ids) if lec.available_timeslot_ids is not None else total_ts
        assert req <= avail, f"Lecturer {lec_id} required {req} > available {avail}"

@pytest.mark.unit
def test_duration_4_period_8_valid():
    avail = set(range(1, 17))
    assert is_valid_period_block(start_period=8, duration_periods=4, available_periods=avail) is True

@pytest.mark.unit
def test_period_exceeding_16_rejected():
    avail = set(range(1, 17))
    assert is_valid_period_block(start_period=14, duration_periods=4, available_periods=avail) is False

@pytest.mark.unit
def test_medium_dataset_feasibility_checker_and_evaluator(medium_dataset):
    from dataset import find_feasible_schedule
    from constraints import ConstraintEvaluator

    ref_schedule = find_feasible_schedule(medium_dataset)
    assert ref_schedule is not None, "Feasibility checker failed to find a valid schedule"
    assert len(ref_schedule.genes) == 60

    evaluator = ConstraintEvaluator(medium_dataset)
    hard_violations, details = evaluator.evaluate_hard(ref_schedule)
    assert hard_violations == 0, f"Reference schedule has hard violations: {details}"

