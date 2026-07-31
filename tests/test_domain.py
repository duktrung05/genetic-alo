import pytest
from domain import Timeslot, CourseSection, Gene, Schedule
from constraints import ConstraintEvaluator

@pytest.mark.unit
def test_timeslot_valid_fields_and_immutability():
    ts = Timeslot(id=0, day="Thứ 2", period=1, start_time="07:00", end_time="07:50", session="morning")
    assert ts.id == 0
    assert ts.day == "Thứ 2"
    assert ts.period == 1
    assert ts.start_time == "07:00"
    assert ts.end_time == "07:50"
    assert ts.session == "morning"

    with pytest.raises(AttributeError):
        ts.period = 2

@pytest.mark.unit
@pytest.mark.parametrize("session", ["morning", "afternoon", "evening"])
def test_timeslot_valid_sessions(session):
    ts = Timeslot(id=1, day="Thứ 2", period=1, start_time="07:00", end_time="07:50", session=session)
    assert ts.session == session

@pytest.mark.unit
def test_timeslot_invalid_session_raises_value_error():
    with pytest.raises(ValueError, match="Invalid session"):
        Timeslot(id=1, day="Thứ 2", period=1, start_time="07:00", end_time="07:50", session="midnight")

@pytest.mark.unit
@pytest.mark.parametrize("duration", [1, 2, 3])
def test_course_section_valid_durations(duration):
    sec = CourseSection("SEC1", "C1", "Course 1", "GV1", "G1", 30, duration_periods=duration)
    assert sec.duration_periods == duration

@pytest.mark.unit
@pytest.mark.parametrize("invalid_duration", [0, -1])
def test_course_section_invalid_duration_raises_value_error(invalid_duration):
    with pytest.raises(ValueError, match="duration_periods must be >= 1"):
        CourseSection("SEC1", "C1", "Course 1", "GV1", "G1", 30, duration_periods=invalid_duration)

@pytest.mark.unit
def test_schedule_gene_count_integrity(small_dataset):
    sections = small_dataset["course_sections"]
    rooms = small_dataset["rooms"]
    evaluator = ConstraintEvaluator(small_dataset)

    # Valid schedule
    genes = [Gene(section_id=s.section_id, timeslot_id=0, room_id=rooms[0].id) for s in sections]
    sched = Schedule(genes=genes)

    assert len(sched.genes) == len(sections)
    _, details = evaluator.evaluate_hard(sched)
    assert details["missing_sections"] == 0
    assert details["duplicate_sections"] == 0

    # Incorrect gene count
    short_sched = Schedule(genes=genes[:-1])
    _, details_short = evaluator.evaluate_hard(short_sched)
    assert details_short["missing_sections"] > 0

@pytest.mark.unit
def test_schedule_missing_or_duplicate_section_ids(small_dataset):
    sections = small_dataset["course_sections"]
    rooms = small_dataset["rooms"]
    evaluator = ConstraintEvaluator(small_dataset)

    # Missing & duplicate section
    genes_missing = [Gene(section_id=s.section_id, timeslot_id=0, room_id=rooms[0].id) for s in sections[1:]]
    genes_missing.append(Gene(section_id=sections[1].section_id, timeslot_id=1, room_id=rooms[0].id))
    sched_missing = Schedule(genes=genes_missing)

    _, details = evaluator.evaluate_hard(sched_missing)
    assert details["missing_sections"] > 0
    assert details["duplicate_sections"] > 0

@pytest.mark.unit
def test_schedule_invalid_room_or_timeslot_ids(small_dataset):
    sections = small_dataset["course_sections"]
    rooms = small_dataset["rooms"]
    evaluator = ConstraintEvaluator(small_dataset)

    # Invalid room ID
    genes_bad_room = [Gene(section_id=sections[0].section_id, timeslot_id=0, room_id="ROOM_999")]
    for s in sections[1:]:
        genes_bad_room.append(Gene(section_id=s.section_id, timeslot_id=0, room_id=rooms[0].id))
    sched_bad_room = Schedule(genes=genes_bad_room)
    _, details_room = evaluator.evaluate_hard(sched_bad_room)
    assert details_room["invalid_room_ids"] == 1

    # Invalid timeslot ID
    genes_bad_ts = [Gene(section_id=sections[0].section_id, timeslot_id=9999, room_id=rooms[0].id)]
    for s in sections[1:]:
        genes_bad_ts.append(Gene(section_id=s.section_id, timeslot_id=0, room_id=rooms[0].id))
    sched_bad_ts = Schedule(genes=genes_bad_ts)
    _, details_ts = evaluator.evaluate_hard(sched_bad_ts)
    assert details_ts["invalid_timeslot_ids"] == 1
