import time
from typing import Dict, List, Any

class BenchmarkEvaluator:
    @staticmethod
    def calculate_conflict_reduction_rate(initial_violations: int, final_violations: int) -> float:
        if initial_violations == 0:
            return 100.0
        reduction = ((initial_violations - final_violations) / initial_violations) * 100.0
        return max(0.0, reduction)

    @staticmethod
    def print_comparison_table(results: Dict[str, dict]):
        print("\n" + "=" * 120)
        print("BẢNG SO SÁNH GA WITHOUT REPAIR, HYBRID GA, GREEDY VÀ RANDOM SEARCH")
        print("=" * 120)
        print(f"{'Phương Pháp':<18} | {'Thời Gian (s)':<14} | {'Hard Violations':<16} | {'Raw Soft Violations':<20} | {'Soft Penalty':<14} | {'Evaluations':<14} | {'Fitness Final'}")
        print("-" * 120)
        for method, res in results.items():
            raw_soft = res.get('raw_soft_violations', sum(res.get('soft_details', {}).values()) if 'soft_details' in res else res.get('soft_violations', 0))
            soft_pen = res.get('soft_penalty', res.get('soft_violations', 0))
            evals = res.get('fitness_evaluations', 'N/A')
            print(f"{method:<18} | {res['runtime']:<14.4f} | {res['hard_violations']:<16} | {raw_soft:<20} | {soft_pen:<14} | {evals:<14} | {res['best_score']:<.2f}")
        print("=" * 120)

    @staticmethod
    def print_summary_table(summary_list: List[Dict[str, Any]]):
        print("\n" + "=" * 135)
        print("MULTI-SEED TIMETABLE ALGORITHM BENCHMARK (AGGREGATED STATISTICS)")
        print("=" * 135)
        print(f"{'Method':<18} | {'Runs':<6} | {'Med Hard':<10} | {'Med Soft Pen':<14} | {'Mean Soft Pen':<15} | {'Feasible %':<12} | {'Perfect %':<11} | {'Mean Time (s)':<14} | {'Mean Evals':<12}")
        print("-" * 135)
        for stat in summary_list:
            method = stat["method"]
            runs = stat["runs"]
            med_h = stat["median_hard"]
            med_s_pen = stat["median_soft_penalty"]
            mean_s_pen = stat["mean_soft_penalty"]
            feas_pct = stat["hard_feasible_rate"] * 100.0
            perf_pct = stat["perfect_solution_rate"] * 100.0
            mean_time = stat["mean_runtime_seconds"]
            mean_evals = stat["mean_fitness_evaluations"]

            print(f"{method:<18} | {runs:<6} | {med_h:<10.1f} | {med_s_pen:<14.1f} | {mean_s_pen:<15.2f} | {feas_pct:<11.1f}% | {perf_pct:<10.1f}% | {mean_time:<14.4f} | {mean_evals:<12.1f}")
        print("=" * 135)
