import os
import pytest
from evaluation.visualizer import ConvergenceVisualizer

def test_extract_x_uses_fitness_evaluations():
    # Test 1: Verify visualizer extracts fitness_evaluations [10, 20] instead of [0, 1]
    history = [
        {"fitness_evaluations": 10, "best_hard": 2, "best_soft_penalty": 20, "best_score": 2020},
        {"fitness_evaluations": 20, "best_hard": 1, "best_soft_penalty": 10, "best_score": 1010},
    ]
    x_vals, y_vals = ConvergenceVisualizer._validate_and_extract(history, "best_hard")

    assert x_vals == [10, 20]
    assert y_vals == [2, 1]

def test_non_decreasing_history_validation():
    # Test 2: Decreasing fitness_evaluations [20, 10] raises ValueError
    history = [
        {"fitness_evaluations": 20, "best_hard": 1, "best_soft_penalty": 10},
        {"fitness_evaluations": 10, "best_hard": 2, "best_soft_penalty": 20},
    ]
    with pytest.raises(ValueError):
        ConvergenceVisualizer._validate_and_extract(history, "best_hard")

def test_extend_to_budget():
    # Test 3: Extend plot data to budget=6000
    x_vals = [10, 180]
    y_vals = [3, 0]
    x_plot, y_plot = ConvergenceVisualizer._prepare_plot_data(x_vals, y_vals, evaluation_budget=6000)

    assert x_plot == [10, 180, 6000]
    assert y_plot == [3, 0, 0]

def test_creates_both_chart_files(tmp_path):
    # Test 4: Create both PNG files and verify file size > 0
    hard_path = str(tmp_path / "convergence_hard.png")
    soft_path = str(tmp_path / "convergence_soft.png")

    dummy_hist = [
        {"fitness_evaluations": 10, "best_hard": 2, "best_soft_penalty": 20},
        {"fitness_evaluations": 20, "best_hard": 0, "best_soft_penalty": 5},
    ]

    ConvergenceVisualizer.plot_convergence(
        dummy_hist,
        dummy_hist,
        dummy_hist,
        hard_output_path=hard_path,
        soft_output_path=soft_path,
        evaluation_budget=100
    )

    assert os.path.exists(hard_path)
    assert os.path.getsize(hard_path) > 0
    assert os.path.exists(soft_path)
    assert os.path.getsize(soft_path) > 0

def test_empty_history_raises_value_error():
    # Test 5: Empty history raises ValueError
    with pytest.raises(ValueError):
        ConvergenceVisualizer._validate_and_extract([], "best_hard")

def test_missing_field_raises_value_error():
    # Test 6: Missing fitness_evaluations field raises ValueError
    history = [{"best_hard": 1, "best_soft_penalty": 0}]
    with pytest.raises(ValueError):
        ConvergenceVisualizer._validate_and_extract(history, "best_hard")

def test_original_history_not_mutated():
    # Test 7: Original history is not mutated when extending to budget
    history = [
        {"fitness_evaluations": 10, "best_hard": 2, "best_soft_penalty": 20},
        {"fitness_evaluations": 180, "best_hard": 0, "best_soft_penalty": 0},
    ]
    orig_len = len(history)
    orig_x_last = history[-1]["fitness_evaluations"]

    x_vals, y_vals = ConvergenceVisualizer._validate_and_extract(history, "best_hard")
    ConvergenceVisualizer._prepare_plot_data(x_vals, y_vals, evaluation_budget=6000)

    assert len(history) == orig_len
    assert history[-1]["fitness_evaluations"] == orig_x_last
