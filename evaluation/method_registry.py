"""Module đăng ký phương pháp — Quản lý mã định danh, hàm thực thi và phân tích CLI cho hệ thống thời khóa biểu GA."""

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
    """Phân tích chuỗi phương pháp từ CLI thành danh sách các mã phương pháp chuẩn hóa.

    Tham số:
        value: Chuỗi các phương pháp phân cách bằng dấu phẩy (ví dụ: "hybrid,ga,greedy")

    Trả về:
        Danh sách các mã phương pháp chuẩn hóa theo thứ tự xuất hiện.
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
    """Chạy phương pháp Hybrid GA + Repair cho một seed."""
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
    """Chạy phương pháp GA không dùng Repair cho một seed."""
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
    """Chạy phương pháp Greedy Search (baseline tham lam 1 lần chạy)."""
    from evaluation.baselines import GreedyScheduler
    scheduler = GreedyScheduler(dataset, seed=seed)
    return scheduler.run(seed=seed)


def run_random_search_runner(dataset: dict, ga_config: dict, budget: int, seed: int) -> dict:
    """Chạy phương pháp Tìm kiếm ngẫu nhiên (Random Search) cho một seed."""
    from evaluation.baselines import RandomSearchScheduler
    scheduler = RandomSearchScheduler(dataset, seed=seed)
    return scheduler.run(evaluation_budget=budget, seed=seed)




METHOD_RUNNERS: Dict[str, Callable[[dict, dict, int, int], dict]] = {
    "hybrid": run_hybrid_runner,
    "ga": run_ga_without_repair_runner,
    "greedy": run_greedy_runner,
    "random": run_random_search_runner,
}
