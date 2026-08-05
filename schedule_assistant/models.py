"""Schedule Assistant Data Models."""

from dataclasses import dataclass, field
from typing import List, Dict, Optional, Any


@dataclass(frozen=True)
class ScheduleQuery:
    """Parsed representation of a natural language timetable query."""
    raw_query: str
    intent: str
    day: Optional[str] = None            # Canonical day e.g. "Thứ 2"
    student_group: Optional[str] = None  # Group ID or Group Name pattern
    lecturer: Optional[str] = None       # Lecturer ID or Lecturer Name pattern
    room: Optional[str] = None           # Room ID or Room Name pattern
    course: Optional[str] = None         # Course ID or Course Name pattern
    campus: Optional[str] = None         # Campus ID e.g. "CS1", "CS2"


@dataclass
class QueryResult:
    """Response returned by ScheduleQueryService."""
    query: ScheduleQuery
    success: bool
    message: str
    assignments: List[Dict[str, Any]] = field(default_factory=list)
    suggestions: List[str] = field(default_factory=list)
