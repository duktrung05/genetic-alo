from dataclasses import dataclass
from typing import Optional, FrozenSet, Union

@dataclass
class Timeslot:
    id: Union[int, str]
    day: str       # e.g., "Thứ 2", "Thứ 3", ...
    period: int    # 1 -> 5 / 6

@dataclass
class Room:
    id: str
    name: str
    capacity: int
    room_type: str = "NORMAL"

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
