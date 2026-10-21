# CEG5101 CA2 运行指南

按作业的 5 个 Task 顺序，列出每一步要在 WSL 里执行的命令。所有命令都在 WSL 的 Ubuntu 20.04 里运行，仓库路径为 `~/CA2`。

## 0. 准备

### 0.1 环境（只需一次）
```bash
cd ~/CA2
bash setup_wsl.sh          # 安装 Mininet / OVS / Ryu / hping3 / iperf / matplotlib，并自检
bash setup_wsl.sh test     # 只跑自检，8 项都应为 PASS
```

### 0.2 每次开始前
```bash
cd ~/CA2 && git pull --rebase                 # 同步代码
pgrep -af "ryu-manager|mnexec|miniedit"       # 不应有输出；有的话先停掉
sudo mn -c                                    # 清理上次残留的 Mininet 状态
```

### 0.3 涉及的文件
| 文件 | 作用 |
|---|---|
| `ceg_code/ceg_mesh_topo.py` | 作业给定的 6 交换机网状拓扑 |
| `solution/anomaly_aware_controller.py` | 集成控制器：检测、封禁、动态代价、重路由、恢复 |
| `solution/run_experiment.py` | 一键跑 Task 4 的三个场景并采集数据（需要 sudo） |
| `solution/summarize_run.py` | 从一轮结果生成 Task 3 / Task 4 的数字（`summary.md`） |
| `solution/plot_results.py` | 从一轮结果生成 Task 5 的图（`plots/`） |
| `solution/miniedit.mn` | Task 1 的 MiniEdit 拓扑文件 |

---

## Task 1：MiniEdit 拓扑（5 分）

需要图形界面，**在 Windows 那台机器上操作**（窗口通过 WSLg 显示在 Windows 桌面）。

**终端 1，先起控制器：**
```bash
cd ~/CA2/solution
ryu-manager --observe-links anomaly_aware_controller.py
```

**终端 2，打开 MiniEdit：**
```bash
sudo -E python3 ~/mininet/examples/miniedit.py
```
从 SSH 里启动时，先执行 `export DISPLAY=:0`。

**在 MiniEdit 里：**
1. File → Open → 选 `~/CA2/solution/miniedit.mn`（6 交换机、6 主机、11 条链路，控制器 c0）。
2. Edit → Preferences：确认已勾选 **OpenFlow 1.3**（`miniedit.mn` 里已存好）。Start CLI 保持不勾（勾了以后，命令行等待输入时再点窗口会报 `can't re-enter readline`）。
3. 确认 c0 的属性：Remote Controller，IP `127.0.0.1`，端口 `6633`（`miniedit.mn` 里已存好）。
4. 点左下角 **Run**。

**验证（终端 3）：**
```bash
sudo ovs-vsctl show | grep -E "Bridge|is_connected"     # 6 台交换机都应 is_connected: true
```
控制器终端应打印 `Topology: 6 switches, 11 links`。再等 5 秒，右键 h1 → Terminal：
```bash
ping -c 5 10.0.0.6
```

**截图**：MiniEdit 画布 + 控制器终端 + `ovs-vsctl show`，对应 `screenshots/task1_*.png`。

**结束**：MiniEdit 点 Stop，控制器终端按 `Ctrl+C`，再 `sudo mn -c`。

---

## Task 2：流量监控、异常检测与源封禁（5 分）

手动演示一次，用于截图。

**终端 1，起控制器：**
```bash
cd ~/CA2/solution
ryu-manager --observe-links anomaly_aware_controller.py
```

**终端 2，起拓扑：**
```bash
cd ~/CA2/ceg_code
sudo mn --switch ovsk --controller remote --custom ceg_mesh_topo.py --topo meshTopo --link tc
```
等终端 1 出现 `Topology: 6 switches, 11 links`，再等 5 秒。

**在 `mininet>` 里依次执行：**
```
pingall
h2 ping -i 1 10.0.0.3 > /tmp/h2_normal.txt &
```
用 ping 建立正常基线，**等 15 秒**。然后注入作业要求的高速率流量（持续 20 秒）：
```
h2 timeout 20 hping3 --icmp --flood 10.0.0.3 > /dev/null 2>&1 &
```
在这 20 秒内，每条命令间隔几秒各执行两次：
```
sh ovs-ofctl -O OpenFlow13 dump-flows s2 | grep priority=5000
sh ovs-ofctl -O OpenFlow13 dump-flows s3 | grep "nw_src=10.0.0.2,nw_dst"
```
- 第一条：`nw_src=10.0.0.2 actions=drop` 的 `n_packets` 在增长，说明流量在入口交换机被丢弃。
- 第二条：h2→h3 转发规则的 `n_packets` 不变，说明异常流量不再被转发。

流量结束后再等约 10 秒，控制器终端出现 `[UNBLOCK] 10.0.0.2 released`。

**要截的内容：**
| 截图 | 内容 |
|---|---|
| 控制器日志 | `[ANOMALY] 10.0.0.2 ...` 和 `[BLOCK] 10.0.0.2 blocked on all switches` |
| s2 丢弃规则 | 两次查询 `n_packets` 增长 |
| s3 转发规则 | 两次查询 `n_packets` 不变 |
| 解封 | `[UNBLOCK] 10.0.0.2 released ...` |

**结束：**
```
exit
```
然后终端 1 按 `Ctrl+C`。

手动运行时，控制器的 CSV 日志写在 `~/CA2/solution/ca2_logs/`（已被 `.gitignore` 忽略）。

---

## Task 3：动态链路代价更新（10 分）

代价公式和参数（在 `anomaly_aware_controller.py` 开头）：

$$C_{ij}(t) = C^0_{ij} + \alpha \frac{R_{ij}(t)}{R^{max}_{ij}} + \beta A_{ij}(t)$$

| 参数 | 取值 |
|---|---|
| $C^0$ | 参考控制器实际生效的代价：s1–s2=5、s2–s3=10、s1–s4=20、s2–s4=8，其余 10 |
| $\alpha$ / $\beta$ | 10 / 20 |
| $R^{max}$ | 40 Mbit/s（链路带宽） |
| 更新周期 | 2 秒 |

**数据来自 Task 4 的实验**，不需要单独跑。每 2 秒每条链路一行，在 `results/<run>/controller/link_costs.csv`。

**手动运行时实时观察代价**（在 Task 2 的演示过程中另开一个终端）：
```bash
watch -n 2 "tail -n 11 ~/CA2/solution/ca2_logs/link_costs.csv"
```
最后 11 行是最新一次计算的 11 条链路，列依次为：时间、链路、正反向速率、利用率、异常标记、C0、代价、归一化代价。

**报告用的数字和图：**
```bash
cd ~/CA2/solution
python3 summarize_run.py results/run4     # summary.md 里的 "Task 3" 表
python3 plot_results.py results/run4      # plots/fig1_normalized_link_cost.png
```

**可选：换一套 C0 或参数对比**
```bash
sudo python3 run_experiment.py --out results/run_delay --cost-mode delay      # C0 用拓扑文件里的时延
sudo python3 run_experiment.py --out results/run_a5b40 --alpha 5 --beta 40    # 改 α / β
```

---

## Task 4：合法流量重路由（10 分）

一条命令跑完：先建立 h1→h6 的 UDP 流（5 Mbit/s）和 ping，再依次注入 a、b、c 三种高速率流量。

```bash
cd ~/CA2/solution
sudo python3 run_experiment.py --out results/run5
```
约 4–5 分钟，终端会打印各阶段的时间点：

| 阶段 | 内容 |
|---|---|
| 基线 30 秒 | 只有合法流量和低速率背景 ping |
| 场景 a | h2→h3，链路 s2–s3，30 秒 + 恢复 30 秒 |
| 场景 b | h2→h6，链路 s2–s6，30 秒 + 恢复 30 秒 |
| 场景 c | h5→h6，链路 s5–s6，30 秒 + 恢复 30 秒 |

**整理 a–f 六项的数字：**
```bash
python3 summarize_run.py results/run5
```
输出同时写入 `results/run5/summary.md`，每个场景依次是：
- a. 负载和代价的变化
- b. 检测时间和被封禁的 IP
- c. h1→h6 是否改道
- d. 异常前、中、后的路径、吞吐和丢包
- e. 连通性
- f. 解封和路径恢复时间

**常用参数：**
| 参数 | 作用 | 默认 |
|---|---|---|
| `--out` | 结果目录 | `results/run_时间戳` |
| `--scenarios` | 只跑部分场景，如 `--scenarios b` | `a,b,c` |
| `--baseline` / `--attack` / `--recover` | 各阶段秒数 | 30 / 30 / 30 |
| `--rate` | h1→h6 合法 UDP 速率 | `5M` |
| `--cost-mode` | C0 用 `controller` 或 `delay` | `controller` |
| `--alpha` / `--beta` | 代价系数 | 10 / 20 |

**结果目录里的主要文件：**
| 文件 | 内容 |
|---|---|
| `timeline.json` | 各场景开始和结束时间 |
| `controller/events.csv` | 检测、封禁、解封、重路由事件 |
| `controller/link_costs.csv` | 每条链路的代价时间序列 |
| `controller/paths.csv` | 每条流的路径和路径代价 |
| `dataplane_path.csv` | 每秒从流表追踪出的 h1→h6 实际路径 |
| `iperf_server.txt` / `ping_h1_h6.txt` | h1→h6 的吞吐、丢包、时延原始数据 |
| `flows_*.txt` | 各阶段的流表快照 |

**手动查看 h1→h6 当前走哪条路**（手动运行时，在 `mininet>` 里）：
```
sh for s in s1 s2 s3 s4 s5 s6; do echo $s; ovs-ofctl -O OpenFlow13 dump-flows $s | grep "nw_src=10.0.0.1,nw_dst=10.0.0.6"; done
```

---

## Task 5：性能评估

```bash
cd ~/CA2/solution
python3 plot_results.py results/run4
```
生成到 `results/run4/plots/`：

| 文件 | 对应要求 |
|---|---|
| `fig1_normalized_link_cost.png` | 5-3a 动态链路代价（归一化）随时间 |
| `fig2_packet_loss.png` | 5-3b 丢包率（%）随时间 |
| `fig3_throughput.png` | 5-3c 吞吐量（Mbps）随时间 |
| `fig4_rtt.png` | 补充：h1→h6 RTT，路径变化时 RTT 随之改变 |
| `overview.png` | 前三张叠在同一时间轴上 |

图中灰色阴影是三个场景的时间段，虚线是 h1→h6 改道和改回的时刻。

| Task 5 条目 | 材料 |
|---|---|
| 5-1 拓扑截图 | `screenshots/task1_miniedit_running_11links_controller_connected.png` |
| 5-2 异常前、中、后的评估 | `results/run4/summary.md` 各场景的 before / during / after 表 |
| 5-3 三张图 | 上表 fig1–fig3 |
| 5-4 解释 | 结合 summary 和图写 |

**最终数据用 run4**（修复后的控制器，没有场景之外的丢包）。各轮说明：
| 轮次 | 控制器版本 | 说明 |
|---|---|---|
| run1 | 修复前 | 目的主机被误封，可作为"修复前"对比 |
| run2 | 第一版修改 | 场景 c 已正常，a、b 仍误封 |
| run3 | 当前版本 | 只封流量源；89–91 秒有一段场景之外的 UDP 丢包（包已送达 h6，属测量主机侧现象） |
| run4 | 当前版本 | 只封流量源，无场景外丢包，**作为最终结果** |

---

## 提交结果

在哪台机器上产生了新结果，就在哪台上提交推送；另一台动手前先 `git pull --rebase`。
```bash
cd ~/CA2
git add solution/results/run5
git commit -m "run5: ..."
git push
```

---

## 常见问题

| 现象 | 原因和处理 |
|---|---|
| 大量 `*** Error: Warning: sch_htb: quantum of class ... is big` | `tc` 的提示，不是错误，可忽略 |
| `ovs-vsctl show` 里没有 `is_connected: true` | 控制器没在跑，或 MiniEdit 没勾 OpenFlow 1.3 |
| `pingall` 100% 丢包 | 先确认上一条；再确认控制器打印了 `11 links` 后又等了 5 秒 |
| 控制器启动报 `Address already in use` | 已有控制器在跑：`pkill -f ryu-manager` |
| MiniEdit 报 `can't re-enter readline` | 勾了 Start CLI 后又点了窗口：Preferences 里去掉 Start CLI |
| 右键主机 Terminal 报找不到 `xhost` | `sudo apt-get install -y x11-xserver-utils` |
| 实验脚本卡住或中断后再跑出错 | `sudo mn -c`，并确认 `pgrep -af ryu-manager` 无输出 |
| Mac 连不上 WSL 的 SSH | WSL 里 `sudo systemctl start ssh`；Windows 上保持一个 WSL 终端打开 |
