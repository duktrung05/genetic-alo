import pytest
from domain import Schedule, Gene, CourseSection, Room, Lecturer, StudentGroup, RepairStatus
from constraints import ConstraintEvaluator, ScheduleRepairEngine, RepairStats
from dataset import create_theory_timeslots

@pytest.fixture
def repair_dataset():
    rooms = [
        Room(id="P101", name="Phòng 101", capacity=100, room_type="NORMAL"),
        Room(id="P102", name="Phòng 102", capacity=100, room_type="NORMAL"),
        Room(id="LAB01", name="Phòng LAB 01", capacity=100, room_type="LAB"),
    ]
    timeslots = create_theory_timeslots(days=["Thứ 2", "Thứ 3"], max_period=16)
    lecturers = [
        Lecturer(id="GV01", name="Giảng viên 1"),
        Lecturer(id="GV02", name="Giảng viên 2"),
        Lecturer(id="GV_RESTRICTED", name="GV Hạn chế", available_timeslot_ids=frozenset([0, 1, 2, 3, 4, 5])), # Chỉ Thứ Hai, tiết 1..6
    ]
    groups = [
        StudentGroup(id="SV_CNTT1", name="CNTT 1", student_count=60),
        StudentGroup(id="SV_CNTT2", name="CNTT 2", student_count=40),
    ]
    sections = [
        CourseSection("SEC_1", "C1", "Course 1", "GV01", "SV_CNTT1", 60, duration_periods=2, required_room_type="NORMAL"),
        CourseSection("SEC_2", "C2", "Course 2", "GV02", "SV_CNTT2", 40, duration_periods=3, required_room_type="LAB"),
        CourseSection("SEC_3", "C3", "Course 3", "GV_RESTRICTED", "SV_CNTT1", 40, duration_periods=2, required_room_type="NORMAL"),
    ]
    return {
        "rooms": rooms,
        "timeslots": timeslots,
        "lecturers": lecturers,
        "student_groups": groups,
        "course_sections": sections,
    }

# 1. Sửa trùng phòng bằng cách đổi phòng trong cùng khung giờ
@pytest.mark.unit
def test_repair_fixes_room_overlap_same_timeslot(repair_dataset):
    repairer = ScheduleRepairEngine(repair_dataset)
    evaluator = ConstraintEvaluator(repair_dataset)

    # SEC_1 và SEC_3 đều ở P101 vào tiết 1 Thứ Hai (ts_id 0) -> Trùng phòng!
    bad_sched = Schedule(genes=[
        Gene(section_id="SEC_1", timeslot_id=0, room_id="P101"),
        Gene(section_id="SEC_2", timeslot_id=16, room_id="LAB01"), # Thứ Ba, tiết 1
        Gene(section_id="SEC_3", timeslot_id=0, room_id="P101"), # Bị trùng!
    ])
    res = repairer.repair(bad_sched)
    assert res.success
    assert evaluator.evaluate_hard(res.schedule)[0] == 0

# 2. Sửa trùng giảng viên bằng cách đổi khung giờ
@pytest.mark.unit
def test_repair_fixes_lecturer_overlap_different_timeslot(repair_dataset):
    ds = dict(repair_dataset)
    # Gán cùng giảng viên GV01 cho SEC_1 và SEC_3
    sec1 = CourseSection("SEC_1", "C1", "Course 1", "GV01", "SV_CNTT1", 60, duration_periods=2)
    sec3 = CourseSection("SEC_3", "C3", "Course 3", "GV01", "SV_CNTT2", 40, duration_periods=2)
    ds["course_sections"] = [sec1, repair_dataset["course_sections"][1], sec3]

    repairer = ScheduleRepairEngine(ds)
    evaluator = ConstraintEvaluator(ds)

    bad_sched = Schedule(genes=[
        Gene(section_id="SEC_1", timeslot_id=0, room_id="P101"), # Thứ Hai, tiết 1-2
        Gene(section_id="SEC_2", timeslot_id=16, room_id="LAB01"),
        Gene(section_id="SEC_3", timeslot_id=0, room_id="P102"), # Thứ Hai, tiết 1-2, GV01 xung đột!
    ])
    res = repairer.repair(bad_sched)
    assert res.success
    assert evaluator.evaluate_hard(res.schedule)[0] == 0

# 3. Sửa trùng nhóm sinh viên
@pytest.mark.unit
def test_repair_fixes_group_overlap(repair_dataset):
    repairer = ScheduleRepairEngine(repair_dataset)
    evaluator = ConstraintEvaluator(repair_dataset)

    # SEC_1 và SEC_3 đều thuộc SV_CNTT1 vào tiết 1 Thứ Hai (ts_id 0) -> Trùng nhóm!
    bad_sched = Schedule(genes=[
        Gene(section_id="SEC_1", timeslot_id=0, room_id="P101"),
        Gene(section_id="SEC_2", timeslot_id=16, room_id="LAB01"),
        Gene(section_id="SEC_3", timeslot_id=0, room_id="P102"), # Cùng nhóm SV_CNTT1!
    ])
    res = repairer.repair(bad_sched)
    assert res.success
    assert evaluator.evaluate_hard(res.schedule)[0] == 0

# 4. Sửa vi phạm sức chứa phòng
@pytest.mark.unit
def test_repair_fixes_room_capacity(repair_dataset):
    ds = dict(repair_dataset)
    ds["rooms"] = [
        Room(id="P_SMALL", name="Small Room", capacity=20, room_type="NORMAL"),
        Room(id="P_LARGE", name="Large Room", capacity=100, room_type="NORMAL"),
        Room(id="LAB01", name="LAB Room", capacity=100, room_type="LAB"),
    ]
    repairer = ScheduleRepairEngine(ds)
    evaluator = ConstraintEvaluator(ds)

    # SEC_1 có 60 sinh viên ở P_SMALL (sức chứa 20) -> Vi phạm sức chứa!
    bad_sched = Schedule(genes=[
        Gene(section_id="SEC_1", timeslot_id=0, room_id="P_SMALL"),
        Gene(section_id="SEC_2", timeslot_id=16, room_id="LAB01"),
        Gene(section_id="SEC_3", timeslot_id=2, room_id="P_LARGE"),
    ])
    res = repairer.repair(bad_sched)
    assert res.success
    assert evaluator.evaluate_hard(res.schedule)[0] == 0

# 5. Sửa loại phòng NORMAL/LAB
@pytest.mark.unit
def test_repair_fixes_room_type_mismatch(repair_dataset):
    repairer = ScheduleRepairEngine(repair_dataset)
    evaluator = ConstraintEvaluator(repair_dataset)

    # SEC_2 yêu cầu LAB nhưng được gán vào P101 (NORMAL)
    bad_sched = Schedule(genes=[
        Gene(section_id="SEC_1", timeslot_id=0, room_id="P101"),
        Gene(section_id="SEC_2", timeslot_id=0, room_id="P101"), # Không khớp loại phòng!
        Gene(section_id="SEC_3", timeslot_id=2, room_id="P102"),
    ])
    res = repairer.repair(bad_sched)
    assert res.success
    lab_gene = [g for g in res.schedule.genes if g.section_id == "SEC_2"][0]
    assert lab_gene.room_id == "LAB01"

# 6. Sửa trường hợp giảng viên không rảnh
@pytest.mark.unit
def test_repair_fixes_lecturer_unavailability(repair_dataset):
    repairer = ScheduleRepairEngine(repair_dataset)
    evaluator = ConstraintEvaluator(repair_dataset)

    # SEC_3 (GV_RESTRICTED rảnh Thứ Hai tiết 1..6) được gán vào Thứ Ba (ts_id 16) -> Không rảnh!
    bad_sched = Schedule(genes=[
        Gene(section_id="SEC_1", timeslot_id=0, room_id="P101"),
        Gene(section_id="SEC_2", timeslot_id=16, room_id="LAB01"),
        Gene(section_id="SEC_3", timeslot_id=16, room_id="P102"), # Thứ Ba -> Giảng viên không rảnh!
    ])
    res = repairer.repair(bad_sched)
    assert res.success
    assert evaluator.evaluate_hard(res.schedule)[0] == 0

# 7. Hỗ trợ thời lượng 4 bắt đầu từ tiết 8
@pytest.mark.unit
def test_repair_supports_duration_4_period_8(repair_dataset):
    ds = dict(repair_dataset)
    sec_d4 = CourseSection("SEC_D4", "C4", "Course 4", "GV01", "SV_CNTT1", 50, duration_periods=4, required_room_type="NORMAL")
    ds["course_sections"] = [sec_d4]
    repairer = ScheduleRepairEngine(ds)
    evaluator = ConstraintEvaluator(ds)

    # Xếp bắt đầu tại ts_id 7 (tiết 8 Thứ Hai)
    sched = Schedule(genes=[Gene(section_id="SEC_D4", timeslot_id=7, room_id="P101")])
    res = repairer.repair(sched)
    assert res.success
    assert evaluator.evaluate_hard(res.schedule)[0] == 0

# 8. Phát hiện và sửa trùng một phần (A chiếm tiết 8-11, B chiếm tiết 11-12)
@pytest.mark.unit
def test_repair_handles_partial_period_overlap(repair_dataset):
    ds = dict(repair_dataset)
    sec_a = CourseSection("SEC_A", "CA", "Course A", "GV01", "SV_CNTT1", 40, duration_periods=4) # Chiếm tiết 8, 9, 10, 11
    sec_b = CourseSection("SEC_B", "CB", "Course B", "GV02", "SV_CNTT2", 40, duration_periods=2) # Chiếm tiết 11, 12
    ds["course_sections"] = [sec_a, sec_b]

    repairer = ScheduleRepairEngine(ds)
    evaluator = ConstraintEvaluator(ds)

    # Cả hai được gán vào P101 Thứ Hai: SEC_A tại ts_id 7 (tiết 8..11), SEC_B tại ts_id 10 (tiết 11..12) -> Trùng tiết 11!
    bad_sched = Schedule(genes=[
        Gene(section_id="SEC_A", timeslot_id=7, room_id="P101"),
        Gene(section_id="SEC_B", timeslot_id=10, room_id="P101"),
    ])
    assert evaluator.evaluate_hard(bad_sched)[0] > 0

    res = repairer.repair(bad_sched)
    assert res.success
    assert evaluator.evaluate_hard(res.schedule)[0] == 0

# 9. Lớp học phần bị lỗi không chiếm tài nguyên
@pytest.mark.unit
def test_failed_section_does_not_consume_resources():
    rooms = [
        Room(id="P101", name="Phòng 101", capacity=10, room_type="NORMAL"),
        Room(id="P102", name="Phòng 102", capacity=10, room_type="NORMAL"),
    ]
    timeslots = create_theory_timeslots(days=["Thứ 2"], max_period=4)
    sections = [
        CourseSection("SEC_FAIL", "CF", "Fail Course", "GV1", "G1", 50, duration_periods=5),
        CourseSection("SEC_OK", "CO", "OK Course", "GV2", "G2", 10, duration_periods=1),
    ]
    ds = {
        "rooms": rooms,
        "timeslots": timeslots,
        "course_sections": sections,
        "lecturers": [Lecturer(id="GV1", name="GV1"), Lecturer(id="GV2", name="GV2")],
        "student_groups": [StudentGroup(id="G1", name="G1", student_count=50), StudentGroup(id="G2", name="G2", student_count=10)],
    }
    repairer = ScheduleRepairEngine(ds)
    bad_sched = Schedule(genes=[
        Gene(section_id="SEC_FAIL", timeslot_id=0, room_id="P101"),
        Gene(section_id="SEC_OK", timeslot_id=0, room_id="P101"),
    ])

    res = repairer.repair(bad_sched)
    assert "SEC_FAIL" in res.failed_section_ids
    # SEC_OK giữ phân công ban đầu hợp lệ tại P101 ts 0 vì SEC_FAIL không làm bẩn các tập tài nguyên
    sec_ok_gene = [g for g in res.schedule.genes if g.section_id == "SEC_OK"][0]
    assert sec_ok_gene.room_id == "P101"
    assert sec_ok_gene.timeslot_id == 0




# 10. Lịch đầu vào KHÔNG bị thay đổi
@pytest.mark.unit
def test_input_schedule_not_mutated(repair_dataset):
    repairer = ScheduleRepairEngine(repair_dataset)
    bad_sched = Schedule(genes=[
        Gene(section_id="SEC_1", timeslot_id=0, room_id="P101"),
        Gene(section_id="SEC_2", timeslot_id=0, room_id="P101"),
        Gene(section_id="SEC_3", timeslot_id=0, room_id="P101"),
    ])
    orig_genes_snapshot = [Gene(g.section_id, g.room_id, g.timeslot_id) for g in bad_sched.genes]

    repairer.repair(bad_sched)
    assert bad_sched.genes == orig_genes_snapshot

# 11. Vi phạm cứng KHÔNG tăng
@pytest.mark.unit
def test_hard_violations_never_increase(repair_dataset):
    repairer = ScheduleRepairEngine(repair_dataset)
    evaluator = ConstraintEvaluator(repair_dataset)

    bad_sched = Schedule(genes=[
        Gene(section_id="SEC_1", timeslot_id=0, room_id="P101"),
        Gene(section_id="SEC_2", timeslot_id=0, room_id="P101"),
        Gene(section_id="SEC_3", timeslot_id=0, room_id="P101"),
    ])
    orig_hard, _ = evaluator.evaluate_hard(bad_sched)

    res = repairer.repair(bad_sched)
    repaired_hard, _ = evaluator.evaluate_hard(res.schedule)
    assert repaired_hard <= orig_hard

# 12. Khi vi phạm cứng bằng nhau, chọn điểm phạt mềm thấp hơn
@pytest.mark.unit
def test_lexicographic_soft_penalty_tie_breaking(repair_dataset):
    repairer = ScheduleRepairEngine(repair_dataset)
    evaluator = ConstraintEvaluator(repair_dataset)

    # Lịch hợp lệ
    valid_sched = Schedule(genes=[
        Gene(section_id="SEC_1", timeslot_id=0, room_id="P101"),
        Gene(section_id="SEC_2", timeslot_id=16, room_id="LAB01"),
        Gene(section_id="SEC_3", timeslot_id=2, room_id="P102"),
    ])
    res = repairer.repair(valid_sched)
    orig_hard, _ = evaluator.evaluate_hard(valid_sched)
    repaired_hard, _ = evaluator.evaluate_hard(res.schedule)
    assert orig_hard == 0 and repaired_hard == 0

# 13. Trả về lần thử tốt nhất
@pytest.mark.unit
def test_repair_returns_best_attempt(repair_dataset):
    repairer = ScheduleRepairEngine(repair_dataset)
    evaluator = ConstraintEvaluator(repair_dataset)

    bad_sched = Schedule(genes=[
        Gene(section_id="SEC_1", timeslot_id=0, room_id="P101"),
        Gene(section_id="SEC_2", timeslot_id=0, room_id="P101"),
        Gene(section_id="SEC_3", timeslot_id=0, room_id="P101"),
    ])
    res = repairer.repair(bad_sched, max_attempts=5)
    best_hard, _ = evaluator.evaluate_hard(res.schedule)
    assert res.remaining_hard_violations == best_hard

# 14. Dừng sớm khi hard = 0
@pytest.mark.unit
def test_early_stopping_on_zero_hard_violations(repair_dataset):
    repairer = ScheduleRepairEngine(repair_dataset)
    valid_sched = Schedule(genes=[
        Gene(section_id="SEC_1", timeslot_id=0, room_id="P101"),
        Gene(section_id="SEC_2", timeslot_id=16, room_id="LAB01"),
        Gene(section_id="SEC_3", timeslot_id=2, room_id="P102"),
    ])
    repairer.stats.reset()
    res = repairer.repair(valid_sched, max_attempts=15)
    assert res.success
    assert repairer.stats.repair_attempts <= 1

# 15. Cùng seed tạo ra cùng kết quả (khả năng tái lập)
@pytest.mark.unit
def test_repair_reproducibility_same_seed(repair_dataset):
    import random
    repairer = ScheduleRepairEngine(repair_dataset)
    bad_sched = Schedule(genes=[
        Gene(section_id="SEC_1", timeslot_id=0, room_id="P101"),
        Gene(section_id="SEC_2", timeslot_id=0, room_id="P101"),
        Gene(section_id="SEC_3", timeslot_id=0, room_id="P101"),
    ])

    random.seed(42)
    res1 = repairer.repair(bad_sched)

    random.seed(42)
    res2 = repairer.repair(bad_sched)

    assert res1.schedule.genes == res2.schedule.genes

@pytest.mark.unit
def test_unrelated_valid_assignments_preserved(repair_dataset):
    ds = dict(repair_dataset)
    sec3_g2 = CourseSection("SEC_3", "C3", "Course 3", "GV_RESTRICTED", "SV_CNTT2", 40, duration_periods=2, required_room_type="NORMAL")
    ds["course_sections"] = [repair_dataset["course_sections"][0], repair_dataset["course_sections"][1], sec3_g2]
    repairer = ScheduleRepairEngine(ds)

    # SEC_1 hợp lệ ở tiết 1 Thứ Hai (ts 0, P101)
    # SEC_2 (LAB, ts 16 P101) và SEC_3 (NORMAL, ts 16 P102) không hợp lệ/xung đột
    sched = Schedule(genes=[
        Gene(section_id="SEC_1", timeslot_id=0, room_id="P101"), # Hợp lệ
        Gene(section_id="SEC_2", timeslot_id=16, room_id="P101"), # Không hợp lệ (yêu cầu LAB)
        Gene(section_id="SEC_3", timeslot_id=16, room_id="P102"), # Không hợp lệ (giảng viên không rảnh)
    ])
    res = repairer.repair(sched)
    sec1_gene = [g for g in res.schedule.genes if g.section_id == "SEC_1"][0]
    assert sec1_gene.timeslot_id == 0
    assert sec1_gene.room_id == "P101"



# 17. RepairStats được cập nhật chính xác
@pytest.mark.unit
def test_repair_stats_updated_correctly(repair_dataset):
    repairer = ScheduleRepairEngine(repair_dataset)
    repairer.stats.reset()

    bad_sched = Schedule(genes=[
        Gene(section_id="SEC_1", timeslot_id=0, room_id="P101"),
        Gene(section_id="SEC_2", timeslot_id=0, room_id="P101"),
        Gene(section_id="SEC_3", timeslot_id=0, room_id="P101"),
    ])
    repairer.repair(bad_sched)
    stats = repairer.stats.to_dict()

    assert stats["repair_calls"] == 1
    assert stats["repair_attempts"] >= 1
    assert stats["sections_repaired"] > 0
    assert stats["repair_runtime_seconds"] >= 0.0


# --- Các kiểm thử bắt buộc để tinh chỉnh Tác vụ 2 ---

@pytest.mark.unit
def test_repair_sections_repaired_counts_only_changed_sections(repair_dataset):
    repairer = ScheduleRepairEngine(repair_dataset)
    repairer.stats.reset()

    # SEC_1 hợp lệ ở tiết 1 Thứ Hai (ts 0, P101).
    # SEC_2 (ts 16, P101 - sai yêu cầu LAB) và SEC_3 (ts 16, P102 - giảng viên không rảnh) sẽ được đổi.
    ds = dict(repair_dataset)
    sec3_g2 = CourseSection("SEC_3", "C3", "Course 3", "GV_RESTRICTED", "SV_CNTT2", 40, duration_periods=2, required_room_type="NORMAL")
    ds["course_sections"] = [repair_dataset["course_sections"][0], repair_dataset["course_sections"][1], sec3_g2]
    repairer = ScheduleRepairEngine(ds)

    sched = Schedule(genes=[
        Gene(section_id="SEC_1", timeslot_id=0, room_id="P101"),  # Không đổi
        Gene(section_id="SEC_2", timeslot_id=16, room_id="P101"), # Đổi sang LAB01
        Gene(section_id="SEC_3", timeslot_id=16, room_id="P102"), # Đổi sang tiết 1 Thứ Hai, P102
    ])
    res = repairer.repair(sched)
    assert res.success
    assert repairer.stats.sections_repaired == 2  # Chính xác 2 lớp học phần thay đổi, không phải 3!

@pytest.mark.unit
def test_repair_output_equals_input_failure(repair_dataset):
    repairer = ScheduleRepairEngine(repair_dataset)
    repairer.stats.reset()

    # Lịch hoàn toàn hợp lệ: đầu ra sửa lỗi bằng đầu vào (không cải thiện)
    valid_sched = Schedule(genes=[
        Gene(section_id="SEC_1", timeslot_id=0, room_id="P101"),
        Gene(section_id="SEC_2", timeslot_id=16, room_id="LAB01"),
        Gene(section_id="SEC_3", timeslot_id=2, room_id="P102"),
    ])
    repairer.repair(valid_sched, max_attempts=1)
    assert repairer.stats.repair_calls == 1
    assert repairer.stats.repair_failures == 1
    assert repairer.stats.repair_successes == 0
    assert repairer.stats.repair_calls == repairer.stats.repair_successes + repairer.stats.repair_failures

@pytest.mark.unit
def test_repair_output_better_than_input_success(repair_dataset):
    repairer = ScheduleRepairEngine(repair_dataset)
    repairer.stats.reset()

    bad_sched = Schedule(genes=[
        Gene(section_id="SEC_1", timeslot_id=0, room_id="P101"),
        Gene(section_id="SEC_2", timeslot_id=0, room_id="P101"),
        Gene(section_id="SEC_3", timeslot_id=0, room_id="P101"),
    ])
    repairer.repair(bad_sched)
    assert repairer.stats.repair_calls == 1
    assert repairer.stats.repair_successes == 1
    assert repairer.stats.repair_failures == 0
    assert repairer.stats.repair_calls == repairer.stats.repair_successes + repairer.stats.repair_failures

@pytest.mark.unit
def test_repair_attempts_increments_per_attempt_pass(repair_dataset):
    repairer = ScheduleRepairEngine(repair_dataset)
    repairer.stats.reset()

    # Lịch không thể xếp vừa, max_attempts = 3
    ds = dict(repair_dataset)
    ds["rooms"] = [Room(id="P101", name="Room 101", capacity=10, room_type="NORMAL")]
    ds["timeslots"] = create_theory_timeslots(days=["Thứ 2"], max_period=2)
    ds["course_sections"] = [CourseSection("SEC_FAIL", "CF", "Fail", "GV1", "G1", 50, duration_periods=3)]

    rep = ScheduleRepairEngine(ds)
    bad_sched = Schedule(genes=[Gene(section_id="SEC_FAIL", timeslot_id=0, room_id="P101")])
    rep.repair(bad_sched, max_attempts=3)

    assert rep.stats.repair_calls == 1
    assert rep.stats.repair_attempts == 3

@pytest.mark.unit
def test_rejected_attempt_changes_not_counted_in_sections_repaired(repair_dataset):
    repairer = ScheduleRepairEngine(repair_dataset)
    repairer.stats.reset()

    # Đầu ra bằng đầu vào -> Lần gọi thất bại -> sections_repaired PHẢI bằng 0
    valid_sched = Schedule(genes=[
        Gene(section_id="SEC_1", timeslot_id=0, room_id="P101"),
        Gene(section_id="SEC_2", timeslot_id=16, room_id="LAB01"),
        Gene(section_id="SEC_3", timeslot_id=2, room_id="P102"),
    ])
    repairer.repair(valid_sched)
    assert repairer.stats.sections_repaired == 0

@pytest.mark.unit
def test_ga_engine_run_resets_repair_stats():
    from ga import GeneticAlgorithmEngine
    from dataset import DatasetFactory

    ds = DatasetFactory.create_medium_dataset(seed=42)
    ga = GeneticAlgorithmEngine(ds, pop_size=10)

    res1 = ga.run(generations=2, use_repair=True)
    calls1 = res1["repair_stats"]["repair_calls"]

    res2 = ga.run(generations=2, use_repair=True)
    calls2 = res2["repair_stats"]["repair_calls"]

    assert calls1 > 0
    assert calls2 > 0
    # Các lần gọi ở lượt chạy thứ hai KHÔNG được cộng dồn từ lượt chạy đầu
    assert calls2 == calls1

@pytest.mark.unit
def test_ga_engine_shares_evaluator_object():
    from ga import GeneticAlgorithmEngine
    from dataset import DatasetFactory

    ds = DatasetFactory.create_medium_dataset(seed=42)
    engine = GeneticAlgorithmEngine(ds, pop_size=10)

    # PHẢI chính xác là cùng một thực thể bộ đánh giá trong bộ nhớ
    assert engine.repairer.evaluator is engine.evaluator


@pytest.mark.unit
def test_repair_rejects_non_schedule_without_crashing(repair_dataset):
    repairer = ScheduleRepairEngine(repair_dataset)

    result = repairer.repair(None)

    assert result.success is False
    assert result.status is RepairStatus.FAILED
    assert result.schedule is None
    assert result.remaining_hard_violations == len(repair_dataset["course_sections"])
    assert repairer.stats.repair_calls == 1
    assert repairer.stats.repair_failed == 1
    assert repairer.stats.repair_failures == 1
    assert repairer.stats.repair_attempts == 0


@pytest.mark.unit
@pytest.mark.parametrize(
    "bad_schedule",
    [
        pytest.param(
            Schedule(genes=[
                Gene("SEC_1", "P101", 0),
                Gene("SEC_2", "LAB01", 16),
            ]),
            id="missing-section",
        ),
        pytest.param(
            Schedule(genes=[
                Gene("SEC_1", "P101", 0),
                Gene("SEC_1", "P102", 1),
                Gene("SEC_3", "P102", 2),
            ]),
            id="duplicate-section",
        ),
        pytest.param(
            Schedule(genes=[
                Gene("UNKNOWN", "P101", 0),
                Gene("SEC_2", "LAB01", 16),
                Gene("SEC_3", "P102", 2),
            ]),
            id="unknown-section",
        ),
    ],
)
def test_repair_rejects_structurally_invalid_chromosome(
    repair_dataset, bad_schedule
):
    repairer = ScheduleRepairEngine(repair_dataset)

    result = repairer.repair(bad_schedule)

    assert result.success is False
    assert result.status is RepairStatus.FAILED
    assert result.schedule is bad_schedule
    assert result.remaining_hard_violations > 0
    assert result.failed_section_ids == sorted(
        section.section_id for section in repair_dataset["course_sections"]
    )
    assert repairer.stats.repair_calls == 1
    assert repairer.stats.repair_failed == 1
    assert repairer.stats.repair_attempts == 0
