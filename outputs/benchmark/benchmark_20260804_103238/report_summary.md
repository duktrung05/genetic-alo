# Formal Academic Benchmark Experiment Report

> **Generated at**: 2026-08-04 10:46:16

## 1. Executive Summary & Statistical Conclusions

- **Feasibility Rate**: There is insufficient statistical evidence to conclude a difference (p_adj = 0.0625 >= 0.05). (Test: McNemar Exact Test, Method=mcnemar_exact, Statistic=6.0000, Raw p=3.1250e-02, Adjusted p=6.2500e-02, Effect Size=+20.0 percentage points).
- **Hard Constraint Violations**: There is insufficient statistical evidence to conclude a difference (p_adj = 0.0625 >= 0.05). (Test: Wilcoxon Signed-Rank Test, Method=exact, Statistic=0.0000, Raw p=6.2500e-02, Adjusted p=6.2500e-02, Effect Size=1.000).
- **Runtime (seconds)**: Statistically significant difference (p_adj = 9.1269e-06 < 0.05). (Test: Wilcoxon Signed-Rank Test, Method=normal_approximation, Statistic=0.0000, Raw p=1.8254e-06, Adjusted p=9.1269e-06, Effect Size=-1.000).
- **Time to First Feasible (seconds)**: Statistically significant difference (p_adj = 7.7690e-05 < 0.05). (Test: Wilcoxon Signed-Rank Test, Method=normal_approximation, Statistic=0.0000, Raw p=1.9422e-05, Adjusted p=7.7690e-05, Effect Size=1.000).
- **Soft Penalty (Paired Feasible Seeds)**: Statistically significant difference (p_adj = 7.7690e-05 < 0.05). (Test: Wilcoxon Signed-Rank Test, Method=normal_approximation, Statistic=0.0000, Raw p=1.9422e-05, Adjusted p=7.7690e-05, Effect Size=Median reduction = 1949.0 (50.1%), r_rb = 1.000).

## 2. Quality & Computational Cost Summaries

| Method | Runs | Feasible % | 95% Wilson CI | Med Hard | Med Feasible Soft | 95% Bootstrap CI | Med Runtime (s) |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| Hybrid GA + Repair | 30 | 100.0% | [88.6%, 100.0%] | 0.0 | 1927.5 | [1901.0, 1953.5] | 17.3210 |
| GA without Repair | 30 | 80.0% | [62.7%, 90.5%] | 0.0 | 3891.0 | [3673.0, 4013.0] | 9.8310 |
| Greedy Search | 1 | 100.0% | [100.0%, 100.0%] | 0.0 | 4225.0 | N/A | 0.0024 |