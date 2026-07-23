from dataclasses import dataclass

@dataclass
class Course:
    course_id: str
    name: str
    credits: int
    is_difficult: bool = False

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
