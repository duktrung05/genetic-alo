from dataclasses import dataclass
from typing import Optional

VALID_SHIFTS = frozenset({"morning", "afternoon", "evening"})

@dataclass
class Course:
    course_id: str
    name: str
    credits: int
    is_difficult: bool = False
    # Chỉ tùy chọn đối với các bộ dữ liệu lập trình/JSON cũ. Đầu vào Excel chuẩn
    # yêu cầu và giữ nguyên mã học phần chính thức.
    course_code: Optional[str] = None

@dataclass
class CourseSection:
    section_id: str
    course_id: str
    course_name: str
    lecturer_id: str
    group_id: str
    student_count: int
    is_difficult: bool = False
    required_room_type: str = "NORMAL"
    duration_periods: int = 1
    preferred_campus_id: Optional[str] = None
    preferred_shift: Optional[str] = None
    meetings_per_week: int = 1
    # Chỉ tùy chọn đối với các bộ dữ liệu lập trình/JSON cũ. Đầu vào Excel chuẩn
    # yêu cầu và giữ nguyên mã lớp chính thức.
    class_code: Optional[str] = None

    def __post_init__(self):
        if self.student_count < 1:
            raise ValueError(f"student_count must be >= 1, got {self.student_count}")
        if self.duration_periods < 1:
            raise ValueError(f"duration_periods must be >= 1, got {self.duration_periods}")
        if self.meetings_per_week < 1:
            raise ValueError(f"meetings_per_week must be >= 1, got {self.meetings_per_week}")
        if self.preferred_shift is not None and self.preferred_shift not in VALID_SHIFTS:
            raise ValueError(
                f"Invalid preferred_shift '{self.preferred_shift}' for section '{self.section_id}'. "
                f"Allowed values: {sorted(VALID_SHIFTS)}"
            )
