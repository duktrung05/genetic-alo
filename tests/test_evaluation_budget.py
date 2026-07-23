import pytest
from dataset import DatasetFactory
from ga import GeneticAlgorithmEngine
from evaluation import RandomSearchScheduler
import main_benchmark

def test_random_search_respects_evaluation_budget():
    dataset = DatasetFactory.create_dataset()
    scheduler = RandomSearchScheduler(dataset)
    res = scheduler.run(evaluation_budget=10)

    assert res["fitness_evaluations"] == 10
    assert len(res["history"]) == 10
    assert res["history"][-1]["fitness_evaluations"] == 10

def test_random_search_history_fitness_evaluations_monotonic():
    dataset = DatasetFactory.create_dataset()
    scheduler = RandomSearchScheduler(dataset)
    res = scheduler.run(evaluation_budget=15)

    counts = [record["fitness_evaluations"] for record in res["history"]]
    assert counts == sorted(counts)
    assert len(counts) == len(set(counts))

def test_ga_does_not_exceed_evaluation_budget():
    dataset = DatasetFactory.create_dataset()
    engine = GeneticAlgorithmEngine(dataset, pop_size=10)
    res = engine.run(generations=100, use_repair=False, evaluation_budget=40)

    assert res["fitness_evaluations"] <= 40

def test_both_ga_modes_respect_same_budget():
    dataset = DatasetFactory.create_dataset()
    engine_no_rep = GeneticAlgorithmEngine(dataset, pop_size=10)
    res_no_rep = engine_no_rep.run(generations=100, use_repair=False, evaluation_budget=50)

    engine_hybrid = GeneticAlgorithmEngine(dataset, pop_size=10)
    res_hybrid = engine_hybrid.run(generations=100, use_repair=True, evaluation_budget=50)

    assert res_no_rep["fitness_evaluations"] <= 50
    assert res_hybrid["fitness_evaluations"] <= 50

def test_budget_smaller_than_population_size_raises_value_error():
    dataset = DatasetFactory.create_dataset()
    engine = GeneticAlgorithmEngine(dataset, pop_size=60)
    with pytest.raises(ValueError):
        engine.run(generations=10, use_repair=False, evaluation_budget=10)

def test_ga_early_stopping_with_budget():
    dataset = DatasetFactory.create_dataset()
    engine = GeneticAlgorithmEngine(dataset, pop_size=10)
    res = engine.run(generations=100, use_repair=True, evaluation_budget=500)

    assert res["fitness_evaluations"] <= 500

def test_main_benchmark_shared_budget():
    assert main_benchmark.EVALUATION_BUDGET == 6000
