"""Small paired-seed sensitivity audit for Phase 1.1 weight profiles."""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from statistics import mean
import sys

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from constraints import SOFT_WEIGHT_PROFILES, ConstraintEvaluator, SoftConstraintConfig
from dataset import ExcelDatasetLoader
from ga import GeneticAlgorithmEngine


SEEDS = (41, 42, 43)
GA_CONFIG = {
    "population_size": 60,
    "generations": 100,
    "evaluation_budget": 600,
    "crossover_rate": 0.8,
    "mutation_rate": 0.2,
    "use_repair": True,
    "use_soft_local_search": True,
    "soft_local_search_max_passes": 2,
    "soft_local_search_max_candidate_checks": 1000,
    "use_guided_mutation": True,
    "guided_mutation_probability": 0.8,
}


def _run(dataset: dict, profile: str, seed: int) -> dict:
    config = SoftConstraintConfig.from_profile(profile)
    engine = GeneticAlgorithmEngine(
        dataset,
        pop_size=GA_CONFIG["population_size"],
        seed=seed,
        soft_config=config,
    )
    result = engine.run(
        generations=GA_CONFIG["generations"],
        evaluation_budget=GA_CONFIG["evaluation_budget"],
        crossover_rate=GA_CONFIG["crossover_rate"],
        mutation_rate=GA_CONFIG["mutation_rate"],
        use_repair=GA_CONFIG["use_repair"],
        use_soft_local_search=GA_CONFIG["use_soft_local_search"],
        soft_local_search_max_passes=GA_CONFIG["soft_local_search_max_passes"],
        soft_local_search_max_candidate_checks=GA_CONFIG[
            "soft_local_search_max_candidate_checks"
        ],
        use_guided_mutation=GA_CONFIG["use_guided_mutation"],
        guided_mutation_probability=GA_CONFIG["guided_mutation_probability"],
        seed=seed,
    )
    final = ConstraintEvaluator(dataset, soft_config=config).evaluate_unified(
        result["best_schedule"]
    )
    row = {
        "profile": profile,
        "seed": seed,
        "hard_violations": final.hard_violations,
        "feasible": final.hard_violations == 0,
        "total_soft_score": final.soft_penalty,
        "runtime_seconds": result["run_metrics"].runtime_seconds,
    }
    total = final.soft_penalty
    by_id = {item.constraint_id: item for item in final.soft_breakdown}
    for constraint_id in [f"S{i}" for i in range(1, 8)]:
        item = by_id[constraint_id]
        row[f"{constraint_id}_normalized"] = item.normalized_penalty
        row[f"{constraint_id}_weighted"] = item.weighted_penalty
        row[f"{constraint_id}_contribution_pct"] = (
            100.0 * item.weighted_penalty / total if total > 0 else 0.0
        )
    row["S6_mismatches"] = by_id["S6"].raw_count
    row["S7_mismatches"] = by_id["S7"].raw_count
    row["campus_mismatches_combined"] = (
        by_id["S6"].raw_count + by_id["S7"].raw_count
    )
    row["room_waste_raw_ratio_sum"] = by_id["S4"].raw_count
    row["room_waste_normalized"] = by_id["S4"].normalized_penalty
    row["S6_S7_combined_contribution_pct"] = (
        row["S6_contribution_pct"] + row["S7_contribution_pct"]
    )
    return row


def _summarize(rows: list[dict]) -> dict:
    summaries = {}
    for profile in SOFT_WEIGHT_PROFILES:
        subset = [row for row in rows if row["profile"] == profile]
        summaries[profile] = {
            "runs": len(subset),
            "feasible_runs": sum(row["feasible"] for row in subset),
            "mean_total_soft_score": mean(row["total_soft_score"] for row in subset),
            "mean_runtime_seconds": mean(row["runtime_seconds"] for row in subset),
            "mean_normalized": {
                f"S{i}": mean(row[f"S{i}_normalized"] for row in subset)
                for i in range(1, 8)
            },
            "mean_weighted": {
                f"S{i}": mean(row[f"S{i}_weighted"] for row in subset)
                for i in range(1, 8)
            },
            "mean_contribution_pct": {
                f"S{i}": mean(row[f"S{i}_contribution_pct"] for row in subset)
                for i in range(1, 8)
            },
            "dominance_over_50_count": {
                f"S{i}": sum(row[f"S{i}_contribution_pct"] > 50 for row in subset)
                for i in range(1, 8)
            },
            "mean_S6_S7_combined_contribution_pct": mean(
                row["S6_S7_combined_contribution_pct"] for row in subset
            ),
            "mean_campus_mismatches_combined": mean(
                row["campus_mismatches_combined"] for row in subset
            ),
            "mean_room_waste_normalized": mean(
                row["room_waste_normalized"] for row in subset
            ),
        }
    return summaries


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", default="data/instances/instance_easy.xlsx")
    parser.add_argument(
        "--output-dir", default="outputs/benchmark/phase1_1_weight_sensitivity"
    )
    args = parser.parse_args()

    dataset = ExcelDatasetLoader.load_and_validate(args.input)
    rows = [
        _run(dataset, profile, seed)
        for seed in SEEDS
        for profile in SOFT_WEIGHT_PROFILES
    ]
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    csv_path = output_dir / "raw_runs.csv"
    with csv_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)

    payload = {
        "scope": "Phase 1.1 small sensitivity; no statistical significance claim",
        "paired_seeds": list(SEEDS),
        "ga_config": GA_CONFIG,
        "profiles": {name: dict(weights) for name, weights in SOFT_WEIGHT_PROFILES.items()},
        "summary": _summarize(rows),
        "runs": rows,
    }
    (output_dir / "summary.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(payload["summary"], ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
