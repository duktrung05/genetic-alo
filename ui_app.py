"""Stable Streamlit demo for frozen EASY and MEDIUM timetable instances."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

import pandas as pd
import streamlit as st

from constraints import ConstraintEvaluator, SoftConstraintConfig
from dataset import DatasetValidator, ExcelDatasetLoader
from domain import expand_scheduling_activities
from evaluation import export_schedule_query_data, export_schedule_to_csv, export_schedule_to_excel
from ga import GeneticAlgorithmEngine


ROOT = Path(__file__).resolve().parent
DEMO_OUTPUT_DIR = ROOT / "outputs" / "demo"
BENCHMARK_DIR = ROOT / "outputs" / "final_benchmark"
DATASET_OPTIONS = {
    "EASY": {
        "path": ROOT / "data" / "instances" / "instance_easy.xlsx",
        "description": "Recommended for live demo. Lower constraint pressure.",
    },
    "MEDIUM": {
        "path": ROOT / "data" / "instances" / "instance_medium.xlsx",
        "description": "Higher LAB and lecturer constraint pressure. Used mainly for robustness evaluation.",
    },
}
PRODUCTION_CONFIG = {
    "population_size": 60, "generations": 100, "evaluation_budget": 1000,
    "crossover_rate": 0.8, "mutation_rate": 0.2,
    "hard_weight": 1000, "soft_weight": 1,
    "soft_local_search_max_passes": 2,
    "soft_local_search_max_candidate_checks": 5000,
}
DAY_ORDER = {
    "Thứ 2": 1, "Monday": 1, "Thứ 3": 2, "Tuesday": 2,
    "Thứ 4": 3, "Wednesday": 3, "Thứ 5": 4, "Thursday": 4,
    "Thứ 6": 5, "Friday": 5, "Thứ 7": 6, "Saturday": 6,
    "Chủ nhật": 7, "Sunday": 7,
}
METHOD_DISPLAY_NAMES = {
    "repair_only": "Repair-only Random Restart", "ga": "GA without Repair",
    "ga_repair": "GA + Repair",
    "ga_repair_sls": "GA + Repair + SLS (Production)",
    "greedy": "Greedy Search", "random": "Random Search",
}
HARD_CONSTRAINT_LABELS = {
    "room_overlap": "Room conflict", "lecturer_overlap": "Lecturer conflict",
    "group_overlap": "Student-group conflict", "capacity_violation": "Room capacity",
    "room_type_mismatch": "Room type", "lecturer_unavailable": "Lecturer availability",
    "same_section_same_day": "Multi-meeting separation",
    "invalid_section_ids": "Activity identity", "invalid_room_ids": "Room reference",
    "invalid_timeslot_ids": "Timeslot and duration block",
    "invalid_lecturer_references": "Lecturer reference",
    "invalid_group_references": "Student-group reference",
    "gene_count_mismatch": "Activity count", "missing_sections": "Missing activities",
    "duplicate_sections": "Duplicate activities",
}
FILTER_FIELDS = {
    "Student Group": ("student_group_id", "student_group_name"),
    "Lecturer": ("lecturer_id", "lecturer_name"),
    "Room": ("room_id", "room_name"),
}


@dataclass
class DatasetLoadResult:
    name: str
    path: Path
    valid: bool
    dataset: Optional[dict]
    errors: list[str]
    warnings: list[str]
    counts: dict[str, int]


def get_method_display_name(metadata: Optional[dict]) -> str:
    metadata = metadata or {}
    method_id = str(metadata.get("primary_method", "")).strip().lower()
    if method_id in METHOD_DISPLAY_NAMES:
        return METHOD_DISPLAY_NAMES[method_id]
    raw_method = str(metadata.get("method", "")).strip()
    if metadata.get("soft_local_search_enabled") or "sls" in raw_method.lower():
        return METHOD_DISPLAY_NAMES["ga_repair_sls"]
    if method_id == "hybrid" or "hybrid" in raw_method.lower():
        return METHOD_DISPLAY_NAMES["ga_repair"]
    return raw_method or METHOD_DISPLAY_NAMES["ga_repair"]


def should_run_text_query(submitted: bool, query: str) -> bool:
    return bool(submitted and query.strip())


def load_production_data():
    """Backward-compatible reader for the former read-only presenter."""
    json_path = Path("outputs/production/schedule_query_data.json")
    meta_path = Path("outputs/production/best_timetable_metadata.json")
    if not json_path.exists():
        return None, None
    try:
        query_data = json.loads(json_path.read_text(encoding="utf-8"))
        meta = json.loads(meta_path.read_text(encoding="utf-8")) if meta_path.exists() else query_data.get("meta", {})
        return query_data, meta
    except (OSError, json.JSONDecodeError):
        return None, None


def sort_assignments(assignments: list[dict]) -> list[dict]:
    return sorted(assignments, key=lambda item: (
        DAY_ORDER.get(item.get("day", ""), 99), item.get("start_period", 1),
        item.get("room_name", ""), item.get("activity_id", item.get("section_id", "")),
    ))


def format_dataframe(assignments: list[dict]) -> pd.DataFrame:
    """Build a projection-friendly table using official course/class codes."""
    rows = []
    for item in sort_assignments(assignments):
        start, end = item.get("start_period", 1), item.get("end_period", item.get("start_period", 1))
        period = f"{start}" if start == end else f"{start}–{end}"
        start_time, end_time = item.get("start_time", ""), item.get("end_time", "")
        time = f"{start_time}–{end_time}" if start_time and end_time else ""
        rows.append({
            "Day": item.get("day", ""),
            "Period / Time": f"Period {period} · {time}".rstrip(" ·"),
            "Course code": item.get("course_code") or item.get("course_id", ""),
            "Course": item.get("course_name", ""),
            "Class code": item.get("class_code") or item.get("section_id", ""),
            "Meeting": f"{item.get('meeting_index', 1)}/{item.get('meeting_count', 1)}",
            "Room": item.get("room_name") or item.get("room_id", ""),
            "Lecturer": item.get("lecturer_name") or item.get("lecturer_id", ""),
            "Student group": item.get("student_group_name") or item.get("student_group_id", ""),
            "Campus": item.get("campus_id", ""),
        })
    return pd.DataFrame(rows)


def load_demo_dataset(dataset_name: str) -> DatasetLoadResult:
    """Load/validate a frozen workbook and convert failures into UI-safe data."""
    option = DATASET_OPTIONS.get(dataset_name)
    if option is None:
        return DatasetLoadResult(dataset_name, Path(), False, None, ["Unknown dataset selection."], [], {})
    path = Path(option["path"])
    if not path.exists():
        return DatasetLoadResult(dataset_name, path, False, None, [f"Dataset file not found: {path}"], [], {})
    try:
        dataset = ExcelDatasetLoader.load(str(path))
        report = DatasetValidator.validate_report(dataset)
        counts = {
            "sections": len(dataset.get("course_sections", [])),
            "activities": len(expand_scheduling_activities(dataset.get("course_sections", []))),
            "lecturers": len(dataset.get("lecturers", [])),
            "student_groups": len(dataset.get("student_groups", [])),
            "rooms": len(dataset.get("rooms", [])),
            "timeslots": len(dataset.get("timeslots", [])),
        }
        return DatasetLoadResult(
            dataset_name, path, bool(report["valid"]), dataset,
            list(report["errors"]), list(report["warnings"]), counts,
        )
    except Exception as error:
        return DatasetLoadResult(dataset_name, path, False, None, [str(error)], [], {})


@st.cache_data(show_spinner=False)
def cached_load_demo_dataset(dataset_name: str, file_mtime_ns: int) -> DatasetLoadResult:
    del file_mtime_ns
    return load_demo_dataset(dataset_name)


def run_demo_scheduler(dataset: dict, seed: int = 0, *, evaluation_budget: int = 1000) -> dict[str, Any]:
    """Run the frozen GA+Repair+SLS method and independently evaluate output."""
    engine = GeneticAlgorithmEngine(
        dataset, pop_size=PRODUCTION_CONFIG["population_size"],
        hard_weight=PRODUCTION_CONFIG["hard_weight"], soft_weight=PRODUCTION_CONFIG["soft_weight"], seed=seed,
    )
    result = engine.run(
        generations=PRODUCTION_CONFIG["generations"],
        crossover_rate=PRODUCTION_CONFIG["crossover_rate"],
        mutation_rate=PRODUCTION_CONFIG["mutation_rate"], use_repair=True,
        use_soft_local_search=True, evaluation_budget=evaluation_budget, seed=seed,
        soft_local_search_max_passes=PRODUCTION_CONFIG["soft_local_search_max_passes"],
        soft_local_search_max_candidate_checks=PRODUCTION_CONFIG["soft_local_search_max_candidate_checks"],
    )
    schedule = result["best_schedule"]
    final = ConstraintEvaluator(dataset).evaluate_unified(schedule, category="reporting")
    activities = expand_scheduling_activities(dataset["course_sections"])
    activity_map = {activity.activity_id: activity for activity in activities}
    scheduled_sections = {
        activity_map[gene.activity_id].section_id
        for gene in schedule.genes if gene.activity_id in activity_map
    }
    return {
        "schedule": schedule, "run_metrics": result["run_metrics"],
        "hard_violations": final.hard_violations, "hard_details": final.hard_details,
        "soft_score": final.soft_penalty, "soft_breakdown": final.soft_breakdown,
        "section_count": len(dataset["course_sections"]),
        "scheduled_section_count": len(scheduled_sections),
        "activity_count": len(activities), "scheduled_count": len(schedule.genes), "seed": seed,
    }


def create_demo_exports(run: dict[str, Any], dataset: dict, dataset_name: str, output_dir: Path = DEMO_OUTPUT_DIR) -> dict[str, Any]:
    """Use production exporters and return download-ready bytes and query data."""
    if run["hard_violations"] != 0:
        raise ValueError("Exports are disabled because the final timetable is not hard-feasible.")
    output_dir.mkdir(parents=True, exist_ok=True)
    slug = dataset_name.lower()
    excel_path = output_dir / f"{slug}_best_timetable.xlsx"
    json_path = output_dir / f"{slug}_schedule.json"
    csv_path = output_dir / f"{slug}_schedule.csv"
    soft_config = SoftConstraintConfig.from_constraint_definitions(dataset.get("constraints", []))
    metadata = {
        "method": "GA + Repair + SLS (Production)", "primary_method": "ga_repair_sls",
        "dataset": dataset_name, "seed": run["seed"],
        "population_size": PRODUCTION_CONFIG["population_size"],
        "evaluation_budget": PRODUCTION_CONFIG["evaluation_budget"],
        "hard_violations": run["hard_violations"], "soft_penalty": run["soft_score"],
        "runtime_seconds": run["run_metrics"].runtime_seconds,
    }
    export_schedule_to_excel(
        run["schedule"], dataset, excel_path, metadata=metadata,
        allow_infeasible_export=False, soft_config=soft_config,
    )
    export_schedule_query_data(
        run["schedule"], dataset, json_path, hard_violations=run["hard_violations"],
        soft_penalty=run["soft_score"], metadata=metadata, soft_config=soft_config,
    )
    export_schedule_to_csv(
        run["schedule"], dataset, csv_path, metadata=metadata, soft_config=soft_config,
    )
    query_data = json.loads(json_path.read_text(encoding="utf-8"))
    return {
        "excel_path": excel_path, "json_path": json_path, "csv_path": csv_path,
        "excel_bytes": excel_path.read_bytes(), "json_bytes": json_path.read_bytes(),
        "csv_bytes": csv_path.read_bytes(),
        "query_data": query_data,
    }


def filter_assignments(assignments: list[dict], view_by: str, selected: str) -> list[dict]:
    fields = FILTER_FIELDS.get(view_by)
    if not fields:
        return list(assignments)
    return [item for item in assignments if selected in {item.get(field) for field in fields}]


def filter_options(assignments: list[dict], view_by: str) -> list[str]:
    fields = FILTER_FIELDS.get(view_by)
    if not fields:
        return []
    id_field, name_field = fields
    return sorted({item.get(name_field) or item.get(id_field) for item in assignments if item.get(name_field) or item.get(id_field)})


def load_benchmark_artifacts(benchmark_dir: Path = BENCHMARK_DIR) -> dict[str, Any]:
    result_path = benchmark_dir / "benchmark_results.json"
    chart_names = ["feasibility_rate.png", "soft_score.png", "runtime.png"]
    missing = (["benchmark_results.json"] if not result_path.exists() else []) + [name for name in chart_names if not (benchmark_dir / name).exists()]
    if missing:
        return {"valid": False, "error": f"Missing benchmark artifact(s): {', '.join(missing)}"}
    try:
        payload = json.loads(result_path.read_text(encoding="utf-8"))
        if len(payload.get("runs", [])) != 60:
            return {"valid": False, "error": "Benchmark artifact does not contain exactly 60 runs."}
        return {"valid": True, "payload": payload, "charts": {name: benchmark_dir / name for name in chart_names}}
    except (OSError, json.JSONDecodeError) as error:
        return {"valid": False, "error": f"Unable to read benchmark artifacts: {error}"}


def _render_validation_card(result: DatasetLoadResult) -> None:
    st.subheader(f"Dataset: {result.name}")
    if result.counts:
        columns = st.columns(6)
        for column, (label, key) in zip(columns, [
            ("Sections", "sections"), ("Activities", "activities"),
            ("Lecturers", "lecturers"), ("Student groups", "student_groups"),
            ("Rooms", "rooms"), ("Timeslots", "timeslots"),
        ]):
            column.metric(label, result.counts[key])
    if result.valid:
        st.success(f"✓ Valid · ✓ {len(result.errors)} errors · ✓ {len(result.warnings)} warnings")
    else:
        st.error(f"Validation failed with {len(result.errors)} error(s). Scheduling is disabled.")
    if result.errors or result.warnings:
        with st.expander("Validation details"):
            for error in result.errors:
                st.error(error)
            for warning in result.warnings:
                st.warning(warning)


def _render_result_summary(run: dict[str, Any]) -> None:
    st.subheader("Final Metrics")
    if run["hard_violations"] == 0:
        st.success("✓ Feasible timetable — all hard constraints are satisfied.")
    else:
        st.error("Timetable is not feasible. Inspect hard-constraint results below.")
    metrics = run["run_metrics"]
    columns = st.columns(6)
    columns[0].metric("Hard Violations", run["hard_violations"])
    columns[1].metric("Soft Score", f"{run['soft_score']:.4f}")
    columns[2].metric("Runtime", f"{metrics.runtime_seconds:.2f}s")
    first = f"Gen {metrics.first_feasible_generation} / Eval {metrics.first_feasible_search_evaluation}" if metrics.first_feasible_generation is not None else "Not reached"
    columns[3].metric("First Feasible", first)
    columns[4].metric("Sections", f"{run['scheduled_section_count']} / {run['section_count']}")
    columns[5].metric("Activities", f"{run['scheduled_count']} / {run['activity_count']}")
    with st.expander("Constraint results", expanded=False):
        st.markdown("**Hard Constraints**")
        for key, label in HARD_CONSTRAINT_LABELS.items():
            value = run["hard_details"].get(key, 0)
            st.write(f"{'✓' if value == 0 else '✗'} {label}: {value}")
        st.markdown(f"**Soft Score:** {run['soft_score']:.4f}")
        with st.expander("S1–S7 breakdown"):
            st.dataframe(pd.DataFrame([{
                "Constraint": item.constraint_id, "Name": item.constraint_name,
                "Raw": item.raw_count, "Normalized": item.normalized_penalty,
                "Weight": item.weight, "Weighted": item.weighted_penalty,
            } for item in run["soft_breakdown"]]), use_container_width=True, hide_index=True)


def _render_scheduler_page() -> None:
    st.title("Final Timetable Demo")
    st.caption("Choose a frozen dataset, validate it, then run the Final Hybrid Method.")
    dataset_name = st.selectbox("Choose dataset", list(DATASET_OPTIONS), index=0)
    st.info(DATASET_OPTIONS[dataset_name]["description"])
    path = Path(DATASET_OPTIONS[dataset_name]["path"])
    result = cached_load_demo_dataset(dataset_name, path.stat().st_mtime_ns if path.exists() else 0)
    _render_validation_card(result)
    st.markdown("#### Final Hybrid Method")
    st.write("**GA** — global search · **Repair** — fixes hard violations · **SLS** — improves soft quality after feasibility")
    with st.expander("Advanced Settings", expanded=False):
        seed = int(st.number_input("Reproducible seed", min_value=0, value=0, step=1))
        st.caption("Frozen production configuration: population 60, GA budget 1,000, SLS enabled.")
    running = bool(st.session_state.get("scheduler_running", False))
    if st.button("Run Scheduler", type="primary", disabled=(not result.valid or running), use_container_width=True):
        st.session_state["scheduler_running"] = True
        progress = st.progress(0, text="Loading and validating dataset...")
        try:
            progress.progress(15, text="Validation passed. Running Genetic Algorithm with Repair...")
            run = run_demo_scheduler(result.dataset, seed=seed)
            progress.progress(80, text="Improving soft constraints with SLS and evaluating final schedule...")
            exports = create_demo_exports(run, result.dataset, dataset_name)
            st.session_state["demo_result"] = {"dataset_name": dataset_name, "run": run, "exports": exports}
            progress.progress(100, text="Done.")
        except Exception as error:
            st.error("Scheduling failed. No result was exported.")
            with st.expander("Technical details"):
                st.exception(error)
        finally:
            st.session_state["scheduler_running"] = False
    demo_result = st.session_state.get("demo_result")
    if demo_result and demo_result["dataset_name"] == dataset_name:
        _render_result_summary(demo_result["run"])
        st.caption("Open Timetable to filter the result and download Excel/JSON exports.")


def _render_timetable_page() -> None:
    st.title("Timetable")
    result = st.session_state.get("demo_result")
    if not result:
        st.info("Run the scheduler on the Scheduler page first.")
        return
    assignments = result["exports"]["query_data"].get("assignments", [])
    st.caption(f"{result['dataset_name']} · {len(assignments)} scheduled activities")
    view_by = st.selectbox("View timetable by", list(FILTER_FIELDS))
    options = filter_options(assignments, view_by)
    selected = st.selectbox("Select", options) if options else None
    filtered = filter_assignments(assignments, view_by, selected) if selected else []
    st.dataframe(format_dataframe(filtered), use_container_width=True, hide_index=True)
    with st.expander("All assignments (raw table)"):
        st.dataframe(format_dataframe(assignments), use_container_width=True, hide_index=True)
    st.subheader("Export")
    columns = st.columns(3)
    columns[0].download_button(
        "Download Excel", result["exports"]["excel_bytes"],
        file_name=f"{result['dataset_name'].lower()}_best_timetable.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", use_container_width=True,
    )
    columns[1].download_button(
        "Download JSON", result["exports"]["json_bytes"],
        file_name=f"{result['dataset_name'].lower()}_schedule.json",
        mime="application/json", use_container_width=True,
    )
    columns[2].download_button(
        "Download CSV", result["exports"]["csv_bytes"],
        file_name=f"{result['dataset_name'].lower()}_schedule.csv",
        mime="text/csv", use_container_width=True,
    )


def _render_benchmark_page() -> None:
    st.title("Final Benchmark")
    st.caption("Frozen Phase 3.1 results — this page never reruns experiments.")
    artifacts = load_benchmark_artifacts()
    if not artifacts["valid"]:
        st.warning(artifacts["error"])
        return
    st.markdown(
        "**GA:** 0/10 feasible on EASY · 0/10 on MEDIUM  \n"
        "**GA + Repair:** 10/10 · 10/10  \n"
        "**GA + Repair + SLS:** 10/10 · 10/10"
    )
    st.image(str(artifacts["charts"]["feasibility_rate.png"]), caption="Feasibility rate")
    st.image(str(artifacts["charts"]["soft_score.png"]), caption="Feasible-only soft score")
    st.image(str(artifacts["charts"]["runtime.png"]), caption="Runtime")


def _render_about_page() -> None:
    st.title("About the Method")
    st.markdown(
        "### Final Hybrid Method\n- **GA:** global search for timetable assignments.\n"
        "- **Repair:** fixes hard-constraint violations.\n"
        "- **SLS:** improves soft-constraint quality after feasibility.\n\n"
        "A timetable is **feasible** when all implemented hard constraints are satisfied. "
        "This does not imply a perfect soft score."
    )


def main() -> None:
    st.set_page_config(page_title="Genetic ALO — Final Demo", page_icon="📅", layout="wide", initial_sidebar_state="expanded")
    page = st.sidebar.radio("Demo", ["Scheduler", "Timetable", "Benchmark", "About / Method"])
    if page == "Scheduler":
        _render_scheduler_page()
    elif page == "Timetable":
        _render_timetable_page()
    elif page == "Benchmark":
        _render_benchmark_page()
    else:
        _render_about_page()


if __name__ == "__main__":
    main()
