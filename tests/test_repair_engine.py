import pytest
from dataset import DatasetFactory
from constraints import ScheduleRepairEngine, RepairResult
from domain import Schedule, Gene, Room

def test_repair_engine_success():
    dataset = DatasetFactory.create_dataset()
    repairer = ScheduleRepairEngine(dataset)
    
    sec_ids = [s.section_id for s in dataset["course_sections"]]
    genes = [
        Gene(section_id=sec_id, room_id=dataset["rooms"][0].id, timeslot_id=0)
        for sec_id in sec_ids
    ]
    sched = Schedule(genes=genes)
    
    result = repairer.repair(sched)
    assert isinstance(result, RepairResult)
    assert result.success is True
    assert result.remaining_hard_violations == 0
    assert result.failed_section_ids == []

def test_repair_engine_failure_with_failed_section_ids():
    dataset = DatasetFactory.create_dataset()
    
    # Set all rooms to small capacity 10, while LHP01 has student_count 65
    dataset["rooms"] = [Room(id="SMALL_ROOM", name="Small Room", capacity=10)]
    
    repairer = ScheduleRepairEngine(dataset)
    
    sec_ids = [s.section_id for s in dataset["course_sections"]]
    genes = [
        Gene(section_id=sec_id, room_id="SMALL_ROOM", timeslot_id=i % len(dataset["timeslots"]))
        for i, sec_id in enumerate(sec_ids)
    ]
    sched = Schedule(genes=genes)
    
    result = repairer.repair(sched)
    assert isinstance(result, RepairResult)
    assert result.success is False
    assert result.remaining_hard_violations > 0
    assert "LHP01" in result.failed_section_ids
