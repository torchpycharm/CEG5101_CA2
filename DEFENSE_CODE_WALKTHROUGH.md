# CA2 答辩：核心代码逐段讲解

讲的是 [solution/anomaly_aware_controller.py](solution/anomaly_aware_controller.py)（817 行，run4 用的就是这个版本）。
行号可以点击，在 VS Code 里直接跳到代码。

---

## 0. 开场 1 分钟：先把整体讲清楚

可以这样开口：

> 我们的控制器把两份参考代码合在了一起：`resilient_controller.py` 负责发现拓扑、用 Dijkstra 算最短路；`anomaly_detection.py` 负责用 EMA 基线检测异常并封禁源 IP。
> 在这基础上我们加了三样参考代码没有的东西：
> 1. 每条链路的**动态代价**：C = C0 + α·负载 + β·是否有攻击；
> 2. 代价一变就**重新给已有的流选路**；
> 3. 攻击停了**自动解封、恢复代价、恢复原路**。
>
> 程序分两部分：一部分是**事件驱动**的（交换机连上来、链路断了、有包送到控制器），另一部分是一个**每 2 秒跑一次的监控循环**，检测、封禁、算代价、改路都在这个循环里按固定顺序做。

整个文件的地图：

| 行号 | 部分 | 对应 Task |
|---|---|---|
| [39–81](solution/anomaly_aware_controller.py#L39) | 参数区 | 全部 |
| [95–129](solution/anomaly_aware_controller.py#L95) | 控制器保存的状态（"内存"） | 全部 |
| [166–222](solution/anomaly_aware_controller.py#L166) | 交换机连上来时的初始化 | 1 |
| [227–330](solution/anomaly_aware_controller.py#L227) | 拓扑发现、链路故障 | 1、4 |
| [335–490](solution/anomaly_aware_controller.py#L335) | Dijkstra、装规则、改路 | 4 |
| [495–562](solution/anomaly_aware_controller.py#L495) | 处理送到控制器的包（ARP、新流） | 4 |
| [567–627](solution/anomaly_aware_controller.py#L567) | 每 2 秒的监控循环 | 2、3、4 |
| [632–697](solution/anomaly_aware_controller.py#L632) | 算每台主机、每条链路的速率 | 2、3 |
| [702–760](solution/anomaly_aware_controller.py#L702) | 检测、封禁、解封 | 2 |
| [765–789](solution/anomaly_aware_controller.py#L765) | 动态代价公式 | 3 |
| [791–817](solution/anomaly_aware_controller.py#L791) | 写 CSV 日志（画图用） | 5 |

---

## 1. 参数区（[39–81 行](solution/anomaly_aware_controller.py#L39)）

所有可调的数字都集中在文件开头，老师问"某个值是多少"时直接指这里。

```python
POLL_INTERVAL = 2.0      # 每 2 秒统计一次
STATS_WAIT = 0.5         # 发出统计请求后等 0.5 秒收回复
TOPOLOGY_SETTLE = 3.0    # 3 秒内没有新链路，才认为拓扑稳定
```

```python
EMA_ALPHA = 0.3          # 基线 = 0.3 × 新速率 + 0.7 × 旧基线（和参考代码一样）
THRESHOLD_MULT = 3.0     # 超过基线 3 倍算异常（和参考代码一样）
MIN_ANOMALY_PPS = 1000.0 # 我们加的：同时必须超过 1000 包/秒
WARMUP_SAMPLES = 3       # 至少有 3 个样本才允许判定异常
RECOVERY_POLLS = 3       # 连续 3 次安静才解封
HEAVY_FLOW_SHARE = 0.2   # 占攻击者流量 20% 以上的流，它经过的链路标记为"有攻击"
```

```python
COST_ALPHA = 10.0        # 代价公式里的 α（负载项权重）
COST_BETA = 20.0         # 代价公式里的 β（攻击项权重）
LINK_CAPACITY_BPS = 40e6 # Rmax = 40 Mbit/s，拓扑里每条线的带宽
LOAD_SMOOTHING = 0.5     # 链路速率平滑：新样本占一半
REROUTE_MARGIN = 2.0     # 新路要便宜 2 以上才换（防止来回切换）
```

[64–68 行](solution/anomaly_aware_controller.py#L64) 是两套 C0：
- `CONTROLLER_COSTS` 照抄参考控制器的代价表，表里没有的链路用默认值 10。**默认用这套**，因为作业说 C0 是"所给控制器里的原始代价"。
- `DELAY_COSTS` 用拓扑文件里每条线的时延作 C0，通过环境变量 `CA2_COST_MODE=delay` 切换。

[71–79 行](solution/anomaly_aware_controller.py#L71) 是 cookie 和优先级。cookie 相当于给规则贴的标签，用来区分规则是哪一类：

| 规则 | cookie | 优先级 | 作用 |
|---|---|---|---|
| 转发规则 | `0xCA20001` | 10 | 每对（源 IP，目的 IP）一条，决定往哪个端口发 |
| ICMP 分类计数规则 | `0xCA20003` | 11 | 只在源主机的接入交换机上，把 Echo Request 和 Echo Reply 分开计数 |
| 封禁（丢包）规则 | `0xCA20002` | 5000 | 丢掉被封 IP 发的所有包，优先级最高 |
| table-miss | 0 | 0 | 什么都没匹配上，就把包送给控制器 |

---

## 2. 控制器保存的状态（[95–129 行](solution/anomaly_aware_controller.py#L95)）

可以把这些变量理解成控制器的"内存"。讲的时候按三组说：

**拓扑**
- `datapaths`：已连接的交换机，用来给它们发命令。
- `switch_ports`：每台交换机有哪些端口。
- `link_port[(u, v)]`：交换机 u 用哪个端口连到交换机 v。
- `down_ports`：报告过断开的端口。
- `graph[u][v]`：当前代价，**Dijkstra 用的就是它**。

**主机和流**
- `hosts[ip] = Host(mac, 接入交换机, 端口)`：每台主机在哪。
- `flows[(源IP, 目的IP)] = {'path': [...], 'rules': {交换机: 输出端口}}`：每条流现在走哪条路、在每台交换机上装的规则。

**测量、检测、代价**
- `flow_prev` / `port_prev`：上一次的计数器，用来和这一次相减算速率。
- `sources[ip] = {'baseline', 'samples', 'rate'}`：每台主机的基线。
- `blocked[ip] = {'since', 'baseline', 'links', 'quiet', 'peak'}`：被封的主机，`links` 是被它的攻击标记过的链路。
- `base_cost`：每条链路的 C0；`link_state`：每条链路当前的速率、利用率、异常标记、代价。

[127 行](solution/anomaly_aware_controller.py#L127) `hub.spawn(self._monitor)` 启动监控循环。

> **可能被问：两个线程同时改这些变量，不会冲突吗？**
> Ryu 用的是 eventlet 协程（`hub`），不是真的多线程。一个函数只会在 `hub.sleep` 或等网络 I/O 时把控制权交出去，所以事件处理函数和监控循环不会在中途互相打断，不需要加锁。

---

## 3. 交换机连上来（[166–222 行](solution/anomaly_aware_controller.py#L166)）

### `switch_features_handler`（[167–194 行](solution/anomaly_aware_controller.py#L167)）

交换机和控制器握手时触发，做四件事：

1. **[173–178 行](solution/anomaly_aware_controller.py#L173)**：按三个 cookie 删掉我们以前装过的规则。如果控制器重启了，交换机上可能还留着旧规则，不删会导致走错路。
2. **[180–182 行](solution/anomaly_aware_controller.py#L180)**：装 table-miss 规则，优先级 0，动作是"送给控制器"。没有它，新流的第一个包就到不了控制器。
3. **[187–189 行](solution/anomaly_aware_controller.py#L187)**：清掉这台交换机的旧状态（断开的端口、上次的计数器）。交换机重连后计数器从 0 开始，旧值留着会算出错误的速率。
4. **[192–194 行](solution/anomaly_aware_controller.py#L192)**：经过这台交换机的流，规则已经没了，从 `flows` 里删掉，下次有包来时重新选路安装。

### `state_change_handler`（[197–203 行](solution/anomaly_aware_controller.py#L197)）

维护 `datapaths`：交换机连上就加进去，断开就删掉。

### `_add_flow` / `_del_flow`（[205–222 行](solution/anomaly_aware_controller.py#L205)）

封装了下发 OpenFlow 规则的代码。
- `_add_flow` 默认是 ADD，也可以传 MODIFY_STRICT。
- `_del_flow` 用 `DELETE_STRICT`，只删优先级、匹配条件、cookie 都完全一样的那一条，不会误删别的规则。

---

## 4. 拓扑发现和链路故障（[227–330 行](solution/anomaly_aware_controller.py#L227)）

### `discover_topology`（[241–262 行](solution/anomaly_aware_controller.py#L241)）

有交换机加入或发现新链路时被调用（[227–233 行](solution/anomaly_aware_controller.py#L227)）。链路是 Ryu 的 `--observe-links` 通过 LLDP 发现的。

- **[243–244 行](solution/anomaly_aware_controller.py#L243)**：记录每台交换机的所有端口。
- **[247–255 行](solution/anomaly_aware_controller.py#L247)**：对每条发现的链路，记下 `link_port[(源交换机, 目的交换机)] = 源端口`。报告过断开的端口跳过。
- **[254 行](solution/anomaly_aware_controller.py#L254)** `_forget_hosts_on`：如果之前在这个端口上"学到过主机"，现在发现它其实是交换机之间的线，就把那个错误的主机记录删掉。
- **[257–262 行](solution/anomaly_aware_controller.py#L257)**：有变化就重建图，并打印 `Topology: 6 switches, N links`。

### `_rebuild_graph`（[264–276 行](solution/anomaly_aware_controller.py#L264)）

- **[268 行](solution/anomaly_aware_controller.py#L268)**：只有两个方向都发现了的链路才放进图。只发现一个方向时，说明还没确认链路是通的。
- **[271–273 行](solution/anomaly_aware_controller.py#L271)**：第一次见到这条链路时算出它的 C0。之后如果已经有动态代价，就用动态代价；否则用 C0。

### 主机端口怎么判断（[284–297 行](solution/anomaly_aware_controller.py#L284)）

- `_is_host_port`：一个端口不属于任何交换机之间的链路，就是连主机的端口。
- `_topology_settled`：3 秒内没有新链路才算拓扑稳定。在这之前收到的包全部忽略（[505–506 行](solution/anomaly_aware_controller.py#L505)），因为链路还没发现完，可能把交换机之间的端口误认成主机端口。

### 链路故障：`port_status_handler`（[306–330 行](solution/anomaly_aware_controller.py#L306)）

- **[312–313 行](solution/anomaly_aware_controller.py#L312)**：端口被删除，或状态是 LINK_DOWN，就算断开。
- **[322–330 行](solution/anomaly_aware_controller.py#L322)**：把这条链路两个方向都从 `link_port` 删掉，重建图，然后对所有流重新选路（`_reroute_flows('link failure')`）。

**[236–239 行](solution/anomaly_aware_controller.py#L236)：故意忽略 LLDP 的"链路删除"事件。**
> 洪泛时链路很拥塞，LLDP 探测包可能超时，Ryu 会误以为链路断了。如果相信它，攻击反而会把它正在攻击的那条线从图里"删掉"。所以我们只相信交换机自己报告的端口状态。

---

## 5. 有包送到控制器（[495–562 行](solution/anomaly_aware_controller.py#L495)）

### `_packet_in_handler`（[496–521 行](solution/anomaly_aware_controller.py#L496)）

交换机上没有匹配的规则时，table-miss 把包送上来，就会进这里。

1. **[503–504 行](solution/anomaly_aware_controller.py#L503)**：LLDP 包交给 Ryu 自己处理，这里不管。
2. **[505–506 行](solution/anomaly_aware_controller.py#L505)**：拓扑还没稳定，先不处理。
3. **[508 行](solution/anomaly_aware_controller.py#L508)**：判断包是不是从主机端口进来的。只有从主机端口进来，才能说明"这台主机就接在这里"。
4. **[510–515 行](solution/anomaly_aware_controller.py#L510)**：如果是 ARP，学习主机位置，然后处理 ARP。
5. **[517–521 行](solution/anomaly_aware_controller.py#L517)**：如果是 IPv4，学习主机位置，然后处理 IPv4。

### `_handle_arp`（[531–539 行](solution/anomaly_aware_controller.py#L531)）

- 目标主机已知：直接把 ARP 包发到目标主机所在的端口。
- 目标未知、而且是 ARP 请求：只发到所有主机端口，**不在交换机之间泛洪**。

> **为什么不像普通交换机那样泛洪？** 这个拓扑有很多环路，广播包会在环里无限转圈（广播风暴）。参考代码用最小生成树（MST）解决这个问题；我们换成由控制器直接投递，更简单，也不受链路变化影响。

### `_handle_ipv4`（[541–551 行](solution/anomaly_aware_controller.py#L541)）

1. **[543–544 行](solution/anomaly_aware_controller.py#L543)**：源 IP 已经被封，直接丢掉。
2. **[545–547 行](solution/anomaly_aware_controller.py#L545)**：还不知道目的主机在哪，先丢掉。等它发过 ARP 就知道了。
3. **[548–549 行](solution/anomaly_aware_controller.py#L548)**：调用 `_ensure_flow`，给这对主机算路并装规则。
4. **[551 行](solution/anomaly_aware_controller.py#L551)**：把这个包直接发到目的主机的端口，第一个包也不会丢。

---

## 6. 选路和装规则（[335–490 行](solution/anomaly_aware_controller.py#L335)）——Task 4 的核心

### `dijkstra`（[335–360 行](solution/anomaly_aware_controller.py#L335)）

和参考代码的算法一样，区别是边的权重 `self.graph[u][v]` 不再固定，而是动态代价。

- **[339–342 行](solution/anomaly_aware_controller.py#L339)**：所有节点距离设为无穷大，起点为 0，起点放进优先队列。
- **[345 行](solution/anomaly_aware_controller.py#L345)**：每次取出当前距离最小的节点。
- **[346–351 行](solution/anomaly_aware_controller.py#L346)**：取到终点就顺着 `previous` 倒推出整条路径，再反转。
- **[352–353 行](solution/anomaly_aware_controller.py#L352)**：队列里的旧记录（已经找到更短的了）直接跳过。
- **[354–359 行](solution/anomaly_aware_controller.py#L354)**：松弛：经过当前节点到邻居更近，就更新邻居的距离和前驱。

### `_path_cost` 与 `_path_rules`（[362–378 行](solution/anomaly_aware_controller.py#L362)）

- `_path_cost`：把路径上每段链路的当前代价加起来。某段链路已经不存在时返回无穷大，这样断了的路一定会被换掉。
- `_path_rules`：把交换机列表变成"每台交换机往哪个端口发"。中间的交换机发往下一跳交换机的端口，最后一台交换机发往目的主机的端口。

### `_install_path`（[380–433 行](solution/anomaly_aware_controller.py#L380)）——装规则，也负责改路

新流和改路都用这个函数。它要解决的问题是：**换路的过程中不能丢包**。

- **[388–393 行](solution/anomaly_aware_controller.py#L388)**：算出新路径上的规则，取出旧路径的规则。
- **[395 行](solution/anomaly_aware_controller.py#L395)** `for dpid in reversed(path)`：**从目的端往源端倒着装**。如果从源端开始装，包可能先到达一台还没有新规则的交换机，被送到控制器或者丢掉。倒着装，等源端交换机切换方向时，后面的路已经全部铺好了。
- **[397 行](solution/anomaly_aware_controller.py#L397)**：如果这台交换机的输出端口没变，就不动它。
- **[400–401 行](solution/anomaly_aware_controller.py#L400)**：匹配条件是"IPv4 + 源 IP + 目的 IP"。
- **[403–404 行](solution/anomaly_aware_controller.py#L403)**：这台交换机上原来就有这条规则，用 `MODIFY_STRICT` 原地修改；否则用 `ADD`。
  > **为什么不直接 ADD 覆盖？** 在 OpenFlow 1.3 里，ADD 一条完全相同的规则会把它的计数器清零，而我们要靠这些计数器算速率。MODIFY 只改动作，计数器保留。
- **[410–416 行](solution/anomaly_aware_controller.py#L410)**：在源主机的接入交换机上，装两条优先级 11 的 ICMP 分类计数规则（见第 9 节）。
- **[420–423 行](solution/anomaly_aware_controller.py#L420)**：如果源主机换了接入交换机，删掉旧交换机上的分类计数规则。
- **[425–431 行](solution/anomaly_aware_controller.py#L425)**：**最后**才删除不在新路径上的交换机里的旧规则。这就是"先建后拆"（make-before-break）。
- **[433 行](solution/anomaly_aware_controller.py#L433)**：在 `flows` 里记下新路径和规则。

### `_ensure_flow`（[459–470 行](solution/anomaly_aware_controller.py#L459)）

一对主机第一次通信时调用：用 Dijkstra 算路，装规则，打印 `New flow ... via ... (cost ...)`。已经装过的不会重复装。

### `_reroute_flows`（[472–490 行](solution/anomaly_aware_controller.py#L472)）——改路的决策

每次代价更新后，以及链路故障时调用。

- **[474 行](solution/anomaly_aware_controller.py#L474)**：遍历所有已经装好的流。
- **[475–476 行](solution/anomaly_aware_controller.py#L475)**：被封主机发出的流不管，它的包反正都被丢掉了。
- **[480–482 行](solution/anomaly_aware_controller.py#L480)**：用当前代价重新跑 Dijkstra；最优路径就是现在这条，就跳过。
- **[485 行](solution/anomaly_aware_controller.py#L485)** `if best_cost + REROUTE_MARGIN < current_cost`：新路至少便宜 2 才换。
- **[487–490 行](solution/anomaly_aware_controller.py#L487)**：调用 `_install_path` 换路，打印 `[REROUTE] ... 旧路 (旧代价) => 新路 (新代价)`。

> **为什么要 2 的余量？** h1→h6 换到 s1–s5–s6 之后，它自己的 5 Mbit/s 流量会让这条路变贵一点（20 → 22.57）。没有余量的话，可能和别的路来回切换。

> **为什么场景 a、c 里 h1→h6 不换路？** 这个函数是对**每条流**比较"它现在这条路"和"最优的路"。场景 a 被攻击的是 s2–s3，h1→h6 的路 s1–s2–s6 代价没变（17.6），仍然最便宜，所以不换；而经过 s2–s3 的 h1→h3 代价涨到 37，就被换了。

---

## 7. 每 2 秒的监控循环（[567–627 行](solution/anomaly_aware_controller.py#L567)）

### `_monitor`（[567–577 行](solution/anomaly_aware_controller.py#L567)）

```python
hub.sleep(5)                                  # 等交换机都连上
while True:
    for datapath in list(self.datapaths.values()):
        self._request_stats(datapath)          # 1. 向每台交换机要统计
    hub.sleep(STATS_WAIT)                      # 2. 等 0.5 秒收回复
    self._evaluate()                           # 3. 分析
    hub.sleep(POLL_INTERVAL - STATS_WAIT)      # 4. 剩下的 1.5 秒休息
```

- `_request_stats`（[579–583 行](solution/anomaly_aware_controller.py#L579)）同时要两种统计：**流表统计**（每条规则匹配了多少包，用来算每台主机的速率），和**端口统计**（每个端口发了多少字节，用来算每条链路的负载）。
- [574–576 行](solution/anomaly_aware_controller.py#L574) 用 try/except 包住 `_evaluate`：某一轮出错只打印日志，循环不会停。

### 收统计回复（[586–615 行](solution/anomaly_aware_controller.py#L586)）

`_flow_stats_reply_handler`：
- **[590–593 行](solution/anomaly_aware_controller.py#L590)**：只看带源 IP 的规则。
- **[594–604 行](solution/anomaly_aware_controller.py#L594)**：按 cookie 分三类存：
  - 转发规则：按（源，目的）存包数和字节数；
  - ICMP 分类计数规则：按（源，目的，ICMP 类型）存；
  - 丢包规则：按源 IP 存丢了多少包，**用来判断攻击是否已经停止**。
- **[605–608 行](solution/anomaly_aware_controller.py#L605)**：规则很多时，交换机会分几个消息回复，`OFPMPF_REPLY_MORE` 标记表示"后面还有"。收齐最后一个才算一个完整样本，并打上时间戳。

`_port_stats_reply_handler`：记下每个端口的 `tx_bytes`（发送字节数）。

### `_evaluate`（[617–627 行](solution/anomaly_aware_controller.py#L617)）——每轮的固定顺序

```python
source_pps, flow_pps, drop_pps = self._measure_sources()  # 1. 每台主机发了多快
self._measure_links()                                     # 2. 每条链路有多忙
self._check_anomalies(source_pps, flow_pps, now)          # 3. 检测，异常就封
self._check_recovery(drop_pps, now)                       # 4. 被封的是否该解封
self._update_costs(now)                                   # 5. 算新代价
self._reroute_flows('cost update')                        # 6. 按新代价改路
self._log_state(now, source_pps, drop_pps)                # 7. 写日志
```

**这个顺序就是答辩时最重要的一张图**：发现攻击、封禁、代价上升、改路，全部发生在**同一轮**里。所以 run4 里检测、封禁和 h1→h6 改路都在攻击开始后 1.2 秒同时发生。

---

## 8. 算速率（[632–697 行](solution/anomaly_aware_controller.py#L632)）

### `_measure_sources`（[632–680 行](solution/anomaly_aware_controller.py#L632)）——每台主机发了多快

- **[636–638 行](solution/anomaly_aware_controller.py#L636)**：建一张表"每台交换机下面接了哪些主机"。
- **[640–646 行](solution/anomaly_aware_controller.py#L640)**：对每台交换机，拿这次的样本和上次的比，算出时间差 `dt`。
- **[649–650 行](solution/anomaly_aware_controller.py#L649)**：这台交换机下的每台主机先记为 0。这样没发包的主机也有样本，基线和预热计数照常更新。
- **[651–657 行](solution/anomaly_aware_controller.py#L651)**：`if src not in local_ips: continue`，**只统计源主机自己的接入交换机**。一条流经过 3 台交换机，只在第一台计一次。
  `delta = pkts - before if pkts >= before else pkts`：计数器变小了，说明规则被重装过、从 0 重新开始数，这时直接用新值。
- **[659–664 行](solution/anomaly_aware_controller.py#L659)**：被封主机的丢包规则计数，算出它现在还在以多快的速度发包。
- **[673–679 行](solution/anomaly_aware_controller.py#L673)**：**不计 Echo Reply**。
  ```python
  if icmp_type == ICMP_ECHO_REPLY:
      continue
  ```
  结合优先级理解：在源主机的接入交换机上，ICMP Request 和 Reply 分别被优先级 11 的两条规则先匹配走了，优先级 10 的转发规则只计其他流量。所以这里"Request 计数 + 其他流量计数"就是除了 Reply 以外的全部流量。

> **为什么不计 Echo Reply？**（答辩重点）
> 洪泛时，受害者会回复每一个 Echo Request，所以它的发包速度和攻击者一样高。如果把回复算进去，受害者也会被封。场景 b、c 的受害者是 h6，封了 h6 就等于切断了要保护的 h1→h6。
> 我们第一版就是这样误封了受害者。第二版试过"同一轮里用收到的 Request 抵扣发出的 Reply"，但各交换机的统计回复是分别、不同时到达的，请求和回复常常落在不同轮次里，还是会误封。
> 最终版直接在交换机上用两条规则把两种消息分开计数，彻底解决了这个问题。run4 里 h3 每秒回复 41,311 个包，算出来的速率仍然只有 1.0 pps（就是它的背景 ping）。

### `_measure_links`（[682–697 行](solution/anomaly_aware_controller.py#L682)）——每条链路有多忙

- **[691–693 行](solution/anomaly_aware_controller.py#L691)**：对每条链路 (u, v)，找 u 上连向 v 的那个端口。
- **[694 行](solution/anomaly_aware_controller.py#L694)**：`速率 = (这次 tx_bytes − 上次 tx_bytes) × 8 / dt`，单位 bit/s。
- **[695–697 行](solution/anomaly_aware_controller.py#L695)**：平滑，`新值 = 0.5 × 这次 + 0.5 × 上次`，避免代价随一次波动跳来跳去。

> 为什么用端口统计而不是流表统计？端口统计计的是真正经过这条线的所有包，包括回复和背景流量，代表真实负载。

---

## 9. 检测、封禁、解封（[702–760 行](solution/anomaly_aware_controller.py#L702)）——Task 2 的核心

### `_check_anomalies`（[702–720 行](solution/anomaly_aware_controller.py#L702)）

```python
for ip, pps in source_pps.items():
    if ip in self.blocked:
        continue                                   # 已经封了的不再检测，基线冻结
    stats = self.sources.setdefault(ip, {'baseline': None, 'samples': 0})
    if stats['baseline'] is None:
        stats['baseline'] = pps                    # 第一个样本直接作为基线
        stats['samples'] = 1
        continue
    threshold = max(3 * baseline, 1000)            # 门槛
    if stats['samples'] >= 3 and pps > threshold:  # 预热完、且超过门槛
        self._block_ip(...)                        # 封禁，基线不更新
    else:
        stats['baseline'] = 0.3 * pps + 0.7 * stats['baseline']   # EMA 更新
        stats['samples'] += 1
```

和参考代码相比的三处改动：

1. **先比较，后更新；异常样本不进基线。** 参考代码先把新样本算进基线再比较。持续的攻击会把基线越抬越高，最后看起来"不异常"了（基线污染）。
2. **门槛加了 1000 pps 的下限。** 背景 ping 让基线只有 1–2 pps，3 倍才 3–6 pps，一次 `pingall` 就会误报。1000 远高于正常 ping，又比实际攻击速度（约 6 万 pps）低几十倍。
3. **预热 3 个样本（6 秒）。** 刚学到的主机第一个样本可能不准，不能马上拿来判定。

### `_block_ip`（[722–742 行](solution/anomaly_aware_controller.py#L722)）

- **[724–729 行](solution/anomaly_aware_controller.py#L724)**：找出被攻击影响的链路。攻击者的流里，速率占它总速率 20% 以上的（也就是洪泛流），这些流所走路径上的每条链路都记下来。之后这些链路的 A 就是 1。攻击者的低速背景 ping 不会把别的链路也标进来。
- **[731–733 行](solution/anomaly_aware_controller.py#L731)**：打印 `[ANOMALY] IP rate=… baseline=… threshold=… links=…`。
- **[735–738 行](solution/anomaly_aware_controller.py#L735)**：在**所有**交换机上装丢包规则：匹配"IPv4 + 源 IP = 攻击者"，动作为空（空动作就是丢掉），优先级 5000。和参考代码一样。真正起作用的是攻击者接入的那台交换机：攻击包第一跳就被丢掉。
- **[740–742 行](solution/anomaly_aware_controller.py#L740)**：记进 `blocked`，打印 `[BLOCK]`。

> 丢包规则只匹配 IPv4，所以被封主机的 ARP 还能正常工作。解封后它马上能恢复通信。

### `_check_recovery`（[744–760 行](solution/anomaly_aware_controller.py#L744)）

- **[747–748 行](solution/anomaly_aware_controller.py#L747)**：用丢包规则的计数，看被封主机现在还在以多快的速度发包。
- **[749–751 行](solution/anomaly_aware_controller.py#L749)**：低于门槛，安静次数 +1；否则清零。
- **[752–753 行](solution/anomaly_aware_controller.py#L752)**：连续 3 次（6 秒）安静才解封，防止攻击者停一下又继续。
- **[754–760 行](solution/anomaly_aware_controller.py#L754)**：在所有交换机上删掉丢包规则，从 `blocked` 移除，打印 `[UNBLOCK] ... released after N s`。

> 为什么 run4 里攻击停止后 7.2 秒解封？攻击停止那一刻所在的那一轮统计里还有攻击包，不算安静；接下来 3 轮各 2 秒都安静，才解封。一轮的一部分 + 3 × 2 秒 ≈ 7 秒。

---

## 10. 动态代价（[765–789 行](solution/anomaly_aware_controller.py#L765)）——Task 3 的核心

```python
anomaly_links = 所有被封主机记录的链路的并集                       # 767–769
for 每条链路 (u, v):                                               # 776–779
    fwd = u→v 方向的速率;  rev = v→u 方向的速率                      # 781–782
    utilisation = min(1, max(fwd, rev) / 40e6)                     # 783
    anomaly = 1 if 链路在 anomaly_links 里 else 0                   # 784
    cost = C0 + 10 * utilisation + 20 * anomaly                    # 785
    self.graph[u][v] = self.graph[v][u] = cost                     # 786–787
```

逐项对应作业 Reference C 的公式 C = C0 + α·R/Rmax + β·A：
- **R/Rmax** = `utilisation`：两个方向里取更忙的那个，因为链路的拥堵程度由更忙的方向决定。用 `min(1, …)` 限制在 0 到 1 之间。
- **A** = `anomaly`：链路在被封攻击者的流经过的路径上就是 1，解封后变回 0。
- **α = 10**：满载时代价多 10，大约是一条默认链路代价的两倍。负载本身也能让流量换路，但只在很拥堵时才会。例如 s2–s6 利用率超过约 57% 时，h1→h6 才会只因为负载而换路。
- **β = 20**：比主路和备用路的代价差大（h1→h6 是 20 − 15 = 5），所以只要有备用路，被攻击的线一定会被避开。β 是有限的，所以如果被攻击的线是唯一的路，仍然会走它，**保证连通**。
- **[786–787 行](solution/anomaly_aware_controller.py#L786)**：直接改 `graph`，下一步 `_reroute_flows` 的 Dijkstra 就用新代价。
- **[771–774 行](solution/anomaly_aware_controller.py#L771)**：已经不在图里的链路（比如断了的）从记录里删掉。

> 为什么代价先冲到约 3.2 倍，再停在 3.0 倍？被检测到的那一轮，负载项和攻击项同时变大。同一轮里攻击者被封，洪泛在入口就被丢掉，这条线上的流量没了，负载项每轮减半，逐渐变成 0。但攻击项 β=20 一直保持到解封，所以停在 (10 + 20) / 10 = 3 倍。

---

## 11. 写日志（[791–817 行](solution/anomaly_aware_controller.py#L791)）

每轮写三个 CSV，画图和 `live_view.py` 用的就是它们：
- `link_costs.csv`：每条链路的速率、利用率、A、C0、代价、归一化代价（代价 / C0，[799 行](solution/anomaly_aware_controller.py#L799)）。
- `sources.csv`：每台主机的速率、基线、门槛、状态（normal / blocked）。
- `paths.csv`：每条流当前的路径和路径代价。

事件（ANOMALY、BLOCK 等）由 `_event`（[158 行](solution/anomaly_aware_controller.py#L158)）随时写进 `events.csv`，同时打印到终端。

---

## 12. 把函数串起来：场景 b 的完整过程（run4 的真实数字）

| 时间 | 发生了什么 | 哪段代码 |
|---|---|---|
| 开始前 | `pingall` 时 h1 发出第一个包，table-miss 送到控制器，算路 s1>s2>s6（代价 15），从 s6 往 s1 倒着装规则 | `_packet_in_handler` → `_handle_ipv4` → `_ensure_flow` → `dijkstra` → `_install_path` |
| 平时每 2 秒 | 统计每台主机速率，h2 约 2 pps，基线约 2；h1→h6 的 5 Mbit/s 让 s1–s2、s2–s6 代价略升（6.30、11.30） | `_monitor` → `_measure_sources` / `_measure_links` → `_check_anomalies` → `_update_costs` |
| 90.2 s | h2 开始洪泛 h6 | — |
| 91.4 s（同一轮） | ① h2 速率 4,124 pps > 门槛 1000，判定异常 | `_check_anomalies` |
| | ② 所有交换机装丢包规则，s2–s6 记为受攻击链路 | `_block_ip` |
| | ③ s2–s6 代价 = 10 + 10×0.20 + 20 = 32.0 | `_update_costs` |
| | ④ h1→h6 原路 6.30 + 32.0 = 38.30，最优路 s1>s5>s6 = 20.00，便宜超过 2，换路；倒着装：先 s6，再 s5，再改 s1，最后删 s2 上的规则 | `_reroute_flows` → `_install_path` |
| 攻击中 | h2 的包在 s2 被丢掉（每秒约 6 万）；s2–s6 负载项减到 0，代价停在 30；h1→h6 在 s1>s5>s6 上保持 5 Mbit/s，RTT 98 → 137 ms | `_measure_sources` 读丢包计数 |
| 120.2 s | 洪泛停止 | — |
| 127.4 s | 连续 3 轮丢包计数低于门槛，解封；s2–s6 的 A = 0，代价回到 10；原路代价 15.00 比当前 22.59 便宜，换回 s1>s2>s6 | `_check_recovery` → `_update_costs` → `_reroute_flows` |

---

## 13. 和参考代码的对比（老师很可能问"你们改了什么"）

| | 参考代码 | 我们的实现 | 为什么 |
|---|---|---|---|
| 链路代价 | 固定 | C0 + α·负载 + β·攻击，每 2 秒更新 | Task 3 的要求 |
| 改路 | 只在链路断开时 | 代价变化时，对每条流都检查是否有便宜 2 以上的路 | Task 4 的要求 |
| 测速位置 | 每台交换机分别算 | 只在源主机的接入交换机算 | 不重复计数 |
| Echo Reply | 计入 | 不计 | 避免误封受害者 |
| 基线更新 | 先更新后比较 | 先比较后更新，异常样本不进基线 | 防止基线被攻击抬高 |
| 门槛 | 3 × 基线 | max(3 × 基线, 1000 pps)，加预热 | 避免低速基线误报 |
| 解封 | 无 | 连续 3 轮安静自动解封 | Task 4 f 的恢复要求 |
| 广播 | MST 泛洪 | ARP 由控制器直接投递 | 避免广播风暴，不受链路变化影响 |
| 换路方式 | 清空流表重来 | 倒着装、能修改就修改、最后删旧规则 | 换路不丢包，计数器不被清零 |
| LLDP 链路删除 | 采信 | 忽略，只信端口状态 | 洪泛时 LLDP 会误报链路断开 |

---

## 14. 老师可能追问的代码问题

| 问题 | 回答 | 指哪里 |
|---|---|---|
| 怎么判断一个端口连的是主机？ | 不属于任何 LLDP 发现的交换机间链路的端口就是主机端口 | [287–291](solution/anomaly_aware_controller.py#L287) |
| 包第一次到达时怎么处理？ | table-miss 送上来，控制器算路装规则，再把这个包直接发给目的主机 | [541–551](solution/anomaly_aware_controller.py#L541) |
| 为什么要倒着装规则？ | 先把后面的路铺好，源端最后切换，包不会走到没规则的交换机 | [395](solution/anomaly_aware_controller.py#L395) |
| 为什么用 MODIFY 不用 ADD？ | ADD 相同规则会清零计数器，测速要靠计数器 | [403–404](solution/anomaly_aware_controller.py#L403) |
| 统计回复分好几个消息怎么办？ | 看 `OFPMPF_REPLY_MORE`，收齐才算一个样本 | [605–608](solution/anomaly_aware_controller.py#L605) |
| 计数器归零了怎么办？ | 新值比旧值小，就直接用新值当增量 | [656](solution/anomaly_aware_controller.py#L656) |
| 检测最慢要多久？ | 一轮 2 秒加等回复 0.5 秒，最坏约 2.5 秒；run4 是 1.2 秒 | [567–577](solution/anomaly_aware_controller.py#L567) |
| 怎么知道攻击停了？ | 被封以后，攻击包仍然会命中丢包规则，看它的计数器还涨不涨 | [659–664](solution/anomaly_aware_controller.py#L659)、[744–760](solution/anomaly_aware_controller.py#L744) |
| 封了以后还能检测吗？ | 被封的主机跳过检测，基线冻结在攻击前的值，解封后照常检测 | [704–705](solution/anomaly_aware_controller.py#L704) |
| 没有备用路会怎样？ | β 是有限的，被攻击的线仍然可以走，不会断网 | [785](solution/anomaly_aware_controller.py#L785) |
| 两个方向的负载怎么处理？ | 每个方向分别测，取较大的那个 | [781–783](solution/anomaly_aware_controller.py#L781) |
| 换 α、β 或 C0 要改哪里？ | 文件开头的参数，或用环境变量 `CA2_ALPHA`、`CA2_BETA`、`CA2_COST_MODE` | [42–69](solution/anomaly_aware_controller.py#L42) |
| 为什么丢包规则装在所有交换机上？ | 和参考代码一致；真正起作用的是攻击者的接入交换机，其他交换机只会拦下装规则那一刻正在路上的包 | [735–738](solution/anomaly_aware_controller.py#L735) |

## 15. 可能被指出的不足（主动承认，并说怎么改）

- **检测靠轮询**：攻击开始后的约 1 秒里攻击包还是会进网络，run4 唯一的丢包就发生在这段时间。改进：用 OpenFlow meter 在交换机上直接限速，或者缩短轮询间隔。
- **门槛下限是固定的 1000 pps**：低速攻击，或者很多台主机同时、每台都低于 1000 的分布式攻击，检测不到。
- **按 IP 封禁**：攻击者伪造源 IP 就能绕过；而且被封主机的正常流量也一起被封。改进：按接入端口封，或只封攻击用的协议。
- **只发 Echo Reply 的攻击检测不到**：但它的流量仍会通过负载项抬高链路代价。
- **C0 用的是参考控制器的表，不反映时延**：所以场景 b 换的路 RTT 多了 38 ms。代码里已经支持 `CA2_COST_MODE=delay` 改用时延。
- **攻击标记要等解封才清除**：比较保守，h1→h6 要在较长的路上多待一会儿；可以改成让攻击项随时间逐渐减小。
