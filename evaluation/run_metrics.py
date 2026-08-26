"""Module chỉ số đánh giá và bộ đếm số lần thực thi.

Cung cấp các cấu trúc dữ liệu đo lường chuẩn hóa cho thuật toán theo từng seed,
đảm bảo tính minh bạch, công bằng và khả năng tái lập kết quả.
"""

from __future__ import annotations
from dataclasses import dataclass, field, asdict
from typing import Optional, Dict, Any
from domain import RepairStatus



@dataclass
class EvaluationCounters:
    """Theo dõi các bộ đếm đánh giá và kiểm tra ứng viên theo từng lần chạy."""
    search_fitness_evaluations: int = 0
    hard_constraint_evaluations: int = 0
    soft_constraint_evaluations: int = 0
    candidate_checks: int = 0

    @property
    def total_constraint_evaluations(self) -> int:
        return self.hard_constraint_evaluations + self.soft_constraint_evaluations

    def reset(self) -> None:
        self.search_fitness_evaluations = 0
        self.hard_constraint_evaluations = 0
        self.soft_constraint_evaluations = 0
        self.candidate_checks = 0

    def snapshot(self) -> EvaluationCounters:
        return EvaluationCounters(
            search_fitness_evaluations=self.search_fitness_evaluations,
            hard_constraint_evaluations=self.hard_constraint_evaluations,
            soft_constraint_evaluations=self.soft_constraint_evaluations,
            candidate_checks=self.candidate_checks,
        )


@dataclass
class RunMetrics:
    """Chỉ số hiệu năng và chi phí tính toán chi tiết cho một lần chạy thuật toán."""
    method: str
    seed: Optional[int]

    runtime_seconds: float
    time_to_first_feasible_seconds: Optional[float]

    search_fitness_evaluations: int
    hard_constraint_evaluations: int
    soft_constraint_evaluations: int
    total_constraint_evaluations: int

    candidate_checks: int
    repair_calls: int
    repair_improved: int
    repair_unchanged: int
    repair_failed: int

    first_feasible_search_evaluation: Optional[int]
    first_feasible_total_constraint_evaluation: Optional[int]
    first_feasible_generation: Optional[int]

    final_hard_violations: int
    final_soft_penalty: float
    feasible: bool
    score: float = 0.0
    raw_soft_violations: float = 0.0

    # Categorized evaluation breakdown fields
    search_hard_constraint_evaluations: int = 0
    search_soft_constraint_evaluations: int = 0
    search_constraint_evaluations: int = 0

    internal_hard_constraint_evaluations: int = 0
    internal_soft_constraint_evaluations: int = 0
    internal_constraint_evaluations: int = 0

    reporting_hard_constraint_evaluations: int = 0
    reporting_soft_constraint_evaluations: int = 0
    reporting_constraint_evaluations: int = 0

    total_hard_constraint_evaluations: int = 0
    total_soft_constraint_evaluations: int = 0

    # Soft Local Search metrics
    soft_ls_calls: int = 0
    soft_ls_candidate_checks: int = 0
    soft_ls_accepted_moves: int = 0
    soft_ls_improvement: float = 0.0
    soft_ls_runtime_seconds: float = 0.0

    # Soft-Guided Mutation & Pre/Post SLS metrics
    soft_before_sls: Optional[float] = None
    soft_after_sls: Optional[float] = None
    guided_mutation_calls: int = 0
    guided_mutation_attempts: int = 0
    guided_mutation_successes: int = 0
    guided_mutation_fallbacks: int = 0



    def __post_init__(self):
        # Auto-compute breakdown properties if not passed explicitly
        if self.search_constraint_evaluations == 0:
            self.search_constraint_evaluations = (
                self.search_hard_constraint_evaluations + self.search_soft_constraint_evaluations
            )
        if self.internal_constraint_evaluations == 0:
            self.internal_constraint_evaluations = (
                self.internal_hard_constraint_evaluations + self.internal_soft_constraint_evaluations
            )
        if self.reporting_constraint_evaluations == 0:
            self.reporting_constraint_evaluations = (
                self.reporting_hard_constraint_evaluations + self.reporting_soft_constraint_evaluations
            )
        if self.total_hard_constraint_evaluations == 0:
            self.total_hard_constraint_evaluations = (
                self.search_hard_constraint_evaluations
                + self.internal_hard_constraint_evaluations
                + self.reporting_hard_constraint_evaluations
            )
        if self.total_soft_constraint_evaluations == 0:
            self.total_soft_constraint_evaluations = (
                self.search_soft_constraint_evaluations
                + self.internal_soft_constraint_evaluations
                + self.reporting_soft_constraint_evaluations
            )
        self.validate()

    def validate(self) -> None:
        """Kiểm tra tính hợp lệ của các chỉ số trong lần chạy. Ném lỗi ValueError nếu vi phạm."""
        sum_statuses = self.repair_improved + self.repair_unchanged + self.repair_failed
        if self.repair_calls != sum_statuses:
            raise ValueError(
                f"Invalid repair metrics for method='{self.method}', seed={self.seed}: "
                f"repair_calls={self.repair_calls} but statuses sum to {sum_statuses}."
            )

        if self.feasible:
            if self.time_to_first_feasible_seconds is None:
                raise ValueError(
                    f"Feasible run (method='{self.method}', seed={self.seed}) must have time_to_first_feasible_seconds."
                )
            if not (0 <= self.time_to_first_feasible_seconds <= self.runtime_seconds + 1e-4):
                raise ValueError(
                    f"Feasible run time_to_first_feasible_seconds ({self.time_to_first_feasible_seconds}) "
                    f"must satisfy 0 <= TTFF <= runtime_seconds ({self.runtime_seconds})."
                )
            if self.first_feasible_search_evaluation is not None:
                if not (1 <= self.first_feasible_search_evaluation <= max(1, self.search_fitness_evaluations)):
                    raise ValueError(
                        f"first_feasible_search_evaluation ({self.first_feasible_search_evaluation}) "
                        f"must satisfy 1 <= ev <= {self.search_fitness_evaluations}."
                    )
            if self.first_feasible_total_constraint_evaluation is not None:
                if not (1 <= self.first_feasible_total_constraint_evaluation <= max(1, self.total_constraint_evaluations)):
                    raise ValueError(
                        f"first_feasible_total_constraint_evaluation ({self.first_feasible_total_constraint_evaluation}) "
                        f"must satisfy 1 <= ev <= {self.total_constraint_evaluations}."
                    )
        else:
            if self.time_to_first_feasible_seconds is not None:
                raise ValueError(
                    f"Infeasible run (method='{self.method}', seed={self.seed}) must have time_to_first_feasible_seconds=None."
                )
            if self.first_feasible_generation is not None:
                raise ValueError(
                    f"Infeasible run (method='{self.method}', seed={self.seed}) must have first_feasible_generation=None."
                )
            if self.first_feasible_search_evaluation is not None:
                raise ValueError(
                    f"Infeasible run (method='{self.method}', seed={self.seed}) must have first_feasible_search_evaluation=None."
                )
            if self.first_feasible_total_constraint_evaluation is not None:
                raise ValueError(
                    f"Infeasible run (method='{self.method}', seed={self.seed}) must have first_feasible_total_constraint_evaluation=None."
                )

    @property
    def is_hard_feasible(self) -> bool:
        return self.feasible

    @property
    def is_perfect(self) -> bool:
        return self.feasible and self.final_soft_penalty == 0

    @property
    def repair_improvement_rate(self) -> Optional[float]:
        if self.repair_calls == 0:
            return None
        return self.repair_improved / self.repair_calls

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["is_hard_feasible"] = self.is_hard_feasible
        d["is_perfect"] = self.is_perfect
        d["repair_improvement_rate"] = self.repair_improvement_rate
        # Legacy compatibility aliases
        d["fitness_evaluations"] = self.search_fitness_evaluations
        d["hard_violations"] = self.final_hard_violations
        d["soft_penalty"] = self.final_soft_penalty
        d["generation_to_first_feasible"] = (
            self.first_feasible_generation
            if self.first_feasible_generation is not None
            else "N/A"
        )
        d["time_to_first_feasible"] = (
            self.time_to_first_feasible_seconds
            if self.time_to_first_feasible_seconds is not None
            else "N/A"
        )
        d["repair_attempts"] = self.repair_calls
        d["repair_successes"] = self.repair_improved
        return d


def validate_search_budget(metrics: RunMetrics, expected_budget: Optional[int]) -> None:
    """Kiểm tra search_fitness_evaluations có khớp chính xác với expected_budget hay không."""
    if expected_budget is None:
        return
    exact_budget_methods = (
        "GA without Repair",
        "GA + Repair",
        "GA + Repair + SLS (Production)",
        "Repair-only Random Restart",
        "Hybrid GA + Repair",  # Legacy result compatibility.
        "Random Search",
    )
    if metrics.method in exact_budget_methods:
        if metrics.search_fitness_evaluations != expected_budget:
            raise ValueError(
                f"Search budget violation for method='{metrics.method}', seed={metrics.seed}: "
                f"expected {expected_budget} search fitness evaluations, got {metrics.search_fitness_evaluations}."
            )


@dataclass(frozen=True)
class AggregateRunMetrics:
    """Chỉ số tổng hợp mô tả kết quả trung bình/trung vị qua nhiều seed."""
    method: str
    run_count: int
    is_deterministic: bool

    feasible_count: int
    feasible_rate: float
    perfect_count: int
    perfect_rate: float

    median_final_hard: float
    mean_final_hard: float
    median_final_soft: float
    mean_final_soft: float

    mean_runtime_seconds: float
    median_runtime_seconds: float
    median_time_to_first_feasible_seconds: Optional[float]
    mean_time_to_first_feasible_seconds: Optional[float]

    median_search_fitness_evaluations: float
    mean_search_fitness_evaluations: float

    median_search_constraint_evaluations: float = 0.0
    median_internal_constraint_evaluations: float = 0.0
    median_reporting_constraint_evaluations: float = 0.0
    median_total_constraint_evaluations: float = 0.0

    median_candidate_checks: float = 0.0
    median_repair_calls: float = 0.0

    total_repair_calls: int = 0
    total_repair_improved: int = 0
    total_repair_unchanged: int = 0
    total_repair_failed: int = 0

    improvement_rate: Optional[float] = None
    non_failure_rate: Optional[float] = None

    best_run: Dict[str, Any] = field(default_factory=dict)
    worst_run: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        # Legacy key aliases for backwards compatibility
        d["runs"] = self.run_count
        d["hard_feasible_rate"] = self.feasible_rate
        d["perfect_solution_rate"] = self.perfect_rate
        d["median_hard"] = self.median_final_hard
        d["mean_hard"] = self.mean_final_hard
        d["median_soft_penalty"] = self.median_final_soft
        d["mean_soft_penalty"] = self.mean_final_soft
        d["search_evaluations_mean"] = self.mean_search_fitness_evaluations
        d["search_evaluations_median"] = self.median_search_fitness_evaluations
        d["mean_fitness_evaluations"] = self.mean_search_fitness_evaluations
        d["median_fitness_evaluations"] = self.median_search_fitness_evaluations
        d["time_to_first_feasible_median"] = self.median_time_to_first_feasible_seconds
        d["time_to_first_feasible_mean"] = self.mean_time_to_first_feasible_seconds
        return d
