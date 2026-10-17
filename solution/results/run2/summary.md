# Run summary: run2

Legitimate flow: h1 -> h6, UDP 5M; time 0 = start of the baseline phase.

## Task 3 - dynamic cost of the loaded links

| Scenario | Link | C0 | Peak utilisation | Peak cost | Peak normalised cost | Cost 10-16 s after |
|---|---|---|---|---|---|---|
| a | s2-s3 | 10 | 0.204 | 32.04 | 3.20 | 10.00 |
| b | s2-s6 | 10 | 0.323 | 33.23 | 3.32 | 10.82 |
| c | s5-s6 | 10 | 0.145 | 31.45 | 3.14 | 10.00 |

## Task 4 - per scenario

### Scenario a: h2 -> h3, link s2-s3 (33-66 s)

- **a. Load / cost of s2-s3**: utilisation peak 0.204, cost 10 -> peak 32.04 (normalised 3.20)
- **b. Detection**: 10.0.0.2 flagged 2.1 s after the start (rate=40892 pps baseline=1.9); IPs blocked in this scenario: 10.0.0.2, 10.0.0.3
- **c. Rerouted**: no (h1->h6 path did not use a penalised link or no cheaper path existed)
- **d. h1->h6 path**: before `s1>s2>s6>h6`; during `s1>s2>s6>h6`

  | Phase | Throughput mean (Mbps) | Throughput min (Mbps) | UDP loss (%) | Ping loss mean (%) | Ping loss peak (%) | Seconds with 100% ping loss |
  |---|---|---|---|---|---|---|
  | before (10 s) | 5.00 | 4.99 | 0.00 | 0.00 | 0 | 0 |
  | during | 5.00 | 4.99 | 0.00 | 0.00 | 0 | 0 |
  | after (+10-16 s) | 5.00 | 4.99 | 0.00 | 0.00 | 0 | 0 |

- **e. Connectivity**: UDP throughput never below 4.99 Mbps during the scenario; 0 s with every ping lost
- **f. Recovery**: 10.0.0.2 released 8.1 s after the traffic stopped; anomaly flag on s2-s3 cleared 8.1 s after; h1->h6 back on `s1>s2>s6>h6` 1.0 s after

### Scenario b: h2 -> h6, link s2-s6 (99-132 s)

- **a. Load / cost of s2-s6**: utilisation peak 0.323, cost 10 -> peak 33.23 (normalised 3.32)
- **b. Detection**: 10.0.0.2 flagged 2.1 s after the start (rate=32505 pps baseline=1.9); IPs blocked in this scenario: 10.0.0.2, 10.0.0.6
- **c. Rerouted**: yes - 2.1 s: s1>s2>s6 (39.50) => s1>s5>s6 (20.00); 4.1 s: s1>s5>s6 (40.95) => s1>s2>s3>s6 (25.80); 10.1 s: s1>s2>s3>s6 (28.37) => s1>s5>s6 (20.20); 41.0 s: s1>s5>s6 (22.58) => s1>s2>s6 (15.00)
- **d. h1->h6 path**: before `s1>s2>s6>h6`; during `s1>s2>s6>h6`, `s1>s5>s6>h6`, `s1>s2>s3>s6>h6`, `s1>s5>s6>h6`

  | Phase | Throughput mean (Mbps) | Throughput min (Mbps) | UDP loss (%) | Ping loss mean (%) | Ping loss peak (%) | Seconds with 100% ping loss |
  |---|---|---|---|---|---|---|
  | before (10 s) | 4.90 | 4.50 | 1.86 | 0.00 | 0 | 0 |
  | during | 5.00 | 4.92 | 0.00 | 19.68 | 100 | 5 |
  | after (+10-16 s) | 5.00 | 4.99 | 0.00 | 0.00 | 0 | 0 |

- **e. Connectivity**: UDP throughput never below 4.92 Mbps during the scenario; 5 s with every ping lost
- **f. Recovery**: 10.0.0.2 released 8.1 s after the traffic stopped; anomaly flag on s2-s6 cleared 8.1 s after; h1->h6 back on `s1>s2>s6>h6` 8.4 s after

### Scenario c: h5 -> h6, link s5-s6 (165-198 s)

- **a. Load / cost of s5-s6**: utilisation peak 0.145, cost 10 -> peak 31.45 (normalised 3.14)
- **b. Detection**: 10.0.0.5 flagged 2.1 s after the start (rate=49698 pps baseline=0.9); IPs blocked in this scenario: 10.0.0.5
- **c. Rerouted**: no (h1->h6 path did not use a penalised link or no cheaper path existed)
- **d. h1->h6 path**: before `s1>s2>s6>h6`; during `s1>s2>s6>h6`

  | Phase | Throughput mean (Mbps) | Throughput min (Mbps) | UDP loss (%) | Ping loss mean (%) | Ping loss peak (%) | Seconds with 100% ping loss |
  |---|---|---|---|---|---|---|
  | before (10 s) | 5.00 | 4.99 | 0.00 | 0.00 | 0 | 0 |
  | during | 5.00 | 4.99 | 0.00 | 0.00 | 0 | 0 |
  | after (+10-16 s) | 4.99 | 4.98 | 0.00 | 0.00 | 0 | 0 |

- **e. Connectivity**: UDP throughput never below 4.99 Mbps during the scenario; 0 s with every ping lost
- **f. Recovery**: 10.0.0.5 released 8.0 s after the traffic stopped; anomaly flag on s5-s6 cleared 8.0 s after; h1->h6 back on `s1>s2>s6>h6` 0.8 s after

