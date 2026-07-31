import sys
from pathlib import Path

# Ensure root directory is on sys.path
root_dir = Path(__file__).parent.parent
if str(root_dir) not in sys.path:
    sys.path.insert(0, str(root_dir))

import pytest
from domain import Room, Lecturer, StudentGroup, CourseSection, Course
from dataset import DatasetFactory, create_theory_timeslots

@pytest.fixture
def small_dataset():
    """Returns a fresh instance of the small dataset."""
    return DatasetFactory.create_small_dataset()

@pytest.fixture
def medium_dataset():
    """Returns a fresh instance of the medium dataset (seed 42)."""
    return DatasetFactory.create_medium_dataset(seed=42)

@pytest.fixture
def sample_rooms():
    """Returns a standard list of rooms (NORMAL and LAB)."""
    return [
        Room(id="P101", name="Phòng 101", capacity=100, room_type="NORMAL"),
        Room(id="P102", name="Phòng 102", capacity=50, room_type="NORMAL"),
        Room(id="LAB101", name="Phòng LAB 101", capacity=100, room_type="LAB"),
        Room(id="LAB102", name="Phòng LAB 102", capacity=40, room_type="LAB"),
    ]

@pytest.fixture
def sample_timeslots():
    """Returns 5 days x 6 periods HaUI theory timeslots."""
    return create_theory_timeslots(days=["Thứ 2", "Thứ 3", "Thứ 4", "Thứ 5", "Thứ 6"], max_period=6)

@pytest.fixture
def sample_lecturers():
    """Returns sample lecturers including restricted availability."""
    return [
        Lecturer(id="GV01", name="Giảng viên 1"),
        Lecturer(id="GV02", name="Giảng viên 2", available_timeslot_ids=frozenset([0, 1, 2, 3, 4, 5])),
        Lecturer(id="GV03", name="Giảng viên 3"),
    ]

@pytest.fixture
def sample_groups():
    """Returns sample student groups."""
    return [
        StudentGroup(id="SV_CNTT1", name="Lớp CNTT 1", student_count=60),
        StudentGroup(id="SV_CNTT2", name="Lớp CNTT 2", student_count=45),
    ]

@pytest.fixture
def sample_sections():
    """Returns sample course sections with duration 1, 2, and 3."""
    return [
        CourseSection("LHP01", "CS101", "Nhập môn Lập trình", "GV01", "SV_CNTT1", 60, duration_periods=2, required_room_type="NORMAL"),
        CourseSection("LHP02", "CS102", "Cấu trúc dữ liệu", "GV02", "SV_CNTT1", 60, duration_periods=2, required_room_type="NORMAL"),
        CourseSection("LHP03", "LAB101", "Thực hành Lập trình", "GV01", "SV_CNTT2", 40, duration_periods=3, required_room_type="LAB"),
        CourseSection("LHP04", "MATH101", "Toán cao cấp", "GV03", "SV_CNTT2", 45, duration_periods=1, required_room_type="NORMAL"),
    ]
