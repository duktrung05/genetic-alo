import matplotlib.pyplot as plt
import sys
import time
import random
import json
import os
import csv
import datetime
import argparse
from pathlib import Path
import numpy as np

sys.stdout.reconfigure(encoding='utf-8')

from dataset import DatasetFactory, ExcelDatasetLoader
from ga import GeneticAlgorithmEngine
from evaluation import (
    RandomSearchScheduler,
    GreedyScheduler,
    BenchmarkEvaluator,
    ConvergenceVisualizer,
    export_schedule_to_excel,
    export_metadata_to_json,
)
from evaluation.benchmark_statistics import aggregate_run_results

def parse_args():
    """Parse command line arguments for benchmark execution mode, data source, and worker count."""
    parser = argparse.ArgumentParser(description="GA Timetable Benchmark Suite")
    parser.add_argument(
        "--mode",
        choices=["fast", "report"],
        default="fast",
        help="Benchmark mode: 'fast' (3 seeds, 1000 evals) or 'report' (30 seeds, 4800 evals)"
    )
    parser.add_argument(
        "--data-source",
        choices=["excel", "mock"],
        default="excel",
        help="Data source: 'excel' or 'mock'"
    )
    parser.add_argument(
        "--input",
        type=str,
        default="data/01_data_timetable(1).xlsx",
        help="Input Excel file path (when --data-source=excel)"
    )
    parser.add_argument(
        "--dataset-seed",
        type=int,
        default=42,
        help="Random seed for mock dataset generation (when --data-source=mock)"
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=1,
        help="Maximum parallel workers (default 1)"
    )
    return parser.parse_args()

def make_json_serializable(obj):
    """Recursively convert benchmark result structures into JSON-serializable dictionaries."""
    if isinstance(obj, dict):
        return {k: make_json_serializable(v) for k, v in obj.items() if k not in ("best_schedule", "schedule")}
    elif isinstance(obj, list):
        return [make_json_serializable(v) for v in obj]
    elif isinstance(obj, (int, float, str, bool, type(None))):
        return obj
    else:
        return str(obj)

def run_single_seed_task(task_args):
    """Execute single-seed benchmark task evaluating GA without Repair, Hybrid GA, and Random Search."""
    seed, dataset, ga_config, budget = task_args

    # 1. GA without Repair (Isolated Engine & RNG)
    random.seed(seed)
    np.random.seed(seed)
    ga_engine_no_repair = GeneticAlgorithmEngine(
        dataset,
        pop_size=ga_config["pop_size"],
        hard_weight=ga_config["hard_weight"],
        soft_weight=ga_config["soft_weight"]
    )
    t0 = time.perf_counter()
    res_no_rep = ga_engine_no_repair.run(
        generations=ga_config["generations"],
        crossover_rate=ga_config["crossover_rate"],
        mutation_rate=ga_config["mutation_rate"],
        use_repair=False,
        evaluation_budget=budget
    )
    t1 = time.perf_counter()

    gen_feasible_no_rep = next((h.get("generation", h.get("iteration", 0)) for h in res_no_rep["history"] if h.get("best_hard") == 0 or h.get("hard_violations") == 0), "N/A")
    time_feasible_no_rep = next((h.get("runtime_seconds", 0.0) for h in res_no_rep["history"] if h.get("best_hard") == 0 or h.get("hard_violations") == 0), "N/A")


    no_rep_run = {
        "method": "GA without Repair",
        "seed": seed,
        "runtime_seconds": t1 - t0,
        "fitness_evaluations": res_no_rep["fitness_evaluations"],
        "score": res_no_rep["best_score"],
        "hard_violations": res_no_rep["hard_violations"],
        "raw_soft_violations": res_no_rep["raw_soft_violations"],
        "soft_penalty": res_no_rep["soft_penalty"],
        "is_hard_feasible": res_no_rep["hard_violations"] == 0,
        "is_perfect": (res_no_rep["hard_violations"] == 0 and res_no_rep["soft_penalty"] == 0),
        "generation_to_first_feasible": gen_feasible_no_rep,
        "time_to_first_feasible": time_feasible_no_rep,
        "repair_calls": 0,
        "repair_attempts": 0,
        "repair_successes": 0,
        "repair_failures": 0,
        "sections_repaired": 0,
        "candidate_checks": 0,
        "repair_runtime_seconds": 0.0,
        "best_schedule": res_no_rep["best_schedule"],
        "history": res_no_rep["history"]
    }

    # 2. Hybrid GA + Repair (Isolated Engine & RNG)
    random.seed(seed)
    np.random.seed(seed)
    ga_engine_hybrid = GeneticAlgorithmEngine(
        dataset,
        pop_size=ga_config["pop_size"],
        hard_weight=ga_config["hard_weight"],
        soft_weight=ga_config["soft_weight"]
    )
    t0 = time.perf_counter()
    res_hybrid = ga_engine_hybrid.run(
        generations=ga_config["generations"],
        crossover_rate=ga_config["crossover_rate"],
        mutation_rate=ga_config["mutation_rate"],
        use_repair=True,
        evaluation_budget=budget
    )
    t1 = time.perf_counter()

    r_stats = res_hybrid.get("repair_stats", None)
    rep_calls = getattr(r_stats, "calls", 0) if r_stats else 0
    rep_succ = getattr(r_stats, "successes", 0) if r_stats else 0
    rep_fail = getattr(r_stats, "failures", 0) if r_stats else 0
    sec_rep = getattr(r_stats, "sections_repaired", 0) if r_stats else 0

    gen_feasible_hybrid = next((h.get("generation", h.get("iteration", 0)) for h in res_hybrid["history"] if h.get("best_hard") == 0 or h.get("hard_violations") == 0), 0)

    time_feasible_hybrid = next((h.get("runtime_seconds", 0.0) for h in res_hybrid["history"] if h.get("best_hard") == 0 or h.get("hard_violations") == 0), 0.0)

    hybrid_run = {
        "method": "Hybrid GA + Repair",
        "seed": seed,
        "runtime_seconds": t1 - t0,
        "fitness_evaluations": res_hybrid["fitness_evaluations"],
        "score": res_hybrid["best_score"],
        "hard_violations": res_hybrid["hard_violations"],
        "raw_soft_violations": res_hybrid["raw_soft_violations"],
        "soft_penalty": res_hybrid["soft_penalty"],
        "is_hard_feasible": res_hybrid["hard_violations"] == 0,
        "is_perfect": (res_hybrid["hard_violations"] == 0 and res_hybrid["soft_penalty"] == 0),
        "generation_to_first_feasible": gen_feasible_hybrid,
        "time_to_first_feasible": time_feasible_hybrid,
        "repair_calls": rep_calls,
        "repair_attempts": rep_calls,
        "repair_successes": rep_succ,
        "repair_failures": rep_fail,
        "sections_repaired": sec_rep,
        "candidate_checks": 0,
        "repair_runtime_seconds": getattr(r_stats, "runtime_seconds", 0.0) if r_stats else 0.0,
        "best_schedule": res_hybrid["best_schedule"],
        "history": res_hybrid["history"]
    }

    # 3. Random Search (Isolated Engine & RNG)
    random.seed(seed)
    np.random.seed(seed)
    random_engine = RandomSearchScheduler(dataset)
    t0 = time.perf_counter()
    res_rand = random_engine.run(evaluation_budget=budget)
    t1 = time.perf_counter()

    random_run = {
        "method": "Random Search",
        "seed": seed,
        "runtime_seconds": t1 - t0,
        "fitness_evaluations": res_rand["fitness_evaluations"],
        "score": res_rand["best_score"],
        "hard_violations": res_rand["hard_violations"],
        "raw_soft_violations": res_rand["raw_soft_violations"],
        "soft_penalty": res_rand["soft_penalty"],
        "is_hard_feasible": res_rand["hard_violations"] == 0,
        "is_perfect": (res_rand["hard_violations"] == 0 and res_rand["soft_penalty"] == 0),
        "generation_to_first_feasible": "N/A",
        "time_to_first_feasible": "N/A",
        "repair_calls": 0,
        "repair_attempts": 0,
        "repair_successes": 0,
        "repair_failures": 0,
        "sections_repaired": 0,
        "candidate_checks": 0,
        "repair_runtime_seconds": 0.0,
        "best_schedule": res_rand["best_schedule"],
        "history": res_rand["history"]
    }

    return seed, no_rep_run, hybrid_run, random_run

def main():
    """Main entry point for official timetable algorithm benchmark suite."""
    args = parse_args()

    # Configure modes (Task 4: Report mode runs 30 seeds: 0..29)
    if args.mode == "fast":
        num_runs = 3
        evaluation_budget = 1000
        generations = 20
    else:  # report mode
        num_runs = 30
        evaluation_budget = 4800
        generations = 80

    seeds = list(range(num_runs))

    ga_config = {
        "pop_size": 60,
        "generations": generations,
        "crossover_rate": 0.8,
        "mutation_rate": 0.2,
        "hard_weight": 1000,
        "soft_weight": 1,
    }

    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    base_dir = Path(__file__).resolve().parent
    benchmark_run_dir = base_dir / "outputs" / "benchmarks" / f"benchmark_{timestamp}"
    benchmark_run_dir.mkdir(parents=True, exist_ok=True)

    print("=" * 80)
    print(f"OFFICIAL BENCHMARK SUITE — Mode: {args.mode.upper()} ({num_runs} seeds: 0..{num_runs-1}, budget: {evaluation_budget} evals/run)")
    print(f"Output Directory: {benchmark_run_dir}")
    print("=" * 80)

    # 1. Load Dataset ONCE
    json_norm_path = "outputs/datasets/01_data_timetable.normalized.json"
    if args.data_source == "excel":
        excel_path = args.input
        if os.path.exists(excel_path):
            print(f"\n[Phase 1] Đang tải dữ liệu từ Excel file '{excel_path}'...")
            dataset = ExcelDatasetLoader.load_and_validate(excel_path)
            json_norm_path = ExcelDatasetLoader.export_normalized_json(dataset, json_norm_path)
            dataset_preset = f"EXCEL ({os.path.basename(excel_path)})"
        elif os.path.exists(json_norm_path):
            print(f"\n[Phase 1] Đang tải dữ liệu từ Normalized JSON Snapshot '{json_norm_path}'...")
            dataset = ExcelDatasetLoader.load_normalized_json(json_norm_path)
            dataset_preset = "EXCEL (Normalized JSON)"
        else:
            raise FileNotFoundError(f"Neither Excel input '{excel_path}' nor JSON snapshot '{json_norm_path}' exist!")
    else:
        print(f"\n[Phase 1] Đang tạo mô hình Dữ liệu Mock (seed={args.dataset_seed})...")
        dataset = DatasetFactory.create_medium_dataset(seed=args.dataset_seed)
        dataset_preset = f"MOCK (seed={args.dataset_seed})"

    dataset["section_by_id"] = {s.section_id: s for s in dataset["course_sections"]}
    dataset["room_by_id"] = {r.id: r for r in dataset["rooms"]}
    dataset["timeslot_by_id"] = {t.id: t for t in dataset["timeslots"]}
    dataset["lecturer_by_id"] = {l.id: l for l in dataset.get("lecturers", [])}
    dataset["group_by_id"] = {g.id: g for g in dataset.get("student_groups", [])}

    # Save dataset snapshot
    dataset_snap_file = benchmark_run_dir / "dataset_snapshot.json"
    ExcelDatasetLoader.export_normalized_json(dataset, str(dataset_snap_file))

    # Save config.json
    config_data = {
        "benchmark_id": f"benchmark_{timestamp}",
        "generated_at": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "dataset_source": args.data_source,
        "dataset_path": args.input if args.data_source == "excel" else f"mock_seed_{args.dataset_seed}",
        "dataset_preset": dataset_preset,
        "seeds": seeds,
        "population_size": ga_config["pop_size"],
        "generations": ga_config["generations"],
        "evaluation_budget": evaluation_budget,
        "crossover_rate": ga_config["crossover_rate"],
        "mutation_rate": ga_config["mutation_rate"],
        "hard_weight": ga_config["hard_weight"],
        "soft_weight": ga_config["soft_weight"],
        "afternoon_start_period": 7,
        "python_version": sys.version.split()[0],
        "platform": sys.platform,
    }
    with open(benchmark_run_dir / "config.json", "w", encoding="utf-8") as f:
        json.dump(config_data, f, ensure_ascii=False, indent=2)

    # 2. Greedy Search (100% Deterministic baseline — runs ONCE)
    print("\n[Phase 2] Đang chạy Thuật toán Tham Ăn (Deterministic Greedy Scheduler)...")
    greedy_engine = GreedyScheduler(dataset, seed=0)
    t0 = time.perf_counter()
    greedy_res = greedy_engine.run()
    t1 = time.perf_counter()
    greedy_run = {
        "method": "Greedy Search",
        "seed": None,
        "runtime_seconds": t1 - t0,
        "fitness_evaluations": greedy_res.get("fitness_evaluations", 1),
        "score": greedy_res["best_score"],
        "hard_violations": greedy_res["hard_violations"],
        "raw_soft_violations": greedy_res["raw_soft_violations"],
        "soft_penalty": greedy_res["soft_penalty"],
        "is_hard_feasible": greedy_res["hard_violations"] == 0,
        "is_perfect": (greedy_res["hard_violations"] == 0 and greedy_res["soft_penalty"] == 0),
        "generation_to_first_feasible": 0 if greedy_res["hard_violations"] == 0 else "N/A",
        "time_to_first_feasible": t1 - t0 if greedy_res["hard_violations"] == 0 else "N/A",
        "repair_calls": 0,
        "repair_attempts": 0,
        "repair_successes": 0,
        "repair_failures": 0,
        "sections_repaired": 0,
        "candidate_checks": 0,
        "repair_runtime_seconds": 0.0,
        "best_schedule": greedy_res["best_schedule"]
    }
    greedy_runs = [greedy_run]

    # 3. Multi-seed runs for Stochastic algorithms
    ga_no_repair_runs = []
    hybrid_ga_runs = []
    random_search_runs = []

    best_hybrid_run = None
    best_hybrid_key = None

    print(f"\nĐang tiến hành chạy {num_runs} seeds ngẫu nhiên (Seeds 0..{num_runs-1}, Budget {evaluation_budget} evals/run)...")

    for run_idx, seed in enumerate(seeds):
        task_args = (seed, dataset, ga_config, evaluation_budget)
        s_id, no_rep_run, hybrid_run_data, rand_run = run_single_seed_task(task_args)

        ga_no_repair_runs.append(no_rep_run)
        hybrid_ga_runs.append(hybrid_run_data)
        random_search_runs.append(rand_run)

        hybrid_key = (
            hybrid_run_data["hard_violations"],
            hybrid_run_data["soft_penalty"],
            hybrid_run_data["runtime_seconds"],
            seed
        )
        if best_hybrid_key is None or hybrid_key < best_hybrid_key:
            best_hybrid_key = hybrid_key
            best_hybrid_run = hybrid_run_data

        if (run_idx + 1) % 5 == 0 or (run_idx + 1) == num_runs or args.mode == "fast":
            print(f"Completed seed {run_idx + 1}/{num_runs} (seed={seed})")

    # 4. Aggregated Statistics
    stat_no_repair = aggregate_run_results("GA without Repair", ga_no_repair_runs, is_deterministic=False)
    stat_hybrid = aggregate_run_results("Hybrid GA + Repair", hybrid_ga_runs, is_deterministic=False)
    stat_greedy = aggregate_run_results("Greedy Search", greedy_runs, is_deterministic=True)
    stat_random = aggregate_run_results("Random Search", random_search_runs, is_deterministic=False)

    summary_list = [stat_no_repair, stat_hybrid, stat_greedy, stat_random]

    # 5. Print Summary Table
    BenchmarkEvaluator.print_summary_table(summary_list)

    # 6. Save raw_runs.json & raw_runs.csv
    all_runs_flat = ga_no_repair_runs + hybrid_ga_runs + greedy_runs + random_search_runs
    with open(benchmark_run_dir / "raw_runs.json", "w", encoding="utf-8") as f:
        json.dump(make_json_serializable(all_runs_flat), f, ensure_ascii=False, indent=2)

    raw_csv_cols = [
        "method", "seed", "runtime_seconds", "fitness_evaluations", "score",
        "hard_violations", "raw_soft_violations", "soft_penalty", "is_hard_feasible",
        "is_perfect", "generation_to_first_feasible", "time_to_first_feasible",
        "repair_calls", "repair_attempts", "repair_successes", "repair_failures",
        "sections_repaired", "candidate_checks", "repair_runtime_seconds"
    ]
    with open(benchmark_run_dir / "raw_runs.csv", "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=raw_csv_cols)
        writer.writeheader()
        for r in all_runs_flat:
            row_dict = {c: r.get(c, "") for c in raw_csv_cols}
            writer.writerow(row_dict)

    # 7. Save summary.json & summary.csv
    with open(benchmark_run_dir / "summary.json", "w", encoding="utf-8") as f:
        json.dump(make_json_serializable(summary_list), f, ensure_ascii=False, indent=2)

    sum_csv_cols = ["method", "runs", "is_deterministic", "feasible_count", "feasible_rate", "perfect_count", "perfect_rate", "hard_mean", "hard_median", "hard_std", "soft_feasible_mean", "soft_feasible_median", "runtime_mean", "runtime_median"]
    with open(benchmark_run_dir / "summary.csv", "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=sum_csv_cols)
        writer.writeheader()
        for s in summary_list:
            row_dict = {c: s.get(c, "") for c in sum_csv_cols}
            writer.writerow(row_dict)

    # Backward compatibility outputs
    legacy_json_path = base_dir / "outputs" / "benchmarks" / "benchmark_results_multiseed.json"
    with open(legacy_json_path, "w", encoding="utf-8") as f:
        json.dump(make_json_serializable({"summary": summary_list, "runs": all_runs_flat}), f, ensure_ascii=False, indent=2)

    # 8. Generate Charts
    hard_chart_path = str(benchmark_run_dir / "convergence_hard.png")
    soft_chart_path = str(benchmark_run_dir / "convergence_soft.png")
    ConvergenceVisualizer.plot_convergence(
        ga_no_repair_runs,
        hybrid_ga_runs,
        random_search_runs,
        hard_output_path=hard_chart_path,
        soft_output_path=soft_chart_path,
        evaluation_budget=evaluation_budget
    )

    # Additional charts (runtime & feasible rate)
    fig, ax = plt.subplots(figsize=(8, 5))
    methods = [s["method"] for s in summary_list]
    runtimes = [s["runtime_mean"] for s in summary_list]
    ax.bar(methods, runtimes, color=["#4C72B0", "#55A868", "#C44E52", "#8172B0"])
    ax.set_ylabel("Mean Runtime (seconds)")
    ax.set_title("Runtime Comparison across Algorithms")
    plt.tight_layout()
    plt.savefig(benchmark_run_dir / "runtime_comparison.png", dpi=300)
    plt.close()

    fig, ax = plt.subplots(figsize=(8, 5))
    rates = [s["feasible_rate"] * 100.0 for s in summary_list]
    ax.bar(methods, rates, color=["#4C72B0", "#55A868", "#C44E52", "#8172B0"])
    ax.set_ylabel("Feasible Schedule Rate (%)")
    ax.set_title("Feasibility Rate Comparison (%)")
    plt.tight_layout()
    plt.savefig(benchmark_run_dir / "feasible_rate.png", dpi=300)
    plt.close()

    # 9. Export Official Best Timetable Excel (7 Sheets)
    if best_hybrid_run and best_hybrid_run.get("best_schedule"):
        best_excel_path = str(benchmark_run_dir / "best_timetable.xlsx")
        legacy_excel_path = str(base_dir / "outputs" / "timetables" / "best_timetable.xlsx")

        meta_export = {
            "method": best_hybrid_run["method"],
            "dataset_preset": dataset_preset,
            "seed": best_hybrid_run["seed"],
            "pop_size": ga_config["pop_size"],
            "generations": ga_config["generations"],
            "evaluation_budget": evaluation_budget,
            "hard_violations": best_hybrid_run["hard_violations"],
            "raw_soft_violations": best_hybrid_run["raw_soft_violations"],
            "soft_penalty": best_hybrid_run["soft_penalty"],
            "score": best_hybrid_run["score"],
            "fitness_evaluations": best_hybrid_run["fitness_evaluations"],
            "runtime_seconds": best_hybrid_run["runtime_seconds"],
            "generation_to_first_feasible": best_hybrid_run.get("generation_to_first_feasible", 0),
            "time_to_first_feasible": best_hybrid_run.get("time_to_first_feasible", 0.0),
            "repair_calls": best_hybrid_run.get("repair_calls", 0),
            "repair_successes": best_hybrid_run.get("repair_successes", 0),
            "repair_failures": best_hybrid_run.get("repair_failures", 0),
            "sections_repaired": best_hybrid_run.get("sections_repaired", 0),
            "repair_runtime_seconds": best_hybrid_run.get("repair_runtime_seconds", 0.0),
        }

        export_schedule_to_excel(
            schedule=best_hybrid_run["best_schedule"],
            dataset=dataset,
            output_path=best_excel_path,
            metadata=meta_export,
            allow_infeasible_export=False
        )

        export_schedule_to_excel(
            schedule=best_hybrid_run["best_schedule"],
            dataset=dataset,
            output_path=legacy_excel_path,
            metadata=meta_export,
            allow_infeasible_export=False
        )

        print("\n" + "=" * 80)
        print("ĐÃ HOÀN THÀNH BENCHMARK VÀ XUẤT WORKBOOK THỜI KHÓA BIỂU CHÍNH THỨC (7 SHEETS):")
        print(f"  Benchmark Directory: {benchmark_run_dir}")
        print(f"  Official Best Excel: {best_excel_path}")
        print(f"  Best Hybrid Seed: {best_hybrid_run['seed']}")
        print(f"  Hard Violations: {best_hybrid_run['hard_violations']}")
        print(f"  Soft Penalty: {best_hybrid_run['soft_penalty']}")
        print("=" * 80)

if __name__ == "__main__":
    main()
