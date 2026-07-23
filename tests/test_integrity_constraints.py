import pytest
from dataset import DatasetFactory
from constraints import ConstraintEvaluator
from domain import Schedule, Gene

def test_missing_section_violation():
    dataset = DatasetFactory.create_dataset()
    evaluator = ConstraintEvaluator(dataset)
    
    sec_ids = [s.section_id for s in dataset["course_sections"]]
    genes = [
        Gene(section_id=sec_id, room_id=dataset["rooms"][0].id, timeslot_id=i)
        for i, sec_id in enumerate(sec_ids[:-1])
    ]
    sched = Schedule(genes=genes)
    
    total_hard, details = evaluator.evaluate_hard(sched)
    assert total_hard > 0
    assert details["missing_sections"] == 1
    assert details["gene_count_mismatch"] == 1

def test_duplicate_section_violation():
    dataset = DatasetFactory.create_dataset()
    evaluator = ConstraintEvaluator(dataset)
    
    sec_ids = [s.section_id for s in dataset["course_sections"]]
    sec_ids[-1] = sec_ids[0]
    genes = [
        Gene(section_id=sec_id, room_id=dataset["rooms"][0].id, timeslot_id=i)
        for i, sec_id in enumerate(sec_ids)
    ]
    sched = Schedule(genes=genes)
    
    total_hard, details = evaluator.evaluate_hard(sched)
    assert total_hard > 0
    assert details["duplicate_sections"] == 1

def test_invalid_section_id_violation():
    dataset = DatasetFactory.create_dataset()
    evaluator = ConstraintEvaluator(dataset)
    
    sec_ids = [s.section_id for s in dataset["course_sections"]]
    sec_ids[0] = "INVALID_SECTION_999"
    genes = [
        Gene(section_id=sec_id, room_id=dataset["rooms"][0].id, timeslot_id=i)
        for i, sec_id in enumerate(sec_ids)
    ]
    sched = Schedule(genes=genes)
    
    total_hard, details = evaluator.evaluate_hard(sched)
    assert total_hard > 0
    assert details["invalid_section_ids"] == 1

def test_invalid_room_id_violation():
    dataset = DatasetFactory.create_dataset()
    evaluator = ConstraintEvaluator(dataset)
    
    sec_ids = [s.section_id for s in dataset["course_sections"]]
    genes = [
        Gene(section_id=sec_id, room_id="NON_EXISTENT_ROOM", timeslot_id=i)
        for i, sec_id in enumerate(sec_ids)
    ]
    sched = Schedule(genes=genes)
    
    total_hard, details = evaluator.evaluate_hard(sched)
    assert total_hard > 0
    assert details["invalid_room_ids"] == len(sec_ids)

def test_invalid_timeslot_id_violation():
    dataset = DatasetFactory.create_dataset()
    evaluator = ConstraintEvaluator(dataset)
    
    sec_ids = [s.section_id for s in dataset["course_sections"]]
    genes = [
        Gene(section_id=sec_id, room_id=dataset["rooms"][0].id, timeslot_id=99999)
        for i, sec_id in enumerate(sec_ids)
    ]
    sched = Schedule(genes=genes)
    
    total_hard, details = evaluator.evaluate_hard(sched)
    assert total_hard > 0
    assert details["invalid_timeslot_ids"] == len(sec_ids)

def test_gene_count_mismatch_violation():
    dataset = DatasetFactory.create_dataset()
    evaluator = ConstraintEvaluator(dataset)
    
    sec_ids = [s.section_id for s in dataset["course_sections"]]
    genes = [
        Gene(section_id=sec_id, room_id=dataset["rooms"][0].id, timeslot_id=i)
        for i, sec_id in enumerate(sec_ids)
    ]
    genes.append(Gene(section_id=sec_ids[0], room_id=dataset["rooms"][0].id, timeslot_id=0))
    sched = Schedule(genes=genes)
    
    total_hard, details = evaluator.evaluate_hard(sched)
    assert total_hard > 0
    assert details["gene_count_mismatch"] == 1
