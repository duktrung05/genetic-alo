import pytest
from dataset import DatasetFactory
from domain import Schedule, Gene, Room, Lecturer, CourseSection, Timeslot
from constraints import ConstraintEvaluator, ScheduleRepairEngine, HardConstraintChecker

def test_lecturer_available_no_violation():
    # Test 1: Section scheduled in a timeslot listed in lecturer's availability -> lecturer_unavailable == 0
    dataset = DatasetFactory.create_small_dataset()
    # GV01 teaches LHP01 (timeslot 0) and LHP12 (timeslot 11)
    dataset["lecturers"][0] = Lecturer(id="GV01", name="Test Lec", available_timeslot_ids=frozenset([0, 1, 2, 11]))
    evaluator = ConstraintEvaluator(dataset)

    sec_ids = [s.section_id for s in dataset["course_sections"]]
    genes = [
        Gene(section_id=sec_ids[i], room_id=dataset["rooms"][i % len(dataset["rooms"])].id, timeslot_id=i)
        for i in range(len(sec_ids))
    ]
    sched = Schedule(genes=genes)
    _, details = evaluator.evaluate_hard(sched)
    assert details["lecturer_unavailable"] == 0

def test_lecturer_unavailable_violation():
    # Test 2: Section scheduled in a timeslot NOT listed in lecturer's availability -> lecturer_unavailable == 1
    dataset = DatasetFactory.create_small_dataset()
    # GV01 teaches LHP01 (ts 0) and LHP12 (ts 11). If availability is [1, 2], both ts 0 and 11 violate.
    # If availability is [0, 1, 2], then ts 11 violates (1 violation).
    dataset["lecturers"][0] = Lecturer(id="GV01", name="Test Lec", available_timeslot_ids=frozenset([0, 1, 2]))
    evaluator = ConstraintEvaluator(dataset)

    sec_ids = [s.section_id for s in dataset["course_sections"]]
    genes = [
        Gene(section_id=sec_ids[i], room_id=dataset["rooms"][i % len(dataset["rooms"])].id, timeslot_id=i)
        for i in range(len(sec_ids))
    ]
    sched = Schedule(genes=genes)
    _, details = evaluator.evaluate_hard(sched)
    assert details["lecturer_unavailable"] >= 1

def test_availability_none_unrestricted():
    # Test 3: available_timeslot_ids = None means unrestricted (0 violations for any valid timeslot)
    dataset = DatasetFactory.create_small_dataset()
    dataset["lecturers"][0] = Lecturer(id="GV01", name="Test Lec", available_timeslot_ids=None)
    evaluator = ConstraintEvaluator(dataset)

    sec_ids = [s.section_id for s in dataset["course_sections"]]
    genes = [
        Gene(section_id=sec_ids[i], room_id=dataset["rooms"][i % len(dataset["rooms"])].id, timeslot_id=i)
        for i in range(len(sec_ids))
    ]
    sched = Schedule(genes=genes)
    _, details = evaluator.evaluate_hard(sched)
    assert details["lecturer_unavailable"] == 0

def test_room_type_match_no_violation():
    # Test 4: required_room_type == room_type -> room_type_mismatch == 0
    dataset = DatasetFactory.create_small_dataset()
    dataset["rooms"][0] = Room(id="P101", name="P101", capacity=100, room_type="LAB")
    dataset["course_sections"][0].required_room_type = "LAB"
    evaluator = ConstraintEvaluator(dataset)

    sec_ids = [s.section_id for s in dataset["course_sections"]]
    genes = [
        Gene(section_id=sec_ids[i], room_id=dataset["rooms"][0].id if i == 0 else dataset["rooms"][1].id, timeslot_id=i)
        for i in range(len(sec_ids))
    ]
    sched = Schedule(genes=genes)
    _, details = evaluator.evaluate_hard(sched)
    assert details["room_type_mismatch"] == 0

def test_room_type_mismatch_violation():
    # Test 5: required_room_type = LAB but room_type = NORMAL -> room_type_mismatch == 1
    dataset = DatasetFactory.create_small_dataset()
    dataset["rooms"][0] = Room(id="P101", name="P101", capacity=100, room_type="NORMAL")
    dataset["course_sections"][0].required_room_type = "LAB"
    evaluator = ConstraintEvaluator(dataset)

    sec_ids = [s.section_id for s in dataset["course_sections"]]
    genes = [
        Gene(section_id=sec_ids[i], room_id=dataset["rooms"][0].id if i == 0 else dataset["rooms"][1].id, timeslot_id=i)
        for i in range(len(sec_ids))
    ]
    sched = Schedule(genes=genes)
    _, details = evaluator.evaluate_hard(sched)
    assert details["room_type_mismatch"] >= 1

def test_capacity_and_room_type_evaluated_independently():
    # Test 6: Room right type but small capacity -> capacity_violation counted. Room right capacity but wrong type -> room_type_mismatch counted.
    dataset = DatasetFactory.create_small_dataset()
    # P101: LAB, capacity 10 (small capacity)
    dataset["rooms"][0] = Room(id="P101", name="P101", capacity=10, room_type="LAB")
    # P102: NORMAL, capacity 100
    dataset["rooms"][1] = Room(id="P102", name="P102", capacity=100, room_type="NORMAL")

    # Section 0: required LAB, student_count 65
    sec0 = dataset["course_sections"][0]
    sec0.required_room_type = "LAB"
    sec0.student_count = 65

    # Case A: Gene in P101 (LAB, cap 10) -> capacity violation
    evaluator = ConstraintEvaluator(dataset)
    sched_a = Schedule(genes=[Gene(section_id=sec0.section_id, room_id="P101", timeslot_id=0)])
    _, details_a = evaluator.evaluate_hard(sched_a)
    assert details_a["capacity_violation"] == 1
    assert details_a["room_type_mismatch"] == 0

    # Case B: Gene in P102 (NORMAL, cap 100) -> room type mismatch
    sched_b = Schedule(genes=[Gene(section_id=sec0.section_id, room_id="P102", timeslot_id=0)])
    _, details_b = evaluator.evaluate_hard(sched_b)
    assert details_b["capacity_violation"] == 0
    assert details_b["room_type_mismatch"] == 1

def test_repair_respects_lecturer_availability():
    # Test 7: Schedule with lecturer availability conflict is repaired into an available timeslot
    dataset = DatasetFactory.create_small_dataset()
    # GV01 teaches LHP01 and LHP12 (2 sections). Give GV01 5 available timeslots [5, 6, 7, 8, 9]
    dataset["lecturers"][0] = Lecturer(id="GV01", name="Test Lec", available_timeslot_ids=frozenset([5, 6, 7, 8, 9]))
    repairer = ScheduleRepairEngine(dataset)

    sec_ids = [s.section_id for s in dataset["course_sections"]]
    # Initial genes: place LHP01 (GV01) at timeslot_id = 0 (conflict!), LHP12 at timeslot_id = 11 (conflict!)
    genes = [
        Gene(section_id=sec_ids[i], room_id=dataset["rooms"][i % len(dataset["rooms"])].id, timeslot_id=i)
        for i in range(len(sec_ids))
    ]
    sched = Schedule(genes=genes)
    res = repairer.repair(sched)

    assert res.remaining_hard_violations == 0
    lhp01_gene = [g for g in res.schedule.genes if g.section_id == "LHP01"][0]
    lhp12_gene = [g for g in res.schedule.genes if g.section_id == "LHP12"][0]
    assert lhp01_gene.timeslot_id in [5, 6, 7, 8, 9]
    assert lhp12_gene.timeslot_id in [5, 6, 7, 8, 9]

def test_repair_respects_required_room_type():
    # Test 8: Section needing LAB room is repaired to a LAB room
    dataset = DatasetFactory.create_small_dataset()
    dataset["rooms"][0] = Room(id="P101", name="P101", capacity=100, room_type="NORMAL")
    dataset["rooms"][1] = Room(id="LAB01", name="LAB01", capacity=100, room_type="LAB")
    dataset["course_sections"][0].required_room_type = "LAB"

    repairer = ScheduleRepairEngine(dataset)
    sec_ids = [s.section_id for s in dataset["course_sections"]]
    genes = [
        Gene(section_id=sec_ids[i], room_id="P101", timeslot_id=i)
        for i in range(len(sec_ids))
    ]
    sched = Schedule(genes=genes)
    res = repairer.repair(sched)

    lhp01_gene = [g for g in res.schedule.genes if g.section_id == sec_ids[0]][0]
    assert lhp01_gene.room_id == "LAB01"

def test_medium_dataset_validates_availability_and_room_types():
    # Test 9: Validate medium dataset properties
    dataset = DatasetFactory.create_medium_dataset(seed=42)

    normal_rooms = [r for r in dataset["rooms"] if r.room_type == "NORMAL"]
    lab_rooms = [r for r in dataset["rooms"] if r.room_type == "LAB"]
    assert len(normal_rooms) == 6
    assert len(lab_rooms) == 2

    lab_sections = [s for s in dataset["course_sections"] if s.required_room_type == "LAB"]
    assert len(lab_sections) == 10

    # Ensure every LAB section has at least one LAB room with sufficient capacity
    for s in lab_sections:
        valid_labs = [r for r in lab_rooms if r.capacity >= s.student_count]
        assert len(valid_labs) >= 1

    # Ensure restricted lecturers have valid available_timeslot_ids
    restricted_lecs = [l for l in dataset["lecturers"] if l.available_timeslot_ids is not None]
    assert len(restricted_lecs) == 5
    for l in restricted_lecs:
        assert len(l.available_timeslot_ids) >= 20
