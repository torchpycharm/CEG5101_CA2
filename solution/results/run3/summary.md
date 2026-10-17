# Run summary: run3

Legitimate flow: h1 -> h6, UDP 5M; time 0 = start of the baseline phase.

## Task 3 - dynamic cost of the loaded links

| Scenario | Link | C0 | Peak utilisation | Peak cost | Peak normalised cost | Cost 10-16 s after |
|---|---|---|---|---|---|---|
| a | s2-s3 | 10 | 0.200 | 32.00 | 3.20 | 10.00 |
| b | s2-s6 | 10 | 0.170 | 31.70 | 3.17 | 10.46 |
| c | s5-s6 | 10 | 0.150 | 31.50 | 3.15 | 10.00 |

## Task 4 - per scenario

### Scenario a: h2 -> h3, link s2-s3 (33-66 s)

- **a. Load / cost of s2-s3**: utilisation peak 0.200, cost 10 -> peak 32.00 (normalised 3.20)
- **b. Detection**: 10.0.0.2 flagged 2.0 s after the start (rate=40836 pps baseline=1.7); IPs blocked in this scenario: 10.0.0.2
- **c. Rerouted**: no (h1->h6 path did not use a penalised link or no cheaper path existed)
- **d. h1->h6 path**: before `s1>s2>s6>h6`; during `s1>s2>s6>h6`

  | Phase | Throughput mean (Mbps) | Throughput min (Mbps) | UDP loss (%) | Ping loss mean (%) | Ping loss peak (%) | Seconds with 100% ping loss |
  |---|---|---|---|---|---|---|
  | before (10 s) | 5.00 | 4.99 | 0.00 | 0.00 | 0 | 0 |
  | during | 5.00 | 4.99 | 0.00 | 0.00 | 0 | 0 |
  | after (+10-16 s) | 5.00 | 4.99 | 0.00 | 0.00 | 0 | 0 |

- **e. Connectivity**: UDP throughput never below 4.99 Mbps during the scenario; 0 s with every ping lost
- **f. Recovery**: 10.0.0.2 released 8.1 s after the traffic stopped; anomaly flag on s2-s3 cleared 8.1 s after; h1->h6 back on `s1>s2>s6>h6` 0.9 s after

### Scenario b: h2 -> h6, link s2-s6 (96-129 s)

- **a. Load / cost of s2-s6**: utilisation peak 0.170, cost 10 -> peak 31.70 (normalised 3.17)
- **b. Detection**: 10.0.0.2 flagged 5.0 s after the start (rate=19115 pps baseline=2.0); IPs blocked in this scenario: 10.0.0.2
- **c. Rerouted**: yes - 5.0 s: s1>s2>s6 (37.61) => s1>s5>s6 (20.00); 44.0 s: s1>s5>s6 (22.40) => s1>s2>s6 (15.00)
- **d. h1->h6 path**: before `s1>s2>s6>h6`; during `s1>s2>s6>h6`, `s1>s5>s6>h6`

  | Phase | Throughput mean (Mbps) | Throughput min (Mbps) | UDP loss (%) | Ping loss mean (%) | Ping loss peak (%) | Seconds with 100% ping loss |
  |---|---|---|---|---|---|---|
  | before (10 s) | 4.90 | 4.54 | 1.81 | 0.00 | 0 | 0 |
  | during | 5.00 | 4.99 | 0.00 | 0.65 | 20 | 0 |
  | after (+10-16 s) | 5.00 | 4.99 | 0.00 | 0.00 | 0 | 0 |

- **e. Connectivity**: UDP throughput never below 4.99 Mbps during the scenario; 0 s with every ping lost
- **f. Recovery**: 10.0.0.2 released 11.0 s after the traffic stopped; anomaly flag on s2-s6 cleared 11.0 s after; h1->h6 back on `s1>s2>s6>h6` 11.3 s after

### Scenario c: h5 -> h6, link s5-s6 (162-195 s)

- **a. Load / cost of s5-s6**: utilisation peak 0.150, cost 10 -> peak 31.50 (normalised 3.15)
- **b. Detection**: 10.0.0.5 flagged 2.1 s after the start (rate=33173 pps baseline=1.0); IPs blocked in this scenario: 10.0.0.5
- **c. Rerouted**: no (h1->h6 path did not use a penalised link or no cheaper path existed)
- **d. h1->h6 path**: before `s1>s2>s6>h6`; during `s1>s2>s6>h6`

  | Phase | Throughput mean (Mbps) | Throughput min (Mbps) | UDP loss (%) | Ping loss mean (%) | Ping loss peak (%) | Seconds with 100% ping loss |
  |---|---|---|---|---|---|---|
  | before (10 s) | 5.00 | 4.99 | 0.00 | 0.00 | 0 | 0 |
  | during | 5.00 | 4.99 | 0.00 | 0.00 | 0 | 0 |
  | after (+10-16 s) | 5.00 | 5.00 | 0.00 | 0.00 | 0 | 0 |

- **e. Connectivity**: UDP throughput never below 4.99 Mbps during the scenario; 0 s with every ping lost
- **f. Recovery**: 10.0.0.5 released 11.0 s after the traffic stopped; anomaly flag on s5-s6 cleared 11.0 s after; h1->h6 back on `s1>s2>s6>h6` 0.5 s after

