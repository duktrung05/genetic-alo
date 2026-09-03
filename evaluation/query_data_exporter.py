"""Module xuất dữ liệu thời khóa biểu cho dịch vụ tra cứu.

Xuất thời khóa biểu sản phẩm chính thức sang cấu trúc JSON phục vụ
cho trợ lý tra cứu lịch học theo ngôn ngữ tự nhiên.
"""

import json
import os
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Union

from domain import Schedule, expand_scheduling_activities
from dataset import get_occupied_periods
from constraints import ConstraintEvaluator, SoftConstraintConfig


DAY_ORDER = {
    "Thứ 2": 1, "Monday": 1,
    "Thứ 3": 2, "Tuesday": 2,
    "Thứ 4": 3, "Wednesday": 3,
    "Thứ 5": 4, "Thursday": 4,
    "Thứ 6": 5, "Friday": 5,
    "Thứ 7": 6, "Saturday": 6,
    "Chủ nhật": 7, "Sunday": 7,
}


def export_schedule_query_data(
    schedule: Schedule,
    dataset: dict,
    output_path: Union[str, Path] = "outputs/production/schedule_query_data.json",
    hard_violations: int = 0,
    soft_penalty: float = 0.0,
    metadata: Optional[dict] = None,
    soft_config: Optional[SoftConstraintConfig] = None,
) -> str:
    """Xuất danh sách phân công lịch học sang định dạng JSON cho trợ lý tra cứu."""

    if hard_violations > 0:
        raise ValueError(f"Cannot export query data for infeasible schedule with {hard_violations} hard violations.")

    if schedule is None or not hasattr(schedule, "genes") or not isinstance(schedule.genes, list) or len(schedule.genes) == 0:
        raise ValueError("Cannot export empty or invalid schedule.")

    if not isinstance(dataset, dict) or "course_sections" not in dataset:
        raise ValueError("Invalid dataset supplied to exporter.")

    activities = expand_scheduling_activities(dataset["course_sections"])
    section_map = {activity.activity_id: activity for activity in activities}
    room_map = {r.id: r for r in dataset["rooms"]}
    timeslot_map = {t.id: t for t in dataset["timeslots"]}
    lecturer_map = {l.id: l for l in dataset.get("lecturers", [])}
    group_map = {g.id: g for g in dataset.get("student_groups", [])}
    course_map = {c.course_id: c for c in dataset.get("courses", [])}

    # Ánh xạ (ngày, tiết) -> Timeslot để tra cứu end_time nhanh
    day_period_map = {(ts.day, ts.period): ts for ts in timeslot_map.values()}

    assignments: List[dict] = []

    for gene in schedule.genes:
        sec = section_map.get(gene.section_id)
        room = room_map.get(gene.room_id)
        ts = timeslot_map.get(gene.timeslot_id)

        if not sec or not ts:
            continue

        duration = getattr(sec, "duration_periods", 1)
        start_period = ts.period
        end_period = start_period + duration - 1
        occupied_p = get_occupied_periods(start_period, duration)

        # Tính thời gian kết thúc
        end_ts = day_period_map.get((ts.day, end_period), ts)
        end_time_str = end_ts.end_time if end_ts else ts.end_time

        lec = lecturer_map.get(sec.lecturer_id)
        lec_name = lec.name if lec else sec.lecturer_id

        grp = group_map.get(sec.group_id)
        grp_name = grp.name if grp else sec.group_id

        rm_name = room.name if room else gene.room_id
        rm_type = getattr(room, "room_type", "NORMAL") if room else "NORMAL"
        campus_id = getattr(room, "campus_id", None) if room else None
        course = course_map.get(sec.course_id)

        record = {
            "activity_id": sec.activity_id,
            "section_id": sec.section_id,
            "meeting_index": sec.meeting_index,
            "meeting_count": sec.meeting_count,
            "meeting": f"{sec.meeting_index}/{sec.meeting_count}",
            "class_code": getattr(sec, "class_code", None),
            "course_id": sec.course_id,
            "course_code": getattr(course, "course_code", None),
            "course_name": sec.course_name,
            "duration_periods": duration,
            "student_group_id": sec.group_id,
            "student_group_name": grp_name,
            "student_count": sec.student_count,
            "lecturer_id": sec.lecturer_id,
            "lecturer_name": lec_name,
            "room_id": gene.room_id,
            "room_name": rm_name,
            "room_type": rm_type,
            "campus_id": campus_id,
            "day": ts.day,
            "day_key": ts.day.lower(),
            "start_period": start_period,
            "end_period": end_period,
            "start_time": ts.start_time,
            "end_time": end_time_str,
            "session": ts.session,
            "occupied_periods": occupied_p,
        }
        assignments.append(record)

    # Sắp xếp phân công ổn định theo ngày, start_period, room_name, section_id
    assignments.sort(
        key=lambda a: (
            DAY_ORDER.get(a["day"], 99),
            a["start_period"],
            a["room_name"],
            a["section_id"],
        )
    )

    out_file = Path(output_path)
    out_file.parent.mkdir(parents=True, exist_ok=True)

    meta_dict = {
        "generated_at": datetime.now().isoformat(),
        "total_assignments": len(assignments),
        "hard_violations": hard_violations,
        "soft_penalty": soft_penalty,
    }
    if metadata and isinstance(metadata, dict):
        meta_dict.update({k: v for k, v in metadata.items() if k not in meta_dict})
    effective_soft_config = (
        soft_config
        if soft_config is not None
        else ConstraintEvaluator(dataset).soft_checker.config
    )
    meta_dict["effective_soft_constraints"] = effective_soft_config.to_metadata()

    data = {
        "meta": meta_dict,
        "assignments": assignments,
    }

    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    return str(out_file.resolve())
