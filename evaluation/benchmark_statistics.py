from typing import List, Dict, Any
from statistics import mean, median, pstdev
from evaluation.run_metrics import AggregateRunMetrics


def aggregate_run_results(method_name: str, runs: List[Dict[str, Any]], is_deterministic: bool = False) -> Dict[str, Any]:
    """Tổng hợp kết quả chạy thử nghiệm qua nhiều seed thành các thống kê mô tả."""

    if not runs:
        raise ValueError(f"No run data available for method: {method_name}")

    # Kiểm tra chỉ số của từng lần chạy trước khi tổng hợp
    for r in runs:
        if isinstance(r, dict) and "run_metrics" in r and hasattr(r["run_metrics"], "validate"):
            r["run_metrics"].validate()
        elif isinstance(r, dict) and "repair_calls" in r:
            r_calls = r.get("repair_calls", 0)
            r_imp = r.get("repair_improved", 0)
            r_unch = r.get("repair_unchanged", 0)
            r_fail = r.get("repair_failed", 0)
            if r_calls != (r_imp + r_unch + r_fail):
                raise ValueError(
                    f"Invalid repair metrics for method='{method_name}', seed={r.get('seed')}: "
                    f"repair_calls={r_calls} but statuses sum to {r_imp + r_unch + r_fail}."
                )

    total_runs = len(runs)

    hards = [r["hard_violations"] for r in runs]
    soft_penalties = [r["soft_penalty"] for r in runs]
    runtimes = [r["runtime_seconds"] for r in runs]

    search_evals = [r.get("search_fitness_evaluations", r.get("fitness_evaluations", 0)) for r in runs]
    total_constraint_evals = [r.get("total_constraint_evaluations", 0) for r in runs]
    cand_checks = [r.get("candidate_checks", 0) for r in runs]

    rep_calls = [r.get("repair_calls", 0) for r in runs]
    rep_improved = [r.get("repair_improved", 0) for r in runs]
    rep_unchanged = [r.get("repair_unchanged", 0) for r in runs]
    rep_failed = [r.get("repair_failed", 0) for r in runs]

    total_rep_calls = sum(rep_calls)
    total_rep_imp = sum(rep_improved)
    total_rep_unch = sum(rep_unchanged)
    total_rep_fail = sum(rep_failed)

    if total_rep_calls != (total_rep_imp + total_rep_unch + total_rep_fail):
        raise ValueError(
            f"Aggregate total repair calls invariant violated for {method_name}: "
            f"total_calls={total_rep_calls} != improved ({total_rep_imp}) + unchanged ({total_rep_unch}) + failed ({total_rep_fail})"
        )

    improvement_rate = (total_rep_imp / total_rep_calls) if total_rep_calls > 0 else None
    non_failure_rate = ((total_rep_imp + total_rep_unch) / total_rep_calls) if total_rep_calls > 0 else None

    feasible_runs = [r for r in runs if r.get("is_hard_feasible", r["hard_violations"] == 0)]
    feasible_count = len(feasible_runs)
    perfect_count = sum(1 for r in runs if r.get("is_perfect", (r["hard_violations"] == 0 and r["soft_penalty"] == 0)))

    feasible_softs = [r["soft_penalty"] for r in feasible_runs] if feasible_runs else []

    best_run = min(runs, key=lambda r: (r["hard_violations"], r["soft_penalty"]))
    worst_run = max(runs, key=lambda r: (r["hard_violations"], r["soft_penalty"]))

    # Thu thập TTFF: loại bỏ None / "N/A"
    ttff_vals = []
    for r in feasible_runs:
        t = r.get("time_to_first_feasible_seconds", r.get("time_to_first_feasible"))
        if t is not None and t != "N/A":
            ttff_vals.append(float(t))

    search_const_evals = [r.get("search_constraint_evaluations", r.get("search_fitness_evaluations", 0) * 2) for r in runs]
    internal_const_evals = [r.get("internal_constraint_evaluations", 0) for r in runs]
    reporting_const_evals = [r.get("reporting_constraint_evaluations", 0) for r in runs]

    agg = AggregateRunMetrics(
        method=method_name,
        run_count=total_runs,
        is_deterministic=is_deterministic,
        feasible_count=feasible_count,
        feasible_rate=float(feasible_count / total_runs),
        perfect_count=perfect_count,
        perfect_rate=float(perfect_count / total_runs),
        median_final_hard=float(median(hards)),
        mean_final_hard=float(mean(hards)),
        median_final_soft=float(median(soft_penalties)),
        mean_final_soft=float(mean(soft_penalties)),
        mean_runtime_seconds=float(mean(runtimes)),
        median_runtime_seconds=float(median(runtimes)),
        median_time_to_first_feasible_seconds=float(median(ttff_vals)) if ttff_vals else None,
        mean_time_to_first_feasible_seconds=float(mean(ttff_vals)) if ttff_vals else None,
        median_search_fitness_evaluations=float(median(search_evals)),
        mean_search_fitness_evaluations=float(mean(search_evals)),
        median_search_constraint_evaluations=float(median(search_const_evals)),
        median_internal_constraint_evaluations=float(median(internal_const_evals)),
        median_reporting_constraint_evaluations=float(median(reporting_const_evals)),
        median_total_constraint_evaluations=float(median(total_constraint_evals)),
        median_candidate_checks=float(median(cand_checks)),
        median_repair_calls=float(median(rep_calls)),
        total_repair_calls=total_rep_calls,
        total_repair_improved=total_rep_imp,
        total_repair_unchanged=total_rep_unch,
        total_repair_failed=total_rep_fail,
        improvement_rate=improvement_rate,
        non_failure_rate=non_failure_rate,
        best_run=best_run,
        worst_run=worst_run,
    )


    res_dict = agg.to_dict()
    # Giữ lại các bí danh khóa cũ
    res_dict.update({
        "hard_mean": float(mean(hards)),
        "hard_median": float(median(hards)),
        "soft_all_runs_mean": float(mean(soft_penalties)),
        "soft_all_runs_median": float(median(soft_penalties)),
        "soft_feasible_runs_count": feasible_count,
        "soft_feasible_mean": float(mean(feasible_softs)) if feasible_softs else None,
        "soft_feasible_median": float(median(feasible_softs)) if feasible_softs else None,
        "soft_feasible_std": float(pstdev(feasible_softs)) if len(feasible_softs) > 1 else 0.0,
        "soft_feasible_min": min(feasible_softs) if feasible_softs else None,
        "soft_feasible_max": max(feasible_softs) if feasible_softs else None,
        "runtime_mean": float(mean(runtimes)),
        "runtime_median": float(median(runtimes)),
        "repair_calls_median": float(median(rep_calls)),
        "repair_improved_total": total_rep_imp,
        "repair_unchanged_total": total_rep_unch,
        "repair_failed_total": total_rep_fail,
    })
    return res_dict



