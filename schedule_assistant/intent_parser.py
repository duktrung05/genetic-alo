"""Schedule Assistant Intent Parser Module.

Rule-based intent parser and entity extractor for natural language timetable queries.
Requires zero external APIs, zero LLMs, and zero network calls.
"""

import re
import unicodedata
from typing import Dict, List, Optional, Set, Tuple, Any

from .models import ScheduleQuery


DAY_ALIASES: Dict[str, str] = {
    "thứ 2": "Thứ 2", "thu 2": "Thứ 2", "t2": "Thứ 2", "thứ hai": "Thứ 2", "thuhai": "Thứ 2", "monday": "Thứ 2", "mon": "Thứ 2",
    "thứ 3": "Thứ 3", "thu 3": "Thứ 3", "t3": "Thứ 3", "thứ ba": "Thứ 3", "thuba": "Thứ 3", "tuesday": "Thứ 3", "tue": "Thứ 3",
    "thứ 4": "Thứ 4", "thu 4": "Thứ 4", "t4": "Thứ 4", "thứ tư": "Thứ 4", "thutu": "Thứ 4", "wednesday": "Thứ 4", "wed": "Thứ 4",
    "thứ 5": "Thứ 5", "thu 5": "Thứ 5", "t5": "Thứ 5", "thứ năm": "Thứ 5", "thunam": "Thứ 5", "thursday": "Thứ 5", "thu": "Thứ 5",
    "thứ 6": "Thứ 6", "thu 6": "Thứ 6", "t6": "Thứ 6", "thứ sáu": "Thứ 6", "thusau": "Thứ 6", "friday": "Thứ 6", "fri": "Thứ 6",
    "thứ 7": "Thứ 7", "thu 7": "Thứ 7", "t7": "Thứ 7", "thứ bảy": "Thứ 7", "thubay": "Thứ 7", "saturday": "Thứ 7", "sat": "Thứ 7",
    "chủ nhật": "Chủ nhật", "chu nhat": "Chủ nhật", "cn": "Chủ nhật", "sunday": "Chủ nhật", "sun": "Chủ nhật",
}


def strip_accents(text: str) -> str:
    """Remove Vietnamese accents for robust regex matching."""
    text = unicodedata.normalize("NFD", text)
    text = "".join(c for c in text if unicodedata.category(c) != "MN")
    return text.lower()


class IntentParser:
    """Deterministic, rule-based parser for timetable queries."""

    def __init__(self, dataset_index: Optional[Dict[str, Any]] = None):
        """Initialize parser with optional index of known entities from dataset."""
        self.known_lecturers: Set[str] = set()
        self.known_groups: Set[str] = set()
        self.known_rooms: Set[str] = set()
        self.known_courses: Set[str] = set()
        self.known_campuses: Set[str] = {"cs1", "cs2", "cơ sở 1", "cơ sở 2"}

        if dataset_index:
            self._build_index(dataset_index)

    def _build_index(self, index: Dict[str, Any]) -> None:
        assignments = index.get("assignments", [])
        for a in assignments:
            if a.get("lecturer_id"):
                self.known_lecturers.add(a["lecturer_id"].lower())
            if a.get("lecturer_name"):
                self.known_lecturers.add(a["lecturer_name"].lower())

            if a.get("student_group_id"):
                self.known_groups.add(a["student_group_id"].lower())
            if a.get("student_group_name"):
                self.known_groups.add(a["student_group_name"].lower())

            if a.get("room_id"):
                self.known_rooms.add(a["room_id"].lower())
            if a.get("room_name"):
                self.known_rooms.add(a["room_name"].lower())

            if a.get("course_id"):
                self.known_courses.add(a["course_id"].lower())
            if a.get("course_name"):
                self.known_courses.add(a["course_name"].lower())

            if a.get("campus_id"):
                self.known_campuses.add(a["campus_id"].lower())

    def parse(self, query_text: str) -> ScheduleQuery:
        """Parse raw query string and extract intent & entity parameters."""
        if not query_text or not query_text.strip():
            return ScheduleQuery(raw_query="", intent="unknown_or_ambiguous")

        cleaned = " ".join(query_text.strip().split())
        lower_q = cleaned.lower()
        no_accent_q = strip_accents(lower_q)

        # 1. Extract Day
        extracted_day = self._extract_day(lower_q, no_accent_q)

        # 2. Extract Campus
        extracted_campus = self._extract_campus(lower_q, no_accent_q)

        # 3. Extract Lecturer
        extracted_lecturer = self._extract_lecturer(cleaned, lower_q)

        # 4. Extract Student Group
        extracted_group = self._extract_group(cleaned, lower_q)

        # 5. Extract Room
        extracted_room = self._extract_room(cleaned, lower_q)

        # 6. Extract Course
        extracted_course = self._extract_course(cleaned, lower_q)

        # Count extracted filter entities
        active_filters = [
            f for f in [extracted_day, extracted_group, extracted_lecturer, extracted_room, extracted_course, extracted_campus]
            if f is not None
        ]

        # Determine Intent
        if len(active_filters) > 1:
            intent = "schedule_combined"
        elif extracted_day:
            intent = "schedule_by_day"
        elif extracted_group:
            intent = "schedule_by_student_group"
        elif extracted_lecturer:
            intent = "schedule_by_lecturer"
        elif extracted_room:
            intent = "schedule_by_room"
        elif extracted_course:
            intent = "schedule_by_course"
        elif extracted_campus:
            intent = "schedule_by_campus"
        else:
            intent = "unknown_or_ambiguous"

        return ScheduleQuery(
            raw_query=cleaned,
            intent=intent,
            day=extracted_day,
            student_group=extracted_group,
            lecturer=extracted_lecturer,
            room=extracted_room,
            course=extracted_course,
            campus=extracted_campus,
        )

    def _extract_day(self, lower_q: str, no_accent_q: str) -> Optional[str]:

        for alias, canonical in DAY_ALIASES.items():
            pattern = r"\b" + re.escape(alias) + r"\b"
            if re.search(pattern, lower_q) or re.search(pattern, no_accent_q):
                return canonical
        return None

    def _extract_campus(self, lower_q: str, no_accent_q: str) -> Optional[str]:
        if re.search(r"\b(cs2|co so 2|cơ sở 2)\b", lower_q) or re.search(r"\b(cs2|co so 2)\b", no_accent_q):
            return "CS2"
        if re.search(r"\b(cs1|co so 1|cơ sở 1)\b", lower_q) or re.search(r"\b(cs1|co so 1)\b", no_accent_q):
            return "CS1"
        return None

    def _extract_lecturer(self, raw_q: str, lower_q: str) -> Optional[str]:

        # Match codes like GV01, GV-05, gv03
        match = re.search(r"\b(gv[-_]?\d+)\b", lower_q)
        if match:
            return match.group(1).upper().replace("-", "").replace("_", "")

        # Match explicit keywords e.g. "giảng viên X", "gv X", "thầy X", "cô X"
        match_kw = re.search(r"\b(?:giảng viên|giang vien|gv|thầy|thay|cô|co)\s+([a-vxyàáảãạăắằẳẵặâấầẩẫậèéẻẽẹêếềểễệìíỉĩịòóỏõọôốồổỗộơớờởỡợùúủũụưứừửữựỳýỷỹỵ\s]+)", lower_q)
        if match_kw:
            candidate = match_kw.group(1).strip()
            # Stop at common query prepositions
            for stop in ["dạy", "học", "khi", "vào", "lúc", "thứ", "phòng", "ở"]:
                if f" {stop} " in f" {candidate} ":
                    candidate = candidate.split(f" {stop} ")[0].strip()
            if candidate and len(candidate) >= 2:
                return candidate

        # Match against known lecturers from dataset index
        for lec in self.known_lecturers:
            if lec in lower_q:
                return lec

        return None

    def _extract_group(self, raw_q: str, lower_q: str) -> Optional[str]:

        # Match phrases like "lớp CNTT01", "lớp CNTT1-K18", "lop KTPM02"
        match = re.search(r"\b(?:lớp|lop|nhóm|nhom|group)\s+([a-z0-9\-_]+)", lower_q)
        if match:
            return match.group(1).upper()

        # Match patterns like CNTT1-K18, SV_CNTT1, KTPM02, CNTT01
        match_code = re.search(r"\b((?:cntt|ktpm|khmt|net|se|cs|sv)[_\-]?[a-z0-9\-_]+)\b", lower_q)
        if match_code:
            return match_code.group(1).upper()

        # Match known groups from index
        for grp in self.known_groups:
            if grp in lower_q:
                return grp.upper()

        return None

    def _extract_room(self, raw_q: str, lower_q: str) -> Optional[str]:

        # Match phrases like "phòng A201", "phong LAB01", "phòng 205-A9-CS1"
        match = re.search(r"\b(?:phòng|phong|room|lab)\s+([a-z0-9\-_]+)", lower_q)
        if match:
            return match.group(1).upper()

        # Match patterns like A201, LAB01, 205-A9-CS1, P101
        match_code = re.search(r"\b([a-z0-9]+[_\-][a-z0-9_\-]+)\b", lower_q)
        if match_code and ("cs" in lower_q or "lab" in lower_q or "a" in lower_q or "p" in lower_q):
            return match_code.group(1).upper()

        # Match known rooms from index
        for rm in self.known_rooms:
            if rm in lower_q:
                return rm.upper()

        return None

    def _extract_course(self, raw_q: str, lower_q: str) -> Optional[str]:

        # Match phrases like "môn Trí tuệ nhân tạo", "mon Co so du lieu"
        match = re.search(r"\b(?:môn|mon|học phần|hoc phan|course)\s+([a-vxyàáảãạăắằẳẵặâấầẩẫậèéẻẽẹêếềểễệìíỉĩịòóỏõọôốồổỗộơớờởỡợùúủũụưứừửữựỳýỷỹỵ\s0-9]+)", lower_q)
        if match:
            candidate = match.group(1).strip()
            for stop in ["học", "dạy", "ở", "tại", "phòng", "vào", "thứ", "lúc"]:
                if f" {stop} " in f" {candidate} ":
                    candidate = candidate.split(f" {stop} ")[0].strip()
            if candidate and len(candidate) >= 2:
                return candidate

        # Match known courses from index
        for crs in self.known_courses:
            if crs in lower_q:
                return crs

        return None
