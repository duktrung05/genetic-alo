import csv
import json
import datetime
from pathlib import Path
from typing import Dict, List, Optional, Any, Union, Tuple
import openpyxl
from openpyxl.styles import Font, Alignment, PatternFill
from openpyxl.utils import get_column_letter

from domain import Schedule
from constraints import ConstraintEvaluator

CSV_HEADERS = [
    "section_id",
    "course_id",
    "lecturer_id",
    "student_group_id",
    "room_id",
    "day",
    "start_period",
    "end_period",
    "start_time",
    "end_time",
    "duration_periods",
    "session",
    "room_type",
]

def export_schedule_to_csv(
    schedule: Schedule,
    dataset: dict,
    output_path: Union[str, Path],
    metadata: Optional[dict] = None,
) -> str:
    """Validate and export best schedule to CSV format sorted by Day, Start Period, Room ID."""
    if schedule is None or not hasattr(schedule, "genes") or not isinstance(schedule.genes, list) or len(schedule.genes) == 0:
        raise ValueError("Cannot export empty or invalid schedule.")

    if not isinstance(dataset, dict) or "course_sections" not in dataset:
        raise ValueError("Invalid dataset supplied to exporter.")

    section_map = {s.section_id: s for s in dataset["course_sections"]}
    room_map = {r.id: r for r in dataset["rooms"]}
    timeslot_map = {t.id: t for t in dataset["timeslots"]}

    genes = schedule.genes
    if len(genes) != len(section_map):
        raise ValueError(f"Gene count mismatch: expected {len(section_map)} sections, got {len(genes)} genes.")

    seen_section_ids = set()
    for gene in genes:
        sec_id = getattr(gene, "section_id", None)
        room_id = getattr(gene, "room_id", None)
        ts_id = getattr(gene, "timeslot_id", None)

        if sec_id not in section_map:
            raise ValueError(f"Invalid section ID in gene: {sec_id}")
        if sec_id in seen_section_ids:
            raise ValueError(f"Duplicate section ID found in schedule: {sec_id}")
        seen_section_ids.add(sec_id)

        if room_id not in room_map:
            raise ValueError(f"Invalid room ID in gene: {room_id}")
        if ts_id not in timeslot_map:
            raise ValueError(f"Invalid timeslot ID in gene: {ts_id}")

    if seen_section_ids != set(section_map.keys()):
        raise ValueError("Schedule is missing some course sections from dataset.")

    # Re-evaluate with ConstraintEvaluator
    evaluator = ConstraintEvaluator(dataset)
    _, hard_violations, _ = evaluator.calculate_fitness(schedule)
    if hard_violations > 0:
        raise ValueError(f"Cannot export schedule with hard violations (hard_violations={hard_violations}).")

    # Map day ordering based on timeslots in dataset

    day_order: Dict[str, int] = {}
    for ts in dataset["timeslots"]:
        if ts.day not in day_order:
            day_order[ts.day] = len(day_order)

    day_period_to_ts: Dict[Tuple[str, int], Any] = {
        (ts.day, ts.period): ts for ts in dataset["timeslots"]
    }

    rows: List[dict] = []
    for gene in genes:
        sec = section_map[gene.section_id]
        room = room_map[gene.room_id]
        start_ts = timeslot_map[gene.timeslot_id]

        duration = getattr(sec, "duration_periods", 1)
        start_period = start_ts.period
        end_period = start_period + duration - 1

        start_time = getattr(start_ts, "start_time", "")
        end_ts = day_period_to_ts.get((start_ts.day, end_period), start_ts)
        end_time = getattr(end_ts, "end_time", getattr(start_ts, "end_time", ""))

        session = getattr(start_ts, "session", "morning")
        room_type = getattr(room, "room_type", "NORMAL")

        row = {
            "section_id": sec.section_id,
            "course_id": getattr(sec, "course_id", ""),
            "lecturer_id": getattr(sec, "lecturer_id", ""),
            "student_group_id": getattr(sec, "group_id", ""),
            "room_id": room.id,
            "day": start_ts.day,
            "start_period": start_period,
            "end_period": end_period,
            "start_time": start_time,
            "end_time": end_time,
            "duration_periods": duration,
            "session": session,
            "room_type": room_type,
        }
        rows.append(row)

    rows.sort(
        key=lambda r: (
            day_order.get(r["day"], 999),
            r["start_period"],
            str(r["room_id"]),
        )
    )

    out_file = Path(output_path)
    out_file.parent.mkdir(parents=True, exist_ok=True)

    with open(out_file, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_HEADERS)
        writer.writeheader()
        writer.writerows(rows)

    return str(out_file)

def export_schedule_to_excel(
    schedule: Schedule,
    dataset: dict,
    output_path: Union[str, Path],
    metadata: Optional[dict] = None,
    allow_infeasible_export: bool = False,
) -> str:
    """Export schedule to a standardized 7-sheet Excel workbook.

    Sheets:
    1. SUMMARY
    2. RAW_ASSIGNMENTS
    3. SCHEDULE_BY_GROUP
    4. SCHEDULE_BY_LECTURER
    5. SCHEDULE_BY_ROOM
    6. VIOLATIONS
    7. RUN_CONFIG
    """
    out_path = Path(output_path)
    
    if schedule is None or not hasattr(schedule, "genes") or not isinstance(schedule.genes, list) or len(schedule.genes) == 0:
        raise ValueError("Cannot export empty or invalid schedule to Excel.")

    if not isinstance(dataset, dict) or "course_sections" not in dataset or "rooms" not in dataset or "timeslots" not in dataset:
        raise ValueError("Invalid dataset supplied to Excel exporter.")

    # Re-evaluate violations
    evaluator = ConstraintEvaluator(dataset)
    score, hard_violations, soft_penalty = evaluator.calculate_fitness(schedule)
    _, hard_details = evaluator.evaluate_hard(schedule)
    _, soft_details = evaluator.evaluate_soft(schedule)

    if hard_violations > 0:
        if not allow_infeasible_export:
            if out_path.exists():
                out_path.unlink()
            raise ValueError(f"Cannot export Excel schedule with hard violations (hard_violations={hard_violations}).")

        # Append _INFEASIBLE suffix if not present
        if "_INFEASIBLE" not in out_path.stem:
            out_path = out_path.parent / f"{out_path.stem}_INFEASIBLE.xlsx"

    meta = metadata or {}
    section_map = {s.section_id: s for s in dataset["course_sections"]}
    room_map = {r.id: r for r in dataset["rooms"]}
    timeslot_map = {t.id: t for t in dataset["timeslots"]}
    lecturer_map = {l.id: l for l in dataset.get("lecturers", [])}
    group_map = {g.id: g for g in dataset.get("student_groups", [])}
    course_map = {c.course_id: c for c in dataset.get("courses", [])}

    day_order: Dict[str, int] = {}
    for ts in dataset["timeslots"]:
        if ts.day not in day_order:
            day_order[ts.day] = len(day_order)

    day_period_to_ts: Dict[Tuple[str, int], Any] = {
        (ts.day, ts.period): ts for ts in dataset["timeslots"]
    }

    wb = openpyxl.Workbook()
    # Remove default sheet
    wb.remove(wb.active)

    bold_font = Font(bold=True, size=11)
    header_fill = PatternFill(start_color="D9E1F2", end_color="D9E1F2", fill_type="solid")

    def format_sheet(ws):
        ws.freeze_panes = "A2"
        if ws.max_row > 1 and ws.max_column > 0:
            ws.auto_filter.ref = f"A1:{get_column_letter(ws.max_column)}{ws.max_row}"
        for col in ws.columns:
            max_len = max(len(str(cell.value or "")) for cell in col)
            col_letter = get_column_letter(col[0].column)
            ws.column_dimensions[col_letter].width = max(max_len + 4, 12)
            for cell in col:
                cell.alignment = Alignment(wrap_text=True, vertical="top")
        for cell in ws[1]:
            cell.font = bold_font
            cell.fill = header_fill

    # --- 1. SHEET SUMMARY ---
    ws_sum = wb.create_sheet(title="SUMMARY")
    ws_sum.append(["Metric", "Value"])
    summary_rows = [
        ("dataset_source", meta.get("dataset_source", meta.get("dataset_preset", "Excel"))),
        ("dataset_path", meta.get("dataset_path", meta.get("input_file", "data/01_data_timetable(1).xlsx"))),
        ("dataset_name", meta.get("dataset_name", "01_data_timetable(1).xlsx")),
        ("dataset_version", meta.get("dataset_version", "1.0")),
        ("dataset_hash", meta.get("dataset_hash", "N/A")),
        ("input_file", meta.get("input_file", "data/01_data_timetable(1).xlsx")),
        ("normalized_json_path", meta.get("normalized_json_path", "outputs/datasets/01_data_timetable.normalized.json")),
        ("algorithm", meta.get("method", "Hybrid GA + Repair")),
        ("seed", meta.get("seed", 0)),
        ("population_size", meta.get("pop_size", 60)),
        ("generations", meta.get("generations", meta.get("generations_run", 80))),
        ("evaluation_budget", meta.get("evaluation_budget", 1000)),
        ("hard_violations", hard_violations),
        ("soft_penalty", soft_penalty),
        ("score", score),
        ("total_score", score),
        ("feasible", hard_violations == 0),
        ("is_feasible", hard_violations == 0),
        ("runtime", meta.get("runtime_seconds", 0.0)),
        ("runtime_seconds", meta.get("runtime_seconds", 0.0)),
        ("fitness_evaluations", meta.get("fitness_evaluations", 0)),
        ("generation_to_first_feasible", meta.get("generation_to_first_feasible", 0 if hard_violations == 0 else "N/A")),
        ("time_to_first_feasible", meta.get("time_to_first_feasible", 0.0 if hard_violations == 0 else "N/A")),
        ("repair_calls", meta.get("repair_calls", 0)),
        ("repair_successes", meta.get("repair_successes", 0)),
        ("repair_failures", meta.get("repair_failures", 0)),
        ("sections_repaired", meta.get("sections_repaired", 0)),
        ("repair_runtime_seconds", meta.get("repair_runtime_seconds", 0.0)),
        ("generated_at", datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")),
    ]
    for k, v in summary_rows:
        ws_sum.append([k, str(v)])
    format_sheet(ws_sum)

    # Prepare gene rows
    assignments = []
    for gene in schedule.genes:
        sec = section_map[gene.section_id]
        room = room_map[gene.room_id]
        start_ts = timeslot_map[gene.timeslot_id]
        dur = getattr(sec, "duration_periods", 1)
        start_p = start_ts.period
        end_p = start_p + dur - 1

        end_ts = day_period_to_ts.get((start_ts.day, end_p), start_ts)
        start_time = getattr(start_ts, "start_time", "07:00")
        end_time = getattr(end_ts, "end_time", "07:50")

        periods_str = f"Tiết {start_p}" if dur == 1 else f"Tiết {start_p}-{end_p}"
        time_range = f"{start_time}-{end_time}"

        lec = lecturer_map.get(sec.lecturer_id)
        grp = group_map.get(sec.group_id)
        crs = course_map.get(sec.course_id)

        assignments.append({
            "section_id": sec.section_id,
            "class_code": getattr(sec, "class_code", sec.section_id),
            "course_id": sec.course_id,
            "course_code": getattr(crs, "course_id", sec.course_id),
            "course_name": getattr(sec, "course_name", getattr(crs, "name", sec.course_id)),
            "student_group_id": sec.group_id,
            "student_group_name": getattr(grp, "name", sec.group_id),
            "lecturer_id": sec.lecturer_id,
            "lecturer_name": getattr(lec, "name", sec.lecturer_id),
            "student_count": sec.student_count,
            "room_id": room.id,
            "room_number": getattr(room, "name", room.id),
            "building": getattr(room, "name", "").split("-")[0] if "-" in getattr(room, "name", "") else "",
            "campus_id": getattr(room, "campus_id", "CS1"),
            "room_type": getattr(room, "room_type", "NORMAL"),
            "day_no": day_order.get(start_ts.day, 99),
            "day_name": start_ts.day,
            "start_period": start_p,
            "end_period": end_p,
            "duration_periods": dur,
            "periods": periods_str,
            "start_time": start_time,
            "end_time": end_time,
            "shift": getattr(start_ts, "session", "morning"),
            "required_room_type": getattr(sec, "required_room_type", "NORMAL"),
            "preferred_campus_id": getattr(sec, "preferred_campus_id", "CS1"),
            "preferred_shift": getattr(sec, "preferred_shift", "morning"),
            "time_range": time_range,
            "room_display": getattr(room, "name", room.id),
        })

    # --- 2. SHEET RAW_ASSIGNMENTS ---
    ws_raw = wb.create_sheet(title="RAW_ASSIGNMENTS")
    raw_cols = [
        "section_id", "class_code", "course_id", "course_code", "course_name",
        "student_group_id", "student_group_name", "lecturer_id", "lecturer_name",
        "student_count", "room_id", "room_number", "building", "campus_id",
        "room_type", "day_no", "day_name", "start_period", "end_period",
        "duration_periods", "periods", "start_time", "end_time", "shift",
        "required_room_type", "preferred_campus_id", "preferred_shift"
    ]
    ws_raw.append(raw_cols)

    # Sort raw assignments by section_id
    raw_sorted = sorted(assignments, key=lambda a: a["section_id"])
    for a in raw_sorted:
        ws_raw.append([a[c] for c in raw_cols])
    format_sheet(ws_raw)

    # --- 3. SHEET SCHEDULE_BY_GROUP ---
    ws_grp = wb.create_sheet(title="SCHEDULE_BY_GROUP")
    grp_cols = ["group_id", "group_name", "day_name", "periods", "time_range", "course_code", "course_name", "lecturer_name", "room_display", "campus_id"]
    ws_grp.append(grp_cols)
    grp_sorted = sorted(assignments, key=lambda a: (a["student_group_id"], a["day_no"], a["start_period"]))
    for a in grp_sorted:
        ws_grp.append([a["student_group_id"], a["student_group_name"], a["day_name"], a["periods"], a["time_range"], a["course_code"], a["course_name"], a["lecturer_name"], a["room_display"], a["campus_id"]])
    format_sheet(ws_grp)

    # --- 4. SHEET SCHEDULE_BY_LECTURER ---
    ws_lec = wb.create_sheet(title="SCHEDULE_BY_LECTURER")
    lec_cols = ["lecturer_id", "lecturer_name", "day_name", "periods", "time_range", "course_name", "student_group_name", "room_display", "campus_id"]
    ws_lec.append(lec_cols)
    lec_sorted = sorted(assignments, key=lambda a: (a["lecturer_id"], a["day_no"], a["start_period"]))
    for a in lec_sorted:
        ws_lec.append([a["lecturer_id"], a["lecturer_name"], a["day_name"], a["periods"], a["time_range"], a["course_name"], a["student_group_name"], a["room_display"], a["campus_id"]])
    format_sheet(ws_lec)

    # --- 5. SHEET SCHEDULE_BY_ROOM ---
    ws_rm = wb.create_sheet(title="SCHEDULE_BY_ROOM")
    rm_cols = ["room_id", "room_display", "campus_id", "day_name", "periods", "time_range", "course_name", "lecturer_name", "student_group_name"]
    ws_rm.append(rm_cols)
    rm_sorted = sorted(assignments, key=lambda a: (a["room_id"], a["day_no"], a["start_period"]))
    for a in rm_sorted:
        ws_rm.append([a["room_id"], a["room_display"], a["campus_id"], a["day_name"], a["periods"], a["time_range"], a["course_name"], a["lecturer_name"], a["student_group_name"]])
    format_sheet(ws_rm)

    # --- 6. SHEET VIOLATIONS ---
    ws_viol = wb.create_sheet(title="VIOLATIONS")
    viol_cols = ["violation_type", "severity", "section_ids", "lecturer_id", "student_group_ids", "room_id", "day", "periods", "description", "penalty"]
    ws_viol.append(viol_cols)

    if hard_violations == 0 and soft_penalty == 0:
        ws_viol.append(["INFO", "NONE", "-", "-", "-", "-", "-", "-", "No hard or soft violations detected", 0])
    elif hard_violations == 0:
        ws_viol.append(["INFO", "HARD", "-", "-", "-", "-", "-", "-", "No hard violations detected", 0])
        for k, v in soft_details.items():
            if v > 0:
                ws_viol.append(["SOFT", "LOW", "-", "-", "-", "-", "-", "-", f"Soft constraint penalty: {k}", v])
    else:
        for k, v in hard_details.items():
            if v > 0:
                ws_viol.append(["HARD", "HIGH", "-", "-", "-", "-", "-", "-", f"Hard constraint violation: {k}", v])
        for k, v in soft_details.items():
            if v > 0:
                ws_viol.append(["SOFT", "LOW", "-", "-", "-", "-", "-", "-", f"Soft constraint penalty: {k}", v])
    format_sheet(ws_viol)

    # --- 7. SHEET RUN_CONFIG ---
    ws_cfg = wb.create_sheet(title="RUN_CONFIG")
    ws_cfg.append(["Parameter", "Value"])
    cfg_rows = [
        ("population_size", meta.get("pop_size", 60)),
        ("generations", meta.get("generations", 80)),
        ("crossover_rate", meta.get("crossover_rate", 0.8)),
        ("mutation_rate", meta.get("mutation_rate", 0.2)),
        ("hard_weight", meta.get("hard_weight", 1000)),
        ("soft_weight", meta.get("soft_weight", 1)),
        ("afternoon_start_period", 7),
        ("student_gaps_weight", 5),
        ("consecutive_teaching_weight", 6),
        ("difficult_afternoon_weight", 3),
        ("daily_imbalance_weight", 8),
        ("repair_enabled", meta.get("use_repair", True)),
    ]
    for k, v in cfg_rows:
        ws_cfg.append([k, str(v)])
    format_sheet(ws_cfg)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    wb.save(out_path)
    return str(out_path)

def export_metadata_to_json(
    metadata: dict,
    output_path: Union[str, Path],
) -> str:
    """Export metadata dictionary to formatted JSON file."""
    out_file = Path(output_path)
    out_file.parent.mkdir(parents=True, exist_ok=True)

    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(metadata, f, ensure_ascii=False, indent=2)

    return str(out_file)
