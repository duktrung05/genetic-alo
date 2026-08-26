from collections import defaultdict
from datetime import time
from typing import Dict, Set, List, Tuple, Any
from domain import Campus, Course, CourseSection, Room, Timeslot, Lecturer, StudentGroup
from .timeslot_factory import get_occupied_periods, is_valid_period_block

VALID_SHIFTS = frozenset({"morning", "afternoon", "evening"})
VALID_ROOM_TYPES = frozenset({"NORMAL", "LAB"})


def _valid_hhmm(value: object) -> bool:
    if not isinstance(value, str):
        return False
    try:
        time.fromisoformat(value)
        return True
    except ValueError:
        return False

class DatasetValidator:
    @staticmethod
    def validate_report(dataset: dict) -> Dict[str, Any]:
        errors: List[str] = []
        warnings: List[str] = []
        
        if not isinstance(dataset, dict):
            return {
                "valid": False,
                "errors": ["Dataset must be a dictionary."],
                "warnings": [],
                "statistics": {}
            }

        sections: List[CourseSection] = dataset.get("course_sections", [])
        rooms: List[Room] = dataset.get("rooms", [])
        timeslots: List[Timeslot] = dataset.get("timeslots", [])
        lecturers: List[Lecturer] = dataset.get("lecturers", [])
        groups: List[StudentGroup] = dataset.get("student_groups", [])
        courses: List[Course] = dataset.get("courses", [])
        campuses: List[Campus] = dataset.get("campuses", [])

        if not sections:
            errors.append("Dataset must contain course_sections.")
        if not rooms:
            errors.append("Dataset must contain rooms.")
        if not timeslots:
            errors.append("Dataset must contain timeslots.")

        if errors:
            return {
                "valid": False,
                "errors": errors,
                "warnings": warnings,
                "statistics": {}
            }

        # 1. Duplicate IDs
        sec_ids = set()
        for sec in sections:
            if sec.section_id in sec_ids:
                errors.append(f"Duplicate section ID found: '{sec.section_id}'.")
            sec_ids.add(sec.section_id)

        lec_ids = set()
        for lec in lecturers:
            if lec.id in lec_ids:
                errors.append(f"Duplicate lecturer ID found: '{lec.id}'.")
            lec_ids.add(lec.id)

        room_ids = set()
        for room in rooms:
            if room.id in room_ids:
                errors.append(f"Duplicate room ID found: '{room.id}'.")
            room_ids.add(room.id)

        grp_ids = set()
        for grp in groups:
            if grp.id in grp_ids:
                errors.append(f"Duplicate student group ID found: '{grp.id}'.")
            grp_ids.add(grp.id)

        ts_ids = set()
        ts_external_ids = set()
        day_periods = set()
        for ts in timeslots:
            if ts.id in ts_ids:
                errors.append(f"Duplicate timeslot ID found: '{ts.id}'.")
            ts_ids.add(ts.id)
            external_id = getattr(ts, "external_id", None)
            if external_id:
                if external_id in ts_external_ids:
                    errors.append(f"Duplicate external timeslot ID found: '{external_id}'.")
                ts_external_ids.add(external_id)
            day_period = (ts.day, ts.period)
            if day_period in day_periods:
                errors.append(f"Duplicate timeslot day/period found: {day_period!r}.")
            day_periods.add(day_period)
            if not isinstance(ts.period, int) or isinstance(ts.period, bool) or ts.period < 1:
                errors.append(f"Timeslot '{ts.id}' has invalid period '{ts.period}'.")
            if ts.session not in VALID_SHIFTS:
                errors.append(f"Timeslot '{ts.id}' has invalid session '{ts.session}'.")
            if not _valid_hhmm(ts.start_time) or not _valid_hhmm(ts.end_time):
                errors.append(f"Timeslot '{ts.id}' has invalid start/end time.")
            elif time.fromisoformat(ts.start_time) >= time.fromisoformat(ts.end_time):
                errors.append(f"Timeslot '{ts.id}' must have start_time before end_time.")

        course_ids = set()
        course_codes = set()
        for course in courses:
            if course.course_id in course_ids:
                errors.append(f"Duplicate course ID found: '{course.course_id}'.")
            course_ids.add(course.course_id)
            code = getattr(course, "course_code", None)
            if code:
                if code in course_codes:
                    errors.append(f"Duplicate course_code found: '{code}'.")
                course_codes.add(code)

        class_codes = set()
        for sec in sections:
            code = getattr(sec, "class_code", None)
            if code:
                if code in class_codes:
                    errors.append(f"Duplicate class_code found: '{code}'.")
                class_codes.add(code)

        campus_ids = set()
        for campus in campuses:
            if campus.id in campus_ids:
                errors.append(f"Duplicate campus ID found: '{campus.id}'.")
            campus_ids.add(campus.id)

        # 2. Foreign keys
        lecturer_map = {l.id: l for l in lecturers} if "lecturers" in dataset and lecturers else {}
        if "lecturers" in dataset and lecturers:
            for sec in sections:
                if sec.lecturer_id and sec.lecturer_id not in lecturer_map:
                    errors.append(f"Section '{sec.section_id}' references non-existent lecturer_id '{sec.lecturer_id}'.")

        group_map = {g.id: g for g in groups} if "student_groups" in dataset and groups else {}
        if "student_groups" in dataset and groups:
            for sec in sections:
                if sec.group_id and sec.group_id not in group_map:
                    errors.append(f"Section '{sec.section_id}' references non-existent group_id '{sec.group_id}'.")

        if "courses" in dataset and courses:
            for sec in sections:
                if sec.course_id not in course_ids:
                    errors.append(f"Section '{sec.section_id}' references non-existent course_id '{sec.course_id}'.")

        # CAMPUSES is authoritative when present. Legacy programmatic datasets
        # without a campus master remain supported, but Excel/normalized JSON
        # always provide this key.
        if "campuses" in dataset:
            for room in rooms:
                if room.campus_id is not None and room.campus_id not in campus_ids:
                    errors.append(f"Room '{room.id}' references unknown campus_id='{room.campus_id}'.")

        # Maps for period validation
        day_available_periods: Dict[str, Set[int]] = defaultdict(set)
        day_period_to_ts_id: Dict[Tuple[str, int], int] = {}
        for ts in timeslots:
            day_available_periods[ts.day].add(ts.period)
            day_period_to_ts_id[(ts.day, ts.period)] = ts.id

        total_timeslots = len(timeslots)

        # Lecturer & Group required periods tracking
        lec_required_periods: Dict[str, int] = defaultdict(int)
        grp_required_periods: Dict[str, int] = defaultdict(int)
        lab_required_periods = 0

        # Section validations
        for sec in sections:
            duration = getattr(sec, "duration_periods", 1)
            if not isinstance(duration, int) or isinstance(duration, bool) or duration < 1:
                errors.append(f"Section '{sec.section_id}' has invalid duration_periods {duration} (must be >= 1).")
                continue

            meetings = getattr(sec, "meetings_per_week", 1)
            if not isinstance(meetings, int) or isinstance(meetings, bool) or meetings < 1:
                errors.append(f"Section '{sec.section_id}' has invalid meetings_per_week {meetings} (must be >= 1).")
            elif meetings > 1:
                errors.append(
                    f"Section '{sec.section_id}' has meetings_per_week={meetings}. "
                    "meetings_per_week > 1 is not supported by the current chromosome."
                )

            if not isinstance(sec.student_count, int) or isinstance(sec.student_count, bool) or sec.student_count < 1:
                errors.append(f"Section '{sec.section_id}' has invalid student_count {sec.student_count}.")

            pref_shift = getattr(sec, "preferred_shift", None)
            if pref_shift is not None and pref_shift not in VALID_SHIFTS:
                errors.append(
                    f"Section '{sec.section_id}' has invalid preferred_shift='{pref_shift}'. "
                    f"Allowed values: {sorted(VALID_SHIFTS)}."
                )

            pref_campus = getattr(sec, "preferred_campus_id", None)
            if "campuses" in dataset and pref_campus is not None and pref_campus not in campus_ids:
                errors.append(
                    f"Section '{sec.section_id}' references unknown preferred_campus_id='{pref_campus}'. "
                    f"Known campuses: {sorted(campus_ids)}."
                )

            if sec.lecturer_id:
                lec_required_periods[sec.lecturer_id] += duration
            if sec.group_id:
                grp_required_periods[sec.group_id] += duration

            req_type = getattr(sec, "required_room_type", "NORMAL")
            if req_type not in VALID_ROOM_TYPES:
                errors.append(f"Section '{sec.section_id}' has invalid required_room_type='{req_type}'.")
            if req_type == "LAB":
                lab_required_periods += duration

            # Room availability check
            matching_rooms = [
                r for r in rooms
                if getattr(r, "room_type", "NORMAL") == req_type and r.capacity >= sec.student_count
            ]
            if not matching_rooms:
                if req_type == "LAB":
                    errors.append(f"Section '{sec.section_id}' requires LAB room with capacity >= {sec.student_count}, but no suitable LAB room exists.")
                else:
                    errors.append(f"Section '{sec.section_id}' requires NORMAL room with capacity >= {sec.student_count}, but no suitable room exists.")

            # Valid start timeslot block check (require_same_session=True enforced by default)
            valid_start_ts = [
                t for t in timeslots
                if is_valid_period_block(t.period, duration, day_available_periods.get(t.day))
            ]
            if not valid_start_ts:
                errors.append(
                    f"Section '{sec.section_id}' (duration_periods={duration}) has no valid "
                    f"timeslot block: all {duration} periods must be consecutive and within the "
                    f"same session (morning=1-6, afternoon=7-12, evening=13-16)."
                )

            # Lecturer availability block check
            if sec.lecturer_id:
                lec = lecturer_map.get(sec.lecturer_id)
                avail_ts = getattr(lec, "available_timeslot_ids", None) if lec else None
                if avail_ts is not None:
                    valid_lec_ts = [
                        t for t in valid_start_ts
                        if all(day_period_to_ts_id.get((t.day, p)) in avail_ts for p in get_occupied_periods(t.period, duration))
                    ]
                    if not valid_lec_ts:
                        errors.append(f"Lecturer '{sec.lecturer_id}' assigned to section '{sec.section_id}' has no available timeslot block of duration {duration}.")

        # Check total lecturer load vs available periods
        for lec in lecturers:
            if lec.available_timeslot_ids is not None:
                unknown_ids = set(lec.available_timeslot_ids) - ts_ids
                if unknown_ids:
                    errors.append(f"Lecturer '{lec.id}' availability references unknown timeslot IDs: {sorted(unknown_ids)}.")
            req = lec_required_periods[lec.id]
            avail_count = len(lec.available_timeslot_ids) if lec.available_timeslot_ids is not None else total_timeslots
            if req > avail_count:
                errors.append(f"Lecturer '{lec.id}' required periods ({req}) exceeds available periods ({avail_count}).")
            elif req > 0.75 * avail_count:
                warnings.append(f"Lecturer '{lec.id}' load is near capacity ({req}/{avail_count} periods).")

        # Check total student group load vs total timeslots
        for grp in groups:
            if not isinstance(grp.student_count, int) or isinstance(grp.student_count, bool) or grp.student_count < 1:
                errors.append(f"StudentGroup '{grp.id}' has invalid student_count {grp.student_count}.")
            req = grp_required_periods[grp.id]
            if req > total_timeslots:
                errors.append(f"StudentGroup '{grp.id}' required periods ({req}) exceeds total available timeslots ({total_timeslots}).")
            elif req > 0.75 * total_timeslots:
                warnings.append(f"StudentGroup '{grp.id}' load is high ({req}/{total_timeslots} periods).")

            # Validate home_campus_id reference
            home_campus = getattr(grp, "home_campus_id", None)
            if "campuses" in dataset and home_campus is not None and home_campus not in campus_ids:
                errors.append(
                    f"StudentGroup '{grp.id}' references unknown home_campus_id='{home_campus}'. "
                    f"Known campuses: {sorted(campus_ids)}."
                )

        for room in rooms:
            if not isinstance(room.capacity, int) or isinstance(room.capacity, bool) or room.capacity < 1:
                errors.append(f"Room '{room.id}' has invalid capacity {room.capacity}.")
            if room.room_type not in VALID_ROOM_TYPES:
                errors.append(f"Room '{room.id}' has invalid room_type='{room.room_type}'.")

        # Check total LAB demand vs LAB room supply
        lab_rooms = [r for r in rooms if getattr(r, "room_type", "NORMAL") == "LAB"]
        total_lab_capacity_periods = len(lab_rooms) * total_timeslots
        if lab_required_periods > total_lab_capacity_periods:
            errors.append(f"Total LAB section period demand ({lab_required_periods}) exceeds total LAB room capacity ({total_lab_capacity_periods}).")

        statistics = {
            "sections": len(sections),
            "courses": len(dataset.get("courses", [])),
            "lecturers": len(lecturers),
            "student_groups": len(groups),
            "rooms": len(rooms),
            "campuses": len(campuses),
            "total_periods": total_timeslots,
        }

        return {
            "valid": len(errors) == 0,
            "errors": errors,
            "warnings": warnings,
            "statistics": statistics,
        }

    @staticmethod
    def validate(dataset: dict) -> None:
        report = DatasetValidator.validate_report(dataset)
        if not report["valid"]:
            raise ValueError(report["errors"][0])
