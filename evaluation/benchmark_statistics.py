from typing import List, Dict, Any
from statistics import mean, median, pstdev

def aggregate_run_results(method_name: str, runs: List[Dict[str, Any]], is_deterministic: bool = False) -> Dict[str, Any]:
    if not runs:
        raise ValueError(f"No run data available for method: {method_name}")

    total_runs = len(runs)
    
    fitnesses = [r["score"] for r in runs]
    hards = [r["hard_violations"] for r in runs]
    raw_softs = [r["raw_soft_violations"] for r in runs]
    soft_penalties = [r["soft_penalty"] for r in runs]
    runtimes = [r["runtime_seconds"] for r in runs]
    evaluations = [r["fitness_evaluations"] for r in runs]

    # Best & Worst runs using Lexicographic Fitness (hard_violations, soft_penalty)
    best_run = min(runs, key=lambda r: (r["hard_violations"], r["soft_penalty"]))
    worst_run = max(runs, key=lambda r: (r["hard_violations"], r["soft_penalty"]))

    feasible_count = sum(1 for r in runs if r["is_hard_feasible"])
    perfect_count = sum(1 for r in runs if r["is_perfect"])

    def calc_std(values: list) -> float:
        if len(values) <= 1 or is_deterministic:
            return 0.0
        return float(pstdev(values))

    return {
        "method": method_name,
        "runs": total_runs,
        "is_deterministic": is_deterministic,

        "mean_fitness": float(mean(fitnesses)),
        "median_fitness": float(median(fitnesses)),
        "std_fitness": calc_std(fitnesses),
        "best_fitness": best_run["score"],
        "worst_fitness": worst_run["score"],

        "mean_hard": float(mean(hards)),
        "median_hard": float(median(hards)),
        "best_hard": best_run["hard_violations"],
        "worst_hard": worst_run["hard_violations"],

        "mean_raw_soft": float(mean(raw_softs)),
        "median_raw_soft": float(median(raw_softs)),

        "mean_soft_penalty": float(mean(soft_penalties)),
        "median_soft_penalty": float(median(soft_penalties)),
        "best_soft_penalty": best_run["soft_penalty"],
        "worst_soft_penalty": worst_run["soft_penalty"],

        "hard_feasible_rate": float(feasible_count / total_runs),
        "perfect_solution_rate": float(perfect_count / total_runs),

        "mean_runtime_seconds": float(mean(runtimes)),
        "median_runtime_seconds": float(median(runtimes)),

        "mean_fitness_evaluations": float(mean(evaluations)),
        "median_fitness_evaluations": float(median(evaluations)),

        "best_run": best_run,
        "worst_run": worst_run
    }
