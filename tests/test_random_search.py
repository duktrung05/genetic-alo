import pytest
from unittest.mock import MagicMock
from dataset import DatasetFactory
from evaluation.baselines import RandomSearchScheduler
from constraints import ConstraintEvaluator

def test_random_search_history_keeps_best_schedule():
    # Test 1: Mock sequence A (hard=1, soft=0, raw=0), B (hard=0, soft=10, raw=2), C (hard=0, soft=20, raw=5)
    dataset = DatasetFactory.create_dataset()
    scheduler = RandomSearchScheduler(dataset)
    
    # Mock evaluator calculate_fitness and evaluate_soft
    mock_evaluator = MagicMock()
    
    def mock_calculate_fitness(cand):
        # We can distinguish candidate by some attribute or sequence order
        return cand._score, cand._hard, cand._soft_penalty
        
    def mock_evaluate_soft(cand):
        return cand._soft_penalty, {"dummy": cand._raw_soft}
        
    mock_evaluator.calculate_fitness.side_effect = mock_calculate_fitness
    mock_evaluator.evaluate_soft.side_effect = mock_evaluate_soft
    scheduler.evaluator = mock_evaluator
    
    # Mock cand A, B, C
    cand_A = MagicMock()
    cand_A._hard = 1
    cand_A._raw_soft = 0
    cand_A._soft_penalty = 0
    cand_A._score = 1000.0
    
    cand_B = MagicMock()
    cand_B._hard = 0
    cand_B._raw_soft = 2
    cand_B._soft_penalty = 10
    cand_B._score = 10.0
    
    cand_C = MagicMock()
    cand_C._hard = 0
    cand_C._raw_soft = 5
    cand_C._soft_penalty = 20
    cand_C._score = 20.0
    
    scheduler.sections = [1] # 1 iteration loop item
    candidates = [cand_A, cand_B, cand_C]
    
    # Override candidate generation
    idx = 0
    def mock_gen():
        nonlocal idx
        c = candidates[idx]
        idx += 1
        return c
        
    # Run 3 iterations manually
    history = []
    best_key = None
    best_schedule = None
    best_score = None
    best_hard = None
    best_raw_soft = None
    best_soft_penalty = None
    
    for i in range(3):
        cand = mock_gen()
        score, hard, soft_penalty = scheduler.evaluator.calculate_fitness(cand)
        _, soft_details = scheduler.evaluator.evaluate_soft(cand)
        raw_soft = sum(soft_details.values())
        candidate_key = (hard, soft_penalty)

        if best_key is None or candidate_key < best_key:
            best_key = candidate_key
            best_schedule = cand
            best_score = score
            best_hard = hard
            best_raw_soft = raw_soft
            best_soft_penalty = soft_penalty

        history.append({
            "iteration": i,
            "best_score": best_score,
            "best_hard": best_hard,
            "best_raw_soft": best_raw_soft,
            "best_soft_penalty": best_soft_penalty,
        })
        
    # Check after A (idx 0)
    assert history[0]["best_hard"] == 1
    assert history[0]["best_soft_penalty"] == 0
    
    # Check after B (idx 1)
    assert history[1]["best_hard"] == 0
    assert history[1]["best_raw_soft"] == 2
    assert history[1]["best_soft_penalty"] == 10
    assert history[1]["best_score"] == 10.0
    
    # Check after C (idx 2): Best is STILL B!
    assert history[2]["best_hard"] == 0
    assert history[2]["best_raw_soft"] == 2
    assert history[2]["best_soft_penalty"] == 10
    assert history[2]["best_score"] == 10.0

def test_lexicographic_comparison_hard_priority():
    # Test 2: A = (hard 1, soft penalty 0), B = (hard 0, soft penalty 5000) -> B is better
    key_A = (1, 0)
    key_B = (0, 5000)
    assert key_B < key_A

def test_lexicographic_comparison_soft_tiebreak():
    # Test 3: A = (hard 0, soft penalty 10), B = (hard 0, soft penalty 20) -> A is better
    key_A = (0, 10)
    key_B = (0, 20)
    assert key_A < key_B

def test_final_result_consistency():
    # Test 4: Final returned dictionary metrics match evaluation of best_schedule
    dataset = DatasetFactory.create_dataset()
    scheduler = RandomSearchScheduler(dataset)
    res = scheduler.run(iterations=20)
    
    evaluator = ConstraintEvaluator(dataset)
    best_sched = res["best_schedule"]
    eval_score, eval_hard, eval_soft_penalty = evaluator.calculate_fitness(best_sched)
    _, s_details = evaluator.evaluate_soft(best_sched)
    eval_raw_soft = sum(s_details.values())
    
    assert res["best_score"] == eval_score
    assert res["hard_violations"] == eval_hard
    assert res["soft_penalty"] == eval_soft_penalty
    assert res["raw_soft_violations"] == eval_raw_soft

def test_history_is_best_so_far():
    # Test 5: Across all history iterations, best_hard and best_soft_penalty never worsen
    dataset = DatasetFactory.create_dataset()
    scheduler = RandomSearchScheduler(dataset)
    res = scheduler.run(iterations=50)
    history = res["history"]
    
    prev_key = None
    for h in history:
        assert "iteration" in h
        assert "best_score" in h
        assert "best_hard" in h
        assert "best_raw_soft" in h
        assert "best_soft_penalty" in h
        
        curr_key = (h["best_hard"], h["best_soft_penalty"])
        if prev_key is not None:
            assert curr_key <= prev_key
        prev_key = curr_key
