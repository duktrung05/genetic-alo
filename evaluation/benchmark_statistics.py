"""Benchmark Statistics Aggregator Module.

Aggregates stochastic algorithm runs across seeds into summary metrics.
"""

from typing import List, Dict, Any
from statistics import mean, median, pstdev

def aggregate_run_results(method_name: str, runs: List[Dict[str, Any]], is_deterministic: bool = False) -> Dict[str, Any]:
    """Aggregate multi-seed benchmark run results into descriptive summary statistics."""
    if not runs:
        raise ValueError(f"No run data available for method: {method_name}")

    total_runs = len(runs)

    fitnesses = [r["score"] for r in runs]
    hards = [r["hard_violations"] for r in runs]
    raw_softs = [r.get("raw_soft_violations", r.get("soft_penalty", 0)) for r in runs]
    soft_penalties = [r["soft_penalty"] for r in runs]
    runtimes = [r["runtime_seconds"] for r in runs]
    evaluations = [r["fitness_evaluations"] for r in runs]

    feasible_runs = [r for r in runs if r.get("is_hard_feasible", r["hard_violations"] == 0)]
    feasible_count = len(feasible_runs)
    perfect_count = sum(1 for r in runs if r.get("is_perfect", (r["hard_violations"] == 0 and r["soft_penalty"] == 0)))

    feasible_softs = [r["soft_penalty"] for r in feasible_runs] if feasible_runs else []

    best_run = min(runs, key=lambda r: (r["hard_violations"], r["soft_penalty"]))
    worst_run = max(runs, key=lambda r: (r["hard_violations"], r["soft_penalty"]))

    def calc_std(values: list) -> float:
        if len(values) <= 1 or is_deterministic:
            return 0.0
        return float(pstdev(values))

    gen_first_feasible = [r.get("generation_to_first_feasible", 0) for r in feasible_runs if "generation_to_first_feasible" in r and r.get("generation_to_first_feasible") != "N/A"]
    time_first_feasible = [r.get("time_to_first_feasible", 0.0) for r in feasible_runs if "time_to_first_feasible" in r and r.get("time_to_first_feasible") != "N/A"]

    return {
        "method": method_name,
        "runs": total_runs,
        "is_deterministic": is_deterministic,

        "feasible_count": feasible_count,
        "feasible_rate": float(feasible_count / total_runs),
        "hard_feasible_rate": float(feasible_count / total_runs),
        "perfect_count": perfect_count,
        "perfect_rate": float(perfect_count / total_runs),
        "perfect_solution_rate": float(perfect_count / total_runs),

        "hard_mean": float(mean(hards)),
        "hard_median": float(median(hards)),
        "median_hard": float(median(hards)),
        "mean_hard": float(mean(hards)),
        "hard_std": calc_std(hards),
        "hard_min": min(hards),
        "hard_max": max(hards),

        "soft_all_runs_mean": float(mean(soft_penalties)),
        "soft_all_runs_median": float(median(soft_penalties)),

        "soft_feasible_runs_count": feasible_count,
        "soft_feasible_mean": float(mean(feasible_softs)) if feasible_softs else None,
        "soft_feasible_median": float(median(feasible_softs)) if feasible_softs else None,
        "soft_feasible_std": calc_std(feasible_softs) if feasible_softs else None,
        "soft_feasible_min": min(feasible_softs) if feasible_softs else None,
        "soft_feasible_max": max(feasible_softs) if feasible_softs else None,

        "mean_soft_penalty": float(mean(soft_penalties)),
        "median_soft_penalty": float(median(soft_penalties)),
        "best_soft_penalty": best_run["soft_penalty"],
        "worst_soft_penalty": worst_run["soft_penalty"],

        "runtime_mean": float(mean(runtimes)),
        "runtime_median": float(median(runtimes)),
        "runtime_std": calc_std(runtimes),
        "mean_runtime_seconds": float(mean(runtimes)),
        "median_runtime_seconds": float(median(runtimes)),

        "evaluations_mean": float(mean(evaluations)),
        "evaluations_median": float(median(evaluations)),
        "mean_fitness_evaluations": float(mean(evaluations)),
        "median_fitness_evaluations": float(median(evaluations)),

        "generation_to_first_feasible_median": float(median(gen_first_feasible)) if gen_first_feasible else None,
        "time_to_first_feasible_mean": float(mean(time_first_feasible)) if time_first_feasible else None,

        "best_run": best_run,
        "worst_run": worst_run
    }
