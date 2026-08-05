"""Tests for Step 6 — Workflow Architecture, Production Entry Point, and Dynamic CLI Benchmarking."""

import pytest
import openpyxl
import json
import os
import csv
from pathlib import Path
from unittest.mock import MagicMock, patch

from evaluation import parse_methods, SUPPORTED_METHODS, METHOD_DISPLAY_NAMES, METHOD_RUNNERS
from evaluation.run_metrics import RunMetrics
from domain import Schedule, Gene
from ga import GeneticAlgorithmEngine
from evaluation.baselines import RandomSearchScheduler, GreedyScheduler


# ============================================================
# 1. Parse Methods Unit Tests (Requirement 19.1)
# ============================================================

@pytest.mark.unit
def test_parse_methods_single():
    assert parse_methods("hybrid") == ["hybrid"]


@pytest.mark.unit
def test_parse_methods_multiple():
    assert parse_methods("hybrid,ga") == ["hybrid", "ga"]
    assert parse_methods("hybrid, ga, greedy") == ["hybrid", "ga", "greedy"]


@pytest.mark.unit
def test_parse_methods_case_insensitive_and_whitespace():
    assert parse_methods("  Hybrid ,  GA  ") == ["hybrid", "ga"]


@pytest.mark.unit
def test_parse_methods_deduplication_preserves_first_occurrence():
    assert parse_methods("hybrid, greedy, hybrid, ga, greedy") == ["hybrid", "greedy", "ga"]


@pytest.mark.unit
def test_parse_methods_unsupported_raises():
    with pytest.raises(ValueError, match="Unsupported method 'gready'"):
        parse_methods("hybrid,gready")


@pytest.mark.unit
def test_parse_methods_empty_raises():
    with pytest.raises(ValueError, match="Methods list cannot be empty"):
        parse_methods("")
    with pytest.raises(ValueError, match="Methods list cannot be empty"):
        parse_methods("   ")


# ============================================================
# 2. Selected Runner Isolation Tests (Requirement 19.2)
# ============================================================

@pytest.mark.unit
def test_selected_runner_isolation(small_dataset):
    ga_config = {"pop_size": 10, "generations": 5, "crossover_rate": 0.8, "mutation_rate": 0.2}

    # Execute only hybrid and ga runners
    selected = parse_methods("hybrid,ga")

    executed_methods = []
    for m in selected:
        res = METHOD_RUNNERS[m](small_dataset, ga_config, budget=10, seed=0)
        executed_methods.append(m)
        assert res["run_metrics"].search_fitness_evaluations == 10

    assert executed_methods == ["hybrid", "ga"]
    assert "greedy" not in executed_methods
    assert "random" not in executed_methods


# ============================================================
# 3. Hybrid Only Benchmark Test (Requirement 19.3)
# ============================================================

@pytest.mark.integration
def test_hybrid_only_benchmark_execution(small_dataset):
    ga_config = {"pop_size": 10, "generations": 5, "crossover_rate": 0.8, "mutation_rate": 0.2}
    selected = parse_methods("hybrid")

    runs = [METHOD_RUNNERS["hybrid"](small_dataset, ga_config, budget=10, seed=s) for s in [0, 1]]

    assert len(runs) == 2
    for r in runs:
        assert r["run_metrics"].method == "Hybrid GA + Repair"
        assert r["run_metrics"].search_fitness_evaluations == 10


# ============================================================
# 4. Hybrid + GA Benchmark Test (Requirement 19.4)
# ============================================================

@pytest.mark.integration
def test_hybrid_plus_ga_benchmark_execution(small_dataset):
    ga_config = {"pop_size": 10, "generations": 5, "crossover_rate": 0.8, "mutation_rate": 0.2}
    selected = parse_methods("hybrid,ga")

    hybrid_runs = [METHOD_RUNNERS["hybrid"](small_dataset, ga_config, budget=10, seed=0)]
    ga_runs = [METHOD_RUNNERS["ga"](small_dataset, ga_config, budget=10, seed=0)]

    assert hybrid_runs[0]["run_metrics"].method == "Hybrid GA + Repair"
    assert ga_runs[0]["run_metrics"].method == "GA without Repair"


# ============================================================
# 5. Greedy Optional Test (Requirement 19.5)
# ============================================================

@pytest.mark.unit
def test_greedy_optional_single_run(small_dataset):
    ga_config = {}
    greedy_res = METHOD_RUNNERS["greedy"](small_dataset, ga_config, budget=1000, seed=0)

    metrics = greedy_res["run_metrics"]
    assert metrics.method == "Greedy Search"
    assert metrics.search_fitness_evaluations == 1


# ============================================================
# 6. Random Search Optional Test (Requirement 19.6)
# ============================================================

@pytest.mark.unit
def test_random_search_optional_execution(small_dataset):
    ga_config = {}
    random_res = METHOD_RUNNERS["random"](small_dataset, ga_config, budget=15, seed=0)

    metrics = random_res["run_metrics"]
    assert metrics.method == "Random Search"
    assert metrics.search_fitness_evaluations == 15


# ============================================================
# 7. Production Main Test (Requirement 19.7)
# ============================================================

@pytest.mark.integration
def test_production_main_execution(tmp_path, small_dataset):
    from dataset import ExcelDatasetLoader

    # Mock load_and_validate to return small_dataset
    out_file = tmp_path / "test_production_timetable.xlsx"

    with patch.object(ExcelDatasetLoader, "load_and_validate", return_value=small_dataset):
        with patch("sys.argv", ["main.py", "--input", "dummy.xlsx", "--output", str(out_file), "--seed", "42", "--search-evaluation-budget", "20", "--population-size", "10"]):
            from main import main as main_prod
            main_prod()


    assert out_file.exists()
    wb = openpyxl.load_workbook(out_file)
    assert "SUMMARY" in wb.sheetnames
    assert "RUN_CONFIG" in wb.sheetnames


    # Check RUN_CONFIG metadata
    ws_cfg = wb["RUN_CONFIG"]
    rows = dict(list(ws_cfg.iter_rows(values_only=True))[1:])
    assert rows.get("primary_method") == "hybrid"
    assert rows.get("selected_methods") == "hybrid"


# ============================================================
# 8. Dynamic Export Verification (Requirement 19.8)
# ============================================================

@pytest.mark.unit
def test_dynamic_export_verification(tmp_path, small_dataset):
    from evaluation import export_schedule_to_excel
    from dataset import find_feasible_schedule

    sched = find_feasible_schedule(small_dataset)
    m_hybrid = RunMetrics(
        method="Hybrid GA + Repair", seed=0, runtime_seconds=1.0,
        time_to_first_feasible_seconds=0.5, search_fitness_evaluations=10,
        hard_constraint_evaluations=10, soft_constraint_evaluations=10,
        total_constraint_evaluations=20, candidate_checks=50,
        repair_calls=2, repair_improved=2, repair_unchanged=0, repair_failed=0,
        first_feasible_search_evaluation=1, first_feasible_total_constraint_evaluation=2,
        first_feasible_generation=0, final_hard_violations=0, final_soft_penalty=10,
        feasible=True, score=10.0
    )

    out_path = tmp_path / "dynamic_export.xlsx"
    meta = {
        "primary_method": "hybrid",
        "selected_methods": "hybrid,ga",
        "all_runs_flat": [m_hybrid.to_dict()],
        "summary_list": [{"method": "Hybrid GA + Repair", "run_count": 1, "feasible_rate": 1.0}],
    }

    export_schedule_to_excel(sched, small_dataset, out_path, metadata=meta)

    wb = openpyxl.load_workbook(out_path)

    # Check RUN_CONFIG
    ws_cfg = wb["RUN_CONFIG"]
    cfg_dict = dict(list(ws_cfg.iter_rows(values_only=True))[1:])
    assert cfg_dict.get("primary_method") == "hybrid"
    assert cfg_dict.get("selected_methods") == "hybrid,ga"

    # Check BENCHMARK_SUMMARY contains only 1 row
    ws_sum = wb["BENCHMARK_SUMMARY"]
    rows = list(ws_sum.iter_rows(values_only=True))
    assert len(rows) == 2  # header + 1 data row
    assert rows[1][0] == "Hybrid GA + Repair"
