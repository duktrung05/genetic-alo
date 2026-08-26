"""Deterministic expansion of business course sections into schedulable meetings."""

from dataclasses import dataclass
from typing import Iterable, List

from .course import CourseSection


@dataclass(frozen=True)
class SchedulingActivity:
    """One independently assigned weekly meeting of a parent CourseSection.

    ``duration_periods`` on the parent section is the duration of *each*
    activity, not a total weekly duration.
    """

    activity_id: str
    section_id: str
    meeting_index: int
    meeting_count: int
    section: CourseSection

    def __getattr__(self, name):
        return getattr(self.section, name)


def expand_scheduling_activities(
    sections: Iterable[CourseSection],
) -> List[SchedulingActivity]:
    """Expand sections in input order, then meeting order, reproducibly."""
    activities: List[SchedulingActivity] = []
    seen_ids = set()
    for section in sections:
        count = section.meetings_per_week
        if not isinstance(count, int) or isinstance(count, bool) or count < 1:
            raise ValueError(
                f"Section '{section.section_id}' has invalid meetings_per_week={count}"
            )
        for meeting_index in range(1, count + 1):
            activity_id = (
                section.section_id
                if count == 1
                else f"{section.section_id}-M{meeting_index}"
            )
            if activity_id in seen_ids:
                raise ValueError(f"Duplicate scheduling activity ID '{activity_id}'")
            seen_ids.add(activity_id)
            activities.append(
                SchedulingActivity(
                    activity_id=activity_id,
                    section_id=section.section_id,
                    meeting_index=meeting_index,
                    meeting_count=count,
                    section=section,
                )
            )
    return activities
