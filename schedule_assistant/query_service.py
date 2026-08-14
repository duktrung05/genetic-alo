"""Service truy vấn dữ liệu thời khóa biểu cho trợ lý cá nhân.

Lọc dữ liệu tĩnh (chỉ đọc) từ file JSON đã xuất trước đó.
Tách biệt hoàn toàn với thuật toán di truyền (GA) và engine sửa lỗi (Repair).
"""

import json
import os
from pathlib import Path
from typing import Dict, List, Optional, Union, Any

from .models import ScheduleQuery, QueryResult
from .intent_parser import IntentParser


DEFAULT_QUERY_DATA_PATH = "outputs/production/schedule_query_data.json"


def normalize_text(text: str) -> str:
    """Chuyển chuỗi về dạng chữ thường và loại bỏ khoảng trắng thừa."""
    if not text:
        return ""
    return " ".join(text.lower().strip().split())


class ScheduleQueryService:
    """Dịch vụ truy vấn lịch (chỉ đọc) cho trợ lý tra cứu."""

    def __init__(self, data_path: Union[str, Path] = DEFAULT_QUERY_DATA_PATH):
        """Khởi tạo service truy vấn với đường dẫn file JSON dữ liệu."""
        self.data_path = Path(data_path)
        self.data: Optional[Dict[str, Any]] = None
        self.parser: Optional[IntentParser] = None
        self._load_data()

    def _load_data(self) -> bool:
        """Tải dữ liệu từ file JSON nếu tồn tại."""
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
        """Kiểm tra xem dữ liệu thời khóa biểu đã sẵn sàng chưa."""
        return self.data is not None and "assignments" in self.data

    def query(self, query_input: Union[str, ScheduleQuery]) -> QueryResult:
        """Thực thi truy vấn thời khóa biểu và trả về QueryResult."""
        if not self.is_data_available():
            # Thử tải lại dữ liệu
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
        """Lọc danh sách phân công theo các tham số truy vấn (phép AND)."""
        filtered = list(assignments)

        # 1. Lọc theo ngày
        if query.day:
            norm_day = normalize_text(query.day)
            filtered = [
                a for a in filtered
                if normalize_text(a.get("day", "")) == norm_day or norm_day in normalize_text(a.get("day_key", ""))
            ]

        # 2. Lọc theo cơ sở
        if query.campus:
            norm_campus = normalize_text(query.campus)
            filtered = [
                a for a in filtered
                if norm_campus in normalize_text(a.get("campus_id", ""))
            ]

        # 3. Lọc theo nhóm sinh viên
        if query.student_group:
            norm_grp = normalize_text(query.student_group)
            filtered = [
                a for a in filtered
                if norm_grp in normalize_text(a.get("student_group_id", ""))
                or norm_grp in normalize_text(a.get("student_group_name", ""))
            ]

        # 4. Lọc theo giảng viên
        if query.lecturer:
            norm_lec = normalize_text(query.lecturer)
            filtered = [
                a for a in filtered
                if norm_lec in normalize_text(a.get("lecturer_id", ""))
                or norm_lec in normalize_text(a.get("lecturer_name", ""))
            ]

        # 5. Lọc theo phòng học
        if query.room:
            norm_rm = normalize_text(query.room)
            filtered = [
                a for a in filtered
                if norm_rm in normalize_text(a.get("room_id", ""))
                or norm_rm in normalize_text(a.get("room_name", ""))
            ]

        # 6. Lọc theo môn học
        if query.course:
            norm_crs = normalize_text(query.course)
            filtered = [
                a for a in filtered
                if norm_crs in normalize_text(a.get("course_id", ""))
                or norm_crs in normalize_text(a.get("course_name", ""))
            ]

        return filtered

