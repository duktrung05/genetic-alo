"""Mô hình dữ liệu cho trợ lý tra cứu thời khóa biểu."""

from dataclasses import dataclass, field
from typing import List, Dict, Optional, Any


@dataclass(frozen=True)
class ScheduleQuery:
    """Biểu diễn dữ liệu sau khi phân tích câu hỏi thời khóa biểu."""
    raw_query: str
    intent: str
    day: Optional[str] = None            # Thứ trong tuần (ví dụ: "Thứ 2")
    student_group: Optional[str] = None  # Mã hoặc tên nhóm sinh viên
    lecturer: Optional[str] = None       # Mã hoặc tên giảng viên
    room: Optional[str] = None           # Mã hoặc tên phòng học
    course: Optional[str] = None         # Mã hoặc tên môn học
    class_code: Optional[str] = None     # Mã lớp học phần chính thức
    campus: Optional[str] = None         # Mã cơ sở (ví dụ: "CS1", "CS2")
    shift: Optional[str] = None          # morning / afternoon / evening


@dataclass
class QueryResult:
    """Kết quả trả về từ ScheduleQueryService."""
    query: ScheduleQuery
    success: bool
    message: str
    assignments: List[Dict[str, Any]] = field(default_factory=list)
    suggestions: List[str] = field(default_factory=list)
    details: Dict[str, Any] = field(default_factory=dict)
