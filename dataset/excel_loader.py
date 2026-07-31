"""Excel Dataset Loader Module.

Parses and validates timetable scheduling dataset from Microsoft Excel workbook format (.xlsx).
"""

import os
import json
from typing import Dict, List, Set, Optional, Any
import openpyxl
from domain import Timeslot, Room, Lecturer, StudentGroup, Course, CourseSection
from .validator import DatasetValidator

class ExcelValidationError(ValueError):
    """Custom exception raised when Excel data fails validation rules with precise row/col context."""
    pass

class ExcelDatasetLoader:
    """Loader responsible for reading timetable scheduling entities from Excel workbooks."""

    SHIFT_MAP = {
        "Sáng": "morning",
        "Chiều": "afternoon",
        "Tối": "evening",
        "MORNING": "morning",
        "AFTERNOON": "afternoon",
        "EVENING": "evening",
    }

    IGNORED_SHEETS = {
        "README",
        "BASELINE_SCHEDULE",
        "BEST_SCHEDULE",
        "SCHEDULE_BY_GROUP",
        "SCHEDULE_BY_LECTURER",
        "SCHEDULE_BY_ROOM",
    }

    @classmethod
    def load(cls, excel_path: str = "data/01_data_timetable(1).xlsx") -> dict:
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

            room = Room(
                id=r_id,
                name=name,
                capacity=cap,
                room_type=r_type,
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

            grp = StudentGroup(
                id=g_id,
                name=g_name,
                student_count=size,
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
            )
            course_sections.append(sec)

        return {
            "timeslots": timeslots,
            "rooms": rooms,
            "lecturers": lecturers,
            "student_groups": student_groups,
            "courses": courses,
            "course_sections": course_sections,
        }

    @classmethod
    def load_and_validate(cls, excel_path: str = "data/01_data_timetable(1).xlsx") -> dict:
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
