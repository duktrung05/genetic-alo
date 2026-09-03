"""Tests for Step 5.2 — Counter Semantics, Category Breakdown, and Search Budget Enforcement."""

import pytest
import openpyxl

from domain import Schedule, Gene
from constraints import ConstraintEvaluator
from evaluation.run_metrics import RunMetrics, validate_search_budget
from ga import GeneticAlgorithmEngine
from evaluation.baselines import RandomSearchScheduler, GreedyScheduler
from evaluation.schedule_exporter import export_schedule_to_excel


# ============================================================
# 1. Kiểm thử đơn vị việc tăng từng loại bộ đếm
# ============================================================

@pytest.mark.unit
def test_search_evaluation_increment(small_dataset):
    evaluator = ConstraintEvaluator(small_dataset)
    sections = small_dataset["course_sections"]
    rooms = small_dataset["rooms"]
    genes = [Gene(s.section_id, rooms[0].id, 0) for s in sections]
    sched = Schedule(genes=genes)

    evaluator.evaluate_hard(sched, category="search")
    evaluator.evaluate_soft(sched, category="search")

    assert evaluator.counters.search_fitness_evaluations == 1
    assert evaluator.counters.search_hard_constraint_evaluations == 1
    assert evaluator.counters.search_soft_constraint_evaluations == 1
    assert evaluator.counters.search_constraint_evaluations == 2
    assert evaluator.counters.internal_constraint_evaluations == 0
    assert evaluator.counters.reporting_constraint_evaluations == 0


@pytest.mark.unit
def test_internal_evaluation_increment(small_dataset):
    evaluator = ConstraintEvaluator(small_dataset)
    sections = small_dataset["course_sections"]
    rooms = small_dataset["rooms"]
    genes = [Gene(s.section_id, rooms[0].id, 0) for s in sections]
    sched = Schedule(genes=genes)

    evaluator.evaluate_hard(sched, category="internal")
    evaluator.evaluate_soft(sched, category="internal")

    assert evaluator.counters.search_fitness_evaluations == 0
    assert evaluator.counters.internal_hard_constraint_evaluations == 1
    assert evaluator.counters.internal_soft_constraint_evaluations == 1
    assert evaluator.counters.internal_constraint_evaluations == 2
    assert evaluator.counters.total_constraint_evaluations == 2


@pytest.mark.unit
def test_reporting_evaluation_increment(small_dataset):
    evaluator = ConstraintEvaluator(small_dataset)
    sections = small_dataset["course_sections"]
    rooms = small_dataset["rooms"]
    genes = [Gene(s.section_id, rooms[0].id, 0) for s in sections]
    sched = Schedule(genes=genes)

    evaluator.evaluate_unified(sched, category="reporting")

    assert evaluator.counters.search_fitness_evaluations == 0
    assert evaluator.counters.reporting_hard_constraint_evaluations == 1
    assert evaluator.counters.reporting_soft_constraint_evaluations == 1
    assert evaluator.counters.reporting_constraint_evaluations == 2
    assert evaluator.counters.total_constraint_evaluations == 2


# ============================================================
# 2. Kiểm thử thực thi ngân sách tìm kiếm GA
# ============================================================

@pytest.mark.unit
def test_ga_budget_enforcement_fractional(small_dataset):
    engine = GeneticAlgorithmEngine(small_dataset, pop_size=6, elite_count=1, seed=42)
    res_no_repair = engine.run(generations=100, use_repair=False, evaluation_budget=17)
    res_hybrid = engine.run(generations=100, use_repair=True, evaluation_budget=17)

    assert res_no_repair["run_metrics"].search_fitness_evaluations == 17
    assert res_hybrid["run_metrics"].search_fitness_evaluations == 17


@pytest.mark.unit
def test_ga_budget_enforcement_exact(small_dataset):
    engine = GeneticAlgorithmEngine(small_dataset, pop_size=5, elite_count=1, seed=42)
    res = engine.run(generations=100, use_repair=False, evaluation_budget=20)
    assert res["run_metrics"].search_fitness_evaluations == 20


@pytest.mark.unit
def test_ga_budget_overrides_too_small_generation_limit(small_dataset):
    engine = GeneticAlgorithmEngine(small_dataset, pop_size=5, elite_count=1, seed=42)

    result = engine.run(
        generations=1,
        use_repair=False,
        evaluation_budget=12,
    )

    assert result["run_metrics"].search_fitness_evaluations == 12
    assert result["history"][-1]["fitness_evaluations"] == 12


@pytest.mark.unit
def test_ga_budget_is_not_shortened_by_perfect_solution(small_dataset, monkeypatch):
    engine = GeneticAlgorithmEngine(small_dataset, pop_size=5, elite_count=1, seed=42)
    calculate_fitness = engine.evaluator.calculate_fitness

    def report_perfect_solution(*args, **kwargs):
        calculate_fitness(*args, **kwargs)
        return 0.0, 0, 0

    monkeypatch.setattr(engine.evaluator, "calculate_fitness", report_perfect_solution)

    result = engine.run(
        generations=100,
        use_repair=False,
        evaluation_budget=12,
    )

    assert result["run_metrics"].search_fitness_evaluations == 12
    assert result["history"][-1]["fitness_evaluations"] == 12


# ============================================================
# 3. Kiểm thử thực thi ngân sách tìm kiếm ngẫu nhiên
# ============================================================

@pytest.mark.unit
def test_random_search_budget_enforcement(small_dataset):
    scheduler = RandomSearchScheduler(small_dataset, seed=42)
    res = scheduler.run(evaluation_budget=17)

    metrics = res["run_metrics"]
    assert metrics.search_fitness_evaluations == 17
    assert metrics.search_constraint_evaluations == 34


# ============================================================
# 4. Kiểm tra tính cô lập của báo cáo và ngân sách
# ============================================================

@pytest.mark.unit
def test_reporting_isolation_after_search(small_dataset):
    engine = GeneticAlgorithmEngine(small_dataset, pop_size=6, elite_count=1, seed=42)
    res = engine.run(generations=100, use_repair=False, evaluation_budget=20)

    # Lần gọi bộ đánh giá sau tìm kiếm không được ảnh hưởng search_fitness_evaluations
    evaluator = engine.evaluator
    evaluator.evaluate_hard(res["best_schedule"], category="reporting")
    evaluator.evaluate_soft(res["best_schedule"], category="reporting")

    assert res["run_metrics"].search_fitness_evaluations == 20
    assert evaluator.counters.search_fitness_evaluations == 20
    assert evaluator.counters.reporting_hard_constraint_evaluations == 2  # 1 từ cuối run() + 1 thủ công
    assert evaluator.counters.reporting_soft_constraint_evaluations == 2


@pytest.mark.unit
def test_search_budget_validation_failure():
    metrics = RunMetrics(
        method="Random Search", seed=0, runtime_seconds=1.0,
        time_to_first_feasible_seconds=0.5, search_fitness_evaluations=1001,  # thực tế = 1001
        hard_constraint_evaluations=1001, soft_constraint_evaluations=1001,
        total_constraint_evaluations=2002, candidate_checks=0,
        repair_calls=0, repair_improved=0, repair_unchanged=0, repair_failed=0,
        first_feasible_search_evaluation=10, first_feasible_total_constraint_evaluation=20,
        first_feasible_generation=1, final_hard_violations=0, final_soft_penalty=50,
        feasible=True, score=50.0
    )

    with pytest.raises(ValueError, match="Search budget violation for method='Random Search'"):
        validate_search_budget(metrics, expected_budget=1000)


# ============================================================
# 5. Xác minh lượt xuất-nạp
# ============================================================

@pytest.mark.unit
def test_export_round_trip_breakdown(tmp_path, small_dataset):
    from dataset import find_feasible_schedule

    sched = find_feasible_schedule(small_dataset)
    m = RunMetrics(
        method="Hybrid GA + Repair", seed=0, runtime_seconds=1.0,
        time_to_first_feasible_seconds=0.5, search_fitness_evaluations=1000,
        hard_constraint_evaluations=1000, soft_constraint_evaluations=1000,
        total_constraint_evaluations=5714, candidate_checks=500,
        repair_calls=928, repair_improved=900, repair_unchanged=28, repair_failed=0,
        first_feasible_search_evaluation=100, first_feasible_total_constraint_evaluation=200,
        first_feasible_generation=2, final_hard_violations=0, final_soft_penalty=2000,
        feasible=True, score=2000.0,
        search_hard_constraint_evaluations=1000, search_soft_constraint_evaluations=1000,
        search_constraint_evaluations=2000,
        internal_hard_constraint_evaluations=1856, internal_soft_constraint_evaluations=1856,
        internal_constraint_evaluations=3712,
        reporting_hard_constraint_evaluations=1, reporting_soft_constraint_evaluations=1,
        reporting_constraint_evaluations=2
    )

    out_file = str(tmp_path / "test_breakdown_export.xlsx")
    meta = {"all_runs_flat": [m.to_dict()]}
    export_schedule_to_excel(sched, small_dataset, out_file, metadata=meta)

    wb = openpyxl.load_workbook(out_file)
    ws = wb["RUN_METRICS"]
    rows = list(ws.iter_rows(values_only=True))
    header = rows[0]
    data = rows[1]

    assert data[header.index("search_fitness_evaluations")] == 1000
    assert data[header.index("search_constraint_evaluations")] == 2000
    assert data[header.index("internal_constraint_evaluations")] == 3712
    assert data[header.index("reporting_constraint_evaluations")] == 2
    assert data[header.index("total_constraint_evaluations")] == 5714
