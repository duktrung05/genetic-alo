import os
from typing import Dict, List, Any, Optional, Union
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

class ConvergenceVisualizer:
    @staticmethod
    def _extract_field_val(record: dict, field: str) -> float:
        val = record.get(field)
        if val is None:
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
        return float(val)

    @classmethod
    def _extract_series(cls, history_input: Any, field: str) -> tuple[list, list, Optional[list], Optional[list]]:
        """Trích xuất (x_vals, median_y, q25_y, q75_y) từ lịch sử của 1 seed hoặc nhiều seed."""

        if not isinstance(history_input, list) or not history_input:
            raise ValueError("History input cannot be empty or invalid.")

        is_multi_seed = False
        first_elem = history_input[0]
        if isinstance(first_elem, list):
            is_multi_seed = True
            seed_histories = history_input
        elif isinstance(first_elem, dict) and "history" in first_elem:
            is_multi_seed = True
            seed_histories = [r["history"] for r in history_input if isinstance(r, dict) and "history" in r]

        if is_multi_seed:
            min_len = min(len(h) for h in seed_histories if isinstance(h, list) and h)
            x_vals = []
            median_y = []
            q25_y = []
            q75_y = []

            for i in range(min_len):
                evals = [h[i]["fitness_evaluations"] for h in seed_histories]
                x_vals.append(float(np.median(evals)))

                vals = [cls._extract_field_val(h[i], field) for h in seed_histories]
                median_y.append(float(np.median(vals)))
                q25_y.append(float(np.percentile(vals, 25)))
                q75_y.append(float(np.percentile(vals, 75)))

            return x_vals, median_y, q25_y, q75_y
        else:
            x_vals = []
            y_vals = []
            for record in history_input:
                if "fitness_evaluations" not in record:
                    raise ValueError("History record missing required field 'fitness_evaluations'.")
                x_vals.append(record["fitness_evaluations"])
                y_vals.append(cls._extract_field_val(record, field))

            for i in range(len(x_vals) - 1):
                if x_vals[i+1] < x_vals[i]:
                    raise ValueError(f"fitness_evaluations must be non-decreasing, got {x_vals[i]} followed by {x_vals[i+1]}")

            return x_vals, y_vals, None, None

    @staticmethod
    def _prepare_plot_data(x_vals: list, y_vals: list, q25_vals: Optional[list], q75_vals: Optional[list], evaluation_budget: Optional[int]):
        x_plot = list(x_vals)
        y_plot = list(y_vals)
        q25_plot = list(q25_vals) if q25_vals is not None else None
        q75_plot = list(q75_vals) if q75_vals is not None else None

        if evaluation_budget is not None and x_plot and x_plot[-1] < evaluation_budget:
            x_plot.append(evaluation_budget)
            y_plot.append(y_plot[-1])
            if q25_plot is not None and q75_plot is not None:
                q25_plot.append(q25_plot[-1])
                q75_plot.append(q75_plot[-1])

        return x_plot, y_plot, q25_plot, q75_plot

    @classmethod
    def plot_convergence(
        cls,
        ga_without_repair_history: Union[list, List[list]],
        hybrid_ga_history: Union[list, List[list]],
        random_history: Union[list, List[list]],
        hard_output_path: str = "outputs/charts/convergence_hard.png",
        soft_output_path: str = "outputs/charts/convergence_soft.png",
        evaluation_budget: Optional[int] = 6000
    ):
        histories = {
            "GA without Repair": ga_without_repair_history,
            "Hybrid GA + Repair": hybrid_ga_history,
            "Random Search": random_history
        }

        colors = {
            "GA without Repair": "#4C72B0",
            "Hybrid GA + Repair": "#55A868",
            "Random Search": "#C44E52",
        }

        # 1. Plot Hard Violations Chart
        os.makedirs(os.path.dirname(hard_output_path), exist_ok=True)
        plt.figure(figsize=(10, 6))

        for method_name, history in histories.items():
            if not history:
                continue
            x_vals, y_vals, q25, q75 = cls._extract_series(history, "best_hard")
            x_plot, y_plot, q25_p, q75_p = cls._prepare_plot_data(x_vals, y_vals, q25, q75, evaluation_budget)

            c = colors.get(method_name, None)
            plt.step(x_plot, y_plot, where="post", label=method_name, linewidth=2, color=c)
            if q25_p is not None and q75_p is not None:
                plt.fill_between(x_plot, q25_p, q75_p, step="post", alpha=0.18, color=c)

        plt.title("Aggregated Hard Constraint Violations Convergence (Median & IQR)", fontsize=13, fontweight="bold", pad=15)
        plt.xlabel("Number of Fitness Evaluations", fontsize=12)
        plt.ylabel("Median Best Hard Violations", fontsize=12)
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
            if not history:
                continue
            x_vals, y_vals, q25, q75 = cls._extract_series(history, "best_soft_penalty")
            x_plot, y_plot, q25_p, q75_p = cls._prepare_plot_data(x_vals, y_vals, q25, q75, evaluation_budget)

            c = colors.get(method_name, None)
            plt.step(x_plot, y_plot, where="post", label=method_name, linewidth=2, color=c)
            if q25_p is not None and q75_p is not None:
                plt.fill_between(x_plot, q25_p, q75_p, step="post", alpha=0.18, color=c)

        plt.title("Aggregated Soft Penalty Convergence (Median & IQR)", fontsize=13, fontweight="bold", pad=15)
        plt.xlabel("Number of Fitness Evaluations", fontsize=12)
        plt.ylabel("Median Best Soft Penalty", fontsize=12)
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
                if not history:
                    continue
                x_vals, y_vals, q25, q75 = cls._extract_series(history, "best_hard")
                x_plot, y_plot, q25_p, q75_p = cls._prepare_plot_data(x_vals, y_vals, q25, q75, evaluation_budget)
                c = colors.get(method_name, None)
                plt.step(x_plot, y_plot, where="post", label=method_name, linewidth=2, color=c)
                if q25_p is not None and q75_p is not None:
                    plt.fill_between(x_plot, q25_p, q75_p, step="post", alpha=0.18, color=c)
            plt.title("Aggregated Hard Constraint Violations Convergence (Median & IQR)", fontsize=13, fontweight="bold", pad=15)
            plt.xlabel("Number of Fitness Evaluations", fontsize=12)
            plt.ylabel("Median Best Hard Violations", fontsize=12)
            plt.grid(True, linestyle=":", alpha=0.6)
            plt.legend(fontsize=11)
            plt.tight_layout()
            plt.savefig(compat_path, dpi=300)
            plt.close()
