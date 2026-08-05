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
        print(f"{'Phương Pháp':<18} | {'Thời Gian (s)':<14} | {'Hard Violations':<16} | {'Raw Soft Violations':<20} | {'Soft Penalty':<14} | {'Search Evals':<14} | {'Fitness Final'}")
        print("-" * 120)
        for method, res in results.items():
            raw_soft = res.get('raw_soft_violations', sum(res.get('soft_details', {}).values()) if 'soft_details' in res else res.get('soft_violations', 0))
            soft_pen = res.get('soft_penalty', res.get('soft_violations', 0))
            evals = res.get('search_fitness_evaluations', res.get('fitness_evaluations', 'N/A'))
            runtime = res.get('runtime_seconds', res.get('runtime', 0.0))
            hard_v = res.get('final_hard_violations', res.get('hard_violations', 0))
            score = res.get('score', res.get('best_score', 0.0))
            print(f"{method:<18} | {runtime:<14.4f} | {hard_v:<16} | {raw_soft:<20} | {soft_pen:<14} | {evals:<14} | {score:<.2f}")
        print("=" * 120)

    @staticmethod
    def print_summary_table(summary_list: List[Dict[str, Any]]):
        BenchmarkEvaluator.print_quality_table(summary_list)
        BenchmarkEvaluator.print_typical_cost_table(summary_list)
        has_repair_methods = any("repair" in s.get("method", "").lower() or s.get("total_repair_calls", 0) > 0 for s in summary_list)
        if has_repair_methods:
            BenchmarkEvaluator.print_repair_aggregate_table(summary_list)


    @staticmethod
    def print_quality_table(summary_list: List[Dict[str, Any]]):
        print("\n" + "=" * 115)
        print("MULTI-SEED TIMETABLE ALGORITHM BENCHMARK — 1. QUALITY SUMMARY TABLE")
        print("=" * 115)
        print(f"{'Method':<18} | {'Runs':<6} | {'Feasible %':<12} | {'Med Hard':<10} | {'Med Soft Pen':<14} | {'Mean Soft Pen':<15}")
        print("-" * 115)
        for stat in summary_list:
            method = stat.get("method", "")
            runs = stat.get("runs", stat.get("run_count", 0))
            feas_pct = stat.get("feasible_rate", stat.get("hard_feasible_rate", 0.0)) * 100.0
            med_h = stat.get("median_final_hard", stat.get("median_hard", 0.0))
            med_s_pen = stat.get("median_final_soft", stat.get("median_soft_penalty", 0.0))
            mean_s_pen = stat.get("mean_final_soft", stat.get("mean_soft_penalty", 0.0))

            print(f"{method:<18} | {runs:<6} | {feas_pct:<11.1f}% | {med_h:<10.1f} | {med_s_pen:<14.1f} | {mean_s_pen:<15.2f}")
        print("=" * 115)

    @staticmethod
    def print_typical_cost_table(summary_list: List[Dict[str, Any]]):
        print("\n" + "=" * 180)
        print("MULTI-SEED TIMETABLE ALGORITHM BENCHMARK — 2. TYPICAL PER-RUN COST TABLE (MEDIANS)")
        print("=" * 180)
        print(f"{'Method':<18} | {'Runs':<6} | {'Med Runtime (s)':<16} | {'Med TTFF (s)':<14} | {'Med Search Fit':<15} | {'Med Search Const':<17} | {'Med Internal Const':<19} | {'Med Report Const':<17} | {'Med Total Const':<16} | {'Med Cand Checks':<16} | {'Med Repair Calls':<16}")
        print("-" * 180)
        for stat in summary_list:
            method = stat.get("method", "")
            runs = stat.get("runs", stat.get("run_count", 0))
            med_time = stat.get("median_runtime_seconds", stat.get("runtime_median", 0.0))
            med_ttff = stat.get("median_time_to_first_feasible_seconds", stat.get("time_to_first_feasible_median"))
            ttff_str = f"{med_ttff:.4f}" if med_ttff is not None else "N/A"
            search_fit = stat.get("median_search_fitness_evaluations", stat.get("search_evaluations_median", 0))
            search_c = stat.get("median_search_constraint_evaluations", search_fit * 2)
            internal_c = stat.get("median_internal_constraint_evaluations", 0)
            report_c = stat.get("median_reporting_constraint_evaluations", 0)
            total_c = stat.get("median_total_constraint_evaluations", stat.get("total_constraint_evaluations_median", 0))
            cand_c = stat.get("median_candidate_checks", stat.get("candidate_checks_median", 0))
            rep_c = stat.get("median_repair_calls", stat.get("repair_calls_median", 0))

            print(f"{method:<18} | {runs:<6} | {med_time:<16.4f} | {ttff_str:<14} | {search_fit:<15.0f} | {search_c:<17.0f} | {internal_c:<19.0f} | {report_c:<17.0f} | {total_c:<16.0f} | {cand_c:<16.0f} | {rep_c:<16.0f}")
        print("=" * 180)


    @staticmethod
    def print_repair_aggregate_table(summary_list: List[Dict[str, Any]]):
        print("\n" + "=" * 135)
        print("MULTI-SEED TIMETABLE ALGORITHM BENCHMARK — 3. REPAIR AGGREGATE TOTALS TABLE")
        print("=" * 135)
        print(f"{'Method':<18} | {'Total Calls':<14} | {'Total Improved':<16} | {'Total Unchanged':<16} | {'Total Failed':<14} | {'Improvement Rate':<18} | {'Non-failure Rate':<18}")
        print("-" * 135)
        for stat in summary_list:
            method = stat.get("method", "")
            tot_calls = stat.get("total_repair_calls", 0)
            tot_imp = stat.get("total_repair_improved", stat.get("repair_improved_total", 0))
            tot_unch = stat.get("total_repair_unchanged", stat.get("repair_unchanged_total", 0))
            tot_fail = stat.get("total_repair_failed", stat.get("repair_failed_total", 0))

            imp_rate = stat.get("improvement_rate")
            non_fail_rate = stat.get("non_failure_rate")

            imp_str = f"{imp_rate * 100.0:.1f}%" if imp_rate is not None else "N/A"
            non_fail_str = f"{non_fail_rate * 100.0:.1f}%" if non_fail_rate is not None else "N/A"

            print(f"{method:<18} | {tot_calls:<14} | {tot_imp:<16} | {tot_unch:<16} | {tot_fail:<14} | {imp_str:<18} | {non_fail_str:<18}")
        print("=" * 135)


