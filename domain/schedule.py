from dataclasses import dataclass, field
from typing import List

@dataclass
class Gene:
    section_id: str
    room_id: str
    timeslot_id: int

@dataclass
class Schedule:
    genes: List[Gene] = field(default_factory=list)
