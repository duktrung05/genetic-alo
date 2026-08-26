from dataclasses import dataclass, field
from typing import List

@dataclass(init=False)
class Gene:
    """Assignment for one scheduling activity.

    ``section_id`` is retained as a compatibility alias for ``activity_id``.
    The official parent section is resolved through the activity map.
    """

    activity_id: str
    room_id: str
    timeslot_id: int

    def __init__(
        self,
        activity_id: str = None,
        room_id: str = None,
        timeslot_id: int = None,
        *,
        section_id: str = None,
    ) -> None:
        resolved_id = activity_id if activity_id is not None else section_id
        if resolved_id is None:
            raise ValueError("Gene requires activity_id (or legacy section_id)")
        self.activity_id = resolved_id
        self.room_id = room_id
        self.timeslot_id = timeslot_id

    @property
    def section_id(self) -> str:
        return self.activity_id

@dataclass
class Schedule:
    genes: List[Gene] = field(default_factory=list)
