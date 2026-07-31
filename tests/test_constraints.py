import pytest
from domain import Schedule, Gene, CourseSection, Room, Lecturer, StudentGroup
from constraints import ConstraintEvaluator, SoftConstraintConfig
from dataset import create_theory_timeslots

@pytest.fixture
def constraint_dataset():
    rooms = [
        Room(id="P101", name="Phòng 101", capacity=100, room_type="NORMAL"),
        Room(id="P102", name="Phòng 102", capacity=50, room_type="NORMAL"),
        Room(id="LAB01", name="Phòng LAB 01", capacity=100, room_type="LAB"),
    ]
    timeslots = create_theory_timeslots(days=["Thứ 2", "Thứ 3"], max_period=6)
    lecturers = [
        Lecturer(id="GV01", name="Giảng viên 1"),
        Lecturer(id="GV02", name="Giảng viên 2"),
        Lecturer(id="GV_RESTRICTED", name="GV Hạn chế", available_timeslot_ids=frozenset([0, 1, 2])), # Mon P1, P2, P3
    ]
    groups = [
        StudentGroup(id="SV_CNTT1", name="CNTT 1", student_count=60),
        StudentGroup(id="SV_CNTT2", name="CNTT 2", student_count=40),
    ]
    sections = [
        CourseSection("SEC_A", "C1", "Course 1", "GV01", "SV_CNTT1", 60, duration_periods=3, required_room_type="NORMAL"),
        CourseSection("SEC_B", "C2", "Course 2", "GV02", "SV_CNTT2", 40, duration_periods=1, required_room_type="NORMAL"),
        CourseSection("SEC_C", "C3", "Course 3", "GV01", "SV_CNTT2", 40, duration_periods=2, required_room_type="NORMAL"),
        CourseSection("SEC_LAB", "C4", "Lab Course", "GV02", "SV_CNTT1", 40, duration_periods=3, required_room_type="LAB"),
    ]
    return {
        "rooms": rooms,
        "timeslots": timeslots,
        "lecturers": lecturers,
        "student_groups": groups,
        "course_sections": sections,
    }

# --- Room Conflict Tests ---

@pytest.mark.unit
def test_room_conflict_overlapping_periods(constraint_dataset):
    evaluator = ConstraintEvaluator(constraint_dataset)
    # SEC_A starts Monday P2 (ts_id 1), duration 3 -> occupies P2, P3, P4
    # SEC_B starts Monday P4 (ts_id 3), duration 1 -> occupies P4
    # Same room P101 -> Overlap on P4!
    sched = Schedule(genes=[
        Gene(section_id="SEC_A", timeslot_id=1, room_id="P101"),
        Gene(section_id="SEC_B", timeslot_id=3, room_id="P101"),
        Gene(section_id="SEC_C", timeslot_id=6, room_id="P101"), # Tuesday P1
        Gene(section_id="SEC_LAB", timeslot_id=0, room_id="LAB01"),
    ])
    _, details = evaluator.evaluate_hard(sched)
    assert details["room_overlap"] == 1

@pytest.mark.unit
def test_room_conflict_different_rooms_or_days_no_conflict(constraint_dataset):
    evaluator = ConstraintEvaluator(constraint_dataset)
    # Same periods P2-P4 vs P4, but SEC_A in P101, SEC_B in LAB01 -> No conflict!
    sched = Schedule(genes=[
        Gene(section_id="SEC_A", timeslot_id=1, room_id="P101"),
        Gene(section_id="SEC_B", timeslot_id=3, room_id="LAB01"),
        Gene(section_id="SEC_C", timeslot_id=6, room_id="P101"),
        Gene(section_id="SEC_LAB", timeslot_id=0, room_id="LAB01"),
    ])
    _, details = evaluator.evaluate_hard(sched)
    assert details["room_overlap"] == 0

# --- Lecturer Conflict Tests ---

@pytest.mark.unit
def test_lecturer_conflict_overlapping_periods(constraint_dataset):
    evaluator = ConstraintEvaluator(constraint_dataset)
    # SEC_A (GV01) Mon P2..P4 (ts 1) vs SEC_C (GV01) Mon P4..P5 (ts 3) -> Overlap P4!
    # Move SEC_LAB to Tuesday (ts 6) so GV02 does not overlap on Mon P1
    sched = Schedule(genes=[
        Gene(section_id="SEC_A", timeslot_id=1, room_id="P101"),
        Gene(section_id="SEC_B", timeslot_id=0, room_id="P101"),
        Gene(section_id="SEC_C", timeslot_id=3, room_id="P101"),
        Gene(section_id="SEC_LAB", timeslot_id=6, room_id="LAB01"),
    ])
    _, details = evaluator.evaluate_hard(sched)
    assert details["lecturer_overlap"] == 1

@pytest.mark.unit
def test_lecturer_conflict_different_lecturers_or_days_no_conflict(constraint_dataset):
    evaluator = ConstraintEvaluator(constraint_dataset)
    # SEC_A (GV01) Monday P2..P4 vs SEC_B (GV02) Monday P4 -> Different lecturers -> No conflict!
    sched = Schedule(genes=[
        Gene(section_id="SEC_A", timeslot_id=1, room_id="P101"),
        Gene(section_id="SEC_B", timeslot_id=3, room_id="P101"),
        Gene(section_id="SEC_C", timeslot_id=6, room_id="P101"),
        Gene(section_id="SEC_LAB", timeslot_id=6, room_id="LAB01"),
    ])
    _, details = evaluator.evaluate_hard(sched)
    assert details["lecturer_overlap"] == 0

# --- Student Group Conflict Tests ---

@pytest.mark.unit
def test_group_conflict_overlapping_periods(constraint_dataset):
    evaluator = ConstraintEvaluator(constraint_dataset)
    # SEC_A (SV_CNTT1) Mon P2..P4 vs SEC_LAB (SV_CNTT1) Mon P4..P6 -> Overlap P4!
    sched = Schedule(genes=[
        Gene(section_id="SEC_A", timeslot_id=1, room_id="P101"),
        Gene(section_id="SEC_B", timeslot_id=0, room_id="P101"),
        Gene(section_id="SEC_C", timeslot_id=6, room_id="P101"),
        Gene(section_id="SEC_LAB", timeslot_id=3, room_id="LAB01"),
    ])
    _, details = evaluator.evaluate_hard(sched)
    assert details["group_overlap"] == 1

# --- Lecturer Availability Tests ---

@pytest.mark.unit
def test_lecturer_availability_full_block_check(constraint_dataset):
    # Create section assigned to GV_RESTRICTED (available Mon P1, P2, P3: ts_ids 0, 1, 2)
    sec_res = CourseSection("SEC_R", "CR", "Restricted Course", "GV_RESTRICTED", "SV_CNTT1", 30, duration_periods=3)
    ds = dict(constraint_dataset)
    ds["course_sections"] = [sec_res]
    evaluator_res = ConstraintEvaluator(ds)

    # 1. Mon P1 (ts_id 0), duration 3 -> occupies P1, P2, P3 -> ALL available -> 0 violations
    sched_ok = Schedule(genes=[Gene(section_id="SEC_R", timeslot_id=0, room_id="P101")])
    _, details_ok = evaluator_res.evaluate_hard(sched_ok)
    assert details_ok["lecturer_unavailable"] == 0

    # 2. Mon P2 (ts_id 1), duration 3 -> occupies P2, P3, P4 -> P4 missing -> 1 violation!
    sched_fail = Schedule(genes=[Gene(section_id="SEC_R", timeslot_id=1, room_id="P101")])
    _, details_fail = evaluator_res.evaluate_hard(sched_fail)
    assert details_fail["lecturer_unavailable"] == 1

# --- Capacity & Room Type Tests ---

@pytest.mark.unit
def test_room_capacity_and_room_type_evaluations(constraint_dataset):
    evaluator = ConstraintEvaluator(constraint_dataset)

    # Capacity violation: SEC_A (sĩ số 60) in P102 (capacity 50)
    sched_cap = Schedule(genes=[
        Gene(section_id="SEC_A", timeslot_id=0, room_id="P102"),
        Gene(section_id="SEC_B", timeslot_id=1, room_id="P101"),
        Gene(section_id="SEC_C", timeslot_id=2, room_id="P101"),
        Gene(section_id="SEC_LAB", timeslot_id=0, room_id="LAB01"),
    ])
    _, details_cap = evaluator.evaluate_hard(sched_cap)
    assert details_cap["capacity_violation"] == 1

    # Room type mismatch: SEC_LAB (requires LAB) in P101 (NORMAL)
    sched_type = Schedule(genes=[
        Gene(section_id="SEC_A", timeslot_id=0, room_id="P101"),
        Gene(section_id="SEC_B", timeslot_id=1, room_id="P101"),
        Gene(section_id="SEC_C", timeslot_id=2, room_id="P101"),
        Gene(section_id="SEC_LAB", timeslot_id=0, room_id="P101"),
    ])
    _, details_type = evaluator.evaluate_hard(sched_type)
    assert details_type["room_type_mismatch"] == 1

# --- Soft Constraints Tests ---

@pytest.mark.unit
def test_soft_constraints_student_gaps_multi_period(constraint_dataset):
    # Set SEC_B group to SV_CNTT1 for testing gaps in SV_CNTT1 schedule
    ds = dict(constraint_dataset)
    sec_b_g1 = CourseSection("SEC_B", "C2", "Course 2", "GV02", "SV_CNTT1", 40, duration_periods=1, required_room_type="NORMAL")
    ds["course_sections"] = [constraint_dataset["course_sections"][0], sec_b_g1, constraint_dataset["course_sections"][2], constraint_dataset["course_sections"][3]]
    evaluator = ConstraintEvaluator(ds)

    # Mon P1..P3 (SEC_A) vs Mon P4 (SEC_B) -> Contiguous P1..P4 -> 0 gap
    sched_no_gap = Schedule(genes=[
        Gene(section_id="SEC_A", timeslot_id=0, room_id="P101"),
        Gene(section_id="SEC_B", timeslot_id=3, room_id="P102"),
        Gene(section_id="SEC_C", timeslot_id=6, room_id="P101"),
        Gene(section_id="SEC_LAB", timeslot_id=6, room_id="LAB01"),
    ])
    _, details_no_gap = evaluator.evaluate_soft_raw(sched_no_gap)
    assert details_no_gap["student_gaps"] == 0

    # Mon P1..P3 (SEC_A) vs Mon P5 (SEC_B) -> Gap on P4 -> 1 gap
    sched_with_gap = Schedule(genes=[
        Gene(section_id="SEC_A", timeslot_id=0, room_id="P101"),
        Gene(section_id="SEC_B", timeslot_id=4, room_id="P102"),
        Gene(section_id="SEC_C", timeslot_id=6, room_id="P101"),
        Gene(section_id="SEC_LAB", timeslot_id=6, room_id="LAB01"),
    ])
    _, details_gap = evaluator.evaluate_soft_raw(sched_with_gap)
    assert details_gap["student_gaps"] == 1

@pytest.mark.unit
def test_soft_constraints_weighted_penalty_calculation(constraint_dataset):
    config = SoftConstraintConfig(weights={"student_gaps": 10, "consecutive_teaching": 5, "difficult_afternoon": 3, "daily_imbalance": 2})
    evaluator = ConstraintEvaluator(constraint_dataset, soft_config=config)

    sched = Schedule(genes=[
        Gene(section_id="SEC_A", timeslot_id=0, room_id="P101"),
        Gene(section_id="SEC_B", timeslot_id=4, room_id="P102"),
        Gene(section_id="SEC_C", timeslot_id=6, room_id="P101"),
        Gene(section_id="SEC_LAB", timeslot_id=6, room_id="LAB01"),
    ])
    tot, details = evaluator.evaluate_soft(sched)
    assert tot == details["student_gaps"] * 10 + details["consecutive_teaching"] * 5 + details["difficult_afternoon"] * 3 + details["daily_imbalance"] * 2
