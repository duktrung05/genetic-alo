from types import SimpleNamespace

from scripts.run_final_benchmark import EVALUATION_BUDGET, aggregate_runs, normalize_run


def _run(dataset, method, seed, feasible, hard, soft, repair=0, sls=0):
    return {
        "dataset": dataset, "method": method, "method_name": method, "seed": seed,
        "feasible": feasible, "final_hard_violations": hard, "final_soft_score": soft,
        "soft_score_comparable": feasible,
        "first_feasible_generation": 1 if feasible else None,
        "first_feasible_ga_evaluation": 10 if feasible else None,
        "runtime_seconds": 1.0, "ga_evaluations": 1000,
        "repair_evaluations": repair, "sls_evaluations": sls,
        "total_evaluations": 1000 + repair + sls,
    }


def test_aggregate_soft_statistics_use_feasible_runs_only():
    runs = [
        _run("EASY", "ga", 0, False, 2, 999.0),
        _run("EASY", "ga", 1, True, 0, 10.0),
    ]
    summary = next(row for row in aggregate_runs(runs) if row["dataset"] == "EASY" and row["method"] == "ga")
    assert summary["feasible_count"] == 1
    assert summary["soft_score_feasible_only"]["mean"] == 10.0


def test_normalized_run_separates_and_totals_work_counters():
    metrics = SimpleNamespace(
        feasible=True, final_hard_violations=0, final_soft_penalty=3.5,
        first_feasible_generation=1, first_feasible_search_evaluation=63,
        runtime_seconds=2.0, search_fitness_evaluations=EVALUATION_BUDGET,
        soft_ls_candidate_checks=80, method="GA + Repair + SLS (Production)",
    )
    row = normalize_run(
        "EASY", "ga_repair_sls", 0,
        {"run_metrics": metrics, "repair_stats": {"candidate_checks": 20}},
    )
    assert row["ga_evaluations"] == 1000
    assert row["repair_evaluations"] == 20
    assert row["sls_evaluations"] == 80
    assert row["total_evaluations"] == 1100
