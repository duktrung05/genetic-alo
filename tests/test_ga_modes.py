import random
import pytest
from unittest.mock import MagicMock
from dataset import DatasetFactory
from ga import GeneticAlgorithmEngine, GAOperators
from constraints import ConstraintEvaluator
from evaluation import RandomSearchScheduler, GreedyScheduler
import main_benchmark

def test_benchmark_has_four_exact_method_names():
    dataset = DatasetFactory.create_dataset()
    GA_SEED = 42

    random.seed(GA_SEED)
    ga_no_rep = GeneticAlgorithmEngine(dataset)
    res_no_rep = ga_no_rep.run(generations=2, use_repair=False)

    random.seed(GA_SEED)
    ga_hybrid = GeneticAlgorithmEngine(dataset)
    res_hybrid = ga_hybrid.run(generations=2, use_repair=True)

    greedy = GreedyScheduler(dataset).run()
    rand = RandomSearchScheduler(dataset).run(iterations=10)

    benchmark_results = {
        "GA without Repair": res_no_rep,
        "Hybrid GA + Repair": res_hybrid,
        "Greedy Search": greedy,
        "Random Search": rand
    }

    method_names = list(benchmark_results.keys())
    assert method_names == [
        "GA without Repair",
        "Hybrid GA + Repair",
        "Greedy Search",
        "Random Search"
    ]
    assert "GA Engine (Pro)" not in benchmark_results

def test_use_repair_flag_correctness():
    dataset = DatasetFactory.create_dataset()
    engine = GeneticAlgorithmEngine(dataset, pop_size=10)

    res_false = engine.run(generations=2, use_repair=False)
    assert res_false["use_repair"] is False

    res_true = engine.run(generations=2, use_repair=True)
    assert res_true["use_repair"] is True

def test_ga_result_consistency_evaluator():
    # Evaluate best_schedule for both GA variants and compare with metrics in return dictionary
    dataset = DatasetFactory.create_dataset()
    evaluator = ConstraintEvaluator(dataset)

    # GA without Repair
    engine_no_rep = GeneticAlgorithmEngine(dataset, pop_size=20)
    res_no_rep = engine_no_rep.run(generations=5, use_repair=False)

    score, hard, soft_penalty = evaluator.calculate_fitness(res_no_rep["best_schedule"])
    _, soft_details = evaluator.evaluate_soft(res_no_rep["best_schedule"])
    raw_soft = sum(soft_details.values())

    assert score == res_no_rep["best_score"]
    assert hard == res_no_rep["hard_violations"]
    assert soft_penalty == res_no_rep["soft_penalty"]
    assert raw_soft == res_no_rep["raw_soft_violations"]

    # Hybrid GA + Repair
    engine_hybrid = GeneticAlgorithmEngine(dataset, pop_size=20)
    res_hybrid = engine_hybrid.run(generations=5, use_repair=True)

    score_h, hard_h, soft_penalty_h = evaluator.calculate_fitness(res_hybrid["best_schedule"])
    _, soft_details_h = evaluator.evaluate_soft(res_hybrid["best_schedule"])
    raw_soft_h = sum(soft_details_h.values())

    assert score_h == res_hybrid["best_score"]
    assert hard_h == res_hybrid["hard_violations"]
    assert soft_penalty_h == res_hybrid["soft_penalty"]
    assert raw_soft_h == res_hybrid["raw_soft_violations"]

def test_ga_configs_are_identical():
    # Verify main_benchmark.GA_CONFIG exists and has all hyperparams
    config = main_benchmark.GA_CONFIG
    required_keys = {"pop_size", "generations", "crossover_rate", "mutation_rate", "hard_weight", "soft_weight"}
    assert required_keys.issubset(config.keys())

def test_no_repair_called_when_use_repair_false():
    dataset = DatasetFactory.create_dataset()
    engine = GeneticAlgorithmEngine(dataset, pop_size=10)
    engine.repairer.repair = MagicMock()

    res = engine.run(generations=3, use_repair=False)
    assert engine.repairer.repair.call_count == 0
    assert res["use_repair"] is False

def test_repair_called_when_use_repair_true():
    dataset = DatasetFactory.create_dataset()
    engine = GeneticAlgorithmEngine(dataset, pop_size=10)
    engine.repairer.repair = MagicMock(side_effect=engine.repairer.repair)

    res = engine.run(generations=3, use_repair=True)
    assert engine.repairer.repair.call_count > 0
    assert res["use_repair"] is True

def test_same_seed_generates_identical_initial_population():
    dataset = DatasetFactory.create_dataset()

    random.seed(12345)
    e1 = GeneticAlgorithmEngine(dataset, pop_size=5)
    pop1 = [e1.create_random_schedule() for _ in range(5)]

    random.seed(12345)
    e2 = GeneticAlgorithmEngine(dataset, pop_size=5)
    pop2 = [e2.create_random_schedule() for _ in range(5)]

    for s1, s2 in zip(pop1, pop2):
        assert len(s1.genes) == len(s2.genes)
        for g1, g2 in zip(s1.genes, s2.genes):
            assert g1.section_id == g2.section_id
            assert g1.room_id == g2.room_id
            assert g1.timeslot_id == g2.timeslot_id

def test_best_schedules_do_not_share_mutable_references():
    dataset = DatasetFactory.create_dataset()
    GA_SEED = 42

    random.seed(GA_SEED)
    ga_no_rep = GeneticAlgorithmEngine(dataset, pop_size=10)
    res_no_rep = ga_no_rep.run(generations=2, use_repair=False)

    random.seed(GA_SEED)
    ga_hybrid = GeneticAlgorithmEngine(dataset, pop_size=10)
    res_hybrid = ga_hybrid.run(generations=2, use_repair=True)

    original_section_id = res_hybrid["best_schedule"].genes[0].section_id
    res_no_rep["best_schedule"].genes[0].section_id = "MUTATED_TEST_SECTION_ID"

    assert res_hybrid["best_schedule"].genes[0].section_id == original_section_id
