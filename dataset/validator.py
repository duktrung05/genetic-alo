from collections import defaultdict
from typing import Dict, Set, List, Tuple, Any
from domain import CourseSection, Room, Timeslot, Lecturer, StudentGroup
from .timeslot_factory import get_occupied_periods, is_valid_period_block

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
        for ts in timeslots:
            if ts.id in ts_ids:
                errors.append(f"Duplicate timeslot ID found: '{ts.id}'.")
            ts_ids.add(ts.id)

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
            if duration < 1:
                errors.append(f"Section '{sec.section_id}' has invalid duration_periods {duration} (must be >= 1).")
                continue

            if sec.lecturer_id:
                lec_required_periods[sec.lecturer_id] += duration
            if sec.group_id:
                grp_required_periods[sec.group_id] += duration

            req_type = getattr(sec, "required_room_type", "NORMAL")
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

            # Valid start timeslot block check
            valid_start_ts = [
                t for t in timeslots
                if is_valid_period_block(t.period, duration, day_available_periods.get(t.day))
            ]
            if not valid_start_ts:
                errors.append(f"No valid timeslot block of duration {duration} available for section '{sec.section_id}'.")

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
            req = lec_required_periods[lec.id]
            avail_count = len(lec.available_timeslot_ids) if lec.available_timeslot_ids is not None else total_timeslots
            if req > avail_count:
                errors.append(f"Lecturer '{lec.id}' required periods ({req}) exceeds available periods ({avail_count}).")
            elif req > 0.75 * avail_count:
                warnings.append(f"Lecturer '{lec.id}' load is near capacity ({req}/{avail_count} periods).")

        # Check total student group load vs total timeslots
        for grp in groups:
            req = grp_required_periods[grp.id]
            if req > total_timeslots:
                errors.append(f"StudentGroup '{grp.id}' required periods ({req}) exceeds total available timeslots ({total_timeslots}).")
            elif req > 0.75 * total_timeslots:
                warnings.append(f"StudentGroup '{grp.id}' load is high ({req}/{total_timeslots} periods).")

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
