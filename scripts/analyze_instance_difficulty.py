"""Reproducible structural analysis and small sanity run for timetable instances."""

from __future__ import annotations

import argparse
import hashlib
import json
import statistics
import subprocess
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from dataset import ExcelDatasetLoader, DatasetValidator, get_occupied_periods, is_valid_period_block
from domain import expand_scheduling_activities
from evaluation.method_registry import METHOD_RUNNERS


DEFAULT_INSTANCE = ROOT / "data" / "instances" / "instance_easy.xlsx"
DEFAULT_JSON = ROOT / "outputs" / "dataset_analysis" / "instance_easy_metrics.json"
DEFAULT_REPORT = ROOT / "outputs" / "dataset_analysis" / "instance_easy_report.md"
DEFAULT_SEEDS = (0, 1, 2)
BASELINE_CONFIG = {
    "pop_size": 60,
    "generations": 100,
    "crossover_rate": 0.8,
    "mutation_rate": 0.2,
    "hard_weight": 1000,
    "soft_weight": 1,
    "soft_local_search_max_passes": 2,
    "soft_local_search_max_candidate_checks": 5000,
}
BASELINE_BUDGET = 1000
BASELINE_METHODS = ("ga", "ga_repair", "ga_repair_sls")


def _summary(values: Iterable[float], *, include_min: bool = True) -> dict[str, float]:
    data = list(values)
    result = {
        "mean": statistics.fmean(data) if data else 0.0,
        "median": statistics.median(data) if data else 0.0,
        "max": max(data) if data else 0.0,
    }
    if include_min:
        result["min"] = min(data) if data else 0.0
    return result


def _percentile(values: list[int], percentile: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    position = (len(ordered) - 1) * percentile
    lower = int(position)
    upper = min(lower + 1, len(ordered) - 1)
    fraction = position - lower
    return ordered[lower] + (ordered[upper] - ordered[lower]) * fraction


def _pair_count(counts: Counter[str]) -> int:
    return sum(count * (count - 1) // 2 for count in counts.values())


def analyze_dataset(dataset: dict) -> dict[str, Any]:
    """Return deterministic difficulty metrics without running an optimizer."""
    DatasetValidator.validate(dataset)
    sections = dataset["course_sections"]
    activities = expand_scheduling_activities(sections)
    rooms = dataset["rooms"]
    timeslots = dataset["timeslots"]
    lecturers = dataset.get("lecturers", [])
    groups = dataset.get("student_groups", [])
    teaching_days = sorted({slot.day for slot in timeslots})
    day_periods: dict[str, set[int]] = defaultdict(set)
    day_period_to_id = {}
    for slot in timeslots:
        day_periods[slot.day].add(slot.period)
        day_period_to_id[(slot.day, slot.period)] = slot.id

    total_demand = sum(activity.duration_periods for activity in activities)
    room_supply = len(rooms) * len(timeslots)
    lab_activities = [a for a in activities if a.required_room_type == "LAB"]
    lab_rooms = [room for room in rooms if room.room_type == "LAB"]
    lab_demand = sum(activity.duration_periods for activity in lab_activities)
    lab_supply = len(lab_rooms) * len(timeslots)

    lecturer_demand = Counter()
    group_demand = Counter()
    lecturer_activity_counts = Counter()
    group_activity_counts = Counter()
    for activity in activities:
        lecturer_demand[activity.lecturer_id] += activity.duration_periods
        group_demand[activity.group_id] += activity.duration_periods
        lecturer_activity_counts[activity.lecturer_id] += 1
        group_activity_counts[activity.group_id] += 1

    lecturer_rows = []
    unrestricted = 0
    for lecturer in lecturers:
        available = lecturer.available_timeslot_ids
        if available is None:
            unrestricted += 1
            available_periods = len(timeslots)
        else:
            available_periods = len(available)
        demand = lecturer_demand[lecturer.id]
        lecturer_rows.append({
            "lecturer_id": lecturer.id,
            "demand_periods": demand,
            "available_periods": available_periods,
            "load_ratio": demand / available_periods if available_periods else None,
        })

    group_rows = []
    for group in groups:
        demand = group_demand[group.id]
        group_rows.append({
            "group_id": group.id,
            "required_activity_periods": demand,
            "available_teaching_periods": len(timeslots),
            "load_ratio": demand / len(timeslots) if timeslots else None,
        })

    lecturer_map = {lecturer.id: lecturer for lecturer in lecturers}
    domain_rows = []
    for activity in activities:
        lecturer = lecturer_map.get(activity.lecturer_id)
        availability = lecturer.available_timeslot_ids if lecturer else None
        valid_rooms = [
            room for room in rooms
            if room.room_type == activity.required_room_type
            and room.capacity >= activity.student_count
        ]
        valid_starts = []
        for slot in timeslots:
            occupied = get_occupied_periods(slot.period, activity.duration_periods)
            if not is_valid_period_block(
                slot.period, activity.duration_periods, day_periods[slot.day]
            ):
                continue
            occupied_ids = [day_period_to_id.get((slot.day, period)) for period in occupied]
            if availability is not None and not all(slot_id in availability for slot_id in occupied_ids):
                continue
            valid_starts.append(slot.id)
        domain_rows.append({
            "activity_id": activity.activity_id,
            "section_id": activity.section_id,
            "candidate_count": len(valid_rooms) * len(valid_starts),
        })

    domain_counts = [row["candidate_count"] for row in domain_rows]
    lecturer_ratios = [row["load_ratio"] for row in lecturer_rows if row["load_ratio"] is not None]
    group_ratios = [row["load_ratio"] for row in group_rows if row["load_ratio"] is not None]
    lecturer_counts = list(lecturer_activity_counts.values())
    group_counts = list(group_activity_counts.values())

    return {
        "dataset_counts": {
            "sections": len(sections),
            "activities": len(activities),
            "courses": len(dataset.get("courses", [])),
            "lecturers": len(lecturers),
            "student_groups": len(groups),
            "rooms": len(rooms),
            "timeslots": len(timeslots),
            "teaching_days": len(teaching_days),
        },
        "resource_pressure": {
            "total_activity_period_demand": total_demand,
            "total_room_period_capacity": room_supply,
            "room_utilization_ratio": total_demand / room_supply if room_supply else None,
            "lab_activity_period_demand": lab_demand,
            "lab_room_period_supply": lab_supply,
            "lab_utilization_ratio": lab_demand / lab_supply if lab_supply else None,
        },
        "lecturer_pressure": {
            "summary": _summary(lecturer_ratios),
            "unrestricted_count": unrestricted,
            "restricted_count": len(lecturers) - unrestricted,
            "per_lecturer": lecturer_rows,
        },
        "student_group_pressure": {
            "summary": _summary(group_ratios, include_min=False),
            "per_group": group_rows,
        },
        "candidate_domains": {
            "summary": {
                "min": min(domain_counts) if domain_counts else 0,
                "p25": _percentile(domain_counts, 0.25),
                "median": statistics.median(domain_counts) if domain_counts else 0,
                "p75": _percentile(domain_counts, 0.75),
                "max": max(domain_counts) if domain_counts else 0,
                "mean": statistics.fmean(domain_counts) if domain_counts else 0.0,
            },
            "activities_below_20": sum(value < 20 for value in domain_counts),
            "activities_below_50": sum(value < 50 for value in domain_counts),
            "activities_below_100": sum(value < 100 for value in domain_counts),
            "per_activity": domain_rows,
        },
        "conflict_pressure": {
            "activities_per_lecturer": _summary(lecturer_counts),
            "activities_per_student_group": _summary(group_counts),
            "activity_pairs_sharing_lecturer": _pair_count(lecturer_activity_counts),
            "activity_pairs_sharing_student_group": _pair_count(group_activity_counts),
        },
    }


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _git_commit() -> str:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
        ).strip()
    except (OSError, subprocess.CalledProcessError):
        return "unknown"


def run_baselines(dataset: dict, seeds: Iterable[int]) -> list[dict[str, Any]]:
    results = []
    for seed in seeds:
        for method in BASELINE_METHODS:
            result = METHOD_RUNNERS[method](dataset, BASELINE_CONFIG, BASELINE_BUDGET, seed)
            metrics = result["run_metrics"]
            results.append({
                "method": method,
                "seed": seed,
                "hard_feasible": metrics.feasible,
                "first_feasible_generation": metrics.first_feasible_generation,
                "first_feasible_evaluation": metrics.first_feasible_search_evaluation,
                "final_hard_violations": metrics.final_hard_violations,
                "final_soft_score": metrics.final_soft_penalty,
                "runtime_seconds": metrics.runtime_seconds,
            })
    return results


def build_report(payload: dict[str, Any]) -> str:
    metrics = payload["difficulty_metrics"]
    resource = metrics["resource_pressure"]
    lecturer = metrics["lecturer_pressure"]
    group = metrics["student_group_pressure"]
    domains = metrics["candidate_domains"]
    conflict = metrics["conflict_pressure"]
    lines = [
        "# EASY Instance Difficulty Report", "",
        "**Difficulty classification: EASY**", "",
        "## Instance identity", "",
        f"- SHA-256: `{payload['checksum_sha256']}`",
        f"- Sections / activities: {payload['dataset_counts']['sections']} / {payload['dataset_counts']['activities']}",
        f"- Rooms / timeslots / teaching days: {payload['dataset_counts']['rooms']} / {payload['dataset_counts']['timeslots']} / {payload['dataset_counts']['teaching_days']}",
        "", "## Structural evidence", "",
        f"- Room utilization: {resource['room_utilization_ratio']:.4%}",
        f"- LAB utilization: {resource['lab_utilization_ratio']:.4%}",
        f"- Lecturer load ratio (mean / median / max): {lecturer['summary']['mean']:.4f} / {lecturer['summary']['median']:.4f} / {lecturer['summary']['max']:.4f}",
        f"- Student-group load ratio (mean / median / max): {group['summary']['mean']:.4f} / {group['summary']['median']:.4f} / {group['summary']['max']:.4f}",
        f"- Candidate domain (min / median / mean / max): {domains['summary']['min']} / {domains['summary']['median']} / {domains['summary']['mean']:.2f} / {domains['summary']['max']}",
        f"- Activity pairs sharing lecturer / group: {conflict['activity_pairs_sharing_lecturer']} / {conflict['activity_pairs_sharing_student_group']}",
        "", "## Paired sanity experiment", "",
        f"Configuration: seeds {payload['seeds']}, population {payload['baseline_run_config']['pop_size']}, search budget {payload['baseline_run_config']['evaluation_budget']} per run.", "",
        "| Method | Seed | Feasible | First generation | First evaluation | Final hard | Final soft | Runtime (s) |",
        "|---|---:|:---:|---:|---:|---:|---:|---:|",
    ]
    for run in payload["baseline_results"]:
        lines.append(
            f"| {run['method']} | {run['seed']} | {str(run['hard_feasible']).lower()} | "
            f"{run['first_feasible_generation']} | {run['first_feasible_evaluation']} | "
            f"{run['final_hard_violations']} | {run['final_soft_score']:.6f} | {run['runtime_seconds']:.3f} |"
        )
    lines.extend([
        "", "## Classification rationale", "",
        "The EASY label is supported by the low aggregate room and LAB utilization, "
        "large individually legal activity domains, modest lecturer/group load ratios, "
        "and the observed feasibility timing in the paired sanity runs. This is a baseline "
        "classification, not a claim that every random schedule is feasible.", "",
        "## Metric definitions", "",
        "See `metric_definitions` in the JSON artifact for the exact reproducible definitions.", "",
    ])
    return "\n".join(lines)


def create_payload(instance_path: Path, *, seeds: Iterable[int], run_experiment: bool = True) -> dict[str, Any]:
    dataset = ExcelDatasetLoader.load_and_validate(str(instance_path))
    metrics = analyze_dataset(dataset)
    seed_list = list(seeds)
    config = dict(BASELINE_CONFIG)
    config["evaluation_budget"] = BASELINE_BUDGET
    return {
        "instance_name": "easy",
        "source_filename": "data/01_data_timetable.xlsx",
        "frozen_instance_filename": str(instance_path.relative_to(ROOT)).replace("\\", "/"),
        "checksum_sha256": sha256_file(instance_path),
        "git_commit": _git_commit(),
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "metric_definitions": {
            "activity_demand": "Sum of duration_periods over expanded scheduling activities; duration is per meeting.",
            "room_period_supply": "Number of rooms multiplied by number of teaching timeslots.",
            "lab_supply": "Number of LAB rooms multiplied by number of teaching timeslots.",
            "lecturer_load_ratio": "Activity-period demand divided by available timeslot periods; unrestricted means every dataset timeslot.",
            "student_group_load_ratio": "Activity-period demand divided by all dataset teaching timeslots.",
            "candidate_domain": "Count of individually legal (room, start_timeslot) pairs satisfying room capacity/type, same-session consecutive duration fit, and lecturer availability; global conflicts excluded.",
            "shared_resource_pairs": "For each resource with n activities, n*(n-1)/2, summed across resources.",
        },
        "dataset_counts": metrics["dataset_counts"],
        "difficulty_metrics": metrics,
        "baseline_run_config": config,
        "seeds": seed_list,
        "baseline_results": run_baselines(dataset, seed_list) if run_experiment else [],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--instance", type=Path, default=DEFAULT_INSTANCE)
    parser.add_argument("--output-json", type=Path, default=DEFAULT_JSON)
    parser.add_argument("--output-report", type=Path, default=DEFAULT_REPORT)
    parser.add_argument("--skip-experiment", action="store_true")
    args = parser.parse_args()
    instance = args.instance.resolve()
    payload = create_payload(instance, seeds=DEFAULT_SEEDS, run_experiment=not args.skip_experiment)
    args.output_json.parent.mkdir(parents=True, exist_ok=True)
    args.output_report.parent.mkdir(parents=True, exist_ok=True)
    args.output_json.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    args.output_report.write_text(build_report(payload), encoding="utf-8")
    print(f"Wrote {args.output_json}")
    print(f"Wrote {args.output_report}")


if __name__ == "__main__":
    main()
