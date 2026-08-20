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
        Lecturer(id="GV_RESTRICTED", name="GV Hạn chế", available_timeslot_ids=frozenset([0, 1, 2, 3, 4, 5])), # Mon P1..P6 only
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

# 1. Room overlap fixed by changing room at same timeslot
@pytest.mark.unit
def test_repair_fixes_room_overlap_same_timeslot(repair_dataset):
    repairer = ScheduleRepairEngine(repair_dataset)
    evaluator = ConstraintEvaluator(repair_dataset)

    # SEC_1 and SEC_3 both in P101 at Mon P1 (ts_id 0) -> Room overlap!
    bad_sched = Schedule(genes=[
        Gene(section_id="SEC_1", timeslot_id=0, room_id="P101"),
        Gene(section_id="SEC_2", timeslot_id=16, room_id="LAB01"), # Tue P1
        Gene(section_id="SEC_3", timeslot_id=0, room_id="P101"), # Overlap!
    ])
    res = repairer.repair(bad_sched)
    assert res.success
    assert evaluator.evaluate_hard(res.schedule)[0] == 0

# 2. Lecturer overlap fixed by changing timeslot
@pytest.mark.unit
def test_repair_fixes_lecturer_overlap_different_timeslot(repair_dataset):
    ds = dict(repair_dataset)
    # Give SEC_1 and SEC_3 same lecturer GV01
    sec1 = CourseSection("SEC_1", "C1", "Course 1", "GV01", "SV_CNTT1", 60, duration_periods=2)
    sec3 = CourseSection("SEC_3", "C3", "Course 3", "GV01", "SV_CNTT2", 40, duration_periods=2)
    ds["course_sections"] = [sec1, repair_dataset["course_sections"][1], sec3]

    repairer = ScheduleRepairEngine(ds)
    evaluator = ConstraintEvaluator(ds)

    bad_sched = Schedule(genes=[
        Gene(section_id="SEC_1", timeslot_id=0, room_id="P101"), # Mon P1-P2
        Gene(section_id="SEC_2", timeslot_id=16, room_id="LAB01"),
        Gene(section_id="SEC_3", timeslot_id=0, room_id="P102"), # Mon P1-P2, GV01 conflict!
    ])
    res = repairer.repair(bad_sched)
    assert res.success
    assert evaluator.evaluate_hard(res.schedule)[0] == 0

# 3. Group overlap fixed
@pytest.mark.unit
def test_repair_fixes_group_overlap(repair_dataset):
    repairer = ScheduleRepairEngine(repair_dataset)
    evaluator = ConstraintEvaluator(repair_dataset)

    # SEC_1 and SEC_3 both SV_CNTT1 at Mon P1 (ts_id 0) -> Group overlap!
    bad_sched = Schedule(genes=[
        Gene(section_id="SEC_1", timeslot_id=0, room_id="P101"),
        Gene(section_id="SEC_2", timeslot_id=16, room_id="LAB01"),
        Gene(section_id="SEC_3", timeslot_id=0, room_id="P102"), # Same group SV_CNTT1!
    ])
    res = repairer.repair(bad_sched)
    assert res.success
    assert evaluator.evaluate_hard(res.schedule)[0] == 0

# 4. Room capacity violation fixed
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

    # SEC_1 student count 60 in P_SMALL (capacity 20) -> Capacity violation!
    bad_sched = Schedule(genes=[
        Gene(section_id="SEC_1", timeslot_id=0, room_id="P_SMALL"),
        Gene(section_id="SEC_2", timeslot_id=16, room_id="LAB01"),
        Gene(section_id="SEC_3", timeslot_id=2, room_id="P_LARGE"),
    ])
    res = repairer.repair(bad_sched)
    assert res.success
    assert evaluator.evaluate_hard(res.schedule)[0] == 0

# 5. Room type NORMAL/LAB fixed
@pytest.mark.unit
def test_repair_fixes_room_type_mismatch(repair_dataset):
    repairer = ScheduleRepairEngine(repair_dataset)
    evaluator = ConstraintEvaluator(repair_dataset)

    # SEC_2 requires LAB but assigned to P101 (NORMAL)
    bad_sched = Schedule(genes=[
        Gene(section_id="SEC_1", timeslot_id=0, room_id="P101"),
        Gene(section_id="SEC_2", timeslot_id=0, room_id="P101"), # Room type mismatch!
        Gene(section_id="SEC_3", timeslot_id=2, room_id="P102"),
    ])
    res = repairer.repair(bad_sched)
    assert res.success
    lab_gene = [g for g in res.schedule.genes if g.section_id == "SEC_2"][0]
    assert lab_gene.room_id == "LAB01"

# 6. Lecturer unavailable fixed
@pytest.mark.unit
def test_repair_fixes_lecturer_unavailability(repair_dataset):
    repairer = ScheduleRepairEngine(repair_dataset)
    evaluator = ConstraintEvaluator(repair_dataset)

    # SEC_3 (GV_RESTRICTED Mon P1..P6) assigned to Tuesday (ts_id 16) -> Unavailable!
    bad_sched = Schedule(genes=[
        Gene(section_id="SEC_1", timeslot_id=0, room_id="P101"),
        Gene(section_id="SEC_2", timeslot_id=16, room_id="LAB01"),
        Gene(section_id="SEC_3", timeslot_id=16, room_id="P102"), # Tuesday -> Lecturer unavailable!
    ])
    res = repairer.repair(bad_sched)
    assert res.success
    assert evaluator.evaluate_hard(res.schedule)[0] == 0

# 7. Duration 4 starting period 8 supported
@pytest.mark.unit
def test_repair_supports_duration_4_period_8(repair_dataset):
    ds = dict(repair_dataset)
    sec_d4 = CourseSection("SEC_D4", "C4", "Course 4", "GV01", "SV_CNTT1", 50, duration_periods=4, required_room_type="NORMAL")
    ds["course_sections"] = [sec_d4]
    repairer = ScheduleRepairEngine(ds)
    evaluator = ConstraintEvaluator(ds)

    # Place starting at ts_id 7 (Mon period 8)
    sched = Schedule(genes=[Gene(section_id="SEC_D4", timeslot_id=7, room_id="P101")])
    res = repairer.repair(sched)
    assert res.success
    assert evaluator.evaluate_hard(res.schedule)[0] == 0

# 8. Partial period overlap (A occupies 8-11, B occupies 11-12) detected and fixed
@pytest.mark.unit
def test_repair_handles_partial_period_overlap(repair_dataset):
    ds = dict(repair_dataset)
    sec_a = CourseSection("SEC_A", "CA", "Course A", "GV01", "SV_CNTT1", 40, duration_periods=4) # Occupies 8,9,10,11
    sec_b = CourseSection("SEC_B", "CB", "Course B", "GV02", "SV_CNTT2", 40, duration_periods=2) # Occupies 11,12
    ds["course_sections"] = [sec_a, sec_b]

    repairer = ScheduleRepairEngine(ds)
    evaluator = ConstraintEvaluator(ds)

    # Both assigned to P101 on Mon: SEC_A at ts_id 7 (P8..P11), SEC_B at ts_id 10 (P11..P12) -> Overlap on P11!
    bad_sched = Schedule(genes=[
        Gene(section_id="SEC_A", timeslot_id=7, room_id="P101"),
        Gene(section_id="SEC_B", timeslot_id=10, room_id="P101"),
    ])
    assert evaluator.evaluate_hard(bad_sched)[0] > 0

    res = repairer.repair(bad_sched)
    assert res.success
    assert evaluator.evaluate_hard(res.schedule)[0] == 0

# 9. Failed section does not consume resources
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
    # SEC_OK preserves its valid initial assignment at P101 ts 0 because SEC_FAIL did not pollute resource sets
    sec_ok_gene = [g for g in res.schedule.genes if g.section_id == "SEC_OK"][0]
    assert sec_ok_gene.room_id == "P101"
    assert sec_ok_gene.timeslot_id == 0




# 10. Input schedule is NOT mutated
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

# 11. Hard violations do NOT increase
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

# 12. When hard violations tie, pick lower soft penalty
@pytest.mark.unit
def test_lexicographic_soft_penalty_tie_breaking(repair_dataset):
    repairer = ScheduleRepairEngine(repair_dataset)
    evaluator = ConstraintEvaluator(repair_dataset)

    # Valid schedule
    valid_sched = Schedule(genes=[
        Gene(section_id="SEC_1", timeslot_id=0, room_id="P101"),
        Gene(section_id="SEC_2", timeslot_id=16, room_id="LAB01"),
        Gene(section_id="SEC_3", timeslot_id=2, room_id="P102"),
    ])
    res = repairer.repair(valid_sched)
    orig_hard, _ = evaluator.evaluate_hard(valid_sched)
    repaired_hard, _ = evaluator.evaluate_hard(res.schedule)
    assert orig_hard == 0 and repaired_hard == 0

# 13. Returns best attempt
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

# 14. Early stopping when hard = 0
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

# 15. Same seed produces same result (reproducibility)
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

    # SEC_1 is valid at Mon P1 (ts 0, P101)
    # SEC_2 (LAB, ts 16 P101) and SEC_3 (NORMAL, ts 16 P102) are invalid/conflicting
    sched = Schedule(genes=[
        Gene(section_id="SEC_1", timeslot_id=0, room_id="P101"), # Valid
        Gene(section_id="SEC_2", timeslot_id=16, room_id="P101"), # Invalid (LAB req)
        Gene(section_id="SEC_3", timeslot_id=16, room_id="P102"), # Invalid (Lecturer unavailable)
    ])
    res = repairer.repair(sched)
    sec1_gene = [g for g in res.schedule.genes if g.section_id == "SEC_1"][0]
    assert sec1_gene.timeslot_id == 0
    assert sec1_gene.room_id == "P101"



# 17. RepairStats updated correctly
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


# --- Task 2 Refinement Mandatory Tests ---

@pytest.mark.unit
def test_repair_sections_repaired_counts_only_changed_sections(repair_dataset):
    repairer = ScheduleRepairEngine(repair_dataset)
    repairer.stats.reset()

    # SEC_1 is valid at Mon P1 (ts 0, P101).
    # SEC_2 (ts 16, P101 - invalid LAB req) and SEC_3 (ts 16, P102 - invalid lecturer unavailable) will be changed.
    ds = dict(repair_dataset)
    sec3_g2 = CourseSection("SEC_3", "C3", "Course 3", "GV_RESTRICTED", "SV_CNTT2", 40, duration_periods=2, required_room_type="NORMAL")
    ds["course_sections"] = [repair_dataset["course_sections"][0], repair_dataset["course_sections"][1], sec3_g2]
    repairer = ScheduleRepairEngine(ds)

    sched = Schedule(genes=[
        Gene(section_id="SEC_1", timeslot_id=0, room_id="P101"),  # Unchanged
        Gene(section_id="SEC_2", timeslot_id=16, room_id="P101"), # Changed to LAB01
        Gene(section_id="SEC_3", timeslot_id=16, room_id="P102"), # Changed to Mon P1 P102
    ])
    res = repairer.repair(sched)
    assert res.success
    assert repairer.stats.sections_repaired == 2  # Exactly 2 sections changed, not 3!

@pytest.mark.unit
def test_repair_output_equals_input_failure(repair_dataset):
    repairer = ScheduleRepairEngine(repair_dataset)
    repairer.stats.reset()

    # Fully valid schedule: repair output is equal to input (no improvement)
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

    # Impossible schedule to fit, max_attempts = 3
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

    # Output equal to input -> Call failed -> sections_repaired MUST be 0
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
    # Calls in second run must NOT accumulate calls from first run
    assert calls2 == calls1

@pytest.mark.unit
def test_ga_engine_shares_evaluator_object():
    from ga import GeneticAlgorithmEngine
    from dataset import DatasetFactory

    ds = DatasetFactory.create_medium_dataset(seed=42)
    engine = GeneticAlgorithmEngine(ds, pop_size=10)

    # Must be the EXACT same evaluator instance in memory
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
