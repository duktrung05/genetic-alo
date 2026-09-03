import sys
import json
import os
import csv
import datetime
import argparse
from pathlib import Path

sys.stdout.reconfigure(encoding='utf-8')

from dataset import DatasetFactory, ExcelDatasetLoader

from evaluation import (
    BenchmarkEvaluator,
    ConvergenceVisualizer,
    export_schedule_to_excel,
    METHOD_DISPLAY_NAMES,
    METHOD_ROLES,
    METHOD_RUNNERS,
    parse_methods,
)

from evaluation.benchmark_statistics import aggregate_run_results
from evaluation.run_metrics import validate_search_budget



def parse_args():
    """Phân tích tham số dòng lệnh cho chế độ chạy thử nghiệm benchmark, chọn phương pháp và dữ liệu đầu vào."""
    parser = argparse.ArgumentParser(description="GA Timetable Benchmark Suite")
    parser.add_argument(
        "--mode",
        choices=["fast", "report", "quick"],
        default="fast",
        help="Benchmark mode: 'fast'/'quick' (3 seeds, 1000 evals) or 'report' (30 seeds, 4800 evals)"
    )
    parser.add_argument(
        "--methods",
        type=str,
        default="ga_repair_sls,ga_repair,ga,repair_only,greedy",
        help=(
            "Comma-separated methods: repair_only, ga, ga_repair, "
            "ga_repair_sls, greedy, random. Deprecated alias: hybrid=ga_repair."
        )
    )
    parser.add_argument(
        "--seeds",
        type=str,
        default=None,
        help="Seed specification string (e.g. '0-29', '0,1,2', '0-4,10,12')"
    )
    parser.add_argument(
        "--search-evaluation-budget",
        type=int,
        default=None,
        help="Search evaluation budget (overrides mode default)"
    )
    parser.add_argument(
        "--experiment-name",
        type=str,
        default=None,
        help="Custom experiment name for output directory"
    )
    parser.add_argument(
        "--output-dir",
        type=str,
        default=None,
        help="Custom output directory path"
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
        default="data/instances/instance_easy.xlsx",
        help="Path to Excel dataset file when data-source is 'excel'",
    )
    parser.add_argument(
        "--preset",
        choices=["small", "medium"],
        default="small",
        help="Mock dataset preset size (when --data-source=mock)"
    )
    parser.add_argument(
        "--dataset-seed",
        type=int,
        default=42,
        help="Random seed for mock dataset generation (when --data-source=mock)"
    )
    return parser.parse_args()


def make_json_serializable(obj):
    """Chuyển đổi đệ quy cấu trúc kết quả benchmark thành dictionary để ghi JSON."""
    if isinstance(obj, dict):
        return {k: make_json_serializable(v) for k, v in obj.items() if k not in ("best_schedule", "schedule")}
    elif isinstance(obj, list):
        return [make_json_serializable(v) for v in obj]
    elif isinstance(obj, (int, float, str, bool, type(None))):
        return obj
    else:
        return str(obj)


def parse_seed_spec(seed_spec: str) -> list:
    """Phân tích chuỗi quy định seed (ví dụ: '0-9' hoặc '0,1,2') thành danh sách các số nguyên seed duy nhất."""
    if not seed_spec or not seed_spec.strip():
        return list(range(30))
    seeds = []
    parts = seed_spec.split(",")
    for part in parts:
        part = part.strip()
        if "-" in part:
            start, end = part.split("-")
            seeds.extend(range(int(start), int(end) + 1))
        else:
            seeds.append(int(part))
    return sorted(list(set(seeds)))


def select_best_feasible_run(all_runs: list, dataset: dict):
    """Re-evaluate schedules and return the best hard-feasible run for export.

    Benchmark result dictionaries are reporting artifacts, not a source of
    truth for export safety. This function independently verifies each stored
    schedule before ranking feasible candidates by weighted soft penalty.
    """
    from constraints import ConstraintEvaluator

    evaluator = ConstraintEvaluator(dataset)
    candidates = []

    for position, run in enumerate(all_runs):
        schedule = run.get("best_schedule") if isinstance(run, dict) else None
        genes = getattr(schedule, "genes", None)
        if not isinstance(genes, list) or not genes:
            continue

        try:
            evaluation = evaluator.evaluate_unified(schedule, category="reporting")
        except (AttributeError, KeyError, TypeError, ValueError):
            continue

        if evaluation.hard_violations != 0:
            continue

        normalized_run = dict(run)
        raw_soft = sum(item.raw_count for item in evaluation.soft_breakdown)
        normalized_run.update({
            "hard_violations": 0,
            "soft_violations": evaluation.soft_penalty,
            "soft_penalty": evaluation.soft_penalty,
            "raw_soft_violations": raw_soft,
            "score": float(evaluation.soft_penalty),
        })
        candidates.append((evaluation.soft_penalty, raw_soft, position, normalized_run))

    if not candidates:
        return None
    return min(candidates, key=lambda item: item[:3])[3]


def main():
    """Điểm khởi chạy chính cho bộ thử nghiệm benchmark thuật toán xếp thời khóa biểu."""
    args = parse_args()
    selected_methods = parse_methods(args.methods)

    if args.seeds:
        seeds = parse_seed_spec(args.seeds)
        num_runs = len(seeds)
    elif args.mode in ("fast", "quick"):
        num_runs = 3
        seeds = list(range(num_runs))
    else:
        num_runs = 30
        seeds = list(range(num_runs))

    if args.search_evaluation_budget:
        evaluation_budget = args.search_evaluation_budget
    elif args.mode in ("fast", "quick"):
        evaluation_budget = 1000
    else:
        evaluation_budget = 4800

    generations = 20 if args.mode in ("fast", "quick") else 80

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
    exp_name = args.experiment_name if args.experiment_name else f"benchmark_{timestamp}"

    if args.output_dir:
        benchmark_run_dir = Path(args.output_dir)
    else:
        benchmark_run_dir = base_dir / "outputs" / "benchmark" / exp_name

    benchmark_run_dir.mkdir(parents=True, exist_ok=True)


    print("=" * 80)
    print(f"OFFICIAL BENCHMARK SUITE — Experiment: {exp_name} (Mode: {args.mode.upper()})")
    print(f"Selected Methods: {', '.join([METHOD_DISPLAY_NAMES[m] for m in selected_methods])}")
    print(f"Seeds ({num_runs}): {seeds} | Budget: {evaluation_budget} search evals/run")
    print(f"Output Directory: {benchmark_run_dir}")
    print("=" * 80)


    # 1. Chỉ nạp bộ dữ liệu MỘT LẦN
    json_norm_path = "outputs/datasets/instance_easy.normalized.json"
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
        print(f"\n[Phase 1] Đang tạo Mock Dataset preset '{args.preset}' (seed={args.dataset_seed})...")
        if args.preset == "small":
            dataset = DatasetFactory.create_small_dataset()
        else:
            dataset = DatasetFactory.create_medium_dataset(seed=args.dataset_seed)
        dataset_preset = f"MOCK_{args.preset.upper()}"

    dataset_snap_file = benchmark_run_dir / "dataset_snapshot.json"
    ExcelDatasetLoader.export_normalized_json(dataset, str(dataset_snap_file))

    # In các ràng buộc mềm đã nạp
    if "constraints" in dataset and dataset["constraints"]:
        soft_defs = [c for c in dataset["constraints"] if c.constraint_type == "SOFT"]
        print("\nSOFT CONSTRAINTS LOADED FROM EXCEL:")
        for c in soft_defs:
            key = ExcelDatasetLoader.SOFT_CONSTRAINT_KEY_BY_ID.get(c.constraint_id, c.constraint_id)
            print(f"  {c.constraint_id} | {key:<26} | weight={c.weight:<3} | enabled={c.enabled}")
    else:
        print("\nSOFT CONSTRAINTS LOADED: DEFAULT CONFIG (S1=10, S2=5, S3=4, S4=2, S5=8)")

    # Lưu config.json
    config_data = {
        "benchmark_id": f"benchmark_{timestamp}",
        "generated_at": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "dataset_source": args.data_source,
        "dataset_path": args.input if args.data_source == "excel" else f"mock_seed_{args.dataset_seed}",
        "dataset_preset": dataset_preset,
        "mode": args.mode,
        "num_runs": num_runs,
        "seeds": seeds,
        "selected_methods": selected_methods,
        "primary_method": "ga_repair_sls",
        "search_evaluation_budget": evaluation_budget,
        "ga_config": ga_config,
        "platform": sys.platform,
    }
    with open(benchmark_run_dir / "config.json", "w", encoding="utf-8") as f:
        json.dump(config_data, f, ensure_ascii=False, indent=2)

    # 2. CHỈ chạy các phương pháp đã chọn
    runs_by_method: dict = {}
    all_runs_flat = []

    for method_id in selected_methods:
        runner = METHOD_RUNNERS[method_id]
        display_name = METHOD_DISPLAY_NAMES[method_id]
        print(f"\n[Phase 2] Running method '{display_name}' ({METHOD_ROLES[method_id]})...")

        if method_id == "greedy":
            # Đường cơ sở heuristic xác định chỉ chạy MỘT LẦN
            run_res = runner(dataset, ga_config, evaluation_budget, 0)
            runs_by_method[method_id] = [run_res]
            all_runs_flat.append(run_res)
        else:
            method_runs = []
            for run_idx, seed in enumerate(seeds):
                run_res = runner(dataset, ga_config, evaluation_budget, seed)
                method_runs.append(run_res)
                all_runs_flat.append(run_res)
                if (run_idx + 1) % 5 == 0 or (run_idx + 1) == num_runs or args.mode in ("fast", "quick"):
                    print(f"  Completed seed {run_idx + 1}/{num_runs} (seed={seed})")
            runs_by_method[method_id] = method_runs

    # Kiểm tra ngân sách tìm kiếm cho các phương pháp ngẫu nhiên
    for method_id in selected_methods:
        if method_id != "greedy":
            for r in runs_by_method[method_id]:
                if "run_metrics" in r:
                    validate_search_budget(r["run_metrics"], evaluation_budget)

    # 3. CHỈ tính thống kê tổng hợp cho các phương pháp đã chọn
    summary_list = []
    for method_id in selected_methods:
        runs = runs_by_method[method_id]
        is_det = (method_id == "greedy")
        stat = aggregate_run_results(METHOD_DISPLAY_NAMES[method_id], runs, is_deterministic=is_det)
        summary_list.append(stat)

    # 4. In các bảng tổng kết
    BenchmarkEvaluator.print_summary_table(summary_list)

    # 5. Lưu raw_runs.json và raw_runs.csv (CHỈ các phương pháp đã chọn)
    with open(benchmark_run_dir / "raw_runs.json", "w", encoding="utf-8") as f:
        json.dump(make_json_serializable(all_runs_flat), f, ensure_ascii=False, indent=2)

    raw_csv_cols = [
        "method", "seed", "is_hard_feasible", "is_perfect", "hard_violations",
        "raw_soft_violations", "soft_penalty", "runtime_seconds",
        "time_to_first_feasible_seconds", "search_fitness_evaluations",
        "search_hard_constraint_evaluations", "search_soft_constraint_evaluations",
        "search_constraint_evaluations", "internal_hard_constraint_evaluations",
        "internal_soft_constraint_evaluations", "internal_constraint_evaluations",
        "reporting_hard_constraint_evaluations", "reporting_soft_constraint_evaluations",
        "reporting_constraint_evaluations", "total_constraint_evaluations",
        "candidate_checks", "repair_calls", "repair_improved", "repair_unchanged",
        "repair_failed", "first_feasible_generation", "first_feasible_search_evaluation",
        "first_feasible_total_constraint_evaluation"
    ]
    with open(benchmark_run_dir / "raw_runs.csv", "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=raw_csv_cols)
        writer.writeheader()
        for r in all_runs_flat:
            row_dict = {c: r.get(c, "") for c in raw_csv_cols}
            writer.writerow(row_dict)

    # 6. Lưu summary.json và summary.csv (CHỈ các phương pháp đã chọn)
    with open(benchmark_run_dir / "summary.json", "w", encoding="utf-8") as f:
        json.dump(make_json_serializable(summary_list), f, ensure_ascii=False, indent=2)

    sum_csv_cols = [
        "method", "runs", "is_deterministic", "feasible_count", "feasible_rate",
        "perfect_count", "perfect_rate", "hard_mean", "hard_median", "hard_std",
        "soft_feasible_mean", "soft_feasible_median", "runtime_mean", "runtime_median",
        "search_evaluations_mean", "total_constraint_evaluations_median",
        "candidate_checks_median", "repair_calls_median", "time_to_first_feasible_median"
    ]
    with open(benchmark_run_dir / "summary.csv", "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=sum_csv_cols)
        writer.writeheader()
        for s in summary_list:
            row_dict = {c: s.get(c, "") for c in sum_csv_cols}
            writer.writerow(row_dict)




    # 7. Tạo biểu đồ hội tụ (chỉ cho phương pháp có lịch sử)
    ga_no_rep_runs = runs_by_method.get("ga", [])
    ga_repair_runs = runs_by_method.get("ga_repair", [])
    if not ga_repair_runs:
        ga_repair_runs = runs_by_method.get("ga_repair_sls", [])
    random_search_runs = runs_by_method.get("random", [])

    if ga_no_rep_runs or ga_repair_runs or random_search_runs:
        hard_chart_path = str(benchmark_run_dir / "convergence_hard.png")
        soft_chart_path = str(benchmark_run_dir / "convergence_soft.png")
        ConvergenceVisualizer.plot_convergence(
            ga_no_rep_runs,
            ga_repair_runs,
            random_search_runs,
            hard_output_path=hard_chart_path,
            soft_output_path=soft_chart_path,
            evaluation_budget=evaluation_budget
        )

    # 8. Kiểm tra độc lập tính khả thi, sau đó xuất lịch hợp lệ tốt nhất.
    best_overall_run = select_best_feasible_run(all_runs_flat, dataset)

    if best_overall_run and best_overall_run.get("best_schedule"):
        best_excel_path = str(benchmark_run_dir / "best_timetable.xlsx")
        legacy_excel_path = str(base_dir / "outputs" / "timetables" / "best_timetable.xlsx")

        meta_export = {
            "method": best_overall_run["method"],
            "primary_method": "ga_repair_sls",
            "selected_methods": ",".join(selected_methods),
            "dataset_preset": dataset_preset,
            "seed": best_overall_run.get("seed", 0),
            "pop_size": ga_config["pop_size"],
            "generations": ga_config["generations"],
            "evaluation_budget": evaluation_budget,
            "hard_violations": best_overall_run["hard_violations"],
            "raw_soft_violations": best_overall_run.get("raw_soft_violations", 0),
            "soft_penalty": best_overall_run["soft_penalty"],
            "score": best_overall_run.get("score", 0.0),
            "fitness_evaluations": best_overall_run.get("fitness_evaluations", 0),
            "runtime_seconds": best_overall_run.get("runtime_seconds", 0.0),
            "generation_to_first_feasible": best_overall_run.get("generation_to_first_feasible", 0),
            "time_to_first_feasible": best_overall_run.get("time_to_first_feasible", 0.0),
            "all_runs_flat": all_runs_flat,
            "summary_list": summary_list,
        }

        export_schedule_to_excel(
            schedule=best_overall_run["best_schedule"],
            dataset=dataset,
            output_path=best_excel_path,
            metadata=meta_export,
            allow_infeasible_export=False
        )

        export_schedule_to_excel(
            schedule=best_overall_run["best_schedule"],
            dataset=dataset,
            output_path=legacy_excel_path,
            metadata=meta_export,
            allow_infeasible_export=False
        )

        print("\n" + "=" * 80)
        print("ĐÃ HOÀN THÀNH BENCHMARK VÀ XUẤT WORKBOOK THỜI KHÓA BIỂU (7 SHEETS):")
        print(f"  Benchmark Directory: {benchmark_run_dir}")
        print(f"  Best Timetable Excel: {best_excel_path}")
        print(f"  Best Method: {best_overall_run['method']}")
        print(f"  Best Seed: {best_overall_run.get('seed', 0)}")
        print(f"  Hard Violations: {best_overall_run['hard_violations']}")
        print(f"  Soft Penalty Total: {best_overall_run['soft_penalty']}")
        print("=" * 80)
    else:
        print("\n" + "=" * 80)
        print("BENCHMARK ĐÃ HOÀN THÀNH NHƯNG CHƯA CÓ LỊCH HARD-FEASIBLE ĐỂ XUẤT.")
        print(f"  Benchmark Directory: {benchmark_run_dir}")
        print("  Raw runs và summary vẫn được lưu đầy đủ để phân tích.")
        print("=" * 80)


if __name__ == "__main__":
    main()
