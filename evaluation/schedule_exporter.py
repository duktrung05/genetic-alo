import csv
import json
from pathlib import Path
from typing import Dict, List, Optional, Any, Union
from domain import Schedule
from constraints import ConstraintEvaluator

CSV_HEADERS = [
    "Day",
    "Period",
    "Timeslot ID",
    "Section ID",
    "Course ID",
    "Course Name",
    "Lecturer ID",
    "Lecturer Name",
    "Student Group ID",
    "Student Group Name",
    "Student Count",
    "Room ID",
    "Room Name",
    "Room Capacity",
    "Room Type",
    "Required Room Type",
    "Is Difficult",
]

def export_schedule_to_csv(
    schedule: Schedule,
    dataset: dict,
    output_path: Union[str, Path],
    metadata: Optional[dict] = None,
) -> str:
    """Validate and export best schedule to CSV format sorted by Day, Period, Room ID, Section ID."""
    if schedule is None or not hasattr(schedule, "genes") or not isinstance(schedule.genes, list) or len(schedule.genes) == 0:
        raise ValueError("Cannot export empty or invalid schedule.")

    if not isinstance(dataset, dict) or "course_sections" not in dataset:
        raise ValueError("Invalid dataset supplied to exporter.")

    section_map = {s.section_id: s for s in dataset["course_sections"]}
    room_map = {r.id: r for r in dataset["rooms"]}
    timeslot_map = {t.id: t for t in dataset["timeslots"]}
    lecturer_map = {l.id: l for l in dataset.get("lecturers", [])}
    group_map = {g.id: g for g in dataset.get("student_groups", [])}

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

    rows: List[dict] = []
    for gene in genes:
        sec = section_map[gene.section_id]
        room = room_map[gene.room_id]
        ts = timeslot_map[gene.timeslot_id]
        lec = lecturer_map.get(sec.lecturer_id)
        grp = group_map.get(sec.group_id)

        row = {
            "Day": ts.day,
            "Period": ts.period,
            "Timeslot ID": ts.id,
            "Section ID": sec.section_id,
            "Course ID": getattr(sec, "course_id", ""),
            "Course Name": getattr(sec, "course_name", ""),
            "Lecturer ID": getattr(sec, "lecturer_id", ""),
            "Lecturer Name": lec.name if lec else getattr(sec, "lecturer_id", ""),
            "Student Group ID": getattr(sec, "group_id", ""),
            "Student Group Name": grp.name if grp else getattr(sec, "group_id", ""),
            "Student Count": getattr(sec, "student_count", getattr(grp, "student_count", 0)),
            "Room ID": room.id,
            "Room Name": getattr(room, "name", room.id),
            "Room Capacity": room.capacity,
            "Room Type": getattr(room, "room_type", "NORMAL"),
            "Required Room Type": getattr(sec, "required_room_type", "NORMAL"),
            "Is Difficult": getattr(sec, "is_difficult", False),
        }
        rows.append(row)

    # Sort rows by Day (natural order), Period, Room ID, Section ID
    rows.sort(
        key=lambda r: (
            day_order.get(r["Day"], 999),
            r["Period"],
            str(r["Room ID"]),
            str(r["Section ID"]),
        )
    )

    out_file = Path(output_path)
    out_file.parent.mkdir(parents=True, exist_ok=True)

    with open(out_file, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_HEADERS)
        writer.writeheader()
        writer.writerows(rows)

    return str(out_file)

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
