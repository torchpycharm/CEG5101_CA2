# Run summary: run4

Legitimate flow: h1 -> h6, UDP 5M; time 0 = start of the baseline phase.

## Task 3 - dynamic cost of the loaded links

| Scenario | Link | C0 | Peak utilisation | Peak cost | Peak normalised cost | Cost 10-16 s after |
|---|---|---|---|---|---|---|
| a | s2-s3 | 10 | 0.089 | 30.89 | 3.09 | 10.00 |
| b | s2-s6 | 10 | 0.200 | 32.00 | 3.20 | 11.06 |
| c | s5-s6 | 10 | 0.076 | 30.76 | 3.08 | 10.00 |

## Task 4 - per scenario

### Scenario a: h2 -> h3, link s2-s3 (30-60 s)

- **a. Load / cost of s2-s3**: utilisation peak 0.089, cost 10 -> peak 30.89 (normalised 3.09)
- **b. Detection**: 10.0.0.2 flagged 1.2 s after the start (rate=5708 pps baseline=2.0); IPs blocked in this scenario: 10.0.0.2
- **c. Rerouted**: no (h1->h6 path did not use a penalised link or no cheaper path existed)
- **d. h1->h6 path**: before `s1>s2>s6>h6`; during `s1>s2>s6>h6`

  | Phase | Throughput mean (Mbps) | Throughput min (Mbps) | UDP loss (%) | Ping loss mean (%) | Ping loss peak (%) | Seconds with 100% ping loss |
  |---|---|---|---|---|---|---|
  | before (10 s) | 5.00 | 4.99 | 0.00 | 0.00 | 0 | 0 |
  | during | 5.00 | 4.99 | 0.00 | 0.00 | 0 | 0 |
  | after (+10-16 s) | 5.00 | 4.99 | 0.00 | 0.00 | 0 | 0 |

- **e. Connectivity**: UDP throughput never below 4.99 Mbps during the scenario; 0 s with every ping lost
- **f. Recovery**: 10.0.0.2 released 7.2 s after the traffic stopped; anomaly flag on s2-s3 cleared 7.2 s after; h1->h6 back on `s1>s2>s6>h6` 0.9 s after

### Scenario b: h2 -> h6, link s2-s6 (90-120 s)

- **a. Load / cost of s2-s6**: utilisation peak 0.200, cost 10 -> peak 32.00 (normalised 3.20)
- **b. Detection**: 10.0.0.2 flagged 1.2 s after the start (rate=4124 pps baseline=2.0); IPs blocked in this scenario: 10.0.0.2
- **c. Rerouted**: yes - 1.2 s: s1>s2>s6 (38.30) => s1>s5>s6 (20.00); 37.3 s: s1>s5>s6 (22.59) => s1>s2>s6 (15.00)
- **d. h1->h6 path**: before `s1>s2>s6>h6`; during `s1>s2>s6>h6`, `s1>s5>s6>h6`

  | Phase | Throughput mean (Mbps) | Throughput min (Mbps) | UDP loss (%) | Ping loss mean (%) | Ping loss peak (%) | Seconds with 100% ping loss |
  |---|---|---|---|---|---|---|
  | before (10 s) | 4.96 | 4.67 | 0.65 | 0.00 | 0 | 0 |
  | during | 5.00 | 4.99 | 0.00 | 0.00 | 0 | 0 |
  | after (+10-16 s) | 5.00 | 4.99 | 0.00 | 0.00 | 0 | 0 |

- **e. Connectivity**: UDP throughput never below 4.99 Mbps during the scenario; 0 s with every ping lost
- **f. Recovery**: 10.0.0.2 released 7.2 s after the traffic stopped; anomaly flag on s2-s6 cleared 7.2 s after; h1->h6 back on `s1>s2>s6>h6` 7.8 s after

### Scenario c: h5 -> h6, link s5-s6 (150-180 s)

- **a. Load / cost of s5-s6**: utilisation peak 0.076, cost 10 -> peak 30.76 (normalised 3.08)
- **b. Detection**: 10.0.0.5 flagged 1.2 s after the start (rate=17147 pps baseline=1.0); IPs blocked in this scenario: 10.0.0.5
- **c. Rerouted**: no (h1->h6 path did not use a penalised link or no cheaper path existed)
- **d. h1->h6 path**: before `s1>s2>s6>h6`; during `s1>s2>s6>h6`

  | Phase | Throughput mean (Mbps) | Throughput min (Mbps) | UDP loss (%) | Ping loss mean (%) | Ping loss peak (%) | Seconds with 100% ping loss |
  |---|---|---|---|---|---|---|
  | before (10 s) | 5.00 | 4.99 | 0.00 | 0.00 | 0 | 0 |
  | during | 5.00 | 4.99 | 0.00 | 0.00 | 0 | 0 |
  | after (+10-16 s) | 5.00 | 4.99 | 0.00 | 0.00 | 0 | 0 |

- **e. Connectivity**: UDP throughput never below 4.99 Mbps during the scenario; 0 s with every ping lost
- **f. Recovery**: 10.0.0.5 released 7.2 s after the traffic stopped; anomaly flag on s5-s6 cleared 7.2 s after; h1->h6 back on `s1>s2>s6>h6` 0.7 s after

