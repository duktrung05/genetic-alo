# Final Benchmark: Easy vs Medium

All methods use paired seeds 0–9, population 60, and exactly 1,000 GA objective evaluations per run.

Final soft-score statistics include hard-feasible runs only.

## Results

| Dataset | Method | Feasible | Hard median | Feasible soft median | Runtime median (s) | Repair checks mean | SLS checks mean | Total work mean |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| Easy | GA without Repair | 0/10 | 5.00 | N/A | 6.541 | 0.0 | 0.0 | 1000.0 |
| Easy | GA + Repair | 10/10 | 0.00 | 9.6597 | 14.649 | 30999.7 | 0.0 | 31999.7 |
| Easy | GA + Repair + SLS (Production) | 10/10 | 0.00 | 6.3194 | 25.525 | 30999.7 | 5000.0 | 36999.7 |
| Medium | GA without Repair | 0/10 | 5.00 | N/A | 7.134 | 0.0 | 0.0 | 1000.0 |
| Medium | GA + Repair | 10/10 | 0.00 | 9.6210 | 15.792 | 35353.6 | 0.0 | 36353.6 |
| Medium | GA + Repair + SLS (Production) | 10/10 | 0.00 | 5.5768 | 27.118 | 35353.6 | 5000.0 | 41353.6 |

## Main questions

### Q1 — Does Repair improve feasibility?

Yes in these runs: Easy improves from 0/10 to 10/10, and Medium from 0/10 to 10/10.

### Q2 — Does SLS improve feasible soft quality?

Easy feasible-soft median changes from 9.6597 to 6.3194; Medium changes from 9.6210 to 5.5768.

### Q3 — What changes from Easy to Medium?

Candidate-domain median falls from 468 to 274; LAB utilization rises from 7.29% to 22.22%; and maximum lecturer load rises from 26.04% to 34.72%. Vanilla GA mean hard violations rise from 5.10 to 5.70, while the median remains 5.00 on both datasets. Repair remains feasible in all runs.

### Q4 — What is the computational cost?

Every method receives the same 1,000 GA objective evaluations. Repair candidate checks and SLS candidate checks are reported separately and included in total work; runtime captures remaining implementation overhead.
