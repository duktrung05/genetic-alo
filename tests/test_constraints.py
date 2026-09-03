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
        Lecturer(id="GV_RESTRICTED", name="GV Hạn chế", available_timeslot_ids=frozenset([0, 1, 2])), # Thứ Hai, tiết 1, 2, 3
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

# --- Kiểm thử xung đột phòng ---

@pytest.mark.unit
def test_room_conflict_overlapping_periods(constraint_dataset):
    evaluator = ConstraintEvaluator(constraint_dataset)
    # SEC_A bắt đầu Thứ Hai tiết 2 (ts_id 1), thời lượng 3 -> chiếm tiết 2, 3, 4
    # SEC_B bắt đầu Thứ Hai tiết 4 (ts_id 3), thời lượng 1 -> chiếm tiết 4
    # Cùng phòng P101 -> Trùng ở tiết 4!
    sched = Schedule(genes=[
        Gene(section_id="SEC_A", timeslot_id=1, room_id="P101"),
        Gene(section_id="SEC_B", timeslot_id=3, room_id="P101"),
        Gene(section_id="SEC_C", timeslot_id=6, room_id="P101"), # Thứ Ba, tiết 1
        Gene(section_id="SEC_LAB", timeslot_id=0, room_id="LAB01"),
    ])
    _, details = evaluator.evaluate_hard(sched)
    assert details["room_overlap"] == 1

@pytest.mark.unit
def test_room_conflict_different_rooms_or_days_no_conflict(constraint_dataset):
    evaluator = ConstraintEvaluator(constraint_dataset)
    # Cùng các tiết 2-4 và tiết 4, nhưng SEC_A ở P101, SEC_B ở LAB01 -> Không xung đột!
    sched = Schedule(genes=[
        Gene(section_id="SEC_A", timeslot_id=1, room_id="P101"),
        Gene(section_id="SEC_B", timeslot_id=3, room_id="LAB01"),
        Gene(section_id="SEC_C", timeslot_id=6, room_id="P101"),
        Gene(section_id="SEC_LAB", timeslot_id=0, room_id="LAB01"),
    ])
    _, details = evaluator.evaluate_hard(sched)
    assert details["room_overlap"] == 0

# --- Kiểm thử xung đột giảng viên ---

@pytest.mark.unit
def test_lecturer_conflict_overlapping_periods(constraint_dataset):
    evaluator = ConstraintEvaluator(constraint_dataset)
    # SEC_A (GV01) Thứ Hai tiết 2-4 (ts 1) và SEC_C (GV01) Thứ Hai tiết 4-5 (ts 3) -> Trùng tiết 4!
    # Chuyển SEC_LAB sang Thứ Ba (ts 6) để GV02 không trùng ở tiết 1 Thứ Hai
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
    # SEC_A (GV01) Thứ Hai tiết 2-4 và SEC_B (GV02) Thứ Hai tiết 4 -> Khác giảng viên, không xung đột!
    sched = Schedule(genes=[
        Gene(section_id="SEC_A", timeslot_id=1, room_id="P101"),
        Gene(section_id="SEC_B", timeslot_id=3, room_id="P101"),
        Gene(section_id="SEC_C", timeslot_id=6, room_id="P101"),
        Gene(section_id="SEC_LAB", timeslot_id=6, room_id="LAB01"),
    ])
    _, details = evaluator.evaluate_hard(sched)
    assert details["lecturer_overlap"] == 0

# --- Kiểm thử xung đột nhóm sinh viên ---

@pytest.mark.unit
def test_group_conflict_overlapping_periods(constraint_dataset):
    evaluator = ConstraintEvaluator(constraint_dataset)
    # SEC_A (SV_CNTT1) Thứ Hai tiết 2-4 và SEC_LAB (SV_CNTT1) Thứ Hai tiết 4-6 -> Trùng tiết 4!
    sched = Schedule(genes=[
        Gene(section_id="SEC_A", timeslot_id=1, room_id="P101"),
        Gene(section_id="SEC_B", timeslot_id=0, room_id="P101"),
        Gene(section_id="SEC_C", timeslot_id=6, room_id="P101"),
        Gene(section_id="SEC_LAB", timeslot_id=3, room_id="LAB01"),
    ])
    _, details = evaluator.evaluate_hard(sched)
    assert details["group_overlap"] == 1

# --- Kiểm thử thời gian rảnh của giảng viên ---

@pytest.mark.unit
def test_lecturer_availability_full_block_check(constraint_dataset):
    # Tạo lớp học phần gán cho GV_RESTRICTED (rảnh Thứ Hai tiết 1, 2, 3: ts_ids 0, 1, 2)
    sec_res = CourseSection("SEC_R", "CR", "Restricted Course", "GV_RESTRICTED", "SV_CNTT1", 30, duration_periods=3)
    ds = dict(constraint_dataset)
    ds["course_sections"] = [sec_res]
    evaluator_res = ConstraintEvaluator(ds)

    # 1. Thứ Hai tiết 1 (ts_id 0), thời lượng 3 -> chiếm tiết 1, 2, 3 -> ĐỀU rảnh -> 0 vi phạm
    sched_ok = Schedule(genes=[Gene(section_id="SEC_R", timeslot_id=0, room_id="P101")])
    _, details_ok = evaluator_res.evaluate_hard(sched_ok)
    assert details_ok["lecturer_unavailable"] == 0

    # 2. Thứ Hai tiết 2 (ts_id 1), thời lượng 3 -> chiếm tiết 2, 3, 4 -> thiếu tiết 4 -> 1 vi phạm!
    sched_fail = Schedule(genes=[Gene(section_id="SEC_R", timeslot_id=1, room_id="P101")])
    _, details_fail = evaluator_res.evaluate_hard(sched_fail)
    assert details_fail["lecturer_unavailable"] == 1

# --- Kiểm thử sức chứa và loại phòng ---

@pytest.mark.unit
def test_room_capacity_and_room_type_evaluations(constraint_dataset):
    evaluator = ConstraintEvaluator(constraint_dataset)

    # Vi phạm sức chứa: SEC_A (sĩ số 60) ở P102 (sức chứa 50)
    sched_cap = Schedule(genes=[
        Gene(section_id="SEC_A", timeslot_id=0, room_id="P102"),
        Gene(section_id="SEC_B", timeslot_id=1, room_id="P101"),
        Gene(section_id="SEC_C", timeslot_id=2, room_id="P101"),
        Gene(section_id="SEC_LAB", timeslot_id=0, room_id="LAB01"),
    ])
    _, details_cap = evaluator.evaluate_hard(sched_cap)
    assert details_cap["capacity_violation"] == 1

    # Không khớp loại phòng: SEC_LAB (yêu cầu LAB) ở P101 (NORMAL)
    sched_type = Schedule(genes=[
        Gene(section_id="SEC_A", timeslot_id=0, room_id="P101"),
        Gene(section_id="SEC_B", timeslot_id=1, room_id="P101"),
        Gene(section_id="SEC_C", timeslot_id=2, room_id="P101"),
        Gene(section_id="SEC_LAB", timeslot_id=0, room_id="P101"),
    ])
    _, details_type = evaluator.evaluate_hard(sched_type)
    assert details_type["room_type_mismatch"] == 1

# --- Kiểm thử ràng buộc mềm ---
# Logic ràng buộc mềm (S1-S5) hiện được kiểm thử kỹ trong test_step4_soft_constraints.py

