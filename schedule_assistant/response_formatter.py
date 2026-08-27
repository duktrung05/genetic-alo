"""Module định dạng kết quả trả về cho trợ lý tra cứu thời khóa biểu.

Chuyển đổi QueryResult thành văn bản tự nhiên hoặc bảng dữ liệu.
"""

from typing import Dict, List, Any
from .models import QueryResult, ScheduleQuery


class ResponseFormatter:
    """Định dạng QueryResult thành dạng văn bản và bảng."""

    @staticmethod
    def format_text(result: QueryResult) -> str:
        """Tạo câu trả lời dạng văn bản tiếng Việt dễ đọc."""
        if not result.success:
            text = f"⚠️ {result.message}\n"
            if result.suggestions:
                text += "\nGợi ý câu hỏi:\n"
                for s in result.suggestions:
                    text += f"• {s}\n"
            return text.strip()

        if not result.assignments:
            return "Không tìm thấy lịch phù hợp với yêu cầu."

        q = result.query
        assignments = result.assignments
        count = len(assignments)

        # Tạo tiêu đề dựa trên ý định / tham số
        header = ResponseFormatter._build_header(q, count)
        lines = [header, ""]

        for idx, a in enumerate(assignments, 1):
            day_str = a.get("day", "N/A")
            start_p = a.get("start_period", 1)
            end_p = a.get("end_period", 1)
            p_str = f"Tiết {start_p}" if start_p == end_p else f"Tiết {start_p}–{end_p}"
            start_t = a.get("start_time", "")
            end_t = a.get("end_time", "")
            time_str = f"({start_t} – {end_t})" if start_t and end_t else ""

            course_str = f"{a.get('course_name', '')} ({a.get('course_id', '')})"
            group_str = f"{a.get('student_group_name', '')} ({a.get('student_group_id', '')})"
            lec_str = f"{a.get('lecturer_name', '')} ({a.get('lecturer_id', '')})"
            room_str = f"{a.get('room_name', '')} ({a.get('campus_id', '')})"

            lines.append(f"{idx}. {day_str}, {p_str} {time_str}")
            lines.append(f"   • Môn học    : {course_str}")
            lines.append(f"   • Lớp SV     : {group_str}")
            lines.append(f"   • Giảng viên : {lec_str}")
            lines.append(f"   • Phòng học  : {room_str}")
            lines.append("")

        return "\n".join(lines).strip()

    @staticmethod
    def _build_header(q: ScheduleQuery, count: int) -> str:
        parts = []
        if q.day:
            parts.append(q.day)
        if q.student_group:
            parts.append(f"Lớp {q.student_group}")
        if q.lecturer:
            parts.append(f"Giảng viên {q.lecturer}")
        if q.room:
            parts.append(f"Phòng {q.room}")
        if q.course:
            parts.append(f"Môn {q.course}")
        if q.campus:
            parts.append(f"Cơ sở {q.campus}")

        filter_desc = ", ".join(parts) if parts else "toàn trường"
        return f"📅 Kết quả tra cứu lịch ({filter_desc}) — Có {count} lịch học:"

    @staticmethod
    def format_table_data(result: QueryResult) -> List[Dict[str, Any]]:
        """Định dạng danh sách phân công thành các dòng dữ liệu cho bảng."""
        table_rows = []
        for a in result.assignments:
            start_p = a.get("start_period", 1)
            end_p = a.get("end_period", 1)
            p_str = f"Tiết {start_p}" if start_p == end_p else f"Tiết {start_p}–{end_p}"
            start_t = a.get("start_time", "")
            end_t = a.get("end_time", "")

            table_rows.append({
                "Ngày": a.get("day", ""),
                "Ca/Tiết": f"{a.get('session', '')} / {p_str}",
                "Thời gian": f"{start_t} – {end_t}",
                "Môn học": a.get("course_name", ""),
                "Mã môn": a.get("course_code") or a.get("course_id", ""),
                "Mã lớp": a.get("class_code") or a.get("section_id", ""),
                "Buổi học": f"{a.get('meeting_index', 1)}/{a.get('meeting_count', 1)}",
                "Lớp SV": a.get("student_group_name", ""),
                "Giảng viên": a.get("lecturer_name") or a.get("lecturer_id", ""),
                "Phòng": a.get("room_id") or a.get("room_name", ""),
                "Loại phòng": a.get("room_type", ""),
                "Cơ sở": a.get("campus_id", ""),
            })
        return table_rows
