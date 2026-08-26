# EASY Instance Difficulty Report

**Difficulty classification: EASY**

## Instance identity

- SHA-256: `dfbff415600ff0a1a2cba8b55c90ab52dbcd7b3db3b090f16f1b49cee2bc6e6d`
- Sections / activities: 62 / 62
- Rooms / timeslots / teaching days: 11 / 96 / 6

## Structural evidence

- Room utilization: 14.9621%
- LAB utilization: 7.2917%
- Lecturer load ratio (mean / median / max): 0.1128 / 0.1042 / 0.2604
- Student-group load ratio (mean / median / max): 0.1372 / 0.1354 / 0.1875
- Candidate domain (min / median / mean / max): 120 / 468.0 / 444.87 / 624
- Activity pairs sharing lecturer / group: 131 / 130

## Paired sanity experiment

Configuration: seeds [0, 1, 2], population 60, search budget 1000 per run.

| Method | Seed | Feasible | First generation | First evaluation | Final hard | Final soft | Runtime (s) |
|---|---:|:---:|---:|---:|---:|---:|---:|
| ga | 0 | false | None | None | 6 | 13.595233 | 5.644 |
| ga_repair | 0 | true | 1 | 63 | 0 | 9.829669 | 14.624 |
| ga_repair_sls | 0 | true | 1 | 63 | 0 | 6.302943 | 25.317 |
| ga | 1 | false | None | None | 5 | 13.556527 | 6.590 |
| ga_repair | 1 | true | 1 | 63 | 0 | 9.559138 | 14.586 |
| ga_repair_sls | 1 | true | 1 | 63 | 0 | 5.637603 | 23.124 |
| ga | 2 | false | None | None | 4 | 13.165174 | 4.139 |
| ga_repair | 2 | true | 1 | 63 | 0 | 9.416315 | 11.091 |
| ga_repair_sls | 2 | true | 1 | 63 | 0 | 7.014106 | 25.748 |

## Classification rationale

The EASY label is supported by the low aggregate room and LAB utilization, large individually legal activity domains, modest lecturer/group load ratios, and the observed feasibility timing in the paired sanity runs. This is a baseline classification, not a claim that every random schedule is feasible.

## Metric definitions

See `metric_definitions` in the JSON artifact for the exact reproducible definitions.
