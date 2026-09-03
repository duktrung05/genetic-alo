"""Read-only queries against the active generated timetable."""

from __future__ import annotations

from dataclasses import replace
import json
from pathlib import Path
import re
from typing import Any, Dict, Iterable, List, Optional, Union

from .intent_parser import NaturalLanguageParser, RuleBasedParser, normalized
from .models import QueryResult, ScheduleQuery


DEFAULT_QUERY_DATA_PATH = "outputs/production/schedule_query_data.json"
SHIFT_LABELS = {"morning": "Sáng", "afternoon": "Chiều", "evening": "Tối"}
ENTITY_FIELDS = {
    "student_group": ("student_group_id", "student_group_name"),
    "lecturer": ("lecturer_id", "lecturer_name"),
    "room": ("room_id", "room_name"),
    "course": ("course_code", "course_id", "course_name"),
    "class_code": ("class_code", "section_id"),
}


def normalize_text(text: str) -> str:
    return " ".join(str(text or "").lower().strip().split())


class ScheduleQueryService:
    """Query service whose only factual source is one timetable payload."""

    def __init__(
        self,
        data_path: Union[str, Path] = DEFAULT_QUERY_DATA_PATH,
        *,
        data: Optional[Dict[str, Any]] = None,
        dataset: Optional[Dict[str, Any]] = None,
        parser: Optional[NaturalLanguageParser] = None,
    ):
        self.data_path = Path(data_path)
        self.data = data
        self.dataset = dataset
        self.parser = parser
        if self.data is None:
            self._load_data()
        else:
            self.parser = self.parser or RuleBasedParser(self.data)

    def _load_data(self) -> bool:
        if not self.data_path.exists():
            self.data = None
            self.parser = self.parser or RuleBasedParser()
            return False
        try:
            self.data = json.loads(self.data_path.read_text(encoding="utf-8"))
            self.parser = self.parser or RuleBasedParser(self.data)
            return True
        except (OSError, json.JSONDecodeError):
            self.data = None
            self.parser = self.parser or RuleBasedParser()
            return False

    def is_data_available(self) -> bool:
        return self.data is not None and isinstance(self.data.get("assignments"), list)

    def query(self, query_input: Union[str, ScheduleQuery]) -> QueryResult:
        if not self.is_data_available() and not self._load_data():
            return QueryResult(
                ScheduleQuery(str(query_input), "missing_data"), False,
                "Chưa có dữ liệu thời khóa biểu. Hãy chạy Scheduler trước.",
                suggestions=["Run the scheduler first"],
            )

        parsed = self.parser.parse(query_input) if isinstance(query_input, str) else query_input
        if re.search(r"\b(?:thứ|thu)\s*(?:0|1|8|9)\b", normalized(parsed.raw_query)):
            return QueryResult(parsed, False, "Invalid day. Please use Thứ 2 through Thứ 7.")
        if parsed.intent in {"unsupported", "unknown_or_ambiguous"}:
            return QueryResult(
                parsed, False,
                "Bạn muốn tra cứu theo lớp, giảng viên, phòng hay môn học? This assistant only answers questions about the generated timetable; use About / Method for algorithm information.",
                suggestions=["Lịch CNTT1-K18", "GV01 dạy khi nào?", "IT2010 học ở đâu?"],
            )

        if parsed.intent == "schedule_summary":
            return self._summary(parsed)
        if parsed.intent == "free_room_search":
            return self._free_rooms(parsed)

        resolved, error = self._resolve_query(parsed)
        if error:
            return error
        if resolved.intent == "lecturer_free_time":
            return self._lecturer_free_time(resolved)

        filtered = self._filter_assignments(self.data["assignments"], resolved)
        if not filtered:
            return QueryResult(resolved, True, "Không tìm thấy lịch phù hợp với yêu cầu.")

        subject = self._subject_label(resolved)
        qualifier = ""
        if resolved.day:
            qualifier += f" on {resolved.day}"
        if resolved.shift:
            qualifier += f" ({SHIFT_LABELS[resolved.shift]})"
        noun = "class" if len(filtered) == 1 else "classes"
        return QueryResult(
            resolved, True, f"{subject} has {len(filtered)} scheduled {noun}{qualifier}.",
            assignments=filtered,
        )

    def _resolve_query(self, query: ScheduleQuery) -> tuple[ScheduleQuery, Optional[QueryResult]]:
        updates: Dict[str, str] = {}
        for attr, fields in ENTITY_FIELDS.items():
            requested = getattr(query, attr)
            if not requested:
                continue
            matches = self._resolve_entity(requested, fields)
            label = attr.replace("_", " ")
            if not matches:
                # Các bên gọi cũ trước đây nhận được kết quả rỗng nhưng thành công.
                return query, QueryResult(query, True, f"Không tìm thấy lịch. No matching {label} was found in the current timetable.")
            if len(matches) > 1:
                choices = [self._display_entity(item, fields) for item in matches]
                return query, QueryResult(
                    query, False,
                    f"I found multiple matching {label}s. Please choose one:",
                    suggestions=choices,
                )
            updates[attr] = str(matches[0].get(fields[0]) or matches[0].get(fields[1]) or requested)
        return replace(query, **updates), None

    def _resolve_entity(self, requested: str, fields: tuple[str, ...]) -> List[dict]:
        entities: Dict[str, dict] = {}
        for assignment in self.data.get("assignments", []):
            identity = str(assignment.get(fields[0]) or assignment.get(fields[1]) or "")
            if identity:
                entities.setdefault(normalized(identity), assignment)
        needle = normalized(requested)
        exact = [item for item in entities.values() if any(normalized(item.get(field, "")) == needle for field in fields)]
        if exact:
            return exact
        return [
            item for item in entities.values()
            if any(needle and (needle in normalized(item.get(field, "")) or normalized(item.get(field, "")) in needle) for field in fields)
        ]

    @staticmethod
    def _display_entity(item: dict, fields: tuple[str, ...]) -> str:
        values = []
        for field in fields:
            value = str(item.get(field) or "")
            if value and value not in values:
                values.append(value)
        return " — ".join(values[:2])

    def _filter_assignments(self, assignments: List[Dict[str, Any]], query: ScheduleQuery) -> List[Dict[str, Any]]:
        filtered = list(assignments)
        if query.day:
            filtered = [a for a in filtered if normalized(a.get("day", "")) == normalized(query.day)]
        if query.shift:
            filtered = [a for a in filtered if normalize_text(a.get("session", "")) == query.shift]
        for attr, fields in ENTITY_FIELDS.items():
            requested = getattr(query, attr)
            if requested:
                needle = normalized(requested)
                filtered = [a for a in filtered if any(normalized(a.get(field, "")) == needle for field in fields)]
        return sorted(filtered, key=lambda a: (self._day_index(a.get("day")), a.get("start_period", 0), a.get("room_id", "")))

    def _free_rooms(self, query: ScheduleQuery) -> QueryResult:
        rooms = self._resources("rooms")
        timeslots = self._timeslots(query.day, query.shift)
        if not rooms or not timeslots:
            return QueryResult(query, False, "Room or timeslot data is unavailable for this active timetable.")
        window = {(slot["day"], slot["period"]) for slot in timeslots}
        occupied = set()
        for assignment in self.data.get("assignments", []):
            periods = assignment.get("occupied_periods") or range(assignment.get("start_period", 0), assignment.get("end_period", 0) + 1)
            if any((assignment.get("day"), period) in window for period in periods):
                occupied.add(assignment.get("room_id"))
        free = [room for room in rooms if room["id"] not in occupied]
        scope = self._scope_label(query)
        message = f"{len(free)} rooms are free for the entire requested window ({scope})."
        rows = [{"room_id": room["id"], "room_name": room.get("name", ""), "campus": room.get("campus_id", ""), "room_type": room.get("room_type", "")} for room in free]
        return QueryResult(query, True, message, details={"free_rooms": rows, "semantic": "free_for_entire_requested_window"})

    def _lecturer_free_time(self, query: ScheduleQuery) -> QueryResult:
        lecturer_id = query.lecturer
        lecturer = next((item for item in self._resources("lecturers") if normalized(item["id"]) == normalized(lecturer_id)), None)
        if lecturer is None:
            return QueryResult(query, True, "No matching lecturer was found in the current timetable.")
        slots = self._timeslots(query.day, query.shift)
        available_ids = lecturer.get("available_timeslot_ids")
        if available_ids is not None:
            available = {str(value) for value in available_ids}
            slots = [slot for slot in slots if str(slot["id"]) in available]
        occupied = set()
        for assignment in self.data.get("assignments", []):
            if normalized(assignment.get("lecturer_id")) != normalized(lecturer_id):
                continue
            for period in assignment.get("occupied_periods") or range(assignment.get("start_period", 0), assignment.get("end_period", 0) + 1):
                occupied.add((assignment.get("day"), period))
        free_slots = [slot for slot in slots if (slot["day"], slot["period"]) not in occupied]
        blocks = self._compact_timeslots(free_slots)
        display = lecturer.get("name") or lecturer_id
        return QueryResult(
            query, True,
            f"{display} has {len(free_slots)} available, unscheduled periods{self._scope_suffix(query)}.",
            details={"free_times": blocks, "lecturer_id": lecturer_id},
        )

    def _summary(self, query: ScheduleQuery) -> QueryResult:
        assignments = self.data.get("assignments", [])
        meta = self.data.get("meta", {})
        values = lambda field: {a.get(field) for a in assignments if a.get(field)}
        by_day: Dict[str, int] = {}
        for assignment in assignments:
            day = assignment.get("day", "Unknown")
            by_day[day] = by_day.get(day, 0) + 1
        summary = {
            "dataset": meta.get("dataset", "Active"),
            "sections": len(values("section_id")),
            "activities": len(assignments),
            "lecturers": len(values("lecturer_id")),
            "student_groups": len(values("student_group_id")),
            "rooms": len(values("room_id")),
            "hard_violations": meta.get("hard_violations"),
            "soft_score": meta.get("soft_penalty"),
            "activities_by_day": dict(sorted(by_day.items(), key=lambda item: self._day_index(item[0]))),
        }
        status = "feasible" if summary["hard_violations"] == 0 else "not feasible"
        return QueryResult(query, True, f"{summary['dataset']} timetable: {summary['activities']} activities; {status}.", details={"summary": summary})

    def _resources(self, key: str) -> List[dict]:
        if self.dataset and self.dataset.get(key):
            return [self._object_dict(item) for item in self.dataset[key]]
        singular = {"rooms": ("room_id", "room_name"), "lecturers": ("lecturer_id", "lecturer_name")}.get(key)
        if not singular:
            return []
        unique = {}
        for assignment in self.data.get("assignments", []):
            item_id = assignment.get(singular[0])
            if item_id:
                unique[item_id] = {"id": item_id, "name": assignment.get(singular[1], "")}
        return list(unique.values())

    def _timeslots(self, day: Optional[str], shift: Optional[str]) -> List[dict]:
        if self.dataset and self.dataset.get("timeslots"):
            slots = [self._object_dict(item) for item in self.dataset["timeslots"]]
        else:
            slots = []
            seen = set()
            for assignment in self.data.get("assignments", []):
                for period in assignment.get("occupied_periods", []):
                    key = (assignment.get("day"), period)
                    if key not in seen:
                        seen.add(key)
                        slots.append({"id": f"{key[0]}-{period}", "day": key[0], "period": period, "session": assignment.get("session", "")})
        if day:
            slots = [slot for slot in slots if normalized(slot.get("day")) == normalized(day)]
        if shift:
            slots = [slot for slot in slots if slot.get("session") == shift]
        return sorted(slots, key=lambda slot: (self._day_index(slot.get("day")), slot.get("period", 0)))

    @staticmethod
    def _object_dict(item: Any) -> dict:
        if isinstance(item, dict):
            return dict(item)
        result = dict(vars(item))
        if result.get("available_timeslot_ids") is not None:
            result["available_timeslot_ids"] = list(result["available_timeslot_ids"])
        return result

    @staticmethod
    def _compact_timeslots(slots: List[dict]) -> List[dict]:
        blocks: List[dict] = []
        for slot in slots:
            if blocks and blocks[-1]["day"] == slot.get("day") and blocks[-1]["shift"] == slot.get("session") and blocks[-1]["end_period"] + 1 == slot.get("period"):
                blocks[-1]["end_period"] = slot.get("period")
                blocks[-1]["end_time"] = slot.get("end_time", "")
            else:
                blocks.append({
                    "day": slot.get("day", ""), "shift": SHIFT_LABELS.get(slot.get("session"), slot.get("session", "")),
                    "start_period": slot.get("period"), "end_period": slot.get("period"),
                    "start_time": slot.get("start_time", ""), "end_time": slot.get("end_time", ""),
                })
        return blocks

    @staticmethod
    def _subject_label(query: ScheduleQuery) -> str:
        if query.student_group:
            return query.student_group
        if query.lecturer:
            return query.lecturer
        if query.room:
            return query.room
        if query.course:
            return query.course
        if query.class_code:
            return query.class_code
        return "The timetable"

    @staticmethod
    def _day_index(day: Any) -> int:
        match = re.search(r"\d+", str(day or ""))
        return int(match.group(0)) if match else 99

    @staticmethod
    def _scope_label(query: ScheduleQuery) -> str:
        parts = [query.day or "all teaching days", SHIFT_LABELS.get(query.shift, "all shifts")]
        return ", ".join(parts)

    @staticmethod
    def _scope_suffix(query: ScheduleQuery) -> str:
        return f" for {ScheduleQueryService._scope_label(query)}" if query.day or query.shift else ""
