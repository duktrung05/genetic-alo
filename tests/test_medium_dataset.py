import pytest
from dataset import DatasetFactory

def test_medium_dataset_entity_counts():
    dataset = DatasetFactory.create_medium_dataset(seed=42)
    assert len(dataset["course_sections"]) == 60
    assert len(dataset["lecturers"]) == 15
    assert len(dataset["rooms"]) == 8
    assert len(dataset["student_groups"]) == 12
    assert len(dataset["timeslots"]) == 30

def test_medium_dataset_unique_ids():
    dataset = DatasetFactory.create_medium_dataset(seed=42)

    section_ids = [s.section_id for s in dataset["course_sections"]]
    assert len(section_ids) == len(set(section_ids)) == 60

    lecturer_ids = [l.id for l in dataset["lecturers"]]
    assert len(lecturer_ids) == len(set(lecturer_ids)) == 15

    room_ids = [r.id for r in dataset["rooms"]]
    assert len(room_ids) == len(set(room_ids)) == 8

    group_ids = [g.id for g in dataset["student_groups"]]
    assert len(group_ids) == len(set(group_ids)) == 12

    course_ids = [c.course_id for c in dataset["courses"]]
    assert len(course_ids) == len(set(course_ids))

    timeslot_ids = [t.id for t in dataset["timeslots"]]
    assert len(timeslot_ids) == len(set(timeslot_ids)) == 30

def test_medium_dataset_valid_references():
    dataset = DatasetFactory.create_medium_dataset(seed=42)

    lecturer_ids = {l.id for l in dataset["lecturers"]}
    group_ids = {g.id for g in dataset["student_groups"]}
    course_ids = {c.course_id for c in dataset["courses"]}

    for sec in dataset["course_sections"]:
        assert sec.lecturer_id in lecturer_ids
        assert sec.group_id in group_ids
        assert sec.course_id in course_ids

def test_medium_dataset_room_capacities_feasible():
    dataset = DatasetFactory.create_medium_dataset(seed=42)
    rooms = dataset["rooms"]

    for sec in dataset["course_sections"]:
        valid_rooms = [r for r in rooms if r.capacity >= sec.student_count]
        assert len(valid_rooms) >= 1

def test_medium_dataset_student_group_distribution():
    dataset = DatasetFactory.create_medium_dataset(seed=42)
    group_counts = {}
    for sec in dataset["course_sections"]:
        group_counts[sec.group_id] = group_counts.get(sec.group_id, 0) + 1

    assert sum(group_counts.values()) == 60
    assert len(group_counts) == 12
    counts_sorted = sorted(group_counts.values())
    # 4 groups x 3, 4 groups x 5, 4 groups x 7
    assert counts_sorted == [3, 3, 3, 3, 5, 5, 5, 5, 7, 7, 7, 7]

def test_medium_dataset_lecturer_distribution():
    dataset = DatasetFactory.create_medium_dataset(seed=42)
    lec_counts = {}
    for sec in dataset["course_sections"]:
        lec_counts[sec.lecturer_id] = lec_counts.get(sec.lecturer_id, 0) + 1

    assert sum(lec_counts.values()) == 60
    assert len(lec_counts) == 15
    counts_sorted = sorted(lec_counts.values())
    # 6 lecturers x 2, 5 lecturers x 4, 4 lecturers x 7
    assert counts_sorted == [2, 2, 2, 2, 2, 2, 4, 4, 4, 4, 4, 7, 7, 7, 7]

def test_medium_dataset_same_seed_same_order():
    d1 = DatasetFactory.create_medium_dataset(seed=42)
    d2 = DatasetFactory.create_medium_dataset(seed=42)

    s1_ids = [s.section_id for s in d1["course_sections"]]
    s2_ids = [s.section_id for s in d2["course_sections"]]
    assert s1_ids == s2_ids

def test_medium_dataset_different_seed_different_order():
    d1 = DatasetFactory.create_medium_dataset(seed=42)
    d2 = DatasetFactory.create_medium_dataset(seed=999)

    s1_ids = [s.section_id for s in d1["course_sections"]]
    s2_ids = [s.section_id for s in d2["course_sections"]]
    assert s1_ids != s2_ids

def test_medium_dataset_sections_not_grouped_sequentially():
    dataset = DatasetFactory.create_medium_dataset(seed=42)
    groups = [s.group_id for s in dataset["course_sections"]]

    # Verify that not all sections of a group appear in one unbroken block
    is_grouped_sequentially = True
    seen_groups = set()
    prev_group = None
    for g in groups:
        if g != prev_group:
            if g in seen_groups:
                is_grouped_sequentially = False
                break
            seen_groups.add(g)
            prev_group = g

    assert not is_grouped_sequentially

def test_small_dataset_backward_compatibility():
    d_small = DatasetFactory.create_small_dataset()
    d_default = DatasetFactory.create_dataset()

    assert len(d_small["course_sections"]) == 14
    assert len(d_small["lecturers"]) == 8
    assert len(d_small["rooms"]) == 5
    assert len(d_small["student_groups"]) == 4
    assert len(d_small["timeslots"]) == 25

    # create_dataset() returns small dataset
    assert len(d_default["course_sections"]) == 14
    assert len(d_default["lecturers"]) == 8
    assert len(d_default["rooms"]) == 5
    assert len(d_default["student_groups"]) == 4
    assert len(d_default["timeslots"]) == 25
