from typing import List, Optional, Dict, Any, Set
from domain import Timeslot

# Cấu hình tiết học lý thuyết HaUI 2025-2026 (Cơ sở 1, 2)
THEORY_PERIODS: tuple[Dict[str, Any], ...] = (
    # Ca sáng
    {"period": 1, "start_time": "07:00", "end_time": "07:50", "session": "morning"},
    {"period": 2, "start_time": "07:50", "end_time": "08:40", "session": "morning"},
    {"period": 3, "start_time": "08:45", "end_time": "09:35", "session": "morning"},
    {"period": 4, "start_time": "09:40", "end_time": "10:30", "session": "morning"},
    {"period": 5, "start_time": "10:35", "end_time": "11:25", "session": "morning"},
    {"period": 6, "start_time": "11:25", "end_time": "12:15", "session": "morning"},
    # Ca chiều
    {"period": 7, "start_time": "12:30", "end_time": "13:20", "session": "afternoon"},
    {"period": 8, "start_time": "13:20", "end_time": "14:10", "session": "afternoon"},
    {"period": 9, "start_time": "14:15", "end_time": "15:05", "session": "afternoon"},
    {"period": 10, "start_time": "15:10", "end_time": "16:00", "session": "afternoon"},
    {"period": 11, "start_time": "16:05", "end_time": "16:55", "session": "afternoon"},
    {"period": 12, "start_time": "16:55", "end_time": "17:45", "session": "afternoon"},
    # Ca tối
    {"period": 13, "start_time": "18:00", "end_time": "18:50", "session": "evening"},
    {"period": 14, "start_time": "18:50", "end_time": "19:40", "session": "evening"},
    {"period": 15, "start_time": "19:45", "end_time": "20:35", "session": "evening"},
    {"period": 16, "start_time": "20:35", "end_time": "21:25", "session": "evening"},
)

DEFAULT_DAYS: List[str] = ["Thứ 2", "Thứ 3", "Thứ 4", "Thứ 5", "Thứ 6" , "Thứ 7"]

def create_theory_timeslots(
    days: Optional[List[str]] = None,
    max_period: Optional[int] = None
) -> List[Timeslot]:
    if days is None:
        days = DEFAULT_DAYS

    periods_to_include = THEORY_PERIODS
    if max_period is not None:
        periods_to_include = tuple(p for p in THEORY_PERIODS if p["period"] <= max_period)

    timeslots: List[Timeslot] = []
    ts_id = 0

    for day in days:
        for p in periods_to_include:
            timeslots.append(
                Timeslot(
                    id=ts_id,
                    day=day,
                    period=p["period"],
                    start_time=p["start_time"],
                    end_time=p["end_time"],
                    session=p["session"],
                )
            )
            ts_id += 1

    return timeslots


def get_occupied_periods(start_period: int, duration_periods: int) -> List[int]:
    if duration_periods < 1:
        raise ValueError(f"duration_periods must be >= 1, got {duration_periods}")
    return list(range(start_period, start_period + duration_periods))


def _get_session_by_period(period: int) -> Optional[str]:
    if 1 <= period <= 6:
        return "morning"
    elif 7 <= period <= 12:
        return "afternoon"
    elif 13 <= period <= 16:
        return "evening"
    return None


def is_valid_period_block(
    start_period: int,
    duration_periods: int,
    available_periods: Optional[Set[int]] = None,
    day: Optional[str] = None,
    max_period_in_day: int = 16,
    require_same_session: bool = True,
) -> bool:
    if duration_periods < 1 or start_period < 1:
        return False
    
    occupied = range(start_period, start_period + duration_periods)
    if start_period + duration_periods - 1 > max_period_in_day:
        return False

    if available_periods is not None:
        if not all(p in available_periods for p in occupied):
            return False
    else:
        if not (1 <= start_period and (start_period + duration_periods - 1) <= max_period_in_day):
            return False

    if require_same_session:
        sessions = {_get_session_by_period(p) for p in occupied}
        if None in sessions or len(sessions) > 1:
            return False

    return True

