"""Schedule Assistant Query Service Module.

Read-only schedule query and filtering engine for natural language assistant requests.
Purely deterministic filtering operating ONLY on pre-generated query JSON datasets.
Strictly isolated from Genetic Algorithm execution, Repair Engine, and schedule generation.
"""

import json
import os
from pathlib import Path
from typing import Dict, List, Optional, Union, Any

from .models import ScheduleQuery, QueryResult
from .intent_parser import IntentParser


DEFAULT_QUERY_DATA_PATH = "outputs/production/schedule_query_data.json"


def normalize_text(text: str) -> str:
    """Normalize string for case-insensitive and whitespace-insensitive matching."""
    if not text:
        return ""
    return " ".join(text.lower().strip().split())


class ScheduleQueryService:
    """Read-only query service for natural language timetable assistant requests."""

    def __init__(self, data_path: Union[str, Path] = DEFAULT_QUERY_DATA_PATH):
        """Initialize query service with target JSON file path."""
        self.data_path = Path(data_path)
        self.data: Optional[Dict[str, Any]] = None
        self.parser: Optional[IntentParser] = None
        self._load_data()

    def _load_data(self) -> bool:
        """Load schedule query data JSON if file exists."""
        if not self.data_path.exists():
            self.data = None
            self.parser = IntentParser()
            return False

        try:
            with open(self.data_path, "r", encoding="utf-8") as f:
                self.data = json.load(f)
            self.parser = IntentParser(dataset_index=self.data)
            return True
        except Exception:
            self.data = None
            self.parser = IntentParser()
            return False

    def is_data_available(self) -> bool:
        """Check if schedule query data is loaded and available."""
        return self.data is not None and "assignments" in self.data

    def query(self, query_input: Union[str, ScheduleQuery]) -> QueryResult:
        """Execute read-only timetable query and return QueryResult."""
        if not self.is_data_available():
            # Reload attempt
            if not self._load_data():
                return QueryResult(
                    query=ScheduleQuery(raw_query=str(query_input), intent="missing_data"),
                    success=False,
                    message="Chưa có dữ liệu thời khóa biểu. Hãy chạy: python main.py để tạo lịch trước khi sử dụng chức năng tra cứu.",
                    assignments=[],
                    suggestions=[
                        "python main.py",
                        "Chạy main.py để sinh thời khóa biểu sản phẩm",
                    ]
                )

        if isinstance(query_input, str):
            parsed_query = self.parser.parse(query_input)
        else:
            parsed_query = query_input

        if parsed_query.intent == "unknown_or_ambiguous":
            return QueryResult(
                query=parsed_query,
                success=False,
                message="Bạn muốn tra cứu theo ngày, lớp, giảng viên, phòng hay môn học?",
                assignments=[],
                suggestions=[
                    "Lịch thứ 2",
                    "Lịch của lớp CNTT1",
                    "Giảng viên GV01 dạy khi nào?",
                    "Phòng A9-205 được sử dụng khi nào?",
                    "Môn Lập trình hướng đối tượng học lúc nào?",
                ]
            )

        assignments = self.data.get("assignments", [])
        filtered = self._filter_assignments(assignments, parsed_query)

        if not filtered:
            return QueryResult(
                query=parsed_query,
                success=True,
                message="Không tìm thấy lịch phù hợp với yêu cầu.",
                assignments=[],
                suggestions=[
                    "Thử tra cứu theo ngày (VD: Lịch thứ 2)",
                    "Thử tra cứu theo tên lớp (VD: Lịch lớp CNTT1)",
                ]
            )

        return QueryResult(
            query=parsed_query,
            success=True,
            message=f"Tìm thấy {len(filtered)} lịch học phù hợp.",
            assignments=filtered,
            suggestions=[]
        )

    def _filter_assignments(self, assignments: List[Dict[str, Any]], query: ScheduleQuery) -> List[Dict[str, Any]]:
        """Filter assignment list deterministically by query parameters (AND logic)."""
        filtered = list(assignments)

        # 1. Day Filter
        if query.day:
            norm_day = normalize_text(query.day)
            filtered = [
                a for a in filtered
                if normalize_text(a.get("day", "")) == norm_day or norm_day in normalize_text(a.get("day_key", ""))
            ]

        # 2. Campus Filter
        if query.campus:
            norm_campus = normalize_text(query.campus)
            filtered = [
                a for a in filtered
                if norm_campus in normalize_text(a.get("campus_id", ""))
            ]

        # 3. Student Group Filter
        if query.student_group:
            norm_grp = normalize_text(query.student_group)
            filtered = [
                a for a in filtered
                if norm_grp in normalize_text(a.get("student_group_id", ""))
                or norm_grp in normalize_text(a.get("student_group_name", ""))
            ]

        # 4. Lecturer Filter
        if query.lecturer:
            norm_lec = normalize_text(query.lecturer)
            filtered = [
                a for a in filtered
                if norm_lec in normalize_text(a.get("lecturer_id", ""))
                or norm_lec in normalize_text(a.get("lecturer_name", ""))
            ]

        # 5. Room Filter
        if query.room:
            norm_rm = normalize_text(query.room)
            filtered = [
                a for a in filtered
                if norm_rm in normalize_text(a.get("room_id", ""))
                or norm_rm in normalize_text(a.get("room_name", ""))
            ]

        # 6. Course Filter
        if query.course:
            norm_crs = normalize_text(query.course)
            filtered = [
                a for a in filtered
                if norm_crs in normalize_text(a.get("course_id", ""))
                or norm_crs in normalize_text(a.get("course_name", ""))
            ]

        return filtered
