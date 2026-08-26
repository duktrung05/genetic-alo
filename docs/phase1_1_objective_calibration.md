# Phase 1.1 objective calibration

## S6/S7 overlap audit — current workbook

Source: `data/01_data_timetable.xlsx`.

- Sections with both `preferred_campus_id` and group `home_campus_id`: 62
- Same: 62
- Different: 0
- Agreement rate: 100%

Conclusion: S6 and S7 are perfectly correlated in the current workbook, so a
campus mismatch is double-counted by both objectives. Keep both because S6 is
the section's requested campus while S7 is the student group's home campus,
but review their combined weight. Correlation never changes weights
automatically.

## Weight profiles

All profiles total 28. Values are ordered S1 through S7.

| Profile | S1 | S2 | S3 | S4 | S5 | S6 | S7 | Rationale |
|---|---:|---:|---:|---:|---:|---:|---:|---|
| Student-centric | 6 | 4 | 5 | 2 | 3 | 3 | 5 | Prioritizes compact days, preferred shift, and student home campus. |
| Balanced (default) | 5 | 4 | 4 | 4 | 4 | 3 | 4 | No stakeholder mandate; balances student, timetable, and room quality while limiting correlated S6+S7. |
| Resource-centric | 3 | 3 | 3 | 10 | 4 | 2 | 3 | Makes normalized room fit the main resource priority. |

## Small paired-seed sensitivity

This is a directional sensitivity check, not a statistical-significance claim.
Seeds 41, 42, and 43 used the same GA configuration: population 60, search
budget 600, crossover 0.8, mutation 0.2, Repair enabled, SLS enabled (2 passes,
1,000 candidate checks), and guided mutation enabled (probability 0.8).

| Profile | Feasible | Mean soft | Mean runtime (s) | Mean S1 share | Mean S4 share | Mean S6+S7 share | Objectives >50% |
|---|---:|---:|---:|---:|---:|---:|---:|
| Student-centric | 3/3 | 7.0852 | 5.9047 | 35.45% | 6.49% | 25.32% | none |
| Balanced | 3/3 | 6.8684 | 5.9295 | 30.68% | 14.46% | 24.61% | none |
| Resource-centric | 3/3 | 6.4150 | 5.9602 | 18.71% | 37.31% | 15.96% | none |

S1 no longer dominates. S4 is intentionally weak only in Student-centric and
becomes material in Balanced/Resource-centric. S6+S7 remains material but does
not dominate under any profile. Balanced is the default because no stakeholder
requirement establishes either extreme profile.
