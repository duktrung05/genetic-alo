import sys
import time
import random
import json
import os
sys.stdout.reconfigure(encoding='utf-8')

from dataset import DatasetFactory
from ga import GeneticAlgorithmEngine
from evaluation import (
    RandomSearchScheduler,
    GreedyScheduler,
    BenchmarkEvaluator,
    ConvergenceVisualizer,
    export_schedule_to_csv,
    export_metadata_to_json,
)
from evaluation.benchmark_statistics import aggregate_run_results

NUM_RUNS = 30
SEEDS = list(range(NUM_RUNS))
EVALUATION_BUDGET = 6000
CONVERGENCE_SEED = 42

GA_CONFIG = {
    "pop_size": 60,
    "generations": 100,
    "crossover_rate": 0.8,
    "mutation_rate": 0.2,
    "hard_weight": 1000,
    "soft_weight": 1,
}

def make_json_serializable(obj):
    if isinstance(obj, dict):
        return {k: make_json_serializable(v) for k, v in obj.items() if k not in ("best_schedule", "schedule")}
    elif isinstance(obj, list):
        return [make_json_serializable(v) for v in obj]
    elif isinstance(obj, (int, float, str, bool, type(None))):
        return obj
    else:
        return str(obj)

def main():
    print("=" * 80)
    print("PHASE 1 -> PHASE 5: SENIOR GA TIMETABLE BENCHMARK SUITE (MULTI-SEED 30 RUNS)")
    print("=" * 80)

    # 1. Load Dataset
    print("\n[Phase 1 & 2] Đang tạo mô hình Dữ liệu và ERD Mapping...")
    dataset = DatasetFactory.create_medium_dataset(seed=42)
    print("Dataset preset: MEDIUM")
    print(f"CourseSections: {len(dataset['course_sections'])}")
    print(f"Lecturers: {len(dataset['lecturers'])}")
    print(f"Rooms: {len(dataset['rooms'])}")
    print(f"StudentGroups: {len(dataset['student_groups'])}")
    print(f"Timeslots: {len(dataset['timeslots'])}")

    # 2. Greedy Search (Deterministic baseline)
    print("\n[Phase 5 Baseline 1] Đang chạy Thuật toán Tham Ăn (Greedy Scheduler)...")
    greedy_engine = GreedyScheduler(dataset)
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
        "best_schedule": greedy_res["best_schedule"]
    }
    greedy_runs = [greedy_run]

    # 3. Multi-seed runs for Stochastic algorithms
    ga_no_repair_runs = []
    hybrid_ga_runs = []
    random_search_runs = []

    best_hybrid_run = None
    best_hybrid_key = None

    print(f"\nĐang tiến hành chạy 30 seeds ngẫu nhiên (Budget {EVALUATION_BUDGET} evals/run)...")

    ga_engine = GeneticAlgorithmEngine(
        dataset,
        pop_size=GA_CONFIG["pop_size"],
        hard_weight=GA_CONFIG["hard_weight"],
        soft_weight=GA_CONFIG["soft_weight"]
    )
    random_engine = RandomSearchScheduler(dataset)

    for run_idx, seed in enumerate(SEEDS):
        # 3a. GA without Repair
        random.seed(seed)
        t0 = time.perf_counter()
        res_no_rep = ga_engine.run(
            generations=GA_CONFIG["generations"],
            crossover_rate=GA_CONFIG["crossover_rate"],
            mutation_rate=GA_CONFIG["mutation_rate"],
            use_repair=False,
            evaluation_budget=EVALUATION_BUDGET
        )
        t1 = time.perf_counter()
        ga_no_repair_runs.append({
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
            "best_schedule": res_no_rep["best_schedule"],
            "history": res_no_rep["history"]
        })

        # 3b. Hybrid GA + Repair
        random.seed(seed)
        t0 = time.perf_counter()
        res_hybrid = ga_engine.run(
            generations=GA_CONFIG["generations"],
            crossover_rate=GA_CONFIG["crossover_rate"],
            mutation_rate=GA_CONFIG["mutation_rate"],
            use_repair=True,
            evaluation_budget=EVALUATION_BUDGET
        )
        t1 = time.perf_counter()
        hybrid_run_data = {
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
            "best_schedule": res_hybrid["best_schedule"],
            "history": res_hybrid["history"]
        }
        hybrid_ga_runs.append(hybrid_run_data)

        # Lexicographic key: (hard_violations, soft_penalty, runtime_seconds, seed)
        hybrid_key = (
            hybrid_run_data["hard_violations"],
            hybrid_run_data["soft_penalty"],
            hybrid_run_data["runtime_seconds"],
            seed
        )
        if best_hybrid_key is None or hybrid_key < best_hybrid_key:
            best_hybrid_key = hybrid_key
            best_hybrid_run = hybrid_run_data

        # 3c. Random Search
        random.seed(seed)
        t0 = time.perf_counter()
        res_rand = random_engine.run(evaluation_budget=EVALUATION_BUDGET)
        t1 = time.perf_counter()
        random_search_runs.append({
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
            "best_schedule": res_rand["best_schedule"],
            "history": res_rand["history"]
        })

        if (run_idx + 1) % 5 == 0 or run_idx + 1 == NUM_RUNS:
            print(f"Completed seed {run_idx + 1}/{NUM_RUNS}")

    # 4. Thống kê kết quả
    stat_no_repair = aggregate_run_results("GA without Repair", ga_no_repair_runs, is_deterministic=False)
    stat_hybrid = aggregate_run_results("Hybrid GA + Repair", hybrid_ga_runs, is_deterministic=False)
    stat_greedy = aggregate_run_results("Greedy Search", greedy_runs, is_deterministic=True)
    stat_random = aggregate_run_results("Random Search", random_search_runs, is_deterministic=False)

    summary_list = [stat_no_repair, stat_hybrid, stat_greedy, stat_random]

    # 5. In bảng thống kê tổng hợp
    BenchmarkEvaluator.print_summary_table(summary_list)

    # 6. Lưu kết quả ra file JSON
    os.makedirs("evaluation", exist_ok=True)
    json_path = "evaluation/benchmark_results_multiseed.json"
    data_to_save = make_json_serializable({
        "summary": summary_list,
        "runs": {
            "GA without Repair": ga_no_repair_runs,
            "Hybrid GA + Repair": hybrid_ga_runs,
            "Greedy Search": greedy_runs,
            "Random Search": random_search_runs,
        }
    })
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(data_to_save, f, ensure_ascii=False, indent=2)
    print(f"\n--> Đã lưu kết quả chi tiết multi-seed benchmark tại: {json_path}")

    # 7. Vẽ đồ thị hội tụ đại diện cho representative seed (seed 0)
    ConvergenceVisualizer.plot_convergence(
        ga_no_repair_runs[0]["history"],
        hybrid_ga_runs[0]["history"],
        random_search_runs[0]["history"],
        hard_output_path="evaluation/convergence_hard.png",
        soft_output_path="evaluation/convergence_soft.png",
        evaluation_budget=EVALUATION_BUDGET
    )

    # 8. Export Best Timetable to CSV and Metadata JSON
    if best_hybrid_run and best_hybrid_run.get("best_schedule"):
        csv_path = "evaluation/exports/best_timetable.csv"
        metadata_path = "evaluation/exports/best_timetable_metadata.json"

        metadata = {
            "method": best_hybrid_run["method"],
            "dataset_preset": "MEDIUM",
            "seed": best_hybrid_run["seed"],
            "hard_violations": best_hybrid_run["hard_violations"],
            "raw_soft_violations": best_hybrid_run["raw_soft_violations"],
            "soft_penalty": best_hybrid_run["soft_penalty"],
            "fitness": best_hybrid_run["score"],
            "fitness_evaluations": best_hybrid_run["fitness_evaluations"],
            "runtime_seconds": best_hybrid_run["runtime_seconds"],
            "course_sections": len(dataset["course_sections"]),
            "lecturers": len(dataset["lecturers"]),
            "rooms": len(dataset["rooms"]),
            "student_groups": len(dataset["student_groups"]),
            "timeslots": len(dataset["timeslots"]),
        }

        export_schedule_to_csv(
            schedule=best_hybrid_run["best_schedule"],
            dataset=dataset,
            output_path=csv_path,
            metadata=metadata
        )
        export_metadata_to_json(
            metadata=metadata,
            output_path=metadata_path
        )

        print("\n" + "=" * 80)
        print("Đã xuất thời khóa biểu tốt nhất:")
        print(f"  CSV: {csv_path}")
        print(f"  Metadata: {metadata_path}")
        print(f"\nBest Hybrid seed: {best_hybrid_run['seed']}")
        print(f"Hard violations: {best_hybrid_run['hard_violations']}")
        print(f"Raw soft violations: {best_hybrid_run['raw_soft_violations']}")
        print(f"Soft penalty: {best_hybrid_run['soft_penalty']}")
        print("=" * 80)

if __name__ == "__main__":
    main()
