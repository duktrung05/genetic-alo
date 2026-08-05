"""Excel Dataset Loader Module.

Parses and validates timetable scheduling dataset from Microsoft Excel workbook format (.xlsx).
"""

import os
import json
from typing import Dict, List, Set, Optional, Any
import openpyxl
from domain import Timeslot, Room, Lecturer, StudentGroup, Course, CourseSection, ConstraintDefinition
from .validator import DatasetValidator

class ExcelValidationError(ValueError):
    """Custom exception raised when Excel data fails validation rules with precise row/col context."""
    pass


class ExcelDatasetLoader:
    """Loader responsible for reading timetable scheduling entities from Excel workbooks."""

    # Canonical mapping from Excel constraint_id to internal technical key
    SOFT_CONSTRAINT_KEY_BY_ID: Dict[str, str] = {
        "S1": "weekly_distribution",
        "S2": "late_day_periods",
        "S3": "preferred_shift_mismatch",
        "S4": "room_seat_waste",
        "S5": "consecutive_cross_campus",
    }
    SUPPORTED_SOFT_IDS: frozenset = frozenset(SOFT_CONSTRAINT_KEY_BY_ID.keys())

    SHIFT_MAP = {
        "Sáng": "morning",
        "Chiều": "afternoon",
        "Tối": "evening",
        "MORNING": "morning",
        "AFTERNOON": "afternoon",
        "EVENING": "evening",
        "morning": "morning",
        "afternoon": "afternoon",
        "evening": "evening",
        "Morning": "morning",
        "Afternoon": "afternoon",
        "Evening": "evening",
    }

    VALID_SHIFTS = frozenset({"morning", "afternoon", "evening"})

    IGNORED_SHEETS = {
        "README",
        "BASELINE_SCHEDULE",
        "BEST_SCHEDULE",
        "SCHEDULE_BY_GROUP",
        "SCHEDULE_BY_LECTURER",
        "SCHEDULE_BY_ROOM",
    }

    @classmethod
    def _normalize_optional_str(cls, value) -> Optional[str]:
        """Convert cell value to stripped string or None if empty/NaN."""
        if value is None:
            return None
        text = str(value).strip()
        if not text or text.lower() == "nan":
            return None
        return text

    @classmethod
    def _parse_meetings_per_week(cls, value, row_idx: int) -> int:
        """Parse meetings_per_week from cell value.

        Rules:
          - blank/None  → default 1
          - integer     → use as-is (must be >= 1)
          - float N.0   → int(N) if fractional part is 0
          - non-integer float → ExcelValidationError
          - non-numeric → ExcelValidationError
        """
        if value is None:
            return 1
        try:
            f = float(value)
        except (ValueError, TypeError):
            raise ExcelValidationError(
                f"Sheet 'COURSE_SECTIONS', Row {row_idx}, Column 'meetings_per_week', "
                f"Value '{value}': Must be a positive integer (e.g. 1, 2)"
            )
        if f != int(f):
            raise ExcelValidationError(
                f"Sheet 'COURSE_SECTIONS', Row {row_idx}, Column 'meetings_per_week', "
                f"Value '{value}': Non-integer value not allowed (got {f})"
            )
        result = int(f)
        if result < 1:
            raise ExcelValidationError(
                f"Sheet 'COURSE_SECTIONS', Row {row_idx}, Column 'meetings_per_week', "
                f"Value '{value}': Must be >= 1 (got {result})"
            )
        return result

    @classmethod
    def _parse_weight_int(cls, value, sheet: str, row_idx: int, col: str) -> int:
        """Parse constraint weight from cell: accepts int, float N.0, or str of those.

        Raises ExcelValidationError for:
          - blank / None
          - non-numeric string (e.g. 'abc')
          - non-integral float (e.g. 2.5)
          - negative value
        """
        if value is None:
            raise ExcelValidationError(
                f"Sheet '{sheet}', Row {row_idx}, Column '{col}': weight must not be blank"
            )
        raw_str = str(value).strip()
        if not raw_str or raw_str.lower() == "nan":
            raise ExcelValidationError(
                f"Sheet '{sheet}', Row {row_idx}, Column '{col}': weight must not be blank"
            )
        try:
            f = float(raw_str)
        except (ValueError, TypeError):
            raise ExcelValidationError(
                f"Sheet '{sheet}', Row {row_idx}, Column '{col}', "
                f"Value '{value}': weight must be a non-negative integer (e.g. 10, 5)"
            )
        if f != int(f):
            raise ExcelValidationError(
                f"Sheet '{sheet}', Row {row_idx}, Column '{col}', "
                f"Value '{value}': Non-integer weight not allowed (got {f}). "
                f"Only integers like 10, 5, 0 are accepted."
            )
        result = int(f)
        if result < 0:
            raise ExcelValidationError(
                f"Sheet '{sheet}', Row {row_idx}, Column '{col}', "
                f"Value '{value}': weight cannot be negative (got {result})"
            )
        return result

    @classmethod
    def _parse_enabled_bool(cls, value, sheet: str, row_idx: int, col: str) -> bool:
        """Parse enabled flag: True/False, 'true'/'false', 1/0.

        Raises ExcelValidationError for any unrecognized value.
        NOTE: bool('False') == True is a Python gotcha — we handle string comparison
        explicitly.
        """
        if value is None:
            raise ExcelValidationError(
                f"Sheet '{sheet}', Row {row_idx}, Column '{col}': enabled must not be blank"
            )
        if isinstance(value, bool):
            return value
        if isinstance(value, (int, float)):
            if value == 1:
                return True
            if value == 0:
                return False
            raise ExcelValidationError(
                f"Sheet '{sheet}', Row {row_idx}, Column '{col}', "
                f"Value '{value}': enabled must be True/False or 1/0"
            )
        s = str(value).strip().lower()
        if s in ("true", "1"):
            return True
        if s in ("false", "0"):
            return False
        raise ExcelValidationError(
            f"Sheet '{sheet}', Row {row_idx}, Column '{col}', "
            f"Value '{value}': enabled must be True/False, 'true'/'false', 1, or 0"
        )

    @classmethod
    def _parse_constraints_sheet(cls, wb) -> List[ConstraintDefinition]:
        """Parse the CONSTRAINTS sheet into a list of ConstraintDefinition objects.

        Validates:
        - Required headers present
        - No duplicate constraint_id
        - Soft constraint IDs must be in SUPPORTED_SOFT_IDS
        - weight: non-negative integer
        - enabled: boolean
        - constraint_type: SOFT or HARD (case-insensitive, normalized to upper)

        Returns empty list if CONSTRAINTS sheet is missing (non-Excel datasets).
        """
        if "CONSTRAINTS" not in wb.sheetnames:
            return []

        ws = wb["CONSTRAINTS"]
        rows = list(ws.iter_rows(values_only=True))
        if not rows:
            return []

        # Validate header
        req_cols = ["constraint_id", "constraint_type", "constraint_name", "weight", "enabled"]
        header = [str(h).strip() if h is not None else "" for h in rows[0]]
        for col in req_cols:
            if col not in header:
                raise ExcelValidationError(
                    f"Sheet 'CONSTRAINTS', Row 1, Column '{col}': "
                    f"Required header column is missing. "
                    f"Expected columns: {req_cols}"
                )

        def _col(name: str):
            return header.index(name)

        seen_ids: Set[str] = set()
        definitions: List[ConstraintDefinition] = []

        for row_idx, row in enumerate(rows[1:], start=2):
            if not row or row[0] is None:
                continue
            # Normalize row to dict by header
            row_dict = {
                h: (row[i] if i < len(row) else None)
                for i, h in enumerate(header) if h
            }

            c_id_raw = cls._normalize_optional_str(row_dict.get("constraint_id"))
            if not c_id_raw:
                raise ExcelValidationError(
                    f"Sheet 'CONSTRAINTS', Row {row_idx}, Column 'constraint_id': "
                    f"constraint_id must not be empty"
                )
            c_id = c_id_raw.strip()

            if c_id in seen_ids:
                raise ExcelValidationError(
                    f"Sheet 'CONSTRAINTS', Row {row_idx}, Column 'constraint_id', "
                    f"Value '{c_id}': Duplicate constraint_id"
                )
            seen_ids.add(c_id)

            # Normalize constraint_type
            c_type_raw = cls._normalize_optional_str(row_dict.get("constraint_type"))
            if not c_type_raw:
                raise ExcelValidationError(
                    f"Sheet 'CONSTRAINTS', Row {row_idx}, Column 'constraint_type': "
                    f"constraint_type must not be empty"
                )
            c_type = c_type_raw.strip().upper()
            if c_type not in ("SOFT", "HARD"):
                raise ExcelValidationError(
                    f"Sheet 'CONSTRAINTS', Row {row_idx}, Column 'constraint_type', "
                    f"Value '{c_type_raw}': Must be 'SOFT' or 'HARD'"
                )

            # Validate soft constraint IDs
            if c_type == "SOFT" and c_id not in cls.SUPPORTED_SOFT_IDS:
                raise ExcelValidationError(
                    f"Sheet 'CONSTRAINTS', Row {row_idx}, Column 'constraint_id', "
                    f"Value '{c_id}': Unsupported soft constraint_id='{c_id}'. "
                    f"Supported IDs: {sorted(cls.SUPPORTED_SOFT_IDS)}."
                )

            c_name = cls._normalize_optional_str(row_dict.get("constraint_name")) or c_id

            weight = cls._parse_weight_int(
                row_dict.get("weight"), "CONSTRAINTS", row_idx, "weight"
            )
            enabled = cls._parse_enabled_bool(
                row_dict.get("enabled"), "CONSTRAINTS", row_idx, "enabled"
            )

            definitions.append(ConstraintDefinition(
                constraint_id=c_id,
                constraint_type=c_type,
                constraint_name=c_name,
                weight=weight,
                enabled=enabled,
            ))

        return definitions

    @classmethod
    def load(cls, excel_path: str = "data/01_data_timetable.xlsx") -> dict:
        """Load and parse dataset dictionary from specified Excel file path.

        Args:
            excel_path: Path to the Excel workbook file.

        Returns:
            Dataset dictionary containing entity lists:
            {"timeslots", "rooms", "lecturers", "student_groups", "courses", "course_sections"}
        """
        if not os.path.exists(excel_path):
            raise FileNotFoundError(f"Excel dataset file not found at path: '{excel_path}'")

        wb = openpyxl.load_workbook(excel_path, data_only=True)

        # 0. Parse CONSTRAINTS sheet (before other sheets)
        constraint_definitions = cls._parse_constraints_sheet(wb)

        # Log ignored sheets if present
        for sheet_name in wb.sheetnames:
            if sheet_name in cls.IGNORED_SHEETS:
                # Intentionally ignored output/documentation sheet
                pass

        # 1. Parse TIMESLOTS
        if "TIMESLOTS" not in wb.sheetnames:
            raise ExcelValidationError("Sheet 'TIMESLOTS', Row 0, Column 'sheet': Sheet is missing from workbook")
        ws_ts = wb["TIMESLOTS"]
        rows_ts = list(ws_ts.iter_rows(values_only=True))
        if not rows_ts:
            raise ExcelValidationError("Sheet 'TIMESLOTS', Row 1, Column 'all': Sheet is empty")

        header_ts = [str(h).strip() if h is not None else "" for h in rows_ts[0]]
        req_ts_cols = ["timeslot_id", "day_name", "period_no", "shift"]
        for col in req_ts_cols:
            if col not in header_ts:
                raise ExcelValidationError(f"Sheet 'TIMESLOTS', Row 1, Column '{col}': Required header column is missing")

        code_to_ts_id: Dict[str, int] = {}
        timeslots: List[Timeslot] = []

        for row_idx, row in enumerate(rows_ts[1:], start=2):
            if not row or row[0] is None:
                continue
            code = str(row[header_ts.index("timeslot_id")]).strip()
            if not code:
                raise ExcelValidationError(f"Sheet 'TIMESLOTS', Row {row_idx}, Column 'timeslot_id', Value '{row[0]}': Invalid empty timeslot_id")
            if code in code_to_ts_id:
                raise ExcelValidationError(f"Sheet 'TIMESLOTS', Row {row_idx}, Column 'timeslot_id', Value '{code}': Duplicate timeslot_id")

            day_name = str(row[header_ts.index("day_name")]).strip()
            try:
                period_no = int(row[header_ts.index("period_no")])
            except (ValueError, TypeError):
                raise ExcelValidationError(f"Sheet 'TIMESLOTS', Row {row_idx}, Column 'period_no', Value '{row[header_ts.index('period_no')]}\': Invalid period number")

            shift = str(row[header_ts.index("shift")]).strip()
            ts_id = len(timeslots)
            code_to_ts_id[code] = ts_id
            session = cls.SHIFT_MAP.get(shift, "morning")
            start_t = str(row[header_ts.index("start_time")]).strip() if "start_time" in header_ts and row[header_ts.index("start_time")] else "07:00"
            end_t = str(row[header_ts.index("end_time")]).strip() if "end_time" in header_ts and row[header_ts.index("end_time")] else "07:50"

            ts = Timeslot(
                id=ts_id,
                day=day_name,
                period=period_no,
                start_time=start_t,
                end_time=end_t,
                session=session,
            )
            timeslots.append(ts)

        # 2. Parse ROOMS
        if "ROOMS" not in wb.sheetnames:
            raise ExcelValidationError("Sheet 'ROOMS', Row 0, Column 'sheet': Sheet is missing from workbook")
        ws_rm = wb["ROOMS"]
        rows_rm = list(ws_rm.iter_rows(values_only=True))
        if not rows_rm:
            raise ExcelValidationError("Sheet 'ROOMS', Row 1, Column 'all': Sheet is empty")

        header_rm = [str(h).strip() if h is not None else "" for h in rows_rm[0]]
        req_rm_cols = ["room_id", "capacity", "room_type"]
        for col in req_rm_cols:
            if col not in header_rm:
                raise ExcelValidationError(f"Sheet 'ROOMS', Row 1, Column '{col}': Required header column is missing")

        rooms: List[Room] = []
        room_ids: Set[str] = set()

        for row_idx, r in enumerate(rows_rm[1:], start=2):
            if not r or r[0] is None:
                continue
            r_id = str(r[header_rm.index("room_id")]).strip()
            if not r_id:
                raise ExcelValidationError(f"Sheet 'ROOMS', Row {row_idx}, Column 'room_id', Value '{r_id}': Invalid empty room_id")
            if r_id in room_ids:
                raise ExcelValidationError(f"Sheet 'ROOMS', Row {row_idx}, Column 'room_id', Value '{r_id}': Duplicate room_id")
            room_ids.add(r_id)

            try:
                cap = int(r[header_rm.index("capacity")])
                if cap <= 0:
                    raise ValueError("Capacity must be positive")
            except (ValueError, TypeError):
                raise ExcelValidationError(f"Sheet 'ROOMS', Row {row_idx}, Column 'capacity', Value '{r[header_rm.index('capacity')]}\': Capacity must be positive integer")

            r_type = str(r[header_rm.index("room_type")]).strip()
            if r_type not in ["NORMAL", "LAB"]:
                raise ExcelValidationError(f"Sheet 'ROOMS', Row {row_idx}, Column 'room_type', Value '{r_type}': Invalid room_type. Must be 'NORMAL' or 'LAB'")

            bld = str(r[header_rm.index("building")]).strip() if "building" in header_rm and r[header_rm.index("building")] else ""
            r_num = str(r[header_rm.index("room_number")]).strip() if "room_number" in header_rm and r[header_rm.index("room_number")] else r_id
            name = f"{bld}-{r_num}" if bld else r_num

            campus_id = cls._normalize_optional_str(
                r[header_rm.index("campus_id")] if "campus_id" in header_rm else None
            )

            room = Room(
                id=r_id,
                name=name,
                capacity=cap,
                room_type=r_type,
                campus_id=campus_id,
            )
            rooms.append(room)

        # 3. Parse LECTURER_AVAILABILITY
        lec_avail_map: Dict[str, Optional[frozenset]] = {}
        if "LECTURER_AVAILABILITY" in wb.sheetnames:
            ws_avail = wb["LECTURER_AVAILABILITY"]
            rows_avail = list(ws_avail.iter_rows(values_only=True))
            if rows_avail:
                avail_header = [str(h).strip() if h is not None else "" for h in rows_avail[0]]
                for row_idx, r in enumerate(rows_avail[1:], start=2):
                    if not r or r[0] is None:
                        continue
                    l_id = str(r[0]).strip()
                    avail_ts_set: Set[int] = set()
                    for col_idx in range(2, len(r)):
                        if col_idx < len(avail_header):
                            col_name = avail_header[col_idx]
                            is_avail = r[col_idx]
                            if is_avail is not True and is_avail is not False and is_avail is not None:
                                raise ExcelValidationError(f"Sheet 'LECTURER_AVAILABILITY', Row {row_idx}, Column '{col_name}', Value '{is_avail}': Availability must be boolean True/False")
                            if is_avail and col_name in code_to_ts_id:
                                avail_ts_set.add(code_to_ts_id[col_name])

                    if len(avail_ts_set) == len(timeslots):
                        lec_avail_map[l_id] = None
                    else:
                        lec_avail_map[l_id] = frozenset(avail_ts_set)

        # 4. Parse LECTURERS
        if "LECTURERS" not in wb.sheetnames:
            raise ExcelValidationError("Sheet 'LECTURERS', Row 0, Column 'sheet': Sheet is missing from workbook")
        ws_lec = wb["LECTURERS"]
        rows_lec = list(ws_lec.iter_rows(values_only=True))
        if not rows_lec:
            raise ExcelValidationError("Sheet 'LECTURERS', Row 1, Column 'all': Sheet is empty")

        header_lec = [str(h).strip() if h is not None else "" for h in rows_lec[0]]
        req_lec_cols = ["lecturer_id", "lecturer_name"]
        for col in req_lec_cols:
            if col not in header_lec:
                raise ExcelValidationError(f"Sheet 'LECTURERS', Row 1, Column '{col}': Required header column is missing")

        lecturers: List[Lecturer] = []
        lecturer_ids: Set[str] = set()

        for row_idx, r in enumerate(rows_lec[1:], start=2):
            if not r or r[0] is None:
                continue
            l_id = str(r[header_lec.index("lecturer_id")]).strip()
            if not l_id:
                raise ExcelValidationError(f"Sheet 'LECTURERS', Row {row_idx}, Column 'lecturer_id', Value '{l_id}': Invalid empty lecturer_id")
            if l_id in lecturer_ids:
                raise ExcelValidationError(f"Sheet 'LECTURERS', Row {row_idx}, Column 'lecturer_id', Value '{l_id}': Duplicate lecturer_id")
            lecturer_ids.add(l_id)

            l_name = str(r[header_lec.index("lecturer_name")]).strip()
            avail = lec_avail_map.get(l_id)
            lec = Lecturer(
                id=l_id,
                name=l_name,
                available_timeslot_ids=avail,
            )
            lecturers.append(lec)

        # 5. Parse STUDENT_GROUPS
        if "STUDENT_GROUPS" not in wb.sheetnames:
            raise ExcelValidationError("Sheet 'STUDENT_GROUPS', Row 0, Column 'sheet': Sheet is missing from workbook")
        ws_grp = wb["STUDENT_GROUPS"]
        rows_grp = list(ws_grp.iter_rows(values_only=True))
        if not rows_grp:
            raise ExcelValidationError("Sheet 'STUDENT_GROUPS', Row 1, Column 'all': Sheet is empty")

        header_grp = [str(h).strip() if h is not None else "" for h in rows_grp[0]]
        req_grp_cols = ["group_id", "group_name", "size"]
        for col in req_grp_cols:
            if col not in header_grp:
                raise ExcelValidationError(f"Sheet 'STUDENT_GROUPS', Row 1, Column '{col}': Required header column is missing")

        student_groups: List[StudentGroup] = []
        group_ids: Set[str] = set()

        for row_idx, r in enumerate(rows_grp[1:], start=2):
            if not r or r[0] is None:
                continue
            g_id = str(r[header_grp.index("group_id")]).strip()
            if not g_id:
                raise ExcelValidationError(f"Sheet 'STUDENT_GROUPS', Row {row_idx}, Column 'group_id', Value '{g_id}': Invalid empty group_id")
            if g_id in group_ids:
                raise ExcelValidationError(f"Sheet 'STUDENT_GROUPS', Row {row_idx}, Column 'group_id', Value '{g_id}': Duplicate group_id")
            group_ids.add(g_id)

            g_name = str(r[header_grp.index("group_name")]).strip()
            try:
                size = int(r[header_grp.index("size")])
                if size <= 0:
                    raise ValueError("Group size must be positive")
            except (ValueError, TypeError):
                raise ExcelValidationError(f"Sheet 'STUDENT_GROUPS', Row {row_idx}, Column 'size', Value '{r[header_grp.index('size')]}\': Group size must be positive integer")

            home_campus_id = cls._normalize_optional_str(
                r[header_grp.index("home_campus_id")] if "home_campus_id" in header_grp else None
            )

            grp = StudentGroup(
                id=g_id,
                name=g_name,
                student_count=size,
                home_campus_id=home_campus_id,
            )
            student_groups.append(grp)

        # 6. Parse COURSES
        if "COURSES" not in wb.sheetnames:
            raise ExcelValidationError("Sheet 'COURSES', Row 0, Column 'sheet': Sheet is missing from workbook")
        ws_crs = wb["COURSES"]
        rows_crs = list(ws_crs.iter_rows(values_only=True))
        if not rows_crs:
            raise ExcelValidationError("Sheet 'COURSES', Row 1, Column 'all': Sheet is empty")

        header_crs = [str(h).strip() if h is not None else "" for h in rows_crs[0]]
        req_crs_cols = ["course_id", "course_name"]
        for col in req_crs_cols:
            if col not in header_crs:
                raise ExcelValidationError(f"Sheet 'COURSES', Row 1, Column '{col}': Required header column is missing")

        courses: List[Course] = []
        course_ids: Set[str] = set()

        for row_idx, r in enumerate(rows_crs[1:], start=2):
            if not r or r[0] is None:
                continue
            c_id = str(r[header_crs.index("course_id")]).strip()
            if not c_id:
                raise ExcelValidationError(f"Sheet 'COURSES', Row {row_idx}, Column 'course_id', Value '{c_id}': Invalid empty course_id")
            if c_id in course_ids:
                raise ExcelValidationError(f"Sheet 'COURSES', Row {row_idx}, Column 'course_id', Value '{c_id}': Duplicate course_id")
            course_ids.add(c_id)

            c_name = str(r[header_crs.index("course_name")]).strip()
            diff = str(r[header_crs.index("difficulty")]).strip() if "difficulty" in header_crs and r[header_crs.index("difficulty")] else ""
            crs = Course(
                course_id=c_id,
                name=c_name,
                credits=3,
                is_difficult=(diff == "HARD"),
            )
            courses.append(crs)

        # 7. Parse COURSE_SECTIONS
        if "COURSE_SECTIONS" not in wb.sheetnames:
            raise ExcelValidationError("Sheet 'COURSE_SECTIONS', Row 0, Column 'sheet': Sheet is missing from workbook")
        ws_sec = wb["COURSE_SECTIONS"]
        rows_sec = list(ws_sec.iter_rows(values_only=True))
        if not rows_sec:
            raise ExcelValidationError("Sheet 'COURSE_SECTIONS', Row 1, Column 'all': Sheet is empty")

        header_sec = [str(h).strip() if h is not None else "" for h in rows_sec[0]]
        req_sec_cols = ["section_id", "course_id", "lecturer_id", "student_group_id", "student_count", "required_room_type", "duration_periods"]
        for col in req_sec_cols:
            if col not in header_sec:
                raise ExcelValidationError(f"Sheet 'COURSE_SECTIONS', Row 1, Column '{col}': Required header column is missing")

        course_sections: List[CourseSection] = []
        section_ids: Set[str] = set()

        for row_idx, r in enumerate(rows_sec[1:], start=2):
            if not r or r[0] is None:
                continue
            sec_id = str(r[header_sec.index("section_id")]).strip()
            if not sec_id:
                raise ExcelValidationError(f"Sheet 'COURSE_SECTIONS', Row {row_idx}, Column 'section_id', Value '{sec_id}': Invalid empty section_id")
            if sec_id in section_ids:
                raise ExcelValidationError(f"Sheet 'COURSE_SECTIONS', Row {row_idx}, Column 'section_id', Value '{sec_id}': Duplicate section_id")
            section_ids.add(sec_id)

            c_id = str(r[header_sec.index("course_id")]).strip()
            if c_id not in course_ids:
                raise ExcelValidationError(f"Sheet 'COURSE_SECTIONS', Row {row_idx}, Column 'course_id', Value '{c_id}': Referenced course_id does not exist in COURSES sheet")

            l_id = str(r[header_sec.index("lecturer_id")]).strip()
            if l_id not in lecturer_ids:
                raise ExcelValidationError(f"Sheet 'COURSE_SECTIONS', Row {row_idx}, Column 'lecturer_id', Value '{l_id}': Referenced lecturer_id does not exist in LECTURERS sheet")

            g_id = str(r[header_sec.index("student_group_id")]).strip()
            if g_id not in group_ids:
                raise ExcelValidationError(f"Sheet 'COURSE_SECTIONS', Row {row_idx}, Column 'student_group_id', Value '{g_id}': Referenced student_group_id does not exist in STUDENT_GROUPS sheet")

            try:
                st_cnt = int(r[header_sec.index("student_count")])
                if st_cnt <= 0:
                    raise ValueError("student_count must be positive")
            except (ValueError, TypeError):
                raise ExcelValidationError(f"Sheet 'COURSE_SECTIONS', Row {row_idx}, Column 'student_count', Value '{r[header_sec.index('student_count')]}\': Student count must be positive integer")

            req_type = str(r[header_sec.index("required_room_type")]).strip()
            if req_type not in ["NORMAL", "LAB"]:
                raise ExcelValidationError(f"Sheet 'COURSE_SECTIONS', Row {row_idx}, Column 'required_room_type', Value '{req_type}': Invalid required_room_type. Must be 'NORMAL' or 'LAB'")

            try:
                dur = int(r[header_sec.index("duration_periods")])
                if dur < 1:
                    raise ValueError("duration_periods must be >= 1")
            except (ValueError, TypeError):
                raise ExcelValidationError(f"Sheet 'COURSE_SECTIONS', Row {row_idx}, Column 'duration_periods', Value '{r[header_sec.index('duration_periods')]}\': Duration periods must be integer >= 1")

            c_name = str(r[header_sec.index("course_name")]).strip() if "course_name" in header_sec and r[header_sec.index("course_name")] else c_id
            diff = str(r[header_sec.index("difficulty")]).strip() if "difficulty" in header_sec and r[header_sec.index("difficulty")] else ""

            # Optional preference fields
            preferred_campus_id = cls._normalize_optional_str(
                r[header_sec.index("preferred_campus_id")] if "preferred_campus_id" in header_sec else None
            )

            # Normalize preferred_shift via SHIFT_MAP then validate
            raw_shift = cls._normalize_optional_str(
                r[header_sec.index("preferred_shift")] if "preferred_shift" in header_sec else None
            )
            preferred_shift: Optional[str] = None
            if raw_shift is not None:
                preferred_shift = cls.SHIFT_MAP.get(raw_shift, raw_shift.lower())
                if preferred_shift not in cls.VALID_SHIFTS:
                    raise ExcelValidationError(
                        f"Sheet 'COURSE_SECTIONS', Row {row_idx}, Column 'preferred_shift', "
                        f"Value '{raw_shift}': Invalid shift. Allowed values: "
                        f"{sorted(cls.VALID_SHIFTS)}"
                    )

            meetings_per_week = cls._parse_meetings_per_week(
                r[header_sec.index("meetings_per_week")] if "meetings_per_week" in header_sec else None,
                row_idx,
            )

            sec = CourseSection(
                section_id=sec_id,
                course_id=c_id,
                course_name=c_name,
                lecturer_id=l_id,
                group_id=g_id,
                student_count=st_cnt,
                is_difficult=(diff == "HARD"),
                required_room_type=req_type,
                duration_periods=dur,
                preferred_campus_id=preferred_campus_id,
                preferred_shift=preferred_shift,
                meetings_per_week=meetings_per_week,
            )
            course_sections.append(sec)

        return {
            "timeslots": timeslots,
            "rooms": rooms,
            "lecturers": lecturers,
            "student_groups": student_groups,
            "courses": courses,
            "course_sections": course_sections,
            "constraints": constraint_definitions,
        }

    @classmethod
    def load_and_validate(cls, excel_path: str = "data/01_data_timetable.xlsx") -> dict:
        """Load dataset from Excel file and run DatasetValidator validation.

        Args:
            excel_path: Path to the Excel workbook file.

        Returns:
            Validated dataset dictionary.
        """
        dataset = cls.load(excel_path)
        DatasetValidator.validate(dataset)
        return dataset

    @classmethod
    def export_normalized_json(cls, dataset: dict, output_path: str = "outputs/datasets/01_data_timetable.normalized.json") -> str:
        """Serialize dataset dictionary into normalized JSON snapshot file.

        Args:
            dataset: Dataset dictionary.
            output_path: Target JSON file path.

        Returns:
            Absolute path of written JSON snapshot file.
        """
        os.makedirs(os.path.dirname(output_path), exist_ok=True)

        data = {
            "timeslots": [
                {
                    "id": t.id,
                    "day": t.day,
                    "period": t.period,
                    "start_time": t.start_time,
                    "end_time": t.end_time,
                    "session": t.session,
                }
                for t in dataset["timeslots"]
            ],
            "rooms": [
                {
                    "id": r.id,
                    "name": r.name,
                    "capacity": r.capacity,
                    "room_type": getattr(r, "room_type", "NORMAL"),
                }
                for r in dataset["rooms"]
            ],
            "lecturers": [
                {
                    "id": l.id,
                    "name": l.name,
                    "available_timeslot_ids": (
                        sorted(list(l.available_timeslot_ids))
                        if l.available_timeslot_ids is not None
                        else None
                    ),
                }
                for l in dataset.get("lecturers", [])
            ],
            "student_groups": [
                {
                    "id": g.id,
                    "name": g.name,
                    "student_count": g.student_count,
                }
                for g in dataset.get("student_groups", [])
            ],
            "courses": [
                {
                    "course_id": c.course_id,
                    "name": c.name,
                    "credits": getattr(c, "credits", 3),
                    "is_difficult": getattr(c, "is_difficult", False),
                }
                for c in dataset.get("courses", [])
            ],
            "course_sections": [
                {
                    "section_id": s.section_id,
                    "course_id": s.course_id,
                    "course_name": s.course_name,
                    "lecturer_id": s.lecturer_id,
                    "group_id": s.group_id,
                    "student_count": s.student_count,
                    "is_difficult": getattr(s, "is_difficult", False),
                    "required_room_type": getattr(s, "required_room_type", "NORMAL"),
                    "duration_periods": getattr(s, "duration_periods", 1),
                }
                for s in dataset["course_sections"]
            ],
        }

        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

        return os.path.abspath(output_path)

    @classmethod
    def load_normalized_json(cls, json_path: str = "outputs/datasets/01_data_timetable.normalized.json") -> dict:
        """Deserialize dataset dictionary from normalized JSON snapshot file."""
        if not os.path.exists(json_path):
            raise FileNotFoundError(f"JSON snapshot file not found: '{json_path}'")

        with open(json_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        timeslots = [Timeslot(**t) for t in data["timeslots"]]
        rooms = [Room(**r) for r in data["rooms"]]
        lecturers = [
            Lecturer(
                id=l["id"],
                name=l["name"],
                available_timeslot_ids=(
                    frozenset(l["available_timeslot_ids"])
                    if l["available_timeslot_ids"] is not None
                    else None
                ),
            )
            for l in data["lecturers"]
        ]
        student_groups = [StudentGroup(**g) for g in data["student_groups"]]
        courses = [Course(**c) for c in data.get("courses", [])]
        course_sections = [CourseSection(**s) for s in data["course_sections"]]

        dataset = {
            "timeslots": timeslots,
            "rooms": rooms,
            "lecturers": lecturers,
            "student_groups": student_groups,
            "courses": courses,
            "course_sections": course_sections,
        }
        DatasetValidator.validate(dataset)
        return dataset

    @classmethod
    def analyze_excel_dataset(cls, dataset: dict) -> dict:
        """Compute detailed statistics report of Excel dataset entities and constraint tightness."""
        sections = dataset["course_sections"]
        lecturers = dataset["lecturers"]
        groups = dataset["student_groups"]
        rooms = dataset["rooms"]
        timeslots = dataset["timeslots"]

        # Duration distribution
        dur_dist = {2: 0, 3: 0, 4: 0}
        lab_count = 0
        for s in sections:
            dur = getattr(s, "duration_periods", 1)
            dur_dist[dur] = dur_dist.get(dur, 0) + 1
            if getattr(s, "required_room_type", "NORMAL") == "LAB":
                lab_count += 1

        # Teaching load per lecturer (sections & total periods)
        lec_load = {}
        for l in lecturers:
            l_secs = [s for s in sections if s.lecturer_id == l.id]
            total_p = sum(getattr(s, "duration_periods", 1) for s in l_secs)
            lec_load[l.id] = {"name": l.name, "sections": len(l_secs), "total_periods": total_p}

        # Study load per student group
        grp_load = {}
        for g in groups:
            g_secs = [s for s in sections if s.group_id == g.id]
            total_p = sum(getattr(s, "duration_periods", 1) for s in g_secs)
            grp_load[g.id] = {"name": g.name, "sections": len(g_secs), "total_periods": total_p}

        # Candidate count min / max / mean
        from .timeslot_factory import get_occupied_periods, is_valid_period_block
        from collections import defaultdict
        day_period_to_ts_id = {(ts.day, ts.period): ts.id for ts in timeslots}
        day_available_periods = defaultdict(set)
        for ts in timeslots:
            day_available_periods[ts.day].add(ts.period)

        cand_counts = []
        for s in sections:
            dur = getattr(s, "duration_periods", 1)
            req_type = getattr(s, "required_room_type", "NORMAL")
            valid_rms = [r for r in rooms if r.capacity >= s.student_count and getattr(r, "room_type", "NORMAL") == req_type]

            lec = next((l for l in lecturers if l.id == s.lecturer_id), None)
            avail_ts = lec.available_timeslot_ids if lec else None

            valid_ts = [
                t for t in timeslots
                if is_valid_period_block(t.period, dur, day_available_periods.get(t.day))
                and (avail_ts is None or all(day_period_to_ts_id.get((t.day, p)) in avail_ts for p in get_occupied_periods(t.period, dur)))
            ]

            cand_counts.append(len(valid_rms) * len(valid_ts))

        mean_cand = sum(cand_counts) / len(cand_counts) if cand_counts else 0.0

        return {
            "duration_distribution": dur_dist,
            "lab_section_count": lab_count,
            "lecturer_load": lec_load,
            "group_load": grp_load,
            "candidate_counts": {
                "min": min(cand_counts) if cand_counts else 0,
                "max": max(cand_counts) if cand_counts else 0,
                "mean": round(mean_cand, 2),
            },
        }
