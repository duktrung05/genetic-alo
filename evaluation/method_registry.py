"""Canonical benchmark method registry and CLI parsing helpers."""

from typing import Any, Callable, Dict, List, Tuple


SUPPORTED_METHODS: Tuple[str, ...] = (
    "repair_only",
    "ga",
    "ga_repair",
    "ga_repair_sls",
    "greedy",
    "random",
)

# Các cách viết CLI tương thích ngược. Bí danh được chuẩn hóa trước khi thực thi
# để báo cáo không bao giờ chứa hai mã định danh cho cùng một thuật toán.
METHOD_ALIASES: Dict[str, str] = {"hybrid": "ga_repair"}

METHOD_DISPLAY_NAMES: Dict[str, str] = {
    "repair_only": "Repair-only Random Restart",
    "ga": "GA without Repair",
    "ga_repair": "GA + Repair",
    "ga_repair_sls": "GA + Repair + SLS (Production)",
    "greedy": "Greedy Search",
    "random": "Random Search",
}

METHOD_ROLES: Dict[str, str] = {
    "repair_only": "Repair Ablation Baseline",
    "ga": "GA Ablation Baseline",
    "ga_repair": "GA with Repair Ablation",
    "ga_repair_sls": "Primary Production Algorithm",
    "greedy": "Deterministic Heuristic Baseline",
    "random": "Random Lower-Bound Baseline",
}


def parse_methods(value: str) -> List[str]:
    """Parse and normalize a comma-separated benchmark method list."""
    if not isinstance(value, str) or not value.strip():
        raise ValueError(
            "Methods list cannot be empty. "
            f"Supported methods: {', '.join(SUPPORTED_METHODS)}."
        )

    parts = [part.strip().lower() for part in value.split(",") if part.strip()]
    if not parts:
        raise ValueError(
            "Methods list cannot be empty. "
            f"Supported methods: {', '.join(SUPPORTED_METHODS)}."
        )

    selected: List[str] = []
    for raw_method in parts:
        method = METHOD_ALIASES.get(raw_method, raw_method)
        if method not in SUPPORTED_METHODS:
            raise ValueError(
                f"Unsupported method '{raw_method}'. "
                f"Supported methods: {', '.join(SUPPORTED_METHODS)}."
            )
        if method not in selected:
            selected.append(method)
    return selected


def _run_ga_variant(
    dataset: dict,
    ga_config: dict,
    budget: int,
    seed: int,
    *,
    method_id: str,
    use_repair: bool,
    use_soft_local_search: bool,
) -> dict:
    """Run one explicitly configured GA variant and apply its public identity."""
    from ga import GeneticAlgorithmEngine

    engine = GeneticAlgorithmEngine(
        dataset,
        pop_size=ga_config.get("pop_size", 60),
        hard_weight=ga_config.get("hard_weight", 1000),
        soft_weight=ga_config.get("soft_weight", 1),
        seed=seed,
    )
    result = engine.run(
        generations=ga_config.get("generations", 100),
        crossover_rate=ga_config.get("crossover_rate", 0.8),
        mutation_rate=ga_config.get("mutation_rate", 0.2),
        use_repair=use_repair,
        evaluation_budget=budget,
        seed=seed,
        use_soft_local_search=use_soft_local_search,
        soft_local_search_max_passes=ga_config.get("soft_local_search_max_passes", 2),
        soft_local_search_max_candidate_checks=ga_config.get(
            "soft_local_search_max_candidate_checks", 5000
        ),
    )

    display_name = METHOD_DISPLAY_NAMES[method_id]
    result["run_metrics"].method = display_name
    result["method"] = display_name
    return result


def run_ga_runner(dataset: dict, ga_config: dict, budget: int, seed: int) -> dict:
    return _run_ga_variant(
        dataset, ga_config, budget, seed,
        method_id="ga", use_repair=False, use_soft_local_search=False,
    )


def run_ga_repair_runner(dataset: dict, ga_config: dict, budget: int, seed: int) -> dict:
    return _run_ga_variant(
        dataset, ga_config, budget, seed,
        method_id="ga_repair", use_repair=True, use_soft_local_search=False,
    )


def run_ga_repair_sls_runner(dataset: dict, ga_config: dict, budget: int, seed: int) -> dict:
    return _run_ga_variant(
        dataset, ga_config, budget, seed,
        method_id="ga_repair_sls", use_repair=True, use_soft_local_search=True,
    )


def run_hybrid_runner(dataset: dict, ga_config: dict, budget: int, seed: int) -> dict:
    """Deprecated Python API alias for the old Hybrid GA + Repair runner."""
    return run_ga_repair_runner(dataset, ga_config, budget, seed)


def run_repair_only_runner(dataset: dict, ga_config: dict, budget: int, seed: int) -> dict:
    from evaluation.baselines import RepairOnlyScheduler

    scheduler = RepairOnlyScheduler(
        dataset,
        hard_weight=ga_config.get("hard_weight", 1000),
        soft_weight=ga_config.get("soft_weight", 1),
        seed=seed,
    )
    return scheduler.run(evaluation_budget=budget, seed=seed)


def run_greedy_runner(dataset: dict, ga_config: dict, budget: int, seed: int) -> dict:
    from evaluation.baselines import GreedyScheduler

    return GreedyScheduler(dataset, seed=seed).run(seed=seed)


def run_random_search_runner(dataset: dict, ga_config: dict, budget: int, seed: int) -> dict:
    from evaluation.baselines import RandomSearchScheduler

    return RandomSearchScheduler(dataset, seed=seed).run(
        evaluation_budget=budget, seed=seed
    )


METHOD_RUNNERS: Dict[str, Callable[[dict, dict, int, int], Dict[str, Any]]] = {
    "repair_only": run_repair_only_runner,
    "ga": run_ga_runner,
    "ga_repair": run_ga_repair_runner,
    "ga_repair_sls": run_ga_repair_sls_runner,
    "greedy": run_greedy_runner,
    "random": run_random_search_runner,
}
