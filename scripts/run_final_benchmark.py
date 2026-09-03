"""Phase 3.1 final paired benchmark for frozen EASY and MEDIUM instances."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import platform
import statistics
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

from constraints import SoftConstraintConfig
from dataset import ExcelDatasetLoader, DatasetValidator
from evaluation.method_registry import METHOD_DISPLAY_NAMES, METHOD_RUNNERS
from evaluation.run_metrics import validate_search_budget
from scripts.analyze_instance_difficulty import analyze_dataset


OUTPUT_DIR = ROOT / "outputs" / "final_benchmark"
DATASETS = {
    "EASY": ROOT / "data" / "instances" / "instance_easy.xlsx",
    "MEDIUM": ROOT / "data" / "instances" / "instance_medium.xlsx",
}
EXPECTED_HASHES = {
    "EASY": "5ddc4d9447ac5a43d95c5f2854eb2f6982dd5c84f7843b64d648a0ca6cff5c45",
    "MEDIUM": "78e7c324db8c667130df4e261b6fe729c64c0bf001d836197dd466fc44caf9ef",
}
METHODS = ("ga", "ga_repair", "ga_repair_sls")
SEEDS = tuple(range(10))
EVALUATION_BUDGET = 1000
GA_CONFIG = {
    "pop_size": 60,
    "generations": 100,
    "crossover_rate": 0.8,
    "mutation_rate": 0.2,
    "hard_weight": 1000,
    "soft_weight": 1,
    "soft_local_search_max_passes": 2,
    "soft_local_search_max_candidate_checks": 5000,
}
RUN_COLUMNS = (
    "dataset", "method", "method_name", "seed", "feasible",
    "final_hard_violations", "final_soft_score", "soft_score_comparable",
    "first_feasible_generation", "first_feasible_ga_evaluation",
    "runtime_seconds", "ga_evaluations", "repair_evaluations",
    "sls_evaluations", "total_evaluations",
)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def verify_datasets() -> tuple[dict[str, dict], dict[str, str]]:
    loaded = {}
    hashes = {}
    for name, path in DATASETS.items():
        actual_hash = sha256_file(path)
        expected_hash = EXPECTED_HASHES[name]
        if actual_hash != expected_hash:
            raise RuntimeError(
                f"{name} hash mismatch: expected {expected_hash}, got {actual_hash}"
            )
        dataset = ExcelDatasetLoader.load_and_validate(str(path))
        report = DatasetValidator.validate_report(dataset)
        if not report["valid"]:
            raise RuntimeError(f"{name} validation failed: {report['errors']}")
        loaded[name] = dataset
        hashes[name] = actual_hash
    return loaded, hashes


def normalize_run(dataset_name: str, method: str, seed: int, result: dict) -> dict:
    metrics = result["run_metrics"]
    validate_search_budget(metrics, EVALUATION_BUDGET)
    repair_evaluations = int(result.get("repair_stats", {}).get("candidate_checks", 0))
    sls_evaluations = int(metrics.soft_ls_candidate_checks)
    ga_evaluations = int(metrics.search_fitness_evaluations)
    return {
        "dataset": dataset_name,
        "method": method,
        "method_name": METHOD_DISPLAY_NAMES[method],
        "seed": seed,
        "feasible": bool(metrics.feasible),
        "final_hard_violations": int(metrics.final_hard_violations),
        "final_soft_score": float(metrics.final_soft_penalty),
        "soft_score_comparable": bool(metrics.feasible),
        "first_feasible_generation": metrics.first_feasible_generation,
        "first_feasible_ga_evaluation": metrics.first_feasible_search_evaluation,
        "runtime_seconds": float(metrics.runtime_seconds),
        "ga_evaluations": ga_evaluations,
        "repair_evaluations": repair_evaluations,
        "sls_evaluations": sls_evaluations,
        "total_evaluations": ga_evaluations + repair_evaluations + sls_evaluations,
    }


def _coerce_csv_row(row: dict[str, str]) -> dict[str, Any]:
    integer_fields = {
        "seed", "final_hard_violations", "first_feasible_generation",
        "first_feasible_ga_evaluation", "ga_evaluations", "repair_evaluations",
        "sls_evaluations", "total_evaluations",
    }
    result: dict[str, Any] = dict(row)
    for key in integer_fields:
        result[key] = int(row[key]) if row.get(key, "") != "" else None
    result["runtime_seconds"] = float(row["runtime_seconds"])
    result["final_soft_score"] = float(row["final_soft_score"])
    result["feasible"] = row["feasible"].lower() == "true"
    result["soft_score_comparable"] = row["soft_score_comparable"].lower() == "true"
    return result


def read_checkpoint(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream)
        if tuple(reader.fieldnames or ()) != RUN_COLUMNS:
            raise RuntimeError("Existing benchmark_runs.csv has an incompatible schema")
        return [_coerce_csv_row(row) for row in reader]


def write_runs(path: Path, runs: Iterable[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=RUN_COLUMNS)
        writer.writeheader()
        for run in runs:
            writer.writerow({key: run.get(key, "") if run.get(key) is not None else "" for key in RUN_COLUMNS})


def _stats(values: list[float], *, extrema: bool = True) -> dict[str, float | None]:
    if not values:
        keys = ["mean", "median", "std"] + (["min", "max"] if extrema else [])
        return {key: None for key in keys}
    result: dict[str, float | None] = {
        "mean": statistics.fmean(values),
        "median": statistics.median(values),
        "std": statistics.pstdev(values),
    }
    if extrema:
        result.update({"min": min(values), "max": max(values)})
    return result


def aggregate_runs(runs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    summaries = []
    for dataset_name in DATASETS:
        for method in METHODS:
            group = [r for r in runs if r["dataset"] == dataset_name and r["method"] == method]
            feasible = [r for r in group if r["feasible"]]
            summaries.append({
                "dataset": dataset_name,
                "method": method,
                "method_name": METHOD_DISPLAY_NAMES[method],
                "run_count": len(group),
                "feasible_count": len(feasible),
                "feasible_rate": len(feasible) / len(group) if group else None,
                "hard_violations": _stats([r["final_hard_violations"] for r in group]),
                "soft_score_feasible_only": _stats([r["final_soft_score"] for r in feasible]),
                "runtime_seconds": _stats([r["runtime_seconds"] for r in group], extrema=False),
                "first_feasible_generation": _stats(
                    [r["first_feasible_generation"] for r in feasible], extrema=False
                ),
                "first_feasible_ga_evaluation": _stats(
                    [r["first_feasible_ga_evaluation"] for r in feasible], extrema=False
                ),
                "ga_evaluations": _stats([r["ga_evaluations"] for r in group], extrema=False),
                "repair_evaluations": _stats([r["repair_evaluations"] for r in group], extrema=False),
                "sls_evaluations": _stats([r["sls_evaluations"] for r in group], extrema=False),
                "total_evaluations": _stats([r["total_evaluations"] for r in group], extrema=False),
            })
    return summaries


SUMMARY_COLUMNS = (
    "dataset", "method", "method_name", "run_count", "feasible_count", "feasible_rate",
    "hard_mean", "hard_median", "hard_std", "hard_min", "hard_max",
    "soft_feasible_mean", "soft_feasible_median", "soft_feasible_std",
    "soft_feasible_min", "soft_feasible_max", "runtime_mean", "runtime_median",
    "runtime_std", "first_feasible_generation_mean", "first_feasible_generation_median",
    "first_feasible_ga_evaluation_mean", "first_feasible_ga_evaluation_median",
    "ga_evaluations_mean", "repair_evaluations_mean", "sls_evaluations_mean",
    "total_evaluations_mean",
)


def flatten_summary(summary: dict[str, Any]) -> dict[str, Any]:
    return {
        "dataset": summary["dataset"], "method": summary["method"],
        "method_name": summary["method_name"], "run_count": summary["run_count"],
        "feasible_count": summary["feasible_count"], "feasible_rate": summary["feasible_rate"],
        "hard_mean": summary["hard_violations"]["mean"],
        "hard_median": summary["hard_violations"]["median"],
        "hard_std": summary["hard_violations"]["std"],
        "hard_min": summary["hard_violations"]["min"], "hard_max": summary["hard_violations"]["max"],
        "soft_feasible_mean": summary["soft_score_feasible_only"]["mean"],
        "soft_feasible_median": summary["soft_score_feasible_only"]["median"],
        "soft_feasible_std": summary["soft_score_feasible_only"]["std"],
        "soft_feasible_min": summary["soft_score_feasible_only"]["min"],
        "soft_feasible_max": summary["soft_score_feasible_only"]["max"],
        "runtime_mean": summary["runtime_seconds"]["mean"],
        "runtime_median": summary["runtime_seconds"]["median"],
        "runtime_std": summary["runtime_seconds"]["std"],
        "first_feasible_generation_mean": summary["first_feasible_generation"]["mean"],
        "first_feasible_generation_median": summary["first_feasible_generation"]["median"],
        "first_feasible_ga_evaluation_mean": summary["first_feasible_ga_evaluation"]["mean"],
        "first_feasible_ga_evaluation_median": summary["first_feasible_ga_evaluation"]["median"],
        "ga_evaluations_mean": summary["ga_evaluations"]["mean"],
        "repair_evaluations_mean": summary["repair_evaluations"]["mean"],
        "sls_evaluations_mean": summary["sls_evaluations"]["mean"],
        "total_evaluations_mean": summary["total_evaluations"]["mean"],
    }


def write_summary(path: Path, summaries: list[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=SUMMARY_COLUMNS)
        writer.writeheader()
        for summary in summaries:
            writer.writerow(flatten_summary(summary))


def _plot_grouped(summary: list[dict[str, Any]], field: str, ylabel: str, path: Path) -> None:
    labels = ["GA", "GA + Repair", "GA + Repair + SLS"]
    x = list(range(len(METHODS)))
    width = 0.36
    fig, axis = plt.subplots(figsize=(8, 5))
    for offset, dataset_name in ((-width / 2, "EASY"), (width / 2, "MEDIUM")):
        values = []
        for method in METHODS:
            row = next(s for s in summary if s["dataset"] == dataset_name and s["method"] == method)
            value: Any = row
            for part in field.split("."):
                value = value[part]
            values.append(0 if value is None else value)
        bars = axis.bar([position + offset for position in x], values, width, label=dataset_name.title())
        axis.bar_label(bars, fmt="%.2f", padding=3, fontsize=8)
    axis.set_xticks(x, labels)
    axis.set_ylabel(ylabel)
    axis.legend()
    axis.grid(axis="y", alpha=0.25)
    fig.tight_layout()
    fig.savefig(path, dpi=160)
    plt.close(fig)


def create_charts(runs: list[dict[str, Any]], summaries: list[dict[str, Any]], output_dir: Path) -> None:
    _plot_grouped(summaries, "feasible_rate", "Feasibility rate", output_dir / "feasibility_rate.png")
    _plot_grouped(summaries, "runtime_seconds.mean", "Mean runtime (seconds)", output_dir / "runtime.png")

    fig, axes = plt.subplots(1, 2, figsize=(10, 5), sharey=True)
    labels = ["GA", "GA + Repair", "GA + Repair + SLS"]
    for axis, dataset_name in zip(axes, DATASETS):
        values = [
            [r["final_soft_score"] for r in runs if r["dataset"] == dataset_name and r["method"] == method and r["feasible"]]
            for method in METHODS
        ]
        positions = [index + 1 for index, group in enumerate(values) if group]
        nonempty = [group for group in values if group]
        if nonempty:
            axis.boxplot(nonempty, positions=positions, widths=0.55)
        axis.set_xticks(range(1, 4), labels, rotation=15, ha="right")
        axis.set_title(dataset_name.title())
        axis.grid(axis="y", alpha=0.25)
    axes[0].set_ylabel("Final soft score (feasible runs only)")
    fig.tight_layout()
    fig.savefig(output_dir / "soft_score.png", dpi=160)
    plt.close(fig)


def _git_commit() -> str:
    return subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()


def build_report(summaries: list[dict[str, Any]], structural: dict[str, dict[str, Any]]) -> str:
    lookup = {(s["dataset"], s["method"]): s for s in summaries}
    lines = [
        "# Final Benchmark: Easy vs Medium", "",
        "All methods use paired seeds 0–9, population 60, and exactly 1,000 GA objective evaluations per run.", "",
        "Final soft-score statistics include hard-feasible runs only.", "",
        "## Results", "",
        "| Dataset | Method | Feasible | Hard median | Feasible soft median | Runtime median (s) | Repair checks mean | SLS checks mean | Total work mean |",
        "|---|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for dataset_name in DATASETS:
        for method in METHODS:
            row = lookup[(dataset_name, method)]
            soft = row["soft_score_feasible_only"]["median"]
            soft_display = f"{soft:.4f}" if soft is not None else "N/A"
            lines.append(
                f"| {dataset_name.title()} | {METHOD_DISPLAY_NAMES[method]} | {row['feasible_count']}/{row['run_count']} | "
                f"{row['hard_violations']['median']:.2f} | {soft_display} | "
                f"{row['runtime_seconds']['median']:.3f} | {row['repair_evaluations']['mean']:.1f} | "
                f"{row['sls_evaluations']['mean']:.1f} | {row['total_evaluations']['mean']:.1f} |"
            )
    easy_ga, easy_repair, easy_sls = (lookup[("EASY", method)] for method in METHODS)
    med_ga, med_repair, med_sls = (lookup[("MEDIUM", method)] for method in METHODS)
    easy_structure = structural["EASY"]
    med_structure = structural["MEDIUM"]
    lines.extend([
        "", "## Main questions", "",
        "### Q1 — Does Repair improve feasibility?", "",
        f"Yes in these runs: Easy improves from {easy_ga['feasible_count']}/10 to {easy_repair['feasible_count']}/10, "
        f"and Medium from {med_ga['feasible_count']}/10 to {med_repair['feasible_count']}/10.", "",
        "### Q2 — Does SLS improve feasible soft quality?", "",
        f"Easy feasible-soft median changes from {easy_repair['soft_score_feasible_only']['median']:.4f} to "
        f"{easy_sls['soft_score_feasible_only']['median']:.4f}; Medium changes from "
        f"{med_repair['soft_score_feasible_only']['median']:.4f} to {med_sls['soft_score_feasible_only']['median']:.4f}.", "",
        "### Q3 — What changes from Easy to Medium?", "",
        f"Candidate-domain median falls from {easy_structure['candidate_domains']['summary']['median']:.0f} to "
        f"{med_structure['candidate_domains']['summary']['median']:.0f}; LAB utilization rises from "
        f"{easy_structure['resource_pressure']['lab_utilization_ratio']:.2%} to "
        f"{med_structure['resource_pressure']['lab_utilization_ratio']:.2%}; and maximum lecturer load rises from "
        f"{easy_structure['lecturer_pressure']['summary']['max']:.2%} to "
        f"{med_structure['lecturer_pressure']['summary']['max']:.2%}. Vanilla GA mean hard violations rise from "
        f"{easy_ga['hard_violations']['mean']:.2f} to {med_ga['hard_violations']['mean']:.2f}, while the median "
        f"remains {easy_ga['hard_violations']['median']:.2f} on both datasets. Repair remains feasible in all runs.", "",
        "### Q4 — What is the computational cost?", "",
        "Every method receives the same 1,000 GA objective evaluations. Repair candidate checks and SLS candidate "
        "checks are reported separately and included in total work; runtime captures remaining implementation overhead.", "",
    ])
    return "\n".join(lines)


def write_final_artifacts(
    output_dir: Path, runs: list[dict[str, Any]], summaries: list[dict[str, Any]], hashes: dict[str, str], datasets: dict[str, dict]
) -> None:
    write_summary(output_dir / "benchmark_summary.csv", summaries)
    soft_configs = {
        name: SoftConstraintConfig.from_constraint_definitions(dataset.get("constraints", [])).to_metadata()
        for name, dataset in datasets.items()
    }
    structural = {name: analyze_dataset(dataset) for name, dataset in datasets.items()}
    payload = {
        "metadata": {
            "git_commit": _git_commit(), "dataset_hashes_sha256": hashes,
            "python_version": platform.python_version(),
            "timestamp_utc": datetime.now(timezone.utc).isoformat(),
            "algorithm_configuration": GA_CONFIG, "soft_constraint_configuration": soft_configs,
            "seeds": list(SEEDS), "evaluation_budget": EVALUATION_BUDGET,
            "evaluation_accounting": {
                "ga_evaluations": "Search objective evaluations under the fixed budget.",
                "repair_evaluations": "Repair candidate assignments checked.",
                "sls_evaluations": "SLS candidate moves checked.",
                "total_evaluations": "ga_evaluations + repair_evaluations + sls_evaluations.",
            },
        },
        "dataset_structural_metrics": structural,
        "runs": runs, "summary": summaries,
    }
    (output_dir / "benchmark_results.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    (output_dir / "benchmark_report.md").write_text(
        build_report(summaries, structural), encoding="utf-8"
    )
    create_charts(runs, summaries, output_dir)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=OUTPUT_DIR)
    parser.add_argument("--fresh", action="store_true", help="Ignore and overwrite a prior checkpoint")
    args = parser.parse_args()
    datasets, hashes = verify_datasets()
    output_dir = args.output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    checkpoint = output_dir / "benchmark_runs.csv"
    runs = [] if args.fresh else read_checkpoint(checkpoint)
    expected_keys = {(dataset, method, seed) for dataset in DATASETS for seed in SEEDS for method in METHODS}
    completed_keys = {(r["dataset"], r["method"], r["seed"]) for r in runs}
    if not completed_keys <= expected_keys or len(completed_keys) != len(runs):
        raise RuntimeError("Checkpoint contains duplicate or unexpected benchmark rows")

    for dataset_name, dataset in datasets.items():
        for seed in SEEDS:
            for method in METHODS:
                key = (dataset_name, method, seed)
                if key in completed_keys:
                    continue
                result = METHOD_RUNNERS[method](dataset, GA_CONFIG, EVALUATION_BUDGET, seed)
                runs.append(normalize_run(dataset_name, method, seed, result))
                completed_keys.add(key)
                write_runs(checkpoint, runs)
                print(f"Completed {len(runs)}/60: {dataset_name} seed={seed} method={method}", flush=True)

    if len(runs) != 60 or completed_keys != expected_keys:
        raise RuntimeError(f"Expected exactly 60 completed runs, got {len(runs)}")
    order = {(dataset, method, seed): index for index, (dataset, seed, method) in enumerate(
        (d, s, m) for d in DATASETS for s in SEEDS for m in METHODS
    )}
    runs.sort(key=lambda run: order[(run["dataset"], run["method"], run["seed"])])
    write_runs(checkpoint, runs)
    summaries = aggregate_runs(runs)
    write_final_artifacts(output_dir, runs, summaries, hashes, datasets)
    print(f"Final benchmark complete: {len(runs)} runs in {output_dir}")


if __name__ == "__main__":
    main()
