"""Main Entry Point — Production Timetable Generation (Hybrid GA + Repair).

Executes the primary project algorithm (Hybrid GA + Repair) to generate the
official timetable workbook.
"""

import sys
import os
import argparse
import time
from pathlib import Path
import matplotlib.pyplot as plt

sys.stdout.reconfigure(encoding='utf-8')

from dataset import ExcelDatasetLoader
from constraints import ConstraintEvaluator
from ga import GeneticAlgorithmEngine
from evaluation import export_schedule_to_excel, export_schedule_query_data



def parse_args():
    parser = argparse.ArgumentParser(description="Production Timetable Generator (Hybrid GA + Repair)")
    parser.add_argument(
        "--input",
        type=str,
        default="data/01_data_timetable.xlsx",
        help="Input Excel dataset path (default: data/01_data_timetable.xlsx)"
    )
    parser.add_argument(
        "--output",
        type=str,
        default="outputs/production/best_timetable.xlsx",
        help="Output official Excel timetable path (default: outputs/production/best_timetable.xlsx)"
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=42,
        help="Random seed for execution reproducibility (default: 42)"
    )
    parser.add_argument(
        "--search-evaluation-budget",
        type=int,
        default=1000,
        help="Search fitness evaluation budget (default: 1000)"
    )
    parser.add_argument(
        "--population-size",
        type=int,
        default=60,
        help="GA Population Size (default: 60)"
    )
    return parser.parse_args()


def main():
    args = parse_args()
    print("=" * 80)
    print("PRODUCTION TIMETABLE GENERATOR — HYBRID GA + REPAIR (PRIMARY METHOD)")
    print("=" * 80)

    # 1. Load Dataset
    input_path = args.input
    snapshot_path = "outputs/datasets/01_data_timetable.normalized.json"

    if os.path.exists(input_path):
        print(f"\n[Phase 1] Đang tải dữ liệu từ Excel file '{input_path}'...")
        dataset = ExcelDatasetLoader.load_and_validate(input_path)
    elif os.path.exists(snapshot_path):
        print(f"\n[Phase 1] Đang tải dữ liệu từ Normalized JSON Snapshot '{snapshot_path}'...")
        dataset = ExcelDatasetLoader.load_normalized_json(snapshot_path)
    else:
        raise FileNotFoundError(f"Neither Excel input '{input_path}' nor snapshot '{snapshot_path}' exist!")

    # 2. Run Hybrid GA + Repair (Primary Project Method ONLY)
    print("\n[Phase 2] Đang chạy Thuật toán chính: Hybrid GA + Repair...")
    ga_config = {
        "pop_size": args.population_size,
        "generations": 100,
        "crossover_rate": 0.8,
        "mutation_rate": 0.2,
        "hard_weight": 1000,
        "soft_weight": 1,
    }

    engine = GeneticAlgorithmEngine(
        dataset,
        pop_size=ga_config["pop_size"],
        hard_weight=ga_config["hard_weight"],
        soft_weight=ga_config["soft_weight"],
        seed=args.seed,
    )

    start_time = time.perf_counter()
    run_result = engine.run(
        generations=ga_config["generations"],
        crossover_rate=ga_config["crossover_rate"],
        mutation_rate=ga_config["mutation_rate"],
        use_repair=True,
        evaluation_budget=args.search_evaluation_budget,
        seed=args.seed,
    )

    best_schedule = run_result["best_schedule"]
    hard_violations = run_result["hard_violations"]
    soft_penalty = run_result["soft_penalty"]
    metrics = run_result["run_metrics"]

    print("\n" + "=" * 80)
    print("KẾT QUẢ TẠO THỜI KHÓA BIỂU — HYBRID GA + REPAIR:")
    print("=" * 80)
    print(f"  METHOD                   : Hybrid GA + Repair")
    print(f"  Seed                     : {args.seed}")
    print(f"  Search Budget            : {args.search_evaluation_budget}")
    print(f"  Runtime (s)              : {metrics.runtime_seconds:.4f}")
    print(f"  Time to First Feasible   : {metrics.time_to_first_feasible_seconds}")
    print(f"  Final Hard Violations    : {hard_violations}")
    print(f"  Final Soft Penalty       : {soft_penalty}")
    print(f"  Hard Feasible            : {'CÓ (0 vi phạm)' if hard_violations == 0 else 'KHÔNG'}")

    # 3. Soft constraint breakdown
    evaluator = ConstraintEvaluator(dataset)
    unified = evaluator.evaluate_unified(best_schedule)
    print("\n  CHI TIẾT RÀNG BUỘC MỀM (SOFT CONSTRAINTS S1–S5):")
    print(f"  {'ID':<4} | {'Technical Key':<26} | {'Raw':<5} | {'Weight':<6} | {'Weighted Penalty'}")
    print("  " + "-" * 65)
    for item in unified.soft_breakdown:
        print(f"  {item.constraint_id:<4} | {item.constraint_key:<26} | {item.raw_count:<5} | {item.weight:<6} | {item.weighted_penalty}")
    print(f"  TỔNG PHẠM QUY MỀM (SOFT PENALTY): {unified.soft_penalty}")
    print("=" * 80)

    # 4. Export official timetable workbook if feasible
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    meta_export = {
        "method": "Hybrid GA + Repair",
        "primary_method": "hybrid",
        "selected_methods": "hybrid",
        "seed": args.seed,
        "hard_violations": hard_violations,
        "soft_penalty": soft_penalty,
        "runtime_seconds": metrics.runtime_seconds,
        "all_runs_flat": [metrics.to_dict()],
    }

    exported_file = export_schedule_to_excel(
        schedule=best_schedule,
        dataset=dataset,
        output_path=output_path,
        metadata=meta_export,
        allow_infeasible_export=False,
    )
    print(f"\n--> Đã xuất workbook thời khóa biểu chính thức tại: {exported_file}")

    if hard_violations == 0:
        query_json_path = output_path.parent / "schedule_query_data.json"
        query_file = export_schedule_query_data(
            schedule=best_schedule,
            dataset=dataset,
            output_path=query_json_path,
            hard_violations=hard_violations,
            soft_penalty=soft_penalty,
            metadata=meta_export,
        )
        print(f"--> Đã xuất dữ liệu tra cứu JSON tại: {query_file}")

    # 5. Plot Hybrid convergence chart
    history = run_result.get("history", [])
    if history:
        chart_dir = output_path.parent
        chart_path = chart_dir / "convergence_hybrid.png"
        gens = [h["generation"] for h in history]
        hards = [h["best_hard"] for h in history]
        softs = [h["best_soft_penalty"] for h in history]

        fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(12, 4.5))
        ax1.plot(gens, hards, color="#D95F02", linewidth=2, label="Hard Violations")
        ax1.set_title("Hybrid GA + Repair — Hard Violations Convergence")
        ax1.set_xlabel("Generation")
        ax1.set_ylabel("Hard Violations")
        ax1.grid(True, linestyle="--", alpha=0.6)

        ax2.plot(gens, softs, color="#7570B3", linewidth=2, label="Soft Penalty")
        ax2.set_title("Hybrid GA + Repair — Soft Penalty Convergence")
        ax2.set_xlabel("Generation")
        ax2.set_ylabel("Soft Penalty")
        ax2.grid(True, linestyle="--", alpha=0.6)

        plt.tight_layout()
        plt.savefig(chart_path, dpi=300)
        plt.close()
        print(f"--> Đã lưu biểu đồ hội tụ Hybrid tại: {chart_path}")


if __name__ == "__main__":
    main()
