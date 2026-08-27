"""Deterministic Vietnamese/English parser for timetable questions."""

from __future__ import annotations

import re
import unicodedata
from typing import Any, Dict, Optional

from .models import ScheduleQuery


DAY_ALIASES: Dict[str, str] = {
    "thứ 2": "Thứ 2", "thu 2": "Thứ 2", "t2": "Thứ 2", "thứ hai": "Thứ 2", "thu hai": "Thứ 2", "thuhai": "Thứ 2", "monday": "Thứ 2", "mon": "Thứ 2",
    "thứ 3": "Thứ 3", "thu 3": "Thứ 3", "t3": "Thứ 3", "thứ ba": "Thứ 3", "thu ba": "Thứ 3", "thuba": "Thứ 3", "tuesday": "Thứ 3", "tue": "Thứ 3",
    "thứ 4": "Thứ 4", "thu 4": "Thứ 4", "t4": "Thứ 4", "thứ tư": "Thứ 4", "thu tu": "Thứ 4", "thutu": "Thứ 4", "wednesday": "Thứ 4", "wed": "Thứ 4",
    "thứ 5": "Thứ 5", "thu 5": "Thứ 5", "t5": "Thứ 5", "thứ năm": "Thứ 5", "thu nam": "Thứ 5", "thunam": "Thứ 5", "thursday": "Thứ 5", "thu": "Thứ 5",
    "thứ 6": "Thứ 6", "thu 6": "Thứ 6", "t6": "Thứ 6", "thứ sáu": "Thứ 6", "thu sau": "Thứ 6", "thusau": "Thứ 6", "friday": "Thứ 6", "fri": "Thứ 6",
    "thứ 7": "Thứ 7", "thu 7": "Thứ 7", "t7": "Thứ 7", "thứ bảy": "Thứ 7", "thu bay": "Thứ 7", "thubay": "Thứ 7", "saturday": "Thứ 7", "sat": "Thứ 7",
    "chủ nhật": "Chủ nhật", "chu nhat": "Chủ nhật", "cn": "Chủ nhật", "sunday": "Chủ nhật", "sun": "Chủ nhật",
}

SHIFT_ALIASES = {
    "sáng": "morning", "sang": "morning", "buổi sáng": "morning", "buoi sang": "morning", "morning": "morning",
    "chiều": "afternoon", "chieu": "afternoon", "buổi chiều": "afternoon", "buoi chieu": "afternoon", "afternoon": "afternoon",
    "tối": "evening", "toi": "evening", "buổi tối": "evening", "buoi toi": "evening", "evening": "evening",
}


def strip_accents(text: str) -> str:
    text = unicodedata.normalize("NFD", str(text or ""))
    return "".join(c for c in text if unicodedata.category(c) != "Mn").lower()


def normalized(text: str) -> str:
    return " ".join(strip_accents(text).replace("_", "-").split())


class NaturalLanguageParser:
    """Small parser abstraction; implementations never answer schedule facts."""

    def parse(self, query_text: str) -> ScheduleQuery:  # pragma: no cover - interface
        raise NotImplementedError


class RuleBasedParser(NaturalLanguageParser):
    """Rule-first parser used by the Phase 4.2 offline demo."""

    def __init__(self, dataset_index: Optional[Dict[str, Any]] = None):
        self.assignments = list((dataset_index or {}).get("assignments", []))

    def parse(self, query_text: str) -> ScheduleQuery:
        if not query_text or not query_text.strip():
            return ScheduleQuery(raw_query="", intent="unsupported")

        raw = " ".join(query_text.strip().split())
        norm = normalized(raw)
        day = self._extract_day(raw)
        shift = self._extract_shift(raw)
        lecturer = self._entity_from_index(raw, "lecturer_id", "lecturer_name")
        room = self._entity_from_index(raw, "room_id", "room_name")
        course = self._entity_from_index(raw, "course_code", "course_id", "course_name")
        class_code = self._entity_from_index(raw, "class_code", "section_id")
        group = self._entity_from_index(raw, "student_group_id", "student_group_name")

        # Unknown explicit entities still reach the resolver, which can then
        # return a precise "not found" message instead of an unsupported one.
        lecturer = lecturer or self._match(r"\bgv[-_]?\d+\b", raw)
        if not room and not self._is_free_room(norm):
            room = self._after_keyword(raw, ("phòng", "phong", "room"))
        class_code = class_code or self._class_after_keyword(raw)
        group = group or (None if class_code else self._group_after_keyword(raw))
        course = course or self._course_code(raw) or self._course_after_keyword(raw)
        lecturer = lecturer or self._lecturer_name_after_keyword(raw)

        if self._contains_any(norm, ("tom tat", "tong quan", "schedule summary", "summary")):
            intent = "schedule_summary"
        elif self._is_free_room(norm):
            intent = "free_room_search"
            room = None
        elif lecturer and self._contains_any(norm, ("ranh", "free", "available")):
            intent = "lecturer_free_time"
        elif class_code:
            intent = "class_schedule"
        elif lecturer:
            intent = "lecturer_schedule"
        elif room:
            intent = "room_schedule"
        elif course:
            intent = "course_schedule"
        elif group:
            intent = "student_group_schedule"
        elif day or shift:
            intent = "schedule_by_day"
        else:
            intent = "unsupported"

        return ScheduleQuery(
            raw_query=raw, intent=intent, day=day, shift=shift,
            student_group=group, lecturer=lecturer, room=room,
            course=course, class_code=class_code,
        )

    @staticmethod
    def _contains_any(text: str, needles: tuple[str, ...]) -> bool:
        return any(needle in text for needle in needles)

    def _entity_from_index(self, raw: str, *fields: str) -> Optional[str]:
        q = normalized(raw)
        candidates = []
        for assignment in self.assignments:
            for field in fields:
                value = str(assignment.get(field) or "").strip()
                norm_value = normalized(value)
                if value and re.search(rf"(?<![\w-]){re.escape(norm_value)}(?![\w-])", q):
                    candidates.append(value)
        return max(candidates, key=len) if candidates else None

    @staticmethod
    def _match(pattern: str, raw: str) -> Optional[str]:
        match = re.search(pattern, raw, flags=re.IGNORECASE)
        return match.group(0).upper().replace("_", "").replace("-", "") if match else None

    @staticmethod
    def _after_keyword(raw: str, keywords: tuple[str, ...]) -> Optional[str]:
        joined = "|".join(re.escape(key) for key in keywords)
        match = re.search(rf"\b(?:{joined})\s+([\w-]+)", raw, flags=re.IGNORECASE)
        if not match or normalized(match.group(1)) in {"nao", "trong", "ranh", "free"}:
            return None
        return match.group(1)

    @staticmethod
    def _class_after_keyword(raw: str) -> Optional[str]:
        match = re.search(r"\b(?:lớp|lop|class)\s+([0-9][A-Za-z0-9._-]{5,})\b", raw, flags=re.IGNORECASE)
        return match.group(1) if match else None

    @staticmethod
    def _group_after_keyword(raw: str) -> Optional[str]:
        match = re.search(r"\b(?:lớp|lop|nhóm|nhom|group)\s+([A-Za-z][A-Za-z0-9_-]+)\b", raw, flags=re.IGNORECASE)
        return match.group(1) if match else None

    @staticmethod
    def _course_code(raw: str) -> Optional[str]:
        match = re.search(r"\b[A-Za-z]{2,}[0-9]{2,}[A-Za-z0-9-]*\b", raw)
        if match and not match.group(0).upper().startswith("GV"):
            return match.group(0)
        return None

    @staticmethod
    def _course_after_keyword(raw: str) -> Optional[str]:
        match = re.search(
            r"\b(?:môn|mon|học phần|hoc phan|course)\s+(.+?)(?=\s+(?:học|hoc|dạy|day|ở|tại|tai|phòng|phong|vào|vao|thứ|thu|lúc|luc)\b|[?.!,]|$)",
            raw, flags=re.IGNORECASE,
        )
        return match.group(1).strip() if match else None

    @staticmethod
    def _lecturer_name_after_keyword(raw: str) -> Optional[str]:
        match = re.search(r"\b(?:giảng viên|giang vien|thầy|thay|cô|co)\s+(.+?)(?=\s+(?:dạy|day|rảnh|ranh|thứ|thu|khi|lúc|luc)\b|[?.!,]|$)", raw, flags=re.IGNORECASE)
        return match.group(1).strip() if match else None

    @staticmethod
    def _is_free_room(norm: str) -> bool:
        return ("phong" in norm or "room" in norm) and any(word in norm for word in ("trong", "ranh", "free", "available"))

    @staticmethod
    def _extract_day(raw: str) -> Optional[str]:
        raw_lower, norm = raw.lower(), normalized(raw)
        english = {"mon", "tue", "wed", "thu", "fri", "sat", "sun", "monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"}
        for alias, canonical in sorted(DAY_ALIASES.items(), key=lambda item: -len(item[0])):
            if alias in english:
                continue
            candidate = normalized(alias)
            if re.search(rf"(?<!\w){re.escape(candidate)}(?!\w)", norm):
                return canonical
        for alias in sorted(english, key=len, reverse=True):
            if re.search(rf"(?<!\w){alias}(?!\w)", raw_lower):
                return DAY_ALIASES[alias]
        return None

    @staticmethod
    def _extract_shift(raw: str) -> Optional[str]:
        q, raw_lower = normalized(raw), raw.lower()
        # Keep accented "tối" distinct from the pronoun "tôi"; accent
        # stripping would otherwise misread "Cho tôi xem lịch" as evening.
        if re.search(r"(?<!\w)tối(?!\w)", raw_lower) or re.search(r"(?<!\w)evening(?!\w)", raw_lower):
            return "evening"
        for alias, canonical in sorted(SHIFT_ALIASES.items(), key=lambda item: -len(item[0])):
            if canonical == "evening":
                continue
            if re.search(rf"(?<!\w){re.escape(normalized(alias))}(?!\w)", q):
                return canonical
        return None


class IntentParser(RuleBasedParser):
    """Backward-compatible parser name for the pre-Phase-4.2 API."""

    _LEGACY_INTENTS = {
        "student_group_schedule": "schedule_by_student_group",
        "lecturer_schedule": "schedule_by_lecturer",
        "room_schedule": "schedule_by_room",
        "course_schedule": "schedule_by_course",
        "unsupported": "unknown_or_ambiguous",
    }

    def parse(self, query_text: str) -> ScheduleQuery:
        query = super().parse(query_text)
        intent = self._LEGACY_INTENTS.get(query.intent, query.intent)
        active = [query.day, query.shift, query.student_group, query.lecturer, query.room, query.course, query.class_code]
        if sum(value is not None for value in active) > 1 and query.intent not in {"free_room_search", "lecturer_free_time"}:
            intent = "schedule_combined"
        elif query.day and all(value is None for value in active[1:]):
            intent = "schedule_by_day"
        return ScheduleQuery(**{**query.__dict__, "intent": intent})
