# Run summary: run1

Legitimate flow: h1 -> h6, UDP 5M; time 0 = start of the baseline phase.

## Task 3 - dynamic cost of the loaded links

| Scenario | Link | C0 | Peak utilisation | Peak cost | Peak normalised cost | Cost 10-16 s after |
|---|---|---|---|---|---|---|
| a | s2-s3 | 10 | 0.201 | 32.01 | 3.20 | 10.00 |
| b | s2-s6 | 10 | 0.314 | 33.14 | 3.31 | 10.82 |
| c | s5-s6 | 10 | 0.135 | 31.35 | 3.13 | 10.00 |

## Task 4 - per scenario

### Scenario a: h2 -> h3, link s2-s3 (33-66 s)

- **a. Load / cost of s2-s3**: utilisation peak 0.201, cost 10 -> peak 32.01 (normalised 3.20)
- **b. Detection**: 10.0.0.2 flagged 2.0 s after the start (rate=42475 pps baseline=2.0); IPs blocked in this scenario: 10.0.0.3, 10.0.0.2
- **c. Rerouted**: no (h1->h6 path did not use a penalised link or no cheaper path existed)
- **d. h1->h6 path**: before `s1>s2>s6>h6`; during `s1>s2>s6>h6`

  | Phase | Throughput mean (Mbps) | Throughput min (Mbps) | UDP loss (%) | Ping loss mean (%) | Ping loss peak (%) | Seconds with 100% ping loss |
  |---|---|---|---|---|---|---|
  | before (10 s) | 5.00 | 4.99 | 0.00 | 0.00 | 0 | 0 |
  | during | 5.00 | 4.99 | 0.00 | 0.00 | 0 | 0 |
  | after (+10-16 s) | 5.00 | 4.99 | 0.00 | 0.00 | 0 | 0 |

- **e. Connectivity**: UDP throughput never below 4.99 Mbps during the scenario; 0 s with every ping lost
- **f. Recovery**: 10.0.0.2 released 8.0 s after the traffic stopped; anomaly flag on s2-s3 cleared 8.0 s after; h1->h6 back on `s1>s2>s6>h6` (path unchanged)

### Scenario b: h2 -> h6, link s2-s6 (99-132 s)

- **a. Load / cost of s2-s6**: utilisation peak 0.314, cost 10 -> peak 33.14 (normalised 3.31)
- **b. Detection**: 10.0.0.2 flagged 2.0 s after the start (rate=29987 pps baseline=1.9); IPs blocked in this scenario: 10.0.0.6, 10.0.0.2
- **c. Rerouted**: yes - 2.0 s: s1>s2>s6 (39.43) => s1>s5>s6 (20.00); 41.0 s: s1>s5>s6 (22.59) => s1>s2>s6 (15.00)
- **d. h1->h6 path**: before `s1>s2>s6>h6`; during `s1>s2>s6>h6`, `s1>s5>s6>h6`

  | Phase | Throughput mean (Mbps) | Throughput min (Mbps) | UDP loss (%) | Ping loss mean (%) | Ping loss peak (%) | Seconds with 100% ping loss |
  |---|---|---|---|---|---|---|
  | before (10 s) | 4.93 | 4.63 | 1.27 | 0.00 | 0 | 0 |
  | during | 5.00 | 4.99 | 0.00 | 26.13 | 100 | 7 |
  | after (+10-16 s) | 5.00 | 4.99 | 0.00 | 0.00 | 0 | 0 |

- **e. Connectivity**: UDP throughput never below 4.99 Mbps during the scenario; 7 s with every ping lost
- **f. Recovery**: 10.0.0.2 released 8.0 s after the traffic stopped; anomaly flag on s2-s6 cleared 8.0 s after; h1->h6 back on `s1>s2>s6>h6` 8.7 s after

### Scenario c: h5 -> h6, link s5-s6 (165-198 s)

- **a. Load / cost of s5-s6**: utilisation peak 0.135, cost 10 -> peak 31.35 (normalised 3.13)
- **b. Detection**: 10.0.0.5 flagged 2.0 s after the start (rate=46654 pps baseline=0.9); IPs blocked in this scenario: 10.0.0.6, 10.0.0.5
- **c. Rerouted**: no (h1->h6 path did not use a penalised link or no cheaper path existed)
- **d. h1->h6 path**: before `s1>s2>s6>h6`; during `s1>s2>s6>h6`

  | Phase | Throughput mean (Mbps) | Throughput min (Mbps) | UDP loss (%) | Ping loss mean (%) | Ping loss peak (%) | Seconds with 100% ping loss |
  |---|---|---|---|---|---|---|
  | before (10 s) | 5.00 | 4.99 | 0.00 | 0.00 | 0 | 0 |
  | during | 5.00 | 4.99 | 0.00 | 19.68 | 100 | 6 |
  | after (+10-16 s) | 5.00 | 5.00 | 0.00 | 0.00 | 0 | 0 |

- **e. Connectivity**: UDP throughput never below 4.99 Mbps during the scenario; 6 s with every ping lost
- **f. Recovery**: 10.0.0.5 released 8.0 s after the traffic stopped; anomaly flag on s5-s6 cleared 8.0 s after; h1->h6 back on `s1>s2>s6>h6` (path unchanged)

