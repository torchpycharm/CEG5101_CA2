# CEG5101 CA2 运行与演示指南

**网络里有人疯狂发包攻击，控制器要发现他、把他堵住，并让正常用户的流量绕开出问题的路。** |


| 屏幕上的词 | 意思 |
|---|---|
| `Topology: 6 switches, 11 links` | 认出了 6 台交换机和它们之间的 11 条线 |
| `New flow A -> B via s1>s2>s6 (cost 15.00)` | 给 A 到 B 的流量选了一条路，这条路的"代价"是 15 |
| `[ANOMALY]` | 发现某台主机发包速度异常 |
| `[BLOCK]` | 把这台主机封了（它发的包全部丢掉） |
| `[REROUTE]` | 给某条流量换了一条路 |
| `[UNBLOCK]` | 攻击停了，解封 |

**代价（cost）** 可以理解成"走这条线的难受程度"：线越忙、或者线上有攻击，代价越高。控制器总是给流量选总代价最低的路。

---

## 演示总览

| Task | 要证明什么 | 怎么演示 | 大约时长 |
|---|---|---|---|
| 1 | 拓扑搭好了，控制器连上了 | 打开 MiniEdit，点 Run | 1 分钟 |
| 2 | 能发现攻击者并封掉他 | 手动发一次攻击，看日志和交换机里的丢包规则 | 2–3 分钟 |
| 3 | 线路的代价会随负载和攻击变化 | 和 Task 4 一起演示，看实时面板里的代价 | 一起 |
| 4 | 正常流量 h1→h6 会绕开被攻击的线，并且一直不断 | 跑一键脚本，三次攻击依次发生，看日志和实时面板 | 3 分钟 |
| 5 | 用图说明攻击前、中、后的变化 | 打开脚本画好的图 | 2 分钟 |

---

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
sudo mn -c                                    # 清理上次残留
```

---

## Task 1：拓扑（MiniEdit）

**要证明什么**：作业给的拓扑在 MiniEdit 里搭好了，能运行，控制器认出了全部 11 条线。

**步骤**（需要图形界面，在 Windows 那台机器上操作）

终端 1，先启动控制器：
```bash
cd ~/CA2/solution
ryu-manager --observe-links anomaly_aware_controller.py
```

终端 2，打开 MiniEdit（从 SSH 启动时先执行 `export DISPLAY=:0`）：
```bash
sudo -E python3 ~/mininet/examples/miniedit.py
```

在 MiniEdit 里：
1. File → Open → 选 `~/CA2/solution/miniedit.mn`。
2. Edit → Preferences：确认勾了 **OpenFlow 1.3**，**不要**勾 Start CLI。
3. 点左下角 **Run**。

终端 3，检查交换机是否都连上了控制器：
```bash
sudo ovs-vsctl show | grep -E "Bridge|is_connected"
```

**屏幕上应该看到**
- 终端 1 的数字慢慢涨到 `Topology: 6 switches, 11 links`。
- 终端 3 里 6 台交换机都是 `is_connected: true`。
- 右键 h1 → Terminal，执行 `ping -c 5 10.0.0.6`，能通。

**跟老师说**：拓扑是 6 台交换机、6 台主机、11 条交换机之间的线，每条线 40 Mbit/s。控制器自动发现了全部 11 条线，所有交换机都连上了。

**结束**：MiniEdit 点 Stop，终端 1 按 `Ctrl+C`，再执行 `sudo mn -c`。

---

## Task 2：发现攻击者并封掉

**要证明什么**：
1. 控制器平时会记住每台主机正常发多少包（叫"基线"）。
2. 有人突然狂发包，超过基线很多，就被认定为攻击者，并被封掉。
3. 被封之后，他的包在第一台交换机就被丢掉，不会再进网络。
4. 被攻击的那台主机不会被误封。

**步骤**

终端 1，启动控制器：
```bash
cd ~/CA2/solution
ryu-manager --observe-links anomaly_aware_controller.py
```

终端 2，启动拓扑：
```bash
cd ~/CA2/ceg_code
sudo mn --switch ovsk --controller remote --custom ceg_mesh_topo.py --topo meshTopo --link tc
```
等终端 1 出现 `11 links`，再等 5 秒。

在 `mininet>` 里：
```
pingall
h2 ping -i 1 10.0.0.3 > /tmp/h2_normal.txt &
```
第一行确认全网能通；第二行让 h2 每秒正常 ping 一次 h3，控制器借此记住 h2 平时的速度。**等 15 秒。**

然后让 h2 对 h3 发起攻击，持续 20 秒：
```
h2 timeout 20 hping3 --icmp --flood 10.0.0.3 > /dev/null 2>&1 &
```

攻击期间，每条命令隔几秒各执行两次：
```
sh ovs-ofctl -O OpenFlow13 dump-flows s2 | grep priority=5000
sh ovs-ofctl -O OpenFlow13 dump-flows s3 | grep "nw_src=10.0.0.2,nw_dst"
```

**屏幕上应该看到**

| 位置 | 看到什么 | 说明什么 |
|---|---|---|
| 终端 1 | `[ANOMALY] 10.0.0.2 rate=几万 pps baseline=2.0 ...` | h2 平时每秒 2 个包，现在每秒几万个，被认定为攻击者 |
| 终端 1 | `[BLOCK] 10.0.0.2 blocked on all switches` | h2 被封。**只有 10.0.0.2，没有 10.0.0.3**，被攻击的 h3 没被误封 |
| 终端 1 | 几行 `[REROUTE]` | 原来经过 s2–s3 这条线的流量换了路 |
| s2 的查询 | `nw_src=10.0.0.2 actions=drop`，`n_packets` 两次之间涨了十几万 | h2 的包在它接入的交换机 s2 就被丢掉了 |
| s3 的查询 | h2→h3 那条规则的 `n_packets` 两次一样 | 攻击包没有再被送到 h3 那边 |
| 终端 1（攻击结束约 7 秒后） | `[UNBLOCK] 10.0.0.2 released ...`，接着几行 `[REROUTE]` 改回原路 | 攻击停了，自动解封，流量走回原来的路 |

**跟老师说**：控制器每 2 秒统计一次每台主机发了多少包。h2 平时每秒 2 个包；攻击时每秒几万个，超过门槛（1000 包/秒，或者平时的 3 倍，取大的那个），于是在所有交换机上装一条"丢掉 h2 所有包"的规则。被攻击的 h3 会自动回复每一个攻击包，我们专门不把这些回复算进 h3 的速度，所以 h3 不会被误封。

**结束**：`exit`，终端 1 按 `Ctrl+C`。

---

## Task 3 + Task 4：代价变化和绕路（一次演示完）

**Task 3 要证明什么**：每条线的代价会随两件事变高：线有多忙，以及线上有没有攻击。代价公式在控制器文件开头：

> 代价 = 原始代价 C0 + 10 × 线的忙碌程度（0 到 1）+ 20 × 是否有攻击（0 或 1）

例如一条原始代价 10 的线，被攻击时代价约 30，是平时的 3 倍。

**Task 4 要证明什么**：
1. 先让 h1 持续给 h6 发正常流量（每秒 5 Mbit），记下它走哪条路、速度多少、丢不丢包。
2. 依次在三条线上制造攻击：
   - a：h2 攻击 h3，压在 s2–s3 线上；
   - b：h2 攻击 h6，压在 s2–s6 线上；
   - c：h5 攻击 h6，压在 s5–s6 线上。
3. 每次都要看：
   - 攻击者有没有被封；
   - h1→h6 要不要换路；
   - h1→h6 的速度和丢包怎么变，有没有断；
   - 攻击停了之后，代价和路线有没有恢复。

**h1→h6 平时走 s1→s2→s6。** 只有场景 b 攻击的线（s2–s6）在这条路上，所以**只有 b 会换路**，换到 s1→s5→s6。a 和 c 攻击的线不在这条路上，h1→h6 不用动。这正是我们想展示的：只有受影响的流量才换路。

**步骤**：一条命令跑完全部，加 `--monitor` 会自动弹出两个窗口：

```bash
cd ~/CA2/solution
sudo python3 run_experiment.py --out results/demo --baseline 20 --attack 20 --recover 20 --monitor
```

- 每段 20 秒，总共约 3 分钟。
- 运行脚本的终端会打印现在到了哪一段：`baseline`、`scenario a`、`flood stopped` ……
- 左边弹出的窗口 **CA2 controller** 是控制器的实时输出（和 Task 2 的终端 1 一样）。
- 右边弹出的窗口 **CA2 live view** 是实时面板，每秒刷新一次。

如果窗口没弹出来，手动开两个终端代替：
```bash
tail -f ~/CA2/solution/results/demo/controller.log
cd ~/CA2/solution && python3 live_view.py --run results/demo
```

**实时面板怎么看**

| 面板区域 | 内容 |
|---|---|
| 第一行 | 当前时间 |
| `h1 -> h6 path` | h1→h6 现在走哪条路、总代价多少；`data plane` 是直接从交换机里查出来的实际路线 |
| UDP / ping 那一行 | h1→h6 的速度（Mbit/s）、丢包、往返时间 RTT（毫秒） |
| 链路表 | 每条线的流量、忙碌程度 `util`、有无攻击 `A`（1 = 有）、原始代价 `C0`、现在的代价 `cost`、代价是原来的几倍 `C/C0`。有攻击的线标红 |
| `src` 表 | 每台主机的发包速度、平时速度、门槛、状态（`normal` 正常 / `blocked` 被封） |
| `events` | 最近的检测、封禁、换路、解封事件 |

**各阶段应该看到什么**（括号里是 run4 的数字）

| 阶段 | 应该看到 | 跟老师说 |
|---|---|---|
| 开始，没有攻击 | h1→h6 走 `s1>s2>s6`，速度 5 Mbit/s，丢包 0，RTT 约 98 ms | 这是攻击前的初始状态：路线、代价、速度、丢包 |
| 场景 a 攻击中 | h2 变 `blocked`；s2–s3 标红，`A`=1，代价从 10 涨到约 30（3 倍）；h1→h6 **仍走 s1>s2>s6**，速度和 RTT 都没变 | 被攻击的线不在 h1→h6 的路上，原路仍然最便宜，所以不用换。经过 s2–s3 的其他流量（如 h1→h3）换了路 |
| 场景 a 结束约 7 秒后 | `UNBLOCK`；s2–s3 的 `A` 变 0，代价回到 10 | 攻击停了，自动解封，代价恢复 |
| 场景 b 攻击中 | h2 变 `blocked`；s2–s6 标红，代价约 30；events 出现 `REROUTE 10.0.0.1->10.0.0.6 s1>s2>s6 (38.30) => s1>s5>s6 (20.00)`；路线变成 `s1>s5>s6`，RTT 从 98 跳到约 137 ms，速度仍是 5 Mbit/s | 这次被攻击的线就在 h1→h6 的路上：原路代价涨到 38，s1>s5>s6 只要 20，所以换过去。新路的线更长，所以 RTT 变大，但流量没断 |
| 场景 b 结束约 7 秒后 | `UNBLOCK`；h1→h6 换回 `s1>s2>s6`，RTT 回到约 98 ms | 原路又变回最便宜，流量自动换回来 |
| 场景 c 攻击中 | h5 变 `blocked`；s5–s6 标红；h1→h6 **仍走 s1>s2>s6** | 这次攻击的是备用路上的线，h1→h6 本来就没走它，不用动 |
| 场景 c 结束约 7 秒后 | `UNBLOCK`，s5–s6 代价回到 10 | 恢复 |

**跑完之后**，生成数字汇总和图（Task 5 要用）：
```bash
python3 summarize_run.py results/demo > results/demo/summary.md
python3 plot_results.py results/demo
```
`summary.md` 里，每个场景都按作业的 a–f 六项列出了数字。

**万一现场跑不出来**：回放之前跑好的 run4，面板和实时运行时一模一样：
```bash
python3 live_view.py --run results/run4 --replay 5     # 5 倍速
```

---

## Task 5：用图说明

**要证明什么**：用三张图展示攻击前、中、后，代价、丢包、速度是怎么变化的。

报告用的是 run4 的图；现场如果刚跑了 demo，也可以打开 `results/demo/plots/`。

| 文件 | 是什么图 | 指给老师看 |
|---|---|---|
| `overview.png` | 下面三张叠在一起，共用一条时间轴 | 先放这张，一眼看全 |
| `fig1_normalized_link_cost.png` | 代价是原来的几倍 vs 时间 | 三个灰色区域（三次攻击）里，被攻击的线都升到约 3 倍，攻击停了约 7 秒后回到 1 |
| `fig2_packet_loss.png` | 丢包率 vs 时间 | 几乎一直是 0。只有场景 b 刚开始、封禁生效前的约 1 秒丢了一点（全程 109,255 个包丢了 34 个） |
| `fig3_throughput.png` | 速度 vs 时间 | 一直是 5 Mbit/s，攻击也没让正常流量变慢 |
| `fig4_rtt.png` | 往返时间 vs 时间（额外加的） | 场景 b 中间那一段从 98 升到 137 ms 的台阶，就是换路的证据 |

**跟老师说**：攻击发生时，被攻击线路的代价马上升高；h1→h6 只在它的路被攻击时（场景 b）才换路，速度一直保持 5 Mbit/s，ping 一个没丢；攻击停止后约 7 秒，代价和路线都自动恢复。唯一的少量丢包，发生在场景 b 刚开始、控制器还没来得及封掉攻击者的那一秒左右。

---

## 结果目录里有什么

| 文件 | 内容 |
|---|---|
| `controller.log` | 控制器的全部输出 |
| `controller/events.csv` | 发现、封禁、换路、解封事件 |
| `controller/link_costs.csv` | 每条线每 2 秒的代价 |
| `controller/paths.csv` | 每条流量走的路和总代价 |
| `iperf_server.txt` / `ping_h1_h6.txt` | h1→h6 的速度、丢包、往返时间原始数据 |
| `dataplane_path.csv` | 每秒从交换机里查出的 h1→h6 实际路线 |
| `flows_*.txt` | 攻击前、中、后交换机里的规则快照 |
| `summary.md` / `plots/` | 汇总数字和图 |

**最终数据用 run4。** run1、run2 是修复前的旧版控制器（会误封被攻击的主机）；run3 是当前版本，但有一段与攻击无关的测量误差。

---

## 提交结果

在哪台机器上产生了新结果，就在哪台上提交推送；另一台动手前先 `git pull --rebase`。
```bash
cd ~/CA2
git add solution/results/demo
git commit -m "demo run"
git push
```

---

## 常见问题

| 现象 | 处理 |
|---|---|
| 大量 `*** Error: Warning: sch_htb: quantum of class ... is big` | 只是提示，不是错误，可以忽略 |
| `ovs-vsctl show` 里没有 `is_connected: true` | 控制器没在跑，或 MiniEdit 没勾 OpenFlow 1.3 |
| `pingall` 100% 丢包 | 等控制器打印 `11 links` 后再等 5 秒，重试 |
| 控制器启动报 `Address already in use` | 已经有一个控制器在跑：`pkill -f ryu-manager` |
| MiniEdit 报 `can't re-enter readline` | Preferences 里去掉 Start CLI |
| 右键主机 Terminal 报找不到 `xhost` | `sudo apt-get install -y x11-xserver-utils` |
| `--monitor` 没弹窗口，终端打印 `could not open ... window` | 用 Task 4 里"手动开两个终端代替"的办法 |
| 实验中断后再跑出错 | `sudo mn -c`，并确认 `pgrep -af ryu-manager` 没有输出 |
| Mac 连不上 WSL 的 SSH | WSL 里 `sudo systemctl start ssh`；Windows 上保持一个 WSL 终端开着 |
