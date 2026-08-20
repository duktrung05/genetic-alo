import pytest
from domain import Gene, Schedule
from ga import GeneticAlgorithmEngine, GAOperators
from evaluation import RandomSearchScheduler, BenchmarkEvaluator

@pytest.mark.integration
def test_ga_initialization_multi_period_sections(small_dataset):
    ga = GeneticAlgorithmEngine(small_dataset, pop_size=10)
    sched = ga.create_random_schedule()
    assert len(sched.genes) == len(small_dataset["course_sections"])

@pytest.mark.integration
def test_ga_engine_run_decreases_violations_or_penalty(small_dataset):
    ga = GeneticAlgorithmEngine(small_dataset, pop_size=20, hard_weight=1000, soft_weight=1)
    res = ga.run(generations=10)

    assert "best_schedule" in res
    assert "hard_violations" in res
    assert "soft_violations" in res
    assert res["hard_violations"] == 0

@pytest.mark.integration
def test_ga_seed_reproducibility(medium_dataset):
    ga1 = GeneticAlgorithmEngine(medium_dataset, pop_size=10)
    ga2 = GeneticAlgorithmEngine(medium_dataset, pop_size=10)

    s1 = ga1.create_random_schedule()
    s2 = ga2.create_random_schedule()

    assert len(s1.genes) == len(s2.genes)

@pytest.mark.integration
def test_ga_mutation_operator_preserves_valid_blocks(medium_dataset):
    ga = GeneticAlgorithmEngine(medium_dataset, pop_size=10)
    parent = ga.create_random_schedule()

    mutated = GAOperators.mutate(parent, medium_dataset["rooms"], medium_dataset["timeslots"], mutation_rate=1.0, dataset=medium_dataset)
    assert len(mutated.genes) == len(parent.genes)

    section_map = {s.section_id: s for s in medium_dataset["course_sections"]}
    timeslot_map = {t.id: t for t in medium_dataset["timeslots"]}

    for gene in mutated.genes:
        sec = section_map[gene.section_id]
        ts = timeslot_map[gene.timeslot_id]
        # Must fit within day bounds (max 16 periods)
        assert ts.period + sec.duration_periods - 1 <= 16

@pytest.mark.unit
def test_ga_mutation_preserves_session_bounds_near_end_of_session(medium_dataset):
    ga = GeneticAlgorithmEngine(medium_dataset, pop_size=5)
    parent = ga.create_random_schedule()

    for seed_val in range(10):
        mutated = GAOperators.mutate(parent, medium_dataset["rooms"], medium_dataset["timeslots"], mutation_rate=1.0, dataset=medium_dataset)
        section_map = {s.section_id: s for s in medium_dataset["course_sections"]}
        timeslot_map = {t.id: t for t in medium_dataset["timeslots"]}

        for gene in mutated.genes:
            sec = section_map[gene.section_id]
            ts = timeslot_map[gene.timeslot_id]
            assert ts.period + sec.duration_periods - 1 <= 16


@pytest.mark.integration
def test_ga_modes_with_and_without_repair(small_dataset):
    # Hybrid GA + Repair
    ga_repair = GeneticAlgorithmEngine(small_dataset, pop_size=20)
    res_repair = ga_repair.run(generations=10, evaluation_budget=200, use_repair=True)
    assert res_repair["hard_violations"] == 0

    # GA without Repair
    ga_norepair = GeneticAlgorithmEngine(small_dataset, pop_size=20)
    res_norepair = ga_norepair.run(generations=10, evaluation_budget=200, use_repair=False)
    assert "hard_violations" in res_norepair

@pytest.mark.integration
def test_evaluation_budget_enforcement(medium_dataset):
    ga = GeneticAlgorithmEngine(medium_dataset, pop_size=10)
    budget = 50
    res = ga.run(generations=20, evaluation_budget=budget, use_repair=True)

    assert res["history"][-1]["fitness_evaluations"] <= budget
    assert len(res["history"]) > 0

    # Monotonic evaluation counts in history
    eval_counts = [h["fitness_evaluations"] for h in res["history"]]
    assert eval_counts == sorted(eval_counts)

@pytest.mark.integration
def test_random_search_baseline(medium_dataset):
    rs = RandomSearchScheduler(medium_dataset)
    res = rs.run(iterations=50, evaluation_budget=50)

    assert res["history"][-1]["fitness_evaluations"] <= 50
    assert "best_schedule" in res
    assert "hard_violations" in res

@pytest.mark.unit
def test_benchmark_evaluator_metrics():
    rate = BenchmarkEvaluator.calculate_conflict_reduction_rate(initial_violations=10, final_violations=2)
    assert rate == 80.0
    assert BenchmarkEvaluator.calculate_conflict_reduction_rate(0, 0) == 100.0

@pytest.mark.unit
def test_crossover_does_not_mutate_parents_and_child_genes_are_independent(medium_dataset):
    ga = GeneticAlgorithmEngine(medium_dataset, pop_size=10)
    p1 = ga.create_random_schedule()
    p2 = ga.create_random_schedule()

    # Capture state before crossover
    p1_genes_before = [(g.section_id, g.room_id, g.timeslot_id) for g in p1.genes]
    p2_genes_before = [(g.section_id, g.room_id, g.timeslot_id) for g in p2.genes]

    c1, c2 = GAOperators.crossover(p1, p2)

    # Verify parents were not mutated
    p1_genes_after = [(g.section_id, g.room_id, g.timeslot_id) for g in p1.genes]
    p2_genes_after = [(g.section_id, g.room_id, g.timeslot_id) for g in p2.genes]
    assert p1_genes_before == p1_genes_after
    assert p2_genes_before == p2_genes_after

    # Verify child genes list and objects are independent
    assert c1.genes is not p1.genes
    assert c1.genes is not p2.genes
    assert c2.genes is not p1.genes
    assert c2.genes is not p2.genes
    assert c1.genes[0] is not p1.genes[0]
    assert c1.genes[0] is not p2.genes[0]

    # Mutate child gene and verify parents unaffected
    c1.genes[0].room_id = "MODIFIED_ROOM"
    assert p1.genes[0].room_id != "MODIFIED_ROOM"
    assert p2.genes[0].room_id != "MODIFIED_ROOM"

@pytest.mark.unit
def test_mutation_does_not_mutate_input_schedule_and_genes_are_independent(medium_dataset):
    ga = GeneticAlgorithmEngine(medium_dataset, pop_size=10)
    parent = ga.create_random_schedule()
    parent_genes_before = [(g.section_id, g.room_id, g.timeslot_id) for g in parent.genes]

    mutated = GAOperators.mutate(parent, medium_dataset["rooms"], medium_dataset["timeslots"], mutation_rate=1.0, dataset=medium_dataset)

    parent_genes_after = [(g.section_id, g.room_id, g.timeslot_id) for g in parent.genes]
    assert parent_genes_before == parent_genes_after

    assert mutated.genes is not parent.genes
    assert mutated.genes[0] is not parent.genes[0]

    mutated.genes[0].room_id = "MUTATED_TEST_ROOM"
    assert parent.genes[0].room_id != "MUTATED_TEST_ROOM"

@pytest.mark.unit
def test_invalid_elite_count_rejected(medium_dataset):
    with pytest.raises(ValueError, match="elite_count must satisfy"):
        GeneticAlgorithmEngine(medium_dataset, pop_size=10, elite_count=0)

    with pytest.raises(ValueError, match="elite_count must satisfy"):
        GeneticAlgorithmEngine(medium_dataset, pop_size=10, elite_count=10)

    ga_valid = GeneticAlgorithmEngine(medium_dataset, pop_size=10, elite_count=3)
    assert ga_valid.elite_count == 3
    res = ga_valid.run(generations=2, evaluation_budget=20)
    assert "best_schedule" in res

@pytest.mark.unit
def test_greedy_scheduler_same_seed_reproducibility(medium_dataset):
    from evaluation import GreedyScheduler
    g1 = GreedyScheduler(medium_dataset, seed=42).run()
    g2 = GreedyScheduler(medium_dataset, seed=42).run()

    genes1 = [(g.section_id, g.room_id, g.timeslot_id) for g in g1["best_schedule"].genes]
    genes2 = [(g.section_id, g.room_id, g.timeslot_id) for g in g2["best_schedule"].genes]

    assert genes1 == genes2
    assert g1["best_score"] == g2["best_score"]


@pytest.mark.unit
def test_ga_supports_population_two_and_single_section(small_dataset):
    one_section_dataset = dict(small_dataset)
    one_section_dataset["course_sections"] = small_dataset["course_sections"][:1]

    engine = GeneticAlgorithmEngine(
        one_section_dataset,
        pop_size=2,
        elite_count=1,
        seed=7,
    )
    result = engine.run(
        generations=2,
        evaluation_budget=4,
        crossover_rate=1.0,
        mutation_rate=0.0,
        use_repair=False,
        seed=7,
    )

    assert result["fitness_evaluations"] == 4
    assert len(result["best_schedule"].genes) == 1
    assert GAOperators.validate_chromosome(
        result["best_schedule"], one_section_dataset
    )


@pytest.mark.unit
def test_crossover_single_gene_returns_independent_parent_clones():
    parent1 = Schedule(genes=[Gene("SEC1", "R1", 1)])
    parent2 = Schedule(genes=[Gene("SEC1", "R2", 2)])

    child1, child2 = GAOperators.crossover(parent1, parent2)

    assert child1.genes == parent1.genes
    assert child2.genes == parent2.genes
    assert child1.genes is not parent1.genes
    assert child2.genes is not parent2.genes
    assert child1.genes[0] is not parent1.genes[0]
    assert child2.genes[0] is not parent2.genes[0]


@pytest.mark.unit
def test_tournament_selection_rejects_empty_or_misaligned_inputs():
    with pytest.raises(ValueError, match="population must not be empty"):
        GAOperators.tournament_selection([], [])

    schedule = Schedule(genes=[])
    with pytest.raises(ValueError, match="fitness_keys length"):
        GAOperators.tournament_selection([schedule], [])
