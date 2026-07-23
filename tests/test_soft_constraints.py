import pytest
from dataset import DatasetFactory
from domain import Schedule, Gene
from constraints import SoftConstraintChecker, SoftConstraintConfig, ConstraintEvaluator

def test_student_gaps_test_1():
    # Test 1: periods = [1, 1, 2] -> expected gaps = 0
    dataset = DatasetFactory.create_dataset()
    sections = dataset["course_sections"]
    sec1 = [s for s in sections if s.group_id == "SV_CNTT1"][0]
    sec2 = [s for s in sections if s.group_id == "SV_CNTT1"][1]
    sec3 = [s for s in sections if s.group_id == "SV_CNTT1"][2]
    
    ts1 = [t for t in dataset["timeslots"] if t.day == "Thứ 2" and t.period == 1][0]
    ts2 = [t for t in dataset["timeslots"] if t.day == "Thứ 2" and t.period == 2][0]
    
    genes = [
        Gene(section_id=sec1.section_id, room_id=dataset["rooms"][0].id, timeslot_id=ts1.id),
        Gene(section_id=sec2.section_id, room_id=dataset["rooms"][1].id, timeslot_id=ts1.id),
        Gene(section_id=sec3.section_id, room_id=dataset["rooms"][2].id, timeslot_id=ts2.id),
    ]
    sched = Schedule(genes=genes)
    checker = SoftConstraintChecker(
        {c.section_id: c for c in dataset["course_sections"]},
        {r.id: r for r in dataset["rooms"]},
        {t.id: t for t in dataset["timeslots"]}
    )
    raw_count, details = checker.evaluate(sched)
    assert details["student_gaps"] == 0

def test_student_gaps_test_2():
    # Test 2: periods = [1, 3] -> expected gaps = 1
    dataset = DatasetFactory.create_dataset()
    sections = dataset["course_sections"]
    sec1 = [s for s in sections if s.group_id == "SV_CNTT1"][0]
    sec2 = [s for s in sections if s.group_id == "SV_CNTT1"][1]
    
    ts1 = [t for t in dataset["timeslots"] if t.day == "Thứ 2" and t.period == 1][0]
    ts3 = [t for t in dataset["timeslots"] if t.day == "Thứ 2" and t.period == 3][0]
    
    genes = [
        Gene(section_id=sec1.section_id, room_id=dataset["rooms"][0].id, timeslot_id=ts1.id),
        Gene(section_id=sec2.section_id, room_id=dataset["rooms"][1].id, timeslot_id=ts3.id),
    ]
    sched = Schedule(genes=genes)
    checker = SoftConstraintChecker(
        {c.section_id: c for c in dataset["course_sections"]},
        {r.id: r for r in dataset["rooms"]},
        {t.id: t for t in dataset["timeslots"]}
    )
    raw_count, details = checker.evaluate(sched)
    assert details["student_gaps"] == 1

def test_student_gaps_test_3():
    # Test 3: periods = [1, 1, 3] -> expected gaps = 1
    dataset = DatasetFactory.create_dataset()
    sections = dataset["course_sections"]
    sec1 = [s for s in sections if s.group_id == "SV_CNTT1"][0]
    sec2 = [s for s in sections if s.group_id == "SV_CNTT1"][1]
    sec3 = [s for s in sections if s.group_id == "SV_CNTT1"][2]
    
    ts1 = [t for t in dataset["timeslots"] if t.day == "Thứ 2" and t.period == 1][0]
    ts3 = [t for t in dataset["timeslots"] if t.day == "Thứ 2" and t.period == 3][0]
    
    genes = [
        Gene(section_id=sec1.section_id, room_id=dataset["rooms"][0].id, timeslot_id=ts1.id),
        Gene(section_id=sec2.section_id, room_id=dataset["rooms"][1].id, timeslot_id=ts1.id),
        Gene(section_id=sec3.section_id, room_id=dataset["rooms"][2].id, timeslot_id=ts3.id),
    ]
    sched = Schedule(genes=genes)
    checker = SoftConstraintChecker(
        {c.section_id: c for c in dataset["course_sections"]},
        {r.id: r for r in dataset["rooms"]},
        {t.id: t for t in dataset["timeslots"]}
    )
    raw_count, details = checker.evaluate(sched)
    assert details["student_gaps"] == 1

def test_student_gaps_different_days_no_gap():
    # Test 4: Two different days do not form a gap
    dataset = DatasetFactory.create_dataset()
    sections = dataset["course_sections"]
    sec1 = [s for s in sections if s.group_id == "SV_CNTT1"][0]
    sec2 = [s for s in sections if s.group_id == "SV_CNTT1"][1]
    
    ts_mon = [t for t in dataset["timeslots"] if t.day == "Thứ 2" and t.period == 1][0]
    ts_tue = [t for t in dataset["timeslots"] if t.day == "Thứ 3" and t.period == 5][0]
    
    genes = [
        Gene(section_id=sec1.section_id, room_id=dataset["rooms"][0].id, timeslot_id=ts_mon.id),
        Gene(section_id=sec2.section_id, room_id=dataset["rooms"][1].id, timeslot_id=ts_tue.id),
    ]
    sched = Schedule(genes=genes)
    checker = SoftConstraintChecker(
        {c.section_id: c for c in dataset["course_sections"]},
        {r.id: r for r in dataset["rooms"]},
        {t.id: t for t in dataset["timeslots"]}
    )
    raw_count, details = checker.evaluate(sched)
    assert details["student_gaps"] == 0

def test_weighted_penalty_calculation():
    # Test 5: student_gaps = 2, weight = 5; difficult_afternoon = 1, weight = 3 -> raw = 3, weighted = 13
    config = SoftConstraintConfig(weights={
        "student_gaps": 5,
        "consecutive_teaching": 6,
        "difficult_afternoon": 3,
        "daily_imbalance": 8,
    })
    dataset = DatasetFactory.create_dataset()
    checker = SoftConstraintChecker(
        {c.section_id: c for c in dataset["course_sections"]},
        {r.id: r for r in dataset["rooms"]},
        {t.id: t for t in dataset["timeslots"]},
        config=config
    )
    details = {"student_gaps": 2, "difficult_afternoon": 1, "consecutive_teaching": 0, "daily_imbalance": 0}
    raw_count = sum(details.values())
    weighted_penalty = checker.calculate_weighted_penalty(details)
    
    assert raw_count == 3
    assert weighted_penalty == 13

def test_missing_weight_raises_value_error():
    # Test 6: Missing weight in config raises ValueError
    config = SoftConstraintConfig(weights={
        "consecutive_teaching": 6,
        "difficult_afternoon": 3,
        "daily_imbalance": 8,
    })
    dataset = DatasetFactory.create_dataset()
    with pytest.raises(ValueError):
        SoftConstraintChecker(
            {c.section_id: c for c in dataset["course_sections"]},
            {r.id: r for r in dataset["rooms"]},
            {t.id: t for t in dataset["timeslots"]},
            config=config
        )

def test_negative_weight_raises_value_error():
    # Test 7: Negative weight in config raises ValueError
    config = SoftConstraintConfig(weights={
        "student_gaps": -1,
        "consecutive_teaching": 6,
        "difficult_afternoon": 3,
        "daily_imbalance": 8,
    })
    dataset = DatasetFactory.create_dataset()
    with pytest.raises(ValueError):
        SoftConstraintChecker(
            {c.section_id: c for c in dataset["course_sections"]},
            {r.id: r for r in dataset["rooms"]},
            {t.id: t for t in dataset["timeslots"]},
            config=config
        )

def test_afternoon_start_period_less_than_1_raises_value_error():
    # Test 8: afternoon_start_period < 1 raises ValueError
    config = SoftConstraintConfig(afternoon_start_period=0)
    dataset = DatasetFactory.create_dataset()
    with pytest.raises(ValueError):
        SoftConstraintChecker(
            {c.section_id: c for c in dataset["course_sections"]},
            {r.id: r for r in dataset["rooms"]},
            {t.id: t for t in dataset["timeslots"]},
            config=config
        )
