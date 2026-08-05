from dataclasses import dataclass
from typing import Optional, FrozenSet, Union, Literal

SessionType = Literal["morning", "afternoon", "evening"]

@dataclass(frozen=True)
class Timeslot:
    """Represents a time slot in the timetable schedule.

    Attributes:
        id: Unique identifier for the timeslot.
        day: Day of the week (e.g., "Thứ 2", "Thứ 3").
        period: Period index in the day (e.g., 1..6).
        start_time: Start time of the period in HH:MM format (e.g., "07:00").
        end_time: End time of the period in HH:MM format (e.g., "07:50").
        session: Part of the day ("morning", "afternoon", or "evening").
    """
    id: int
    day: str
    period: int
    start_time: str
    end_time: str
    session: str

    def __post_init__(self):
        valid_sessions = {"morning", "afternoon", "evening"}
        if self.session not in valid_sessions:
            raise ValueError(
                f"Invalid session '{self.session}'. Must be one of {sorted(valid_sessions)}"
            )

@dataclass
class Room:
    id: str
    name: str
    capacity: int
    room_type: str = "NORMAL"
    campus_id: Optional[str] = None

@dataclass
class Lecturer:
    id: str
    name: str
    available_timeslot_ids: Optional[FrozenSet[Union[int, str]]] = None

@dataclass
class StudentGroup:
    id: str
    name: str
    student_count: int
    home_campus_id: Optional[str] = None
