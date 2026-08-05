"""Method Registry Module — Canonical method IDs, runners, and CLI parsing for GA Timetable System."""

from typing import List, Dict, Any, Callable, Optional, Tuple
from domain import Schedule
from evaluation.run_metrics import RunMetrics



SUPPORTED_METHODS: Tuple[str, ...] = ("hybrid", "ga", "greedy", "random")

METHOD_DISPLAY_NAMES: Dict[str, str] = {
    "hybrid": "Hybrid GA + Repair",
    "ga": "GA without Repair",
    "greedy": "Greedy Search",
    "random": "Random Search",
}

METHOD_ROLES: Dict[str, str] = {
    "hybrid": "Primary Proposed Algorithm",
    "ga": "Required Ablation Baseline",
    "greedy": "Optional Heuristic Baseline",
    "random": "Optional Lower-Bound Baseline",
}


def parse_methods(value: str) -> List[str]:
    """Parse comma-separated CLI method string into canonical method IDs.

    Args:
        value: Comma-separated string of methods (e.g. "hybrid,ga,greedy")

    Returns:
        List of canonical method IDs in order of first appearance.

    Raises:
        ValueError: If input is empty, invalid, or contains unsupported methods.
    """
    if not value or not isinstance(value, str) or not value.strip():
        raise ValueError(
            "Methods list cannot be empty. "
            f"Supported methods: {', '.join(SUPPORTED_METHODS)}."
        )

    parts = [p.strip().lower() for p in value.split(",") if p.strip()]
    if not parts:
        raise ValueError(
            "Methods list cannot be empty. "
            f"Supported methods: {', '.join(SUPPORTED_METHODS)}."
        )

    selected: List[str] = []
    for p in parts:
        if p not in SUPPORTED_METHODS:
            raise ValueError(
                f"Unsupported method '{p}'. "
                f"Supported methods: {', '.join(SUPPORTED_METHODS)}."
            )
        if p not in selected:
            selected.append(p)

    return selected


def run_hybrid_runner(dataset: dict, ga_config: dict, budget: int, seed: int) -> dict:
    """Execute Hybrid GA + Repair runner for a single seed."""
    from ga import GeneticAlgorithmEngine
    engine = GeneticAlgorithmEngine(
        dataset,
        pop_size=ga_config.get("pop_size", 60),
        hard_weight=ga_config.get("hard_weight", 1000),
        soft_weight=ga_config.get("soft_weight", 1),
        seed=seed,
    )
    return engine.run(
        generations=ga_config.get("generations", 100),
        crossover_rate=ga_config.get("crossover_rate", 0.8),
        mutation_rate=ga_config.get("mutation_rate", 0.2),
        use_repair=True,
        evaluation_budget=budget,
        seed=seed,
    )


def run_ga_without_repair_runner(dataset: dict, ga_config: dict, budget: int, seed: int) -> dict:
    """Execute GA without Repair runner for a single seed."""
    from ga import GeneticAlgorithmEngine
    engine = GeneticAlgorithmEngine(
        dataset,
        pop_size=ga_config.get("pop_size", 60),
        hard_weight=ga_config.get("hard_weight", 1000),
        soft_weight=ga_config.get("soft_weight", 1),
        seed=seed,
    )
    return engine.run(
        generations=ga_config.get("generations", 100),
        crossover_rate=ga_config.get("crossover_rate", 0.8),
        mutation_rate=ga_config.get("mutation_rate", 0.2),
        use_repair=False,
        evaluation_budget=budget,
        seed=seed,
    )


def run_greedy_runner(dataset: dict, ga_config: dict, budget: int, seed: int) -> dict:
    """Execute Greedy Search runner (deterministic 1-run baseline)."""
    from evaluation.baselines import GreedyScheduler
    scheduler = GreedyScheduler(dataset, seed=seed)
    return scheduler.run(seed=seed)


def run_random_search_runner(dataset: dict, ga_config: dict, budget: int, seed: int) -> dict:
    """Execute Random Search runner for a single seed."""
    from evaluation.baselines import RandomSearchScheduler
    scheduler = RandomSearchScheduler(dataset, seed=seed)
    return scheduler.run(evaluation_budget=budget, seed=seed)



METHOD_RUNNERS: Dict[str, Callable[[dict, dict, int, int], dict]] = {
    "hybrid": run_hybrid_runner,
    "ga": run_ga_without_repair_runner,
    "greedy": run_greedy_runner,
    "random": run_random_search_runner,
}
