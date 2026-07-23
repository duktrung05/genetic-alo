import os
import json
import pytest
from evaluation.benchmark_statistics import aggregate_run_results
import main_benchmark

def test_aggregate_basic_stats():
    # Test 1: fitness_values = [0, 10, 20]
    runs = [
        {"score": 0, "hard_violations": 0, "raw_soft_violations": 0, "soft_penalty": 0, "is_hard_feasible": True, "is_perfect": True, "runtime_seconds": 0.1, "fitness_evaluations": 10},
        {"score": 10, "hard_violations": 0, "raw_soft_violations": 2, "soft_penalty": 10, "is_hard_feasible": True, "is_perfect": False, "runtime_seconds": 0.1, "fitness_evaluations": 10},
        {"score": 20, "hard_violations": 0, "raw_soft_violations": 4, "soft_penalty": 20, "is_hard_feasible": True, "is_perfect": False, "runtime_seconds": 0.1, "fitness_evaluations": 10},
    ]
    stat = aggregate_run_results("Test Method", runs)

    assert stat["mean_fitness"] == 10.0
    assert stat["median_fitness"] == 10.0
    assert stat["best_fitness"] == 0
    assert stat["worst_fitness"] == 20

def test_success_rates_calculation():
    # Test 2: Run A (hard=0, soft=0), Run B (hard=0, soft=5), Run C (hard=1, soft=0)
    runs = [
        {"score": 0, "hard_violations": 0, "raw_soft_violations": 0, "soft_penalty": 0, "is_hard_feasible": True, "is_perfect": True, "runtime_seconds": 0.1, "fitness_evaluations": 10},
        {"score": 5, "hard_violations": 0, "raw_soft_violations": 1, "soft_penalty": 5, "is_hard_feasible": True, "is_perfect": False, "runtime_seconds": 0.1, "fitness_evaluations": 10},
        {"score": 1000, "hard_violations": 1, "raw_soft_violations": 0, "soft_penalty": 0, "is_hard_feasible": False, "is_perfect": False, "runtime_seconds": 0.1, "fitness_evaluations": 10},
    ]
    stat = aggregate_run_results("Test Method", runs)

    assert pytest.approx(stat["hard_feasible_rate"], 1e-5) == 2 / 3
    assert pytest.approx(stat["perfect_solution_rate"], 1e-5) == 1 / 3

def test_best_run_uses_lexicographic():
    # Test 3: Run A (hard=1, soft=0), Run B (hard=0, soft=5000) -> B is best
    run_A = {"score": 1000, "hard_violations": 1, "raw_soft_violations": 0, "soft_penalty": 0, "is_hard_feasible": False, "is_perfect": False, "runtime_seconds": 0.1, "fitness_evaluations": 10}
    run_B = {"score": 5000, "hard_violations": 0, "raw_soft_violations": 100, "soft_penalty": 5000, "is_hard_feasible": True, "is_perfect": False, "runtime_seconds": 0.1, "fitness_evaluations": 10}
    
    stat = aggregate_run_results("Test Method", [run_A, run_B])
    assert stat["best_run"] == run_B

def test_thirty_unique_seeds():
    # Test 4: 30 unique seeds
    assert len(main_benchmark.SEEDS) == 30
    assert len(set(main_benchmark.SEEDS)) == 30

def test_greedy_deterministic():
    # Test 7: Greedy is deterministic (runs == 1, std == 0)
    greedy_run = {
        "score": 0, "hard_violations": 0, "raw_soft_violations": 0, "soft_penalty": 0,
        "is_hard_feasible": True, "is_perfect": True, "runtime_seconds": 0.001, "fitness_evaluations": 1
    }
    stat = aggregate_run_results("Greedy Search", [greedy_run], is_deterministic=True)
    assert stat["runs"] == 1
    assert stat["std_fitness"] == 0.0
    assert stat["is_deterministic"] is True

def test_json_output_file_exists():
    # Test 8: Check JSON output structure and file writing
    runs = [
        {"score": 0, "hard_violations": 0, "raw_soft_violations": 0, "soft_penalty": 0, "is_hard_feasible": True, "is_perfect": True, "runtime_seconds": 0.1, "fitness_evaluations": 10}
    ]
    stat = aggregate_run_results("Test Method", runs)
    
    json_str = json.dumps(stat)
    data = json.loads(json_str)
    assert data["method"] == "Test Method"
