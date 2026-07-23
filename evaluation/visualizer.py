import os
from typing import Dict, List, Any, Optional
import matplotlib.pyplot as plt

class ConvergenceVisualizer:
    @staticmethod
    def _validate_and_extract(history: List[Dict[str, Any]], field: str) -> tuple[list, list]:
        if not isinstance(history, list) or not history:
            raise ValueError("History list cannot be empty or invalid.")

        x_vals = []
        y_vals = []

        for record in history:
            if not isinstance(record, dict):
                raise ValueError("History record must be a dictionary.")

            if "fitness_evaluations" not in record:
                raise ValueError("History record missing required field 'fitness_evaluations'.")

            val = record.get(field)
            if val is None:
                # Fallback field names for backward compatibility across GA and Random Search
                if field == "best_hard":
                    val = record.get("hard_violations")
                elif field == "best_soft_penalty":
                    if record.get("best_soft") is not None:
                        val = record.get("best_soft")
                    elif record.get("soft_penalty") is not None:
                        val = record.get("soft_penalty")
                    elif record.get("soft_violations") is not None:
                        val = record.get("soft_violations")

            if val is None:
                raise ValueError(f"History record missing required metric field '{field}'.")

            x_vals.append(record["fitness_evaluations"])
            y_vals.append(val)

        # Check monotonic non-decreasing
        for i in range(len(x_vals) - 1):
            if x_vals[i+1] < x_vals[i]:
                raise ValueError(f"fitness_evaluations must be non-decreasing, got {x_vals[i]} followed by {x_vals[i+1]}")

        return x_vals, y_vals

    @staticmethod
    def _prepare_plot_data(x_vals: list, y_vals: list, evaluation_budget: Optional[int]) -> tuple[list, list]:
        # Copy to prevent mutating original history
        x_plot = list(x_vals)
        y_plot = list(y_vals)

        if evaluation_budget is not None and x_plot and x_plot[-1] < evaluation_budget:
            x_plot.append(evaluation_budget)
            y_plot.append(y_plot[-1])

        return x_plot, y_plot

    @classmethod
    def plot_convergence(
        cls,
        ga_without_repair_history: list,
        hybrid_ga_history: list,
        random_history: list,
        hard_output_path: str = "evaluation/convergence_hard.png",
        soft_output_path: str = "evaluation/convergence_soft.png",
        evaluation_budget: Optional[int] = 6000
    ):
        histories = {
            "GA without Repair": ga_without_repair_history,
            "Hybrid GA + Repair": hybrid_ga_history,
            "Random Search": random_history
        }

        # 1. Plot Hard Violations Chart
        os.makedirs(os.path.dirname(hard_output_path), exist_ok=True)
        plt.figure(figsize=(10, 6))

        for method_name, history in histories.items():
            x_vals, y_vals = cls._validate_and_extract(history, "best_hard")
            x_plot, y_plot = cls._prepare_plot_data(x_vals, y_vals, evaluation_budget)
            plt.step(x_plot, y_plot, where="post", label=method_name, linewidth=2)

        plt.title("Hard Constraint Violations Convergence", fontsize=13, fontweight="bold", pad=15)
        plt.xlabel("Number of Fitness Evaluations", fontsize=12)
        plt.ylabel("Best Hard Violations", fontsize=12)
        plt.grid(True, linestyle=":", alpha=0.6)
        plt.legend(fontsize=11)
        plt.tight_layout()
        plt.savefig(hard_output_path, dpi=300)
        plt.close()
        print(f"\n--> Đã lưu biểu đồ hard convergence tại: {hard_output_path}")

        # 2. Plot Soft Penalty Chart
        os.makedirs(os.path.dirname(soft_output_path), exist_ok=True)
        plt.figure(figsize=(10, 6))

        for method_name, history in histories.items():
            x_vals, y_vals = cls._validate_and_extract(history, "best_soft_penalty")
            x_plot, y_plot = cls._prepare_plot_data(x_vals, y_vals, evaluation_budget)
            plt.step(x_plot, y_plot, where="post", label=method_name, linewidth=2)

        plt.title("Soft Penalty Convergence (Secondary to Hard Feasibility)", fontsize=13, fontweight="bold", pad=15)
        plt.xlabel("Number of Fitness Evaluations", fontsize=12)
        plt.ylabel("Best Soft Penalty", fontsize=12)
        plt.grid(True, linestyle=":", alpha=0.6)
        plt.legend(fontsize=11)
        plt.tight_layout()
        plt.savefig(soft_output_path, dpi=300)
        plt.close()
        print(f"--> Đã lưu biểu đồ soft convergence tại: {soft_output_path}")

        # 3. Create backward compatibility chart at evaluation/convergence_comparison.png
        compat_path = "evaluation/convergence_comparison.png"
        if hard_output_path != compat_path and soft_output_path != compat_path:
            os.makedirs(os.path.dirname(compat_path), exist_ok=True)
            plt.figure(figsize=(10, 6))
            for method_name, history in histories.items():
                x_vals, y_vals = cls._validate_and_extract(history, "best_hard")
                x_plot, y_plot = cls._prepare_plot_data(x_vals, y_vals, evaluation_budget)
                plt.step(x_plot, y_plot, where="post", label=method_name, linewidth=2)
            plt.title("Hard Constraint Violations Convergence", fontsize=13, fontweight="bold", pad=15)
            plt.xlabel("Number of Fitness Evaluations", fontsize=12)
            plt.ylabel("Best Hard Violations", fontsize=12)
            plt.grid(True, linestyle=":", alpha=0.6)
            plt.legend(fontsize=11)
            plt.tight_layout()
            plt.savefig(compat_path, dpi=300)
            plt.close()
