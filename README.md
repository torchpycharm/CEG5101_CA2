## 实验脚本
```bash
cd ~/CA2/solution
sudo python3 run_experiment.py --out results/run2
```
大约 4 分钟，三个场景依次跑完，结果写到 results/run2/
参数表

| 参数 | 作用 | 默认 |
|---|---|---|
| `--out` | 结果目录 | 按时间自动命名 |
| `--scenarios a,b,c` | 只跑其中几个场景，如 `--scenarios b` | 三个都跑 |
| `--baseline` / `--attack` / `--recover` | 各阶段秒数 | 各 30 |
| `--rate` | h1→h6 正常流的速率 | `5M` |
| `--cost-mode` | 初始代价用哪套：`controller` 或 `delay` | `controller` |
| `--alpha` / `--beta` | 代价公式里的两个系数 | 10 / 20 |

## 分布命令
开两个终端。终端 1 起控制器：
```bash
cd ~/CA2/solution
ryu-manager --observe-links anomaly_aware_controller.py
```
终端 2 起拓扑：
```bash
cd ~/CA2/ceg_code
sudo mn --switch ovsk --controller remote --custom ceg_mesh_topo.py --topo meshTopo --link tc
```
等十几秒让链路发现完成，然后在 `mininet>` 提示符下：
```
pingall                              # 6 台主机应全通
h1 ping -c 5 h6                      # 正常流量
sh ovs-ofctl -O OpenFlow13 dump-flows s2    # 看 s2 的流表
```
控制器的 CSV 日志默认写在运行目录下的 `ca2_logs/`。

## 结果目录表
| 文件 | 内容 |
|---|---|
| `timeline.json` | 各场景开始和结束的时间戳 |
| `controller/link_costs.csv` | 每 2 秒每条链路的速率、利用率、异常标记、代价、归一化代价 |
| `controller/sources.csv` | 每个源 IP 的速率、基线、阈值、状态 |
| `controller/paths.csv` | 每条流当前的路径和路径代价 |
| `controller/events.csv` | 检测、封禁、解封、重路由事件 |
| `iperf_server.txt` | h1→h6 每秒的吞吐和丢包 |
| `ping_h1_h6.txt` | h1→h6 的 ping，带时间戳 |
| `dataplane_path.csv` | 每秒从流表里实际追踪出的 h1→h6 路径 |
| `ifstats.csv` | 每秒各接口的收发计数 |
| `flows_*.txt` | 各阶段的流表快照 |

画三张图主要用 `link_costs.csv`（代价）和 `iperf_server.txt`（丢包、吞吐），再用 `timeline.json` 标出各场景的时间段。

## 实验PPT指南
- **`CEG5101 LAB Session(0,1,2)`**：Mininet 命令、MiniEdit 怎么用、`ovs-ofctl` 看和改流表。任务 1 的 MiniEdit 操作看这份。
- **`CEG5101 LAB Session (3,4,5)`**：Ryu 怎么启动、学习型交换机和防火墙控制器的结构。看懂这份，再读控制器代码会顺很多。

读代码建议的顺序：先看 `ceg_code/learning_switch.py`（最简单的 Ryu 程序），再看 `resilient_controller.py`（路由）和 `anomaly_detection.py`（检测），最后看 `anomaly_aware_controller.py`，它的结构就是后两者拼起来再加代价更新和重路由，文件开头的参数区列出了所有可调的值。
