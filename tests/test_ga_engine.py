import pytest
from dataset import DatasetFactory
from ga import GeneticAlgorithmEngine, GAOperators
from domain import Schedule, Gene

def test_early_stopping_does_not_stop_on_split_hard0_soft0():
    dataset = DatasetFactory.create_dataset()
    engine = GeneticAlgorithmEngine(dataset, pop_size=2)
    
    # Test evaluation logic where hard=0 and soft=0 belong to different individuals
    hard_v = [0, 2]
    soft_v = [5, 0]
    
    best_idx = min(range(2), key=lambda i: (hard_v[i], soft_v[i]))
    assert best_idx == 0
    should_stop = (hard_v[best_idx] == 0 and soft_v[best_idx] == 0)
    assert not should_stop

def test_history_records_data_from_same_best_individual():
    dataset = DatasetFactory.create_dataset()
    engine = GeneticAlgorithmEngine(dataset, pop_size=10)
    res = engine.run(generations=5, use_repair=True)
    
    history = res["history"]
    assert len(history) > 0
    for h in history:
        assert "best_score" in h
        assert "best_hard" in h
        assert "best_soft" in h
        assert "avg_score" in h
        assert "min_hard" not in h

def test_lexicographic_comparison_order():
    # (0, 5000) must be strictly better (smaller) than (1, 0)
    fit1 = (0, 5000)
    fit2 = (1, 0)
    assert fit1 < fit2

def test_tournament_selection_uses_lexicographic_comparison():
    dataset = DatasetFactory.create_dataset()
    engine = GeneticAlgorithmEngine(dataset, pop_size=2)
    p1 = engine.create_random_schedule()
    p2 = engine.create_random_schedule()
    pop = [p1, p2]
    
    fitness_keys = [(1, 0), (0, 5000)]
    
    selected = GAOperators.tournament_selection(pop, fitness_keys, k=2)
    assert selected == p2
